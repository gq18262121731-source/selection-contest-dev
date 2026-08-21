from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import joblib
import torch

from backend.config import Settings, get_settings
from backend.logger import get_logger
from backend.ml.feature_engineering import build_single_feature_frame
from backend.ml.preprocess import DataValidationError, validate_inference_record
from backend.ml.rule_engine import HealthRuleEngine
from backend.ml.scoring import fuse_health_scores, risk_raw_to_health_score
from backend.models.static_health_model import StaticHealthMultiTaskModel


LOGGER = get_logger(__name__)


class ModelArtifactMissingError(FileNotFoundError):
    """Raised when inference artifacts are unavailable."""


class InferenceError(RuntimeError):
    """Raised when inference fails unexpectedly."""


@dataclass(slots=True)
class LoadedArtifacts:
    model: StaticHealthMultiTaskModel
    scaler: Any
    feature_columns: list[str]


class HealthInferenceEngine:
    """Unified entrypoint for static health score inference."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.rule_engine = HealthRuleEngine()
        self._artifacts: LoadedArtifacts | None = None
        self.device = self._resolve_device()

    def predict(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            normalized = validate_inference_record(payload)
            rule_assessment = self.rule_engine.assess(normalized)
            artifacts = self._load_artifacts()

            feature_frame = build_single_feature_frame(normalized).loc[:, artifacts.feature_columns]
            scaled = artifacts.scaler.transform(feature_frame)
            tensor = torch.tensor(scaled, dtype=torch.float32, device=self.device)
            with torch.no_grad():
                outputs = artifacts.model(tensor)
                risk_score_raw = float(torch.sigmoid(outputs["risk_score"]).item())
                hr_prob = float(torch.sigmoid(outputs["hr_alert"]).item())
                spo2_prob = float(torch.sigmoid(outputs["spo2_alert"]).item())
                bp_prob = float(torch.sigmoid(outputs["bp_alert"]).item())
                temp_prob = float(torch.sigmoid(outputs["temp_alert"]).item())

            model_health_score = risk_raw_to_health_score(risk_score_raw)
            final_health_score = fuse_health_scores(
                rule_assessment.rule_health_score,
                model_health_score,
                rule_weight=self.settings.model_fusion_rule_weight,
                model_weight=self.settings.model_fusion_model_weight,
            )
            score_based_level = self.rule_engine.determine_risk_level(final_health_score)
            risk_level = self.rule_engine.upgrade_risk_level(score_based_level, rule_assessment.hard_threshold.level)
            recommendation_code = self.rule_engine.recommendation_code(
                risk_level,
                hard_threshold_level=rule_assessment.hard_threshold.level,
                abnormal_tags=rule_assessment.abnormal_tags,
            )
            sub_scores = {
                **rule_assessment.sub_scores,
                "rule_health_score": round(rule_assessment.rule_health_score, 4),
                "model_health_score": round(model_health_score, 4),
                "final_health_score": round(final_health_score, 4),
            }
            return {
                "rule_health_score": round(rule_assessment.rule_health_score, 4),
                "model_health_score": round(model_health_score, 4),
                "final_health_score": round(final_health_score, 4),
                "health_score": round(final_health_score, 4),
                "risk_level": risk_level,
                "risk_score_raw": round(risk_score_raw, 6),
                "sub_scores": sub_scores,
                "alerts": {
                    "hr_alert": {"label": "High" if hr_prob >= self.settings.alert_probability_threshold else "Normal", "probability": round(hr_prob, 6)},
                    "spo2_alert": {"label": "Low" if spo2_prob >= self.settings.alert_probability_threshold else "Normal", "probability": round(spo2_prob, 6)},
                    "bp_alert": {"label": "High" if bp_prob >= self.settings.alert_probability_threshold else "Normal", "probability": round(bp_prob, 6)},
                    "temp_alert": {"label": "Abnormal" if temp_prob >= self.settings.alert_probability_threshold else "Normal", "probability": round(temp_prob, 6)},
                    "hard_threshold_level": rule_assessment.hard_threshold.level,
                },
                "abnormal_tags": rule_assessment.abnormal_tags,
                "trigger_reasons": rule_assessment.hard_threshold.trigger_reasons,
                "recommendation_code": recommendation_code,
            }
        except DataValidationError:
            raise
        except ModelArtifactMissingError:
            raise
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Static health inference failed")
            raise InferenceError(str(exc)) from exc

    def _load_artifacts(self) -> LoadedArtifacts:
        if self._artifacts is not None:
            return self._artifacts

        required = [
            Path(self.settings.static_model_path),
            Path(self.settings.static_scaler_path),
            Path(self.settings.static_feature_columns_path),
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            if self.settings.allow_rule_only_fallback:
                raise InferenceError("Rule-only fallback is configured but not implemented for this runtime")
            raise ModelArtifactMissingError(f"Missing model artifacts: {missing}")

        model = StaticHealthMultiTaskModel.load(self.settings.static_model_path, map_location=self.device)
        LOGGER.info(
            "Loaded static health model on device=%s cuda_available=%s",
            self.device,
            torch.cuda.is_available(),
        )
        scaler = joblib.load(self.settings.static_scaler_path)
        feature_columns = json.loads(Path(self.settings.static_feature_columns_path).read_text(encoding="utf-8"))
        self._artifacts = LoadedArtifacts(model=model, scaler=scaler, feature_columns=list(feature_columns))
        return self._artifacts

    def _resolve_device(self) -> torch.device:
        requested = self.settings.model_device
        if requested == "auto":
            if torch.cuda.is_available():
                device = torch.device("cuda")
            else:
                device = torch.device("cpu")
        elif requested == "cuda":
            if not torch.cuda.is_available():
                raise InferenceError("CUDA was requested but is not available in the current runtime")
            device = torch.device("cuda")
        else:
            device = torch.device("cpu")

        if device.type == "cuda":
            LOGGER.info("Health inference will use CUDA device: %s", torch.cuda.get_device_name(0))
        else:
            LOGGER.info("Health inference will use CPU device")
        return device
