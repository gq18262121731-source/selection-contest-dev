from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class VitalSignsPayload(BaseModel):
    """Normalized single-point vital signs payload."""

    heart_rate: float = Field(..., description="Heart rate in bpm")
    spo2: float = Field(..., description="Blood oxygen percentage")
    sbp: float = Field(..., description="Systolic blood pressure in mmHg")
    dbp: float = Field(..., description="Diastolic blood pressure in mmHg")
    body_temp: float = Field(..., description="Body temperature in Celsius")
    fall_detection: bool = Field(default=False)
    data_accuracy: float = Field(default=100.0)

    @field_validator("fall_detection", mode="before")
    @classmethod
    def normalize_fall_detection(cls, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            return normalized in {"1", "true", "yes", "y", "fall", "detected"}
        return False

    @field_validator("data_accuracy", mode="before")
    @classmethod
    def normalize_data_accuracy(cls, value: Any) -> float:
        if value in (None, ""):
            return 100.0
        return float(value)


class HealthScoreRequest(VitalSignsPayload):
    """Realtime score request payload."""

    elderly_id: str = Field(..., min_length=1)
    device_id: str = Field(..., min_length=1)
    timestamp: datetime


class AlertPrediction(BaseModel):
    """Single task alert inference."""

    label: str
    probability: float | None = None


class AlertSummary(BaseModel):
    """Alert summary payload."""

    hr_alert: AlertPrediction
    spo2_alert: AlertPrediction
    bp_alert: AlertPrediction
    temp_alert: AlertPrediction
    hard_threshold_level: str | None = None


class AggregatedEvent(BaseModel):
    """Debounced and aggregated abnormal event."""

    event_type: str
    severity: str
    status: str
    start_time: datetime
    last_seen_time: datetime
    peak_value: float | bool | dict[str, float] | None = None
    latest_value: float | bool | dict[str, float] | None = None
    sample_count: int = 0
    sustained_seconds: float = 0.0
    trigger_reason: str = ""


class HealthScoreResponse(BaseModel):
    """Unified scoring response payload."""

    elderly_id: str
    device_id: str
    timestamp: datetime
    health_score: float
    final_health_score: float
    rule_health_score: float
    model_health_score: float
    risk_level: str
    risk_score_raw: float
    sub_scores: dict[str, float] = Field(default_factory=dict)
    alerts: AlertSummary
    abnormal_tags: list[str] = Field(default_factory=list)
    trigger_reasons: list[str] = Field(default_factory=list)
    recommendation_code: str
    stability_mode: str = "robust_demo"
    stabilized_vitals: VitalSignsPayload
    active_events: list[AggregatedEvent] = Field(default_factory=list)
    score_adjustment_reason: str | None = None


class HealthScoreApiResponse(BaseModel):
    """Standard envelope for score API."""

    code: str = "OK"
    message: str = "success"
    data: HealthScoreResponse
