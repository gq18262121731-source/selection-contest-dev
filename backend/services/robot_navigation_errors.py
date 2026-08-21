from __future__ import annotations

from enum import Enum
from typing import Any


class RobotNavigationErrorCode(str, Enum):
    ROBOT_GATEWAY_UNAVAILABLE = "ROBOT_GATEWAY_UNAVAILABLE"
    ROBOT_GATEWAY_TIMEOUT = "ROBOT_GATEWAY_TIMEOUT"
    ROBOT_GATEWAY_INVALID_RESPONSE = "ROBOT_GATEWAY_INVALID_RESPONSE"
    MOCK_PROVIDER_CONTRACT_VIOLATION = "MOCK_PROVIDER_CONTRACT_VIOLATION"
    REAL_MOTION_DISABLED = "REAL_MOTION_DISABLED"
    SAFETY_INTERLOCK_BLOCKED = "SAFETY_INTERLOCK_BLOCKED"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    MAP_NOT_FOUND = "MAP_NOT_FOUND"
    MAP_NOT_ACTIVE = "MAP_NOT_ACTIVE"
    MAP_STATE_CONFLICT = "MAP_STATE_CONFLICT"
    MAP_REPLACEMENT_CONFIRMATION_REQUIRED = "MAP_REPLACEMENT_CONFIRMATION_REQUIRED"
    MAP_POINT_NOT_FOUND = "MAP_POINT_NOT_FOUND"
    MAP_POINT_INVALID = "MAP_POINT_INVALID"
    MAP_POINTS_INVALID = "MAP_POINTS_INVALID"
    ROUTE_NOT_FOUND = "ROUTE_NOT_FOUND"
    ROUTE_INVALID = "ROUTE_INVALID"
    HOME_POINT_NOT_FOUND = "HOME_POINT_NOT_FOUND"
    OBSERVATION_POINT_NOT_FOUND = "OBSERVATION_POINT_NOT_FOUND"
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    INCIDENT_NOT_FOUND = "INCIDENT_NOT_FOUND"
    INCIDENT_STATE_CONFLICT = "INCIDENT_STATE_CONFLICT"
    DIALOGUE_ALREADY_STARTED = "DIALOGUE_ALREADY_STARTED"
    RETURN_NOT_IN_PROGRESS = "RETURN_NOT_IN_PROGRESS"
    SAFE_RESPONSE_REQUIRED = "SAFE_RESPONSE_REQUIRED"
    CONTROL_OWNER_CONFLICT = "CONTROL_OWNER_CONFLICT"
    OPERATION_CONFLICT = "OPERATION_CONFLICT"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"


class RobotNavigationServiceError(Exception):
    """Stable service-layer failure with a machine-readable error code."""

    def __init__(
        self,
        code: RobotNavigationErrorCode | str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        self.code = code.value if isinstance(code, RobotNavigationErrorCode) else str(code)
        self.message = message
        self.details = details or {}
        self.retryable = retryable
        super().__init__(f"{self.code}: {self.message}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.code,
            "message": self.message,
            "details": self.details,
            "retryable": self.retryable,
            "provider": "mock",
            "real_motion_enabled": False,
        }
