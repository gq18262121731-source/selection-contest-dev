from __future__ import annotations

from pathlib import Path

import pytest

from backend.ml.inference import HealthInferenceEngine, ModelArtifactMissingError


def test_inference_returns_expected_fields(test_services: dict[str, object]) -> None:
    engine = test_services["inference"]
    result = engine.predict(
        {
            "heart_rate": 78,
            "spo2": 97,
            "sbp": 119,
            "dbp": 77,
            "body_temp": 36.6,
            "fall_detection": False,
            "data_accuracy": 99,
        }
    )
    assert "rule_health_score" in result
    assert "model_health_score" in result
    assert "final_health_score" in result
    assert "alerts" in result
    assert result["risk_level"] in {"normal", "attention", "warning", "critical"}


def test_inference_hard_threshold_overrides_score(test_services: dict[str, object]) -> None:
    engine = test_services["inference"]
    result = engine.predict(
        {
            "heart_rate": 142,
            "spo2": 96,
            "sbp": 121,
            "dbp": 79,
            "body_temp": 36.7,
            "fall_detection": False,
            "data_accuracy": 94,
        }
    )
    assert result["risk_level"] == "critical"
    assert "Heart rate above 140 bpm" in result["trigger_reasons"]
    assert "tachycardia" in result["abnormal_tags"]


def test_inference_missing_artifacts_raise_error(tmp_path: Path) -> None:
    settings = test_services = None
    settings = __import__("backend.config", fromlist=["get_settings"]).get_settings().model_copy(
        update={
            "static_model_path": str(tmp_path / "missing_model.pt"),
            "static_scaler_path": str(tmp_path / "missing_scaler.joblib"),
            "static_feature_columns_path": str(tmp_path / "missing_features.json"),
            "allow_rule_only_fallback": False,
        }
    )
    engine = HealthInferenceEngine(settings=settings)
    with pytest.raises(ModelArtifactMissingError):
        engine.predict(
            {
                "heart_rate": 80,
                "spo2": 98,
                "sbp": 120,
                "dbp": 80,
                "body_temp": 36.5,
                "fall_detection": 0,
                "data_accuracy": 100,
            }
        )
