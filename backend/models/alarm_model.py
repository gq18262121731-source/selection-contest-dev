from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class AlarmType(str, Enum):
    SOS = "sos"
    VITAL_CRITICAL = "vital_critical"
    ZSCORE_WARNING = "zscore_warning"
    INTELLIGENT_ANOMALY = "intelligent_anomaly"
    COMMUNITY_RISK = "community_risk"
    DEVICE_STATUS = "device_status"
    FALL_DETECTED = "fall_detected"
    FALL_INJURY_RISK = "fall_injury_risk"
    VIDEO_FALL = "video_fall"


class AlarmPriority(int, Enum):
    SOS = 1
    CRITICAL = 2
    WARNING = 3
    NOTICE = 4


class AlarmLayer(str, Enum):
    REALTIME = "realtime"
    INTELLIGENT = "intelligent"
    COMMUNITY = "community"


class AlarmRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    device_mac: str
    alarm_type: AlarmType
    alarm_level: AlarmPriority
    alarm_layer: AlarmLayer = AlarmLayer.REALTIME
    message: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged: bool = False
    anomaly_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    queue_key: str = "alarm:priority"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("device_mac")
    @classmethod
    def normalize_mac(cls, value: str) -> str:
        return value.upper()


class AlarmQueueItem(BaseModel):
    score: float
    alarm: AlarmRecord


class MobilePushRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    alarm_id: str
    device_mac: str
    title: str
    body: str
    priority: AlarmPriority
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    delivered: bool = True
