from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


InsightRiskLevel = Literal["low", "medium", "high", "critical"]
DataFreshness = Literal["fresh", "stale", "missing"]


class HealthScoreInsightRequest(BaseModel):
    device_mac: str = Field(..., min_length=1)
    elder_id: str | None = None
    window_minutes: int = Field(default=5, ge=1, le=120)
    use_llm: bool = True

    @field_validator("device_mac")
    @classmethod
    def normalize_device_mac(cls, value: str) -> str:
        compact = "".join(ch for ch in value if ch.isalnum()).upper()
        if len(compact) == 12:
            return ":".join(compact[index : index + 2] for index in range(0, 12, 2))
        return value.strip().upper()


class HealthScoreInsightResponse(BaseModel):
    elder_name: str | None = None
    room_no: str | None = None
    device_mac: str
    generated_at: datetime
    data_freshness: DataFreshness
    risk_level: InsightRiskLevel
    summary: str
    score_explanation: str
    trend_analysis: str
    model_assessment: str
    suggested_actions: list[str] = Field(default_factory=list)
    watch_items: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"
    llm_used: bool = False
    fallback_used: bool = True


class RecentAlarmInsight(BaseModel):
    alarm_id: str
    alarm_type: str
    alarm_level: int
    message: str
    created_at: datetime
    acknowledged: bool = False
