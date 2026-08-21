from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class RobotCompanionIntent(str, Enum):
    CHAT = "chat"
    WALK_REQUEST = "walk_request"
    WEATHER_QUERY = "weather_query"
    HEALTH_CHECK = "health_check"
    COMPANIONSHIP = "companionship"
    EMERGENCY = "emergency"


class RobotCompanionActionType(str, Enum):
    NONE = "none"
    SUGGEST_WALK = "suggest_walk"
    PREPARE_FOLLOW = "prepare_follow"
    CALL_FAMILY = "call_family"
    REQUEST_HELP = "request_help"


class RobotCompanionDialogueRequest(BaseModel):
    elder_id: str = Field(..., min_length=1, max_length=160)
    text: str = Field(..., min_length=1, max_length=1000)
    device_mac: str | None = Field(default=None, max_length=64)
    location_hint: str | None = Field(default=None, max_length=200)
    demo_weather: Literal["sunny", "rain", "windy", "hot", "cold"] = "sunny"
    use_llm: bool = True

    @field_validator("elder_id", "text")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("device_mac")
    @classmethod
    def normalize_device_mac(cls, value: str | None) -> str | None:
        if value is None:
            return None
        compact = "".join(character for character in value if character.isalnum()).upper()
        if len(compact) == 12:
            return ":".join(compact[index : index + 2] for index in range(0, 12, 2))
        return value.strip().upper() or None

    @field_validator("location_hint")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class RobotCompanionHealthContext(BaseModel):
    risk_level: Literal["low", "medium", "high", "unknown"] = "unknown"
    health_score: int | None = Field(default=None, ge=0, le=100)
    recent_fall: bool = False
    sos: bool = False
    today_steps: int | None = Field(default=None, ge=0)
    data_freshness: Literal["fresh", "stale", "missing"] = "missing"
    device_mac: str | None = None


class RobotCompanionEnvironmentContext(BaseModel):
    weather: Literal["sunny", "rain", "windy", "hot", "cold", "unknown"] = "unknown"
    temperature: float | None = None
    humidity: int | None = Field(default=None, ge=0, le=100)
    wind_level: int | None = Field(default=None, ge=0, le=12)
    description: str = ""
    suggestion: str = ""
    provider: Literal["mock", "qweather"] = "mock"
    source: Literal["mock", "qweather"] = "mock"


class RobotCompanionLocationContext(BaseModel):
    city: str
    area: str
    address: str
    provider: Literal["mock"] = "mock"


class RobotCompanionRobotContext(BaseModel):
    online: bool
    motion_enabled: Literal[False] = False
    provider: Literal["mock"] = "mock"


class RobotCompanionContext(BaseModel):
    elder_id: str
    elder_name: str
    generated_at: datetime
    health: RobotCompanionHealthContext
    environment: RobotCompanionEnvironmentContext
    location: RobotCompanionLocationContext
    robot: RobotCompanionRobotContext


class RobotCompanionDecision(BaseModel):
    intent: RobotCompanionIntent
    confidence: float = Field(ge=0.0, le=1.0)
    source: Literal["qwen", "rule"]
    model: str | None = None


class RobotCompanionActionPlan(BaseModel):
    type: RobotCompanionActionType
    parameters: dict[str, Any] = Field(default_factory=dict)
    enabled: Literal[False] = False
    execution: Literal["not_executed"] = "not_executed"


class RobotCompanionSafetyDecision(BaseModel):
    status: Literal["allowed", "blocked"]
    code: str
    reason: str


class RobotCompanionDialogueResponse(BaseModel):
    agent: Literal["care_companion"] = "care_companion"
    version: Literal["1.0"] = "1.0"
    decision: RobotCompanionDecision
    reply: str
    context: RobotCompanionContext
    action_plan: RobotCompanionActionPlan
    safety: RobotCompanionSafetyDecision
