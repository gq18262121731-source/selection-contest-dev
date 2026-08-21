from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from backend.schemas.health import AggregatedEvent, AlertSummary, VitalSignsPayload


class WarningWindowPoint(VitalSignsPayload):
    """Single point in a warning window."""

    timestamp: datetime | None = None


class WarningCheckRequest(BaseModel):
    """Warning check request."""

    current_data: VitalSignsPayload | None = None
    window_data: list[WarningWindowPoint] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_payload(self) -> "WarningCheckRequest":
        if self.current_data is None and not self.window_data:
            raise ValueError("Either current_data or window_data must be provided")
        return self


class WarningCheckResponse(BaseModel):
    """Warning response payload."""

    evaluated_at: datetime
    window_mode: str
    health_score: float
    risk_level: str
    alerts: AlertSummary
    abnormal_tags: list[str] = Field(default_factory=list)
    trigger_reasons: list[str] = Field(default_factory=list)
    recommendation_code: str
    stability_mode: str = "robust_demo"
    stabilized_vitals: VitalSignsPayload
    active_events: list[AggregatedEvent] = Field(default_factory=list)
    score_adjustment_reason: str | None = None


class WarningCheckApiResponse(BaseModel):
    """Standard envelope for warning API."""

    code: str = "OK"
    message: str = "success"
    data: WarningCheckResponse
