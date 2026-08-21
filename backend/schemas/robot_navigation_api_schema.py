from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.models.robot_navigation_model import RobotMapPointType


DataT = TypeVar("DataT")


class RobotApiEnvelope(BaseModel, Generic[DataT]):
    success: bool
    code: str
    message: str
    data: DataT
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: str | None = None


class StrictRobotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RobotOperationRequest(StrictRobotRequest):
    request_id: str = Field(min_length=1, max_length=160)


class RobotMappingStartRequest(RobotOperationRequest):
    session_name: str = Field(min_length=1, max_length=160)


class RobotMappingStopRequest(RobotOperationRequest):
    map_id: str = Field(min_length=1, max_length=160)
    session_id: str = Field(min_length=1, max_length=160)


class RobotMapPreviewRequest(RobotOperationRequest):
    map_id: str = Field(min_length=1, max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RobotMapSaveRequest(RobotOperationRequest):
    map_id: str = Field(min_length=1, max_length=160)
    session_id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=160)
    replace_confirmed: bool


class RobotPointCreateRequest(RobotOperationRequest):
    point_id: str = Field(min_length=1, max_length=160)
    map_id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=160)
    point_type: RobotMapPointType
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    yaw: float = Field(allow_inf_nan=False)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RobotPointUpdateRequest(RobotOperationRequest):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    point_type: RobotMapPointType | None = None
    x: float | None = Field(default=None, allow_inf_nan=False)
    y: float | None = Field(default=None, allow_inf_nan=False)
    yaw: float | None = Field(default=None, allow_inf_nan=False)
    metadata: dict[str, Any] | None = None


class RobotRouteCreateRequest(RobotOperationRequest):
    route_id: str = Field(min_length=1, max_length=160)
    map_id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=160)
    point_ids: list[str] = Field(min_length=1, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("point_ids")
    @classmethod
    def validate_point_ids(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item or len(item) > 160 for item in normalized):
            raise ValueError("point_ids must contain non-empty identifiers")
        if len(set(normalized)) != len(normalized):
            raise ValueError("route point_ids must be unique")
        return normalized


class RobotPatrolStartRequest(RobotOperationRequest):
    source_event_id: str | None = Field(default=None, min_length=1, max_length=160)
    trace_id: str | None = Field(default=None, min_length=1, max_length=160)


class RobotTaskOperationRequest(RobotOperationRequest):
    pass


def success_envelope(data: Any, request_id: str | None = None, *, message: str = "操作成功") -> dict[str, Any]:
    return RobotApiEnvelope[Any](
        success=True,
        code="OK",
        message=message,
        data=data,
        request_id=request_id,
    ).model_dump(mode="json")


def error_envelope(
    code: str,
    message: str,
    data: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    return RobotApiEnvelope[dict[str, Any]](
        success=False,
        code=code,
        message=message,
        data=data or {},
        request_id=request_id,
    ).model_dump(mode="json")
