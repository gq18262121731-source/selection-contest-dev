from __future__ import annotations

from pydantic import Field, field_validator

from backend.models.robot_emergency_model import RobotDialogueIntent
from backend.schemas.robot_navigation_api_schema import RobotOperationRequest


class RobotEmergencyDispatchRequest(RobotOperationRequest):
    area_id: str = Field(min_length=1, max_length=80)
    area_name: str = Field(min_length=1, max_length=120)
    alarm_id: str | None = Field(default=None, min_length=1, max_length=160)
    camera_id: str | None = Field(default=None, min_length=1, max_length=80)
    risk_level: str = Field(default="critical", min_length=1, max_length=40)
    fall_probability: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)


class RobotEmergencyAcknowledgeRequest(RobotOperationRequest):
    admin_id: str = Field(min_length=1, max_length=160)


class RobotEmergencyDialogueRequest(RobotOperationRequest):
    turn_id: str = Field(min_length=1, max_length=160)
    intent: RobotDialogueIntent
    input_text: str | None = Field(default=None, max_length=4000)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)


class RobotEmergencyResolveRequest(RobotOperationRequest):
    resolution: str = Field(default="管理员确认安全并请求返航", min_length=1, max_length=1000)


class RobotEmergencyMockDialogueStartRequest(RobotOperationRequest):
    mock_prompt_text: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("mock_prompt_text")
    @classmethod
    def reject_html_prompt(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("mock_prompt_text must not be blank")
        if "<" in normalized or ">" in normalized:
            raise ValueError("mock_prompt_text must not contain HTML")
        return normalized


class RobotEmergencyMockReturnCompleteRequest(RobotOperationRequest):
    pass
