from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.models.robot_navigation_model import RobotControlOwner, RobotNavigationExecutionState


class RobotTaskStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"


class RobotTaskStep(str, Enum):
    RECEIVED = "RECEIVED"
    PREFLIGHT = "PREFLIGHT"
    MOVING = "MOVING"
    ARRIVED = "ARRIVED"
    CAMERA_CHECK = "CAMERA_CHECK"
    VOICE_PROMPT = "VOICE_PROMPT"
    WAITING_RESPONSE = "WAITING_RESPONSE"
    REPORTING = "REPORTING"


class RobotTaskOutcome(str, Enum):
    SAFE = "SAFE"
    NEED_HELP = "NEED_HELP"
    NO_RESPONSE = "NO_RESPONSE"
    UNKNOWN = "UNKNOWN"


class RobotFallEventRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    event: Literal["fall_detected"] = "fall_detected"
    elder_id: str = Field(default="", alias="elderId")
    location: str = "unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_event_id: str | None = Field(default=None, alias="sourceEventId")
    external_task_id: str | None = Field(default=None, alias="externalTaskId")
    trace_id: str | None = Field(default=None, alias="traceId")
    camera_id: str | None = Field(default=None, alias="cameraId")
    metadata: dict[str, Any] = Field(default_factory=dict)


class RobotTargetMoveRequest(BaseModel):
    location: str
    task: Literal["move_to_target"] = "move_to_target"
    priority: Literal["normal", "high"] = "normal"


class RobotGatewayRelayResponse(BaseModel):
    ok: bool
    status: str
    base_url: str
    endpoint: str
    status_code: int | None = None
    data: Any = None
    error: str | None = None


class RobotTask(BaseModel):
    task_id: str
    gateway_task_id: str | None = None
    source_event_id: str
    trace_id: str
    alarm_event_id: str | None = None
    elder_id: str = ""
    elder_name: str = ""
    robot_id: str | None = None
    task_type: str = "confirm_fall"
    location: str = "unknown"
    risk_level: str = "unknown"
    status: RobotTaskStatus = RobotTaskStatus.QUEUED
    current_step: RobotTaskStep = RobotTaskStep.RECEIVED
    outcome: RobotTaskOutcome | None = None
    last_sequence: int = 0
    error_code: str | None = None
    error_message: str | None = None
    execution_state: RobotNavigationExecutionState | None = None
    control_owner: RobotControlOwner = RobotControlOwner.NONE
    provider: Literal["mock"] | None = None
    real_motion_enabled: Literal[False] = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RobotTaskTimeline(BaseModel):
    id: int | None = None
    task_id: str
    callback_id: str | None = None
    sequence: int = 0
    status: RobotTaskStatus
    step: RobotTaskStep
    message: str = ""
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RobotObservation(BaseModel):
    id: int | None = None
    task_id: str
    snapshot_url: str | None = None
    camera_available: bool | None = None
    voice_available: bool | None = None
    response_type: RobotTaskOutcome | None = None
    transcript: str | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RobotCallbackBase(BaseModel):
    model_config = ConfigDict(extra="allow")

    callback_id: str = Field(..., min_length=1, max_length=160)
    sequence: int = Field(default=0, ge=0)
    task_id: str | None = Field(default=None, max_length=160)
    external_task_id: str | None = Field(default=None, max_length=160)
    source_event_id: str | None = Field(default=None, max_length=200)
    trace_id: str | None = Field(default=None, max_length=160)
    status: RobotTaskStatus
    step: RobotTaskStep
    message: str = ""
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("occurred_at")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class RobotTaskStatusCallbackRequest(RobotCallbackBase):
    pass


class RobotTaskResultCallbackRequest(RobotCallbackBase):
    outcome: RobotTaskOutcome | None = None
    observation: dict[str, Any] | None = None
    robot: dict[str, Any] | None = None


class RobotCallbackAck(BaseModel):
    ok: bool = True
    accepted: bool = True
    duplicate: bool = False
    stale: bool = False
    task_id: str | None = None
    status: RobotTaskStatus | None = None
    step: RobotTaskStep | None = None
    message: str = "accepted"


class RobotTaskListResponse(BaseModel):
    tasks: list[RobotTask]


class RobotTaskDetailResponse(BaseModel):
    task: RobotTask
    gateway: dict[str, Any] | None = None


class RobotTaskObservationResponse(BaseModel):
    observation: RobotObservation | None = None


class RobotTaskTimelineResponse(BaseModel):
    timeline: list[RobotTaskTimeline]


class RobotTaskCancelResponse(BaseModel):
    ok: bool = True
    task: RobotTask


class RobotTaskSimulateResponseRequest(BaseModel):
    response_type: RobotTaskOutcome
    transcript: str | None = None
    snapshot_url: str | None = None
