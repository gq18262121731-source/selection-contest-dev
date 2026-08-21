from __future__ import annotations

from backend.ml.preprocess import DataValidationError, validate_inference_record
from backend.ml.rule_engine import HealthRuleEngine


def test_rule_engine_normal_case() -> None:
    engine = HealthRuleEngine()
    result = engine.assess(
        {
            "heart_rate": 76,
            "spo2": 97,
            "sbp": 118,
            "dbp": 76,
            "body_temp": 36.7,
            "fall_detection": 0,
            "data_accuracy": 98,
        }
    )
    assert result.rule_health_score >= 95
    assert result.hard_threshold.level is None
    assert result.abnormal_tags == []
    assert engine.determine_risk_level(result.rule_health_score) == "normal"


def test_rule_engine_low_spo2_warning() -> None:
    engine = HealthRuleEngine()
    result = engine.assess(
        {
            "heart_rate": 88,
            "spo2": 89,
            "sbp": 126,
            "dbp": 82,
            "body_temp": 36.8,
            "fall_detection": 0,
            "data_accuracy": 95,
        }
    )
    assert result.hard_threshold.level == "warning"
    assert "low_spo2" in result.abnormal_tags
    assert "SpO2 below 90%" in result.hard_threshold.trigger_reasons


def test_rule_engine_fall_with_hypoxia_is_critical() -> None:
    engine = HealthRuleEngine()
    result = engine.assess(
        {
            "heart_rate": 136,
            "spo2": 87,
            "sbp": 145,
            "dbp": 92,
            "body_temp": 37.8,
            "fall_detection": 1,
            "data_accuracy": 88,
        }
    )
    assert result.hard_threshold.level == "critical"
    assert "fall_detected" in result.abnormal_tags
    assert any("Fall" in reason or "SpO2 below 88%" == reason for reason in result.hard_threshold.trigger_reasons)


def test_validate_inference_record_out_of_range() -> None:
    try:
        validate_inference_record(
            {
                "heart_rate": 260,
                "spo2": 99,
                "sbp": 120,
                "dbp": 80,
                "body_temp": 36.5,
                "fall_detection": 0,
                "data_accuracy": 100,
            }
        )
    except DataValidationError as exc:
        assert "heart_rate" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected DataValidationError for out-of-range input")
