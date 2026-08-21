from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import DataLoader

from backend.config import Settings, get_settings
from backend.logger import get_logger
from backend.ml.dataset import (
    ALERT_TARGET_COLUMNS,
    StaticHealthDataset,
    compute_positive_class_weights,
    split_train_validation,
)
from backend.ml.feature_engineering import FEATURE_COLUMNS, build_feature_frame
from backend.ml.preprocess import clean_health_dataframe, load_health_excel
from backend.ml.rule_engine import HealthRuleEngine
from backend.models.static_health_model import StaticHealthMultiTaskModel


LOGGER = get_logger(__name__)


class TrainingError(RuntimeError):
    """Raised when static model training fails."""


@dataclass(slots=True)
class TrainingSummary:
    train_size: int
    val_size: int
    best_val_loss: float
    epochs: int
    feature_count: int
    class_weights: dict[str, float]
    label_distribution: dict[str, dict[str, int]]


class StaticHealthTrainer:
    """Train and persist the static multi-task health model."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.rule_engine = HealthRuleEngine()
        self.device = self._resolve_device()

    def train_from_excel(self, path: str | Path | None = None, sheet_name: str | int | None = None) -> TrainingSummary:
        source = Path(path or self.settings.static_health_data_path)
        frame = load_health_excel(source, sheet_name=sheet_name or self.settings.static_health_sheet_name)
        cleaned, stats = clean_health_dataframe(frame)
        if len(cleaned) < 8:
            raise TrainingError("Not enough valid samples after preprocessing; require at least 8 rows.")

        feature_frame = build_feature_frame(cleaned)
        rule_scores = cleaned.apply(
            lambda row: self.rule_engine.assess(row.to_dict()).rule_health_score,
            axis=1,
        ).astype(float)
        risk_targets = 1.0 - (rule_scores / 100.0)
        labels = cleaned.loc[:, ALERT_TARGET_COLUMNS].astype(float)

        split = split_train_validation(
            feature_frame,
            labels,
            risk_targets,
            val_ratio=self.settings.train_val_ratio,
            random_seed=self.settings.train_random_seed,
        )

        scaler = StandardScaler()
        train_x = scaler.fit_transform(split.train_features)
        val_x = scaler.transform(split.val_features)
        train_y = split.train_labels.to_numpy(dtype=np.float32)
        val_y = split.val_labels.to_numpy(dtype=np.float32)
        train_risk = split.train_risk_targets.to_numpy(dtype=np.float32).reshape(-1, 1)
        val_risk = split.val_risk_targets.to_numpy(dtype=np.float32).reshape(-1, 1)

        train_dataset = StaticHealthDataset(train_x, train_y, train_risk)
        val_dataset = StaticHealthDataset(val_x, val_y, val_risk)
        train_loader = DataLoader(train_dataset, batch_size=self.settings.train_batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=self.settings.train_batch_size, shuffle=False)

        model = StaticHealthMultiTaskModel(input_dim=train_x.shape[1]).to(self.device)
        optimizer = torch.optim.Adam(model.parameters(), lr=self.settings.train_learning_rate)
        mse_loss = nn.MSELoss()
        class_weights = compute_positive_class_weights(split.train_labels)
        bce_losses = {
            column: nn.BCEWithLogitsLoss(
                pos_weight=torch.tensor([class_weights[column]], dtype=torch.float32, device=self.device)
            )
            for column in ALERT_TARGET_COLUMNS
        }

        LOGGER.info(
            "Static model training started on device=%s cuda_available=%s",
            self.device,
            torch.cuda.is_available(),
        )

        best_val_loss = float("inf")
        best_state: dict[str, torch.Tensor] | None = None

        for epoch in range(1, self.settings.train_epochs + 1):
            model.train()
            train_loss_total = 0.0
            for batch_x, batch_y, batch_risk in train_loader:
                batch_x = batch_x.to(self.device)
                batch_y = batch_y.to(self.device)
                batch_risk = batch_risk.to(self.device)
                optimizer.zero_grad()
                outputs = model(batch_x)
                classification_loss = sum(
                    bce_losses[column](outputs[column], batch_y[:, index : index + 1])
                    for index, column in enumerate(ALERT_TARGET_COLUMNS)
                )
                regression_loss = mse_loss(torch.sigmoid(outputs["risk_score"]), batch_risk)
                loss = (0.7 * classification_loss) + (0.3 * regression_loss)
                loss.backward()
                optimizer.step()
                train_loss_total += float(loss.item()) * len(batch_x)

            val_loss = self._evaluate(model, val_loader, bce_losses, mse_loss)
            avg_train_loss = train_loss_total / max(len(train_dataset), 1)
            LOGGER.info(
                "Static model epoch %s/%s train_loss=%.4f val_loss=%.4f",
                epoch,
                self.settings.train_epochs,
                avg_train_loss,
                val_loss,
            )
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}

        if best_state is None:
            raise TrainingError("Model training did not produce a checkpoint.")

        model.load_state_dict(best_state)
        self._save_artifacts(
            model=model,
            scaler=scaler,
            cleaned=cleaned,
            stats=stats.label_distribution,
            class_weights=class_weights,
            best_val_loss=best_val_loss,
            data_path=source,
        )
        return TrainingSummary(
            train_size=len(split.train_features),
            val_size=len(split.val_features),
            best_val_loss=best_val_loss,
            epochs=self.settings.train_epochs,
            feature_count=len(FEATURE_COLUMNS),
            class_weights=class_weights,
            label_distribution=stats.label_distribution,
        )

    def _evaluate(
        self,
        model: StaticHealthMultiTaskModel,
        loader: DataLoader,
        bce_losses: dict[str, nn.BCEWithLogitsLoss],
        mse_loss: nn.MSELoss,
    ) -> float:
        model.eval()
        total = 0.0
        count = 0
        with torch.no_grad():
            for batch_x, batch_y, batch_risk in loader:
                batch_x = batch_x.to(self.device)
                batch_y = batch_y.to(self.device)
                batch_risk = batch_risk.to(self.device)
                outputs = model(batch_x)
                classification_loss = sum(
                    bce_losses[column](outputs[column], batch_y[:, index : index + 1])
                    for index, column in enumerate(ALERT_TARGET_COLUMNS)
                )
                regression_loss = mse_loss(torch.sigmoid(outputs["risk_score"]), batch_risk)
                loss = (0.7 * classification_loss) + (0.3 * regression_loss)
                total += float(loss.item()) * len(batch_x)
                count += len(batch_x)
        return total / max(count, 1)

    def _save_artifacts(
        self,
        *,
        model: StaticHealthMultiTaskModel,
        scaler: StandardScaler,
        cleaned: pd.DataFrame,
        stats: dict[str, dict[str, int]],
        class_weights: dict[str, float],
        best_val_loss: float,
        data_path: Path,
    ) -> None:
        artifact_dir = Path(self.settings.static_model_dir)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        processed_dir = Path(self.settings.processed_data_dir)
        processed_dir.mkdir(parents=True, exist_ok=True)

        model.save(self.settings.static_model_path)
        joblib.dump(scaler, self.settings.static_scaler_path)
        Path(self.settings.static_feature_columns_path).write_text(
            json.dumps(FEATURE_COLUMNS, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        Path(self.settings.static_label_mapping_path).write_text(
            json.dumps(
                {
                    "hr_alert": {"0": "Normal", "1": "High"},
                    "spo2_alert": {"0": "Normal", "1": "Low"},
                    "bp_alert": {"0": "Normal", "1": "High"},
                    "temp_alert": {"0": "Normal", "1": "Abnormal"},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        Path(self.settings.static_training_config_path).write_text(
            json.dumps(
                {
                    "data_path": str(data_path),
                    "sheet_name": self.settings.static_health_sheet_name,
                    "batch_size": self.settings.train_batch_size,
                    "epochs": self.settings.train_epochs,
                    "learning_rate": self.settings.train_learning_rate,
                    "val_ratio": self.settings.train_val_ratio,
                    "random_seed": self.settings.train_random_seed,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        Path(self.settings.static_metrics_path).write_text(
            json.dumps(
                {
                    "best_val_loss": best_val_loss,
                    "class_weights": class_weights,
                    "label_distribution": stats,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        cleaned.to_csv(Path(processed_dir) / "static_health_training_cleaned.csv", index=False, encoding="utf-8")

    def _resolve_device(self) -> torch.device:
        requested = self.settings.model_device
        if requested == "auto":
            if torch.cuda.is_available():
                return torch.device("cuda")
            return torch.device("cpu")
        if requested == "cuda":
            if not torch.cuda.is_available():
                raise TrainingError("CUDA was requested but is not available in the current runtime")
            return torch.device("cuda")
        return torch.device("cpu")
