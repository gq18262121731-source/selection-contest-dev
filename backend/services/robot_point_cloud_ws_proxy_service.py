from __future__ import annotations

import asyncio
import inspect
import json
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse, urlunparse

import websockets
from pydantic import ValidationError

from backend.schemas.robot_point_cloud_schema import (
    RobotPointCloudFrame,
    RobotPointCloudStreamInfo,
    RobotPointCloudUpstreamError,
    connection_state_message,
)
from backend.services.robot_point_cloud_hub import RobotPointCloudHub


class PointCloudContractError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


class RobotPointCloudWsProxyService:
    """One bounded Mock point-cloud upstream shared by all local clients."""

    def __init__(
        self,
        base_url: str,
        hub: RobotPointCloudHub,
        *,
        disconnect_grace_seconds: float = 0.2,
        retry_initial_seconds: float = 0.1,
        retry_max_seconds: float = 2.0,
        connector: Callable[[str], Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.hub = hub
        self.disconnect_grace_seconds = max(0.0, disconnect_grace_seconds)
        self.retry_initial_seconds = max(0.01, retry_initial_seconds)
        self.retry_max_seconds = max(self.retry_initial_seconds, retry_max_seconds)
        self._connector = connector or websockets.connect
        self._lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._subscriber_count = 0
        self._runner_task: asyncio.Task[None] | None = None
        self._delayed_stop_task: asyncio.Task[None] | None = None
        self._active_websocket: Any | None = None
        self._closed = False
        self._connection_attempts = 0
        self._active_upstream_connections = 0
        self._declared_max_points: int | None = None

    async def acquire(self) -> None:
        async with self._lock:
            if self._closed:
                raise RuntimeError("robot point-cloud proxy is closed")
            self._subscriber_count += 1
            if self._delayed_stop_task:
                self._delayed_stop_task.cancel()
                self._delayed_stop_task = None
            if self._runner_task is None or self._runner_task.done():
                self._runner_task = asyncio.create_task(
                    self._run(), name="robot-point-cloud-upstream-ws"
                )

    async def release(self) -> None:
        async with self._lock:
            self._subscriber_count = max(0, self._subscriber_count - 1)
            if self._subscriber_count == 0 and self._runner_task and not self._runner_task.done():
                if self._delayed_stop_task is None or self._delayed_stop_task.done():
                    self._delayed_stop_task = asyncio.create_task(
                        self._stop_after_grace(), name="robot-point-cloud-delayed-stop"
                    )

    async def request_sync(self) -> bool:
        websocket = self._active_websocket
        if websocket is None:
            return False
        try:
            await self._send_json(websocket, {"type": "sync"})
            return True
        except Exception:
            return False

    async def close(self) -> None:
        async with self._lock:
            self._closed = True
            tasks = [task for task in (self._delayed_stop_task, self._runner_task) if task]
            self._delayed_stop_task = None
            self._runner_task = None
            self._subscriber_count = 0
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._active_websocket = None
        self._active_upstream_connections = 0

    async def _stop_after_grace(self) -> None:
        await asyncio.sleep(self.disconnect_grace_seconds)
        async with self._lock:
            if self._subscriber_count == 0 and self._runner_task:
                self._runner_task.cancel()

    async def _run(self) -> None:
        retry_delay = self.retry_initial_seconds
        reconnecting = False
        try:
            while not self._closed and self._subscriber_count > 0:
                self.hub.publish_control(
                    connection_state_message("reconnecting" if reconnecting else "connecting")
                )
                try:
                    self._connection_attempts += 1
                    connection = self._connector(self._upstream_url())
                    if inspect.isawaitable(connection):
                        connection = await connection
                    async with connection as websocket:
                        self._active_websocket = websocket
                        self._active_upstream_connections = 1
                        self._declared_max_points = None
                        self.hub.publish_control(connection_state_message("connected"))
                        if reconnecting:
                            await self._send_json(websocket, {"type": "sync"})
                        reconnecting = True
                        retry_delay = self.retry_initial_seconds
                        async for raw_message in websocket:
                            try:
                                await self._handle_message(websocket, raw_message)
                            except PointCloudContractError as exc:
                                self.hub.publish_error(exc.code, exc.message)
                    raise ConnectionError("point-cloud upstream closed")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._active_websocket = None
                    self._active_upstream_connections = 0
                    code = self._connection_error_code(exc)
                    self.hub.publish_error(code, "Mock 点云上游暂不可用")
                    self.hub.publish_control(connection_state_message("disconnected"))
                    if self._subscriber_count <= 0 or self._closed:
                        break
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(self.retry_max_seconds, retry_delay * 2)
        finally:
            self._active_websocket = None
            self._active_upstream_connections = 0
            self._declared_max_points = None
            self.hub.publish_control(connection_state_message("stopped"))

    async def _handle_message(self, websocket: Any, raw_message: Any) -> None:
        payload = self._decode(raw_message)
        message_type = payload.get("type")
        if message_type == "ping":
            self._require_mock_invariants(payload)
            if not payload.get("timestamp"):
                raise PointCloudContractError(
                    "ROBOT_POINT_CLOUD_INVALID_MESSAGE", "点云心跳缺少 timestamp"
                )
            await self._send_json(websocket, {"type": "pong"})
            return
        try:
            if message_type == "point_cloud_stream_info":
                info = RobotPointCloudStreamInfo.model_validate(payload)
                self._declared_max_points = info.max_points
                self.hub.publish_stream_info(self._local_message(payload))
                return
            if message_type == "point_cloud_frame":
                if self._declared_max_points is None:
                    raise PointCloudContractError(
                        "POINT_CLOUD_PROXY_NOT_READY", "尚未收到合法点云流声明"
                    )
                frame = RobotPointCloudFrame.model_validate(payload)
                if frame.point_count > self._declared_max_points:
                    raise PointCloudContractError(
                        "POINT_CLOUD_FRAME_INVALID", "point_count 超过上游声明的 max_points"
                    )
                self.hub.publish_frame(self._local_message(payload, sequence=frame.sequence))
                return
            if message_type == "error":
                error = RobotPointCloudUpstreamError.model_validate(payload)
                self.hub.publish_error(error.code, error.message)
                return
        except ValidationError as exc:
            code = self._validation_error_code(payload)
            raise PointCloudContractError(code, "上游 Mock 点云消息未通过合同校验") from exc
        raise PointCloudContractError(
            "ROBOT_POINT_CLOUD_INVALID_MESSAGE", "上游发送了未知点云消息类型"
        )

    @staticmethod
    def _decode(raw_message: Any) -> dict[str, Any]:
        try:
            if isinstance(raw_message, bytes):
                raw_message = raw_message.decode("utf-8")
            payload = json.loads(raw_message) if isinstance(raw_message, str) else raw_message
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PointCloudContractError(
                "ROBOT_POINT_CLOUD_INVALID_MESSAGE", "上游点云消息不是合法 JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise PointCloudContractError(
                "ROBOT_POINT_CLOUD_INVALID_MESSAGE", "上游点云消息必须是对象"
            )
        return payload

    @staticmethod
    def _require_mock_invariants(payload: dict[str, Any]) -> None:
        if payload.get("provider") != "mock":
            raise PointCloudContractError(
                "MOCK_PROVIDER_CONTRACT_VIOLATION", "上游点云 provider 不是 mock"
            )
        if payload.get("real_motion_enabled") is not False:
            raise PointCloudContractError(
                "REAL_MOTION_DISABLED", "上游点云未关闭真实运动"
            )

    @staticmethod
    def _validation_error_code(payload: dict[str, Any]) -> str:
        if payload.get("provider") != "mock":
            return "MOCK_PROVIDER_CONTRACT_VIOLATION"
        if payload.get("real_motion_enabled") is not False:
            return "REAL_MOTION_DISABLED"
        if payload.get("type") == "point_cloud_frame":
            return "POINT_CLOUD_FRAME_INVALID"
        return "ROBOT_POINT_CLOUD_INVALID_MESSAGE"

    @staticmethod
    def _local_message(payload: dict[str, Any], *, sequence: int | None = None) -> dict[str, Any]:
        local = dict(payload)
        if sequence is not None:
            local["upstream_sequence"] = sequence
        local["proxy_timestamp"] = datetime.now(timezone.utc).isoformat()
        local["connection_state"] = "connected"
        return local

    async def _send_json(self, websocket: Any, payload: dict[str, Any]) -> None:
        async with self._send_lock:
            await websocket.send(json.dumps(payload, ensure_ascii=False))

    def _upstream_url(self) -> str:
        parsed = urlparse(self.base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        return urlunparse((scheme, parsed.netloc, "/ws/navigation/point-cloud", "", "", ""))

    @staticmethod
    def _connection_error_code(exc: Exception) -> str:
        if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
            return "ROBOT_POINT_CLOUD_UPSTREAM_TIMEOUT"
        return "ROBOT_POINT_CLOUD_UPSTREAM_UNAVAILABLE"

    @property
    def subscriber_count(self) -> int:
        return self._subscriber_count

    @property
    def active_upstream_connections(self) -> int:
        return self._active_upstream_connections

    @property
    def connection_attempts(self) -> int:
        return self._connection_attempts

    @property
    def has_running_task(self) -> bool:
        return self._runner_task is not None and not self._runner_task.done()
