from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import train_test_split
from torch.utils.data import Dataset


ALERT_TARGET_COLUMNS: list[str] = ["hr_alert", "spo2_alert", "bp_alert", "temp_alert"]


class StaticHealthDataset(Dataset[tuple[torch.Tensor, torch.Tensor, torch.Tensor]]):
    """Torch dataset for static multi-task health training."""

    def __init__(self, features: np.ndarray, labels: np.ndarray, risk_targets: np.ndarray) -> None:
        self.features = torch.tensor(features, dtype=torch.float32)
        self.labels = torch.tensor(labels, dtype=torch.float32)
        self.risk_targets = torch.tensor(risk_targets, dtype=torch.float32)

    def __len__(self) -> int:
        return int(self.features.shape[0])

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        return self.features[index], self.labels[index], self.risk_targets[index]


@dataclass(slots=True)
class TrainValidationSplit:
    train_features: pd.DataFrame
    val_features: pd.DataFrame
    train_labels: pd.DataFrame
    val_labels: pd.DataFrame
    train_risk_targets: pd.Series
    val_risk_targets: pd.Series


def split_train_validation(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    risk_targets: pd.Series,
    *,
    val_ratio: float,
    random_seed: int,
) -> TrainValidationSplit:
    """Split feature and label frames with stratification when feasible."""

    stratify = _build_stratify_signature(labels)
    if stratify.nunique() < 2 or stratify.value_counts().min() < 2:
        stratify = None

    train_x, val_x, train_y, val_y, train_risk, val_risk = train_test_split(
        features,
        labels,
        risk_targets,
        test_size=val_ratio,
        random_state=random_seed,
        stratify=stratify,
    )
    return TrainValidationSplit(
        train_features=train_x.reset_index(drop=True),
        val_features=val_x.reset_index(drop=True),
        train_labels=train_y.reset_index(drop=True),
        val_labels=val_y.reset_index(drop=True),
        train_risk_targets=train_risk.reset_index(drop=True),
        val_risk_targets=val_risk.reset_index(drop=True),
    )


def compute_positive_class_weights(labels: pd.DataFrame) -> dict[str, float]:
    """Compute BCE pos_weight values for each alert task."""

    weights: dict[str, float] = {}
    for column in ALERT_TARGET_COLUMNS:
        positives = float(labels[column].sum())
        negatives = float(len(labels) - positives)
        if positives <= 0:
            weights[column] = 1.0
        else:
            weights[column] = max(1.0, negatives / positives)
    return weights


def _build_stratify_signature(labels: pd.DataFrame) -> pd.Series:
    return labels.loc[:, ALERT_TARGET_COLUMNS].astype(int).astype(str).agg("_".join, axis=1)
