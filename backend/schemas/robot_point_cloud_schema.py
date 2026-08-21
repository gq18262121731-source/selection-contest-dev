from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PointCloudScenario = Literal[
    "classroom_default",
    "classroom_sparse",
    "classroom_obstacle",
    "empty",
    "stream_stale",
    "stream_error",
]
NavigationState = Literal[
    "idle",
    "created",
    "safety_checking",
    "blocked",
    "queued",
    "navigating",
    "paused_manual",
    "paused_admin",
    "arrived",
    "returning_home",
    "completed",
    "failed",
    "cancelled",
]
ControlOwner = Literal["NONE", "MANUAL", "NAVIGATION", "FOLLOW", "EMERGENCY_STOP"]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finite_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("value must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError("value must be a finite number")
    return normalized


class StrictPointCloudModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RobotPointCloudPose(StrictPointCloudModel):
    x: float
    y: float
    z: float = 0.0
    yaw: float

    @field_validator("x", "y", "z", "yaw", mode="before")
    @classmethod
    def require_finite(cls, value: Any) -> float:
        return _finite_number(value)


class RobotPointCloudStreamInfo(StrictPointCloudModel):
    type: Literal["point_cloud_stream_info"]
    provider: Literal["mock"]
    real_motion_enabled: Literal[False]
    frame_id: Literal["mock_lidar"]
    coordinate_frame: Literal["map"]
    encoding: Literal["json_xyz_intensity_v1"]
    target_fps: float = Field(gt=0, le=5)
    max_points: int = Field(gt=0, le=5000)
    queue_size: int = Field(gt=0, le=2)
    scenario: PointCloudScenario
    stream_status: Literal["ready", "stale", "error"]
    timestamp: datetime

    @field_validator("target_fps", mode="before")
    @classmethod
    def require_finite_fps(cls, value: Any) -> float:
        return _finite_number(value)


class RobotPointCloudFrame(StrictPointCloudModel):
    type: Literal["point_cloud_frame"]
    sequence: int = Field(ge=1)
    timestamp: datetime
    provider: Literal["mock"]
    real_motion_enabled: Literal[False]
    frame_id: Literal["mock_lidar"]
    coordinate_frame: Literal["map"]
    scenario: PointCloudScenario
    point_count: int = Field(ge=0, le=5000)
    points: list[tuple[float, float, float, float]] = Field(max_length=5000)
    robot_pose: RobotPointCloudPose
    target_pose: RobotPointCloudPose | None
    navigation_state: NavigationState
    control_owner: ControlOwner

    @field_validator("sequence", "point_count", mode="before")
    @classmethod
    def reject_boolean_integers(cls, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("value must be an integer")
        return value

    @field_validator("points", mode="before")
    @classmethod
    def require_strict_finite_points(cls, points: Any) -> Any:
        if not isinstance(points, list):
            raise ValueError("points must be an array")
        for point in points:
            if not isinstance(point, (list, tuple)) or len(point) != 4:
                raise ValueError("each point must contain x, y, z, intensity")
            for value in point:
                _finite_number(value)
        return points

    @model_validator(mode="after")
    def require_matching_count(self) -> "RobotPointCloudFrame":
        if self.point_count != len(self.points):
            raise ValueError("point_count must equal points length")
        return self


class RobotPointCloudUpstreamError(StrictPointCloudModel):
    type: Literal["error"]
    code: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=1000)
    provider: Literal["mock"]
    real_motion_enabled: Literal[False]
    timestamp: datetime


def local_point_cloud_error(code: str, message: str) -> dict[str, Any]:
    return {
        "type": "error",
        "code": code,
        "message": message,
        "provider": "mock",
        "real_motion_enabled": False,
        "timestamp": utc_timestamp(),
    }


def connection_state_message(state: str) -> dict[str, Any]:
    return {
        "type": "connection_state_changed",
        "connection_state": state,
        "provider": "mock",
        "real_motion_enabled": False,
        "timestamp": utc_timestamp(),
    }
