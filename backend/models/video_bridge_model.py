from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.models.alarm_model import AlarmRecord


ServiceState = Literal["mock", "starting", "running", "degraded", "stopped", "error", "unknown"]
VideoStreamType = Literal["ws_image", "mjpeg", "hls", "webrtc", "flv", "snapshot", "unknown"]
FallState = Literal["unknown", "normal", "suspected_fall", "confirmed_fall", "fallen", "recovery", "error"]
RiskLevel = Literal["unknown", "low", "medium", "high", "critical"]


class VideoAnalysisTarget(BaseModel):
    target_id: str | None = None
    label: str | None = None
    matched: bool | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VideoAnalysisPushRequest(BaseModel):
    """Payload accepted from a future standalone video analysis service.

    The model intentionally stays independent from the legacy camera/pose/fall
    runtime. Extra keys are preserved in `metadata` so the future service can
    evolve without forcing a main-system release for every telemetry addition.
    """

    model_config = ConfigDict(extra="allow")

    camera_id: str = Field(..., min_length=1, max_length=80)
    stream_name: str = Field(default="primary", max_length=80)
    service_state: ServiceState = "running"
    camera_lost: bool = False
    capture_stale: bool = False
    frame_age_ms: int | None = Field(default=None, ge=0)
    video_fps: float | None = Field(default=None, ge=0.0)
    overlay_fps: float | None = Field(default=None, ge=0.0)
    ws_fps: float | None = Field(default=None, ge=0.0)
    stream_type: VideoStreamType = "ws_image"
    stream_url: str | None = Field(default=None, max_length=1024)
    track_id: str | None = Field(default=None, max_length=120)
    bbox: list[float] | None = None
    target: VideoAnalysisTarget | dict[str, Any] | str | None = None
    fall_state: FallState = "unknown"
    risk: RiskLevel = "unknown"
    fall_prob: float | None = Field(default=None, ge=0.0, le=1.0)
    snapshot_url: str | None = Field(default=None, max_length=1024)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return None
        if len(value) != 4:
            raise ValueError("bbox must contain [x1, y1, x2, y2]")
        return [float(item) for item in value]

    @field_validator("stream_name")
    @classmethod
    def normalize_stream_name(cls, value: str) -> str:
        stripped = value.strip()
        return stripped or "primary"


class VideoAnalysisRecord(VideoAnalysisPushRequest):
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    stale: bool = False
    adapter_version: str = "video_adapter.v1"


class VideoAnalysisIngestResponse(BaseModel):
    ok: bool = True
    accepted: bool = True
    camera_id: str
    stream_name: str
    received_at: datetime
    service_state: ServiceState
    stale: bool


class VideoBridgeStatusResponse(BaseModel):
    ok: bool = True
    bridge_state: ServiceState
    adapter_version: str
    camera_count: int
    updated_at: datetime
    latest: VideoAnalysisRecord | None = None
    cameras: list[VideoAnalysisRecord] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    vision_service: dict[str, Any] = Field(default_factory=dict)


class VideoBridgeRuntimeConfigResponse(BaseModel):
    base_url: str
    camera_id: str
    poll_enabled: bool
    poll_hz: float
    timeout_seconds: float
    push_token_set: bool = False
    target_device_mac: str
    target_elder_id: str = ""
    target_family_ids: list[str] = Field(default_factory=list)


class VideoBridgeRuntimeConfigUpdateRequest(BaseModel):
    base_url: str | None = Field(default=None, max_length=1024)
    camera_id: str | None = Field(default=None, max_length=80)
    poll_enabled: bool | None = None
    poll_hz: float | None = Field(default=None, ge=0.2, le=5.0)
    timeout_seconds: float | None = Field(default=None, ge=0.5, le=30.0)
    push_token: str | None = Field(default=None, max_length=255)
    target_device_mac: str | None = Field(default=None, max_length=120)
    target_elder_id: str | None = Field(default=None, max_length=120)
    target_family_ids: list[str] | str | None = None


class VisionStreamProbeRequest(BaseModel):
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(default=10554, ge=1, le=65535)
    timeout_ms: int = Field(default=1500, ge=100, le=30000)


class VisionStreamSwitchHostRequest(BaseModel):
    camera_id: str = Field(default="camera_01", min_length=1, max_length=80)
    host: str = Field(..., min_length=1, max_length=255)
    username: str = Field(default="admin", max_length=120)
    password: str = Field(default="", max_length=255)
    port: int = Field(default=10554, ge=1, le=65535)
    main_path: str = Field(default="/tcp/av0_0", max_length=255)
    analysis_path: str = Field(default="/tcp/av0_1", max_length=255)


class VideoBridgeFallAlarmSimulationRequest(BaseModel):
    camera_id: str | None = Field(default=None, max_length=80)
    stream_name: str | None = Field(default=None, max_length=80)
    fall_prob: float | None = Field(default=None, ge=0.0, le=1.0)
    snapshot_url: str | None = Field(default=None, max_length=1024)
    track_id: str | None = Field(default=None, max_length=120)


class VideoBridgeFallAlarmSimulationResponse(BaseModel):
    ok: bool = True
    accepted: bool = True
    alarm: AlarmRecord
    camera_id: str
    stream_name: str
    risk: RiskLevel = "high"
    fall_prob: float
    snapshot_url: str
    triggered_at: datetime
    elder_id: str = ""
    elder_name: str = ""


class VideoBridgeFallEventRequest(BaseModel):
    """Structured fall event pushed by the standalone video demo/service."""

    model_config = ConfigDict(extra="allow")

    camera_id: str = Field(..., min_length=1, max_length=80)
    stream_name: str = Field(default="primary", max_length=80)
    source: str = Field(default="vision_service", max_length=120)
    event_type: str = Field(default="fall_confirmed", max_length=80)
    state: str = Field(default="confirmed_fall", max_length=80)
    status: str | None = Field(default=None, max_length=120)
    service_state: ServiceState = "running"
    severity: str | None = Field(default=None, max_length=20)
    risk: RiskLevel = "high"
    risk_level: RiskLevel | None = None
    fall_detected: bool = True
    fall_prob: float | None = Field(default=None, ge=0.0, le=1.0)
    fall_score: float | None = Field(default=None, ge=0.0, le=1.0)
    track_id: str | None = Field(default=None, max_length=120)
    incident_id: str | None = Field(default=None, max_length=160)
    bbox: list[float] | None = None
    target: VideoAnalysisTarget | dict[str, Any] | str | None = None
    snapshot_url: str | None = Field(default=None, max_length=1024)
    snapshot_path: str | None = Field(default=None, max_length=1024)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    demo: bool = False
    scores: dict[str, Any] = Field(default_factory=dict)
    injury: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return None
        if len(value) != 4:
            raise ValueError("bbox must contain [x1, y1, x2, y2]")
        return [float(item) for item in value]

    @field_validator("stream_name")
    @classmethod
    def normalize_stream_name(cls, value: str) -> str:
        stripped = value.strip()
        return stripped or "primary"


class VideoBridgeFallEventResponse(BaseModel):
    ok: bool = True
    accepted: bool = True
    pushed: bool = True
    alarm_id: str
    alarm_type: str
    alarm: AlarmRecord
    camera_id: str
    stream_name: str
    risk: RiskLevel = "high"
    fall_prob: float
    triggered_at: datetime
    elder_id: str = ""
    elder_name: str = ""
