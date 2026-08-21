from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

import requests

from backend.services.robot_navigation_errors import (
    RobotNavigationErrorCode,
    RobotNavigationServiceError,
)


@dataclass(frozen=True)
class RobotNavigationGatewayResult:
    data: dict[str, Any]
    code: str = "OK"
    message: str = "ok"
    provider: str = "mock"
    real_motion_enabled: bool = False
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class RobotNavigationGatewayService:
    """Strict Mock-only proxy for the frozen go2-gateway navigation contract."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 3.0,
        enabled: bool = True,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.enabled = enabled
        self.session = session or requests.Session()

    def capabilities(self) -> RobotNavigationGatewayResult:
        return self._request("GET", "/api/navigation/capabilities")

    def state(self) -> RobotNavigationGatewayResult:
        return self._request("GET", "/api/navigation/state")

    def start_mapping(self, payload: Mapping[str, Any]) -> RobotNavigationGatewayResult:
        return self._request("POST", "/api/navigation/mapping/start", payload)

    def stop_mapping(self, payload: Mapping[str, Any]) -> RobotNavigationGatewayResult:
        return self._request("POST", "/api/navigation/mapping/stop", payload)

    def save_map(self, payload: Mapping[str, Any]) -> RobotNavigationGatewayResult:
        return self._request("POST", "/api/navigation/maps/save", payload)

    def active_map(self) -> RobotNavigationGatewayResult:
        return self._request("GET", "/api/navigation/maps/active")

    def start_patrol(self, payload: Mapping[str, Any]) -> RobotNavigationGatewayResult:
        return self._request("POST", "/api/navigation/patrol/start", payload)

    def pause_task(self, task_id: str, payload: Mapping[str, Any]) -> RobotNavigationGatewayResult:
        return self._request("POST", f"/api/navigation/tasks/{task_id}/pause", payload)

    def resume_task(self, task_id: str, payload: Mapping[str, Any]) -> RobotNavigationGatewayResult:
        return self._request("POST", f"/api/navigation/tasks/{task_id}/resume", payload)

    def stop_task(self, task_id: str, payload: Mapping[str, Any]) -> RobotNavigationGatewayResult:
        return self._request("POST", f"/api/navigation/tasks/{task_id}/stop", payload)

    def emergency_dispatch(self, payload: Mapping[str, Any]) -> RobotNavigationGatewayResult:
        return self._request("POST", "/api/navigation/emergency/dispatch", payload)

    def return_home(self, payload: Mapping[str, Any]) -> RobotNavigationGatewayResult:
        return self._request("POST", "/api/navigation/return-home", payload)

    def manual_takeover(self, payload: Mapping[str, Any]) -> RobotNavigationGatewayResult:
        return self._request("POST", "/api/navigation/control/manual-takeover", payload)

    def release_control(self, payload: Mapping[str, Any]) -> RobotNavigationGatewayResult:
        return self._request("POST", "/api/navigation/control/release", payload)

    def _request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
    ) -> RobotNavigationGatewayResult:
        if not self.enabled:
            raise RobotNavigationServiceError(
                RobotNavigationErrorCode.ROBOT_GATEWAY_UNAVAILABLE,
                "机器人导航网关代理未启用",
                retryable=True,
            )
        normalized = self._normalize_request_keys(dict(payload or {}))
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                json=normalized if method != "GET" else None,
                timeout=self.timeout_seconds,
            )
        except requests.Timeout as exc:
            raise RobotNavigationServiceError(
                RobotNavigationErrorCode.ROBOT_GATEWAY_TIMEOUT,
                "机器人导航网关请求超时",
                details={"path": path},
                retryable=True,
            ) from exc
        except requests.RequestException as exc:
            raise RobotNavigationServiceError(
                RobotNavigationErrorCode.ROBOT_GATEWAY_UNAVAILABLE,
                "机器人导航网关不可用",
                details={"path": path},
                retryable=True,
            ) from exc

        try:
            body = response.json()
        except (TypeError, ValueError) as exc:
            raise RobotNavigationServiceError(
                RobotNavigationErrorCode.ROBOT_GATEWAY_INVALID_RESPONSE,
                "机器人导航网关返回了非 JSON 响应",
                details={"path": path, "status_code": response.status_code},
            ) from exc
        if not isinstance(body, dict):
            raise RobotNavigationServiceError(
                RobotNavigationErrorCode.ROBOT_GATEWAY_INVALID_RESPONSE,
                "机器人导航网关响应结构无效",
                details={"path": path},
            )
        if response.status_code >= 400:
            raise RobotNavigationServiceError(
                RobotNavigationErrorCode.ROBOT_GATEWAY_UNAVAILABLE,
                str(body.get("message") or "机器人导航网关拒绝请求"),
                details={"path": path, "status_code": response.status_code, "gateway_code": body.get("code")},
                retryable=response.status_code >= 500,
            )

        data = body.get("data", body)
        if not isinstance(data, dict):
            raise RobotNavigationServiceError(
                RobotNavigationErrorCode.ROBOT_GATEWAY_INVALID_RESPONSE,
                "机器人导航网关缺少 data 对象",
                details={"path": path},
            )
        if data.get("provider") != "mock":
            raise RobotNavigationServiceError(
                RobotNavigationErrorCode.MOCK_PROVIDER_CONTRACT_VIOLATION,
                "机器人导航网关未声明 Mock Provider",
                details={"path": path, "provider": data.get("provider")},
            )
        if data.get("real_motion_enabled") is not False:
            raise RobotNavigationServiceError(
                RobotNavigationErrorCode.REAL_MOTION_DISABLED,
                "拒绝任何未显式关闭真实运动的网关响应",
                details={"path": path, "real_motion_enabled": data.get("real_motion_enabled")},
            )
        return RobotNavigationGatewayResult(
            data=data,
            code=str(body.get("code", "OK")),
            message=str(body.get("message", "ok")),
        )

    @classmethod
    def _normalize_request_keys(cls, value: Any) -> Any:
        if isinstance(value, dict):
            normalized: dict[str, Any] = {}
            for key, item in value.items():
                target_key = "request_id" if key == "requestId" else key
                normalized[target_key] = cls._normalize_request_keys(item)
            return normalized
        if isinstance(value, list):
            return [cls._normalize_request_keys(item) for item in value]
        return value
