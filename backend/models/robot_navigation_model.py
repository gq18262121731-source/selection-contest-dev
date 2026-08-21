from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RobotCapabilityState(str, Enum):
    MOCK = "mock"
    UNAVAILABLE = "unavailable"
    NOT_VERIFIED = "not_verified"
    BLOCKED = "blocked"
    READY = "ready"


class RobotControlOwner(str, Enum):
    NONE = "NONE"
    MANUAL = "MANUAL"
    NAVIGATION = "NAVIGATION"
    FOLLOW = "FOLLOW"
    EMERGENCY_STOP = "EMERGENCY_STOP"


class RobotMappingState(str, Enum):
    IDLE = "idle"
    MAPPING = "mapping"
    PREVIEW_READY = "preview_ready"
    SAVED = "saved"
    CANCELLED = "cancelled"
    FAILED = "failed"


class RobotNavigationExecutionState(str, Enum):
    CREATED = "created"
    SAFETY_CHECKING = "safety_checking"
    BLOCKED = "blocked"
    QUEUED = "queued"
    NAVIGATING = "navigating"
    PAUSED_MANUAL = "paused_manual"
    PAUSED_ADMIN = "paused_admin"
    ARRIVED = "arrived"
    VOICE_PROMPTING = "voice_prompting"
    WAITING_RESPONSE = "waiting_response"
    SAFE_RESPONSE = "safe_response"
    HELP_REQUESTED = "help_requested"
    NO_RESPONSE = "no_response"
    UNCERTAIN = "uncertain"
    WAITING_ADMIN_CONFIRMATION = "waiting_admin_confirmation"
    RETURNING_HOME = "returning_home"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RobotMapStatus(str, Enum):
    DRAFT = "draft"
    PREVIEW = "preview"
    ACTIVE = "active"
    REPLACED = "replaced"
    ARCHIVED = "archived"


class RobotMapPointType(str, Enum):
    HOME = "home"
    OBSERVATION = "observation"
    PATROL = "patrol"


class RobotMapPointStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"


class RobotPatrolRouteStatus(str, Enum):
    DRAFT = "draft"
    VALID = "valid"
    ACTIVE = "active"
    INVALID = "invalid"
    ARCHIVED = "archived"


class MockRobotDomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["mock"] = "mock"
    real_motion_enabled: Literal[False] = False


class RobotNavigationCapability(MockRobotDomainModel):
    mapping: RobotCapabilityState = RobotCapabilityState.MOCK
    maps: RobotCapabilityState = RobotCapabilityState.MOCK
    navigation: RobotCapabilityState = RobotCapabilityState.MOCK
    localization: RobotCapabilityState = RobotCapabilityState.MOCK
    path_planning: RobotCapabilityState = RobotCapabilityState.MOCK
    patrol: RobotCapabilityState = RobotCapabilityState.MOCK
    emergency_dispatch: RobotCapabilityState = RobotCapabilityState.MOCK
    return_home: RobotCapabilityState = RobotCapabilityState.MOCK
    point_cloud: RobotCapabilityState = RobotCapabilityState.MOCK
    audio_input: RobotCapabilityState = RobotCapabilityState.MOCK
    audio_output: RobotCapabilityState = RobotCapabilityState.MOCK
    manual_takeover: RobotCapabilityState = RobotCapabilityState.MOCK
    ros2: RobotCapabilityState = RobotCapabilityState.UNAVAILABLE
    nav2: RobotCapabilityState = RobotCapabilityState.UNAVAILABLE
    slam_toolbox: RobotCapabilityState = RobotCapabilityState.UNAVAILABLE
    real_lidar_point_cloud: RobotCapabilityState = RobotCapabilityState.NOT_VERIFIED


class RobotSafetyChecks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    robot_online: bool
    emergency_stop_clear: bool
    localization_valid: bool
    map_loaded: bool
    path_plannable: bool
    robot_stationary: bool
    control_available: bool

    def blocked_names(self) -> list[str]:
        return [name for name, passed in self.model_dump().items() if not passed]


class RobotSafetyInterlock(MockRobotDomainModel):
    passed: bool
    checks: RobotSafetyChecks
    blocked_by: list[str] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=utc_now)


class RobotNavigationState(MockRobotDomainModel):
    robot_id: str | None = Field(default=None, max_length=160)
    execution_state: RobotNavigationExecutionState = RobotNavigationExecutionState.CREATED
    control_owner: RobotControlOwner = RobotControlOwner.NONE
    mapping_state: RobotMappingState = RobotMappingState.IDLE
    active_map_id: str | None = Field(default=None, max_length=160)
    active_task_id: str | None = Field(default=None, max_length=160)
    localization_valid: bool = False
    map_loaded: bool = False
    path_plannable: bool = False
    emergency_stop_active: bool = False
    safety_interlock: RobotSafetyInterlock | None = None
    mock_scenario: str = Field(default="robot_ready", max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=utc_now)


class RobotMap(MockRobotDomainModel):
    map_id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=160)
    status: RobotMapStatus = RobotMapStatus.DRAFT
    revision: int = Field(default=1, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    activated_at: datetime | None = None
    replaced_at: datetime | None = None


class RobotMapPoint(MockRobotDomainModel):
    point_id: str = Field(min_length=1, max_length=160)
    map_id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=160)
    point_type: RobotMapPointType
    x: float
    y: float
    yaw: float
    status: RobotMapPointStatus = RobotMapPointStatus.VALID
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    invalidated_at: datetime | None = None


class RobotPatrolRoute(MockRobotDomainModel):
    route_id: str = Field(min_length=1, max_length=160)
    map_id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=160)
    status: RobotPatrolRouteStatus = RobotPatrolRouteStatus.DRAFT
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RobotPatrolRoutePoint(MockRobotDomainModel):
    id: int | None = None
    route_id: str = Field(min_length=1, max_length=160)
    point_id: str = Field(min_length=1, max_length=160)
    sequence: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RobotNavigationEvent(MockRobotDomainModel):
    id: int | None = None
    event_id: str = Field(min_length=1, max_length=160)
    task_id: str | None = Field(default=None, max_length=160)
    incident_id: str | None = Field(default=None, max_length=160)
    event_type: str = Field(min_length=1, max_length=120)
    execution_state: RobotNavigationExecutionState | None = None
    navigation_state: RobotNavigationExecutionState | None = None
    x: float | None = None
    y: float | None = None
    yaw: float | None = None
    control_owner: RobotControlOwner = RobotControlOwner.NONE
    error_code: str | None = Field(default=None, max_length=120)
    sequence: int = Field(default=0, ge=0)
    message: str = Field(default="", max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=utc_now)
    created_at: datetime = Field(default_factory=utc_now)
