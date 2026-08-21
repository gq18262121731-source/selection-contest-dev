from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from backend.models.robot_navigation_model import (
    MockRobotDomainModel,
    RobotControlOwner,
    RobotNavigationEvent,
    RobotNavigationExecutionState,
    utc_now,
)


RobotEmergencyExecutionState = RobotNavigationExecutionState


class RobotDialogueIntent(str, Enum):
    SAFE_RESPONSE = "safe_response"
    NEED_HELP = "need_help"
    NO_RESPONSE = "no_response"
    UNCERTAIN = "uncertain"


class RobotDialogueRole(str, Enum):
    SYSTEM = "system"
    ASSISTANT = "assistant"
    USER = "user"


class RobotEmergencyCaseStatus(str, Enum):
    OPEN = "open"
    BLOCKED = "blocked"
    ACTIVE = "active"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


class RobotEmergencyCase(MockRobotDomainModel):
    case_id: str = Field(min_length=1, max_length=160)
    incident_id: str = Field(min_length=1, max_length=160)
    robot_task_id: str | None = Field(default=None, max_length=160)
    alarm_id: str | None = Field(default=None, max_length=160)
    camera_id: str | None = Field(default=None, max_length=80)
    area_id: str | None = Field(default=None, max_length=80)
    area_name: str | None = Field(default=None, max_length=120)
    observation_point_id: str | None = Field(default=None, max_length=160)
    home_point_id: str | None = Field(default=None, max_length=160)
    risk_level: str = Field(default="unknown", max_length=40)
    fall_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    status: RobotEmergencyCaseStatus = RobotEmergencyCaseStatus.OPEN
    execution_state: RobotEmergencyExecutionState = RobotEmergencyExecutionState.CREATED
    navigation_state: RobotNavigationExecutionState = RobotNavigationExecutionState.CREATED
    control_owner: RobotControlOwner = RobotControlOwner.NONE
    dialogue_intent: RobotDialogueIntent | None = None
    acknowledged_by: str | None = Field(default=None, max_length=160)
    acknowledged_at: datetime | None = None
    resolution: str | None = Field(default=None, max_length=1000)
    resolved_at: datetime | None = None
    error_code: str | None = Field(default=None, max_length=120)
    error_message: str | None = Field(default=None, max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RobotDialogueTurn(MockRobotDomainModel):
    id: int | None = None
    turn_id: str = Field(min_length=1, max_length=160)
    incident_id: str = Field(min_length=1, max_length=160)
    robot_task_id: str | None = Field(default=None, max_length=160)
    role: RobotDialogueRole
    text: str = Field(default="", max_length=4000)
    input_text: str | None = Field(default=None, max_length=4000)
    intent: RobotDialogueIntent | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    recommended_action: str | None = Field(default=None, max_length=160)
    reply_text: str | None = Field(default=None, max_length=4000)
    asr_status: str | None = Field(default=None, max_length=80)
    tts_status: str | None = Field(default=None, max_length=80)
    conversation_complete: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=utc_now)
    created_at: datetime = Field(default_factory=utc_now)


class RobotEmergencyIncidentBundle(MockRobotDomainModel):
    incident_id: str
    emergency_case: RobotEmergencyCase
    robot_task_id: str | None
    navigation_events: list[RobotNavigationEvent] = Field(default_factory=list)
    dialogue_turns: list[RobotDialogueTurn] = Field(default_factory=list)
