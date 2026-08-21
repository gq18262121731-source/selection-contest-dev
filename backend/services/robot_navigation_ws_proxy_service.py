from __future__ import annotations

import asyncio
import inspect
import json
from contextlib import suppress
from typing import Any, Callable
from urllib.parse import urlparse, urlunparse

import websockets

from backend.services.robot_navigation_event_hub import RobotNavigationEventHub
from backend.services.robot_navigation_gateway_service import RobotNavigationGatewayService


class RobotNavigationWsProxyService:
    """Shares one validated upstream Mock navigation WebSocket connection."""

    def __init__(
        self,
        gateway_service: RobotNavigationGatewayService,
        event_hub: RobotNavigationEventHub,
        *,
        disconnect_grace_seconds: float = 0.2,
        retry_initial_seconds: float = 0.1,
        retry_max_seconds: float = 2.0,
        connector: Callable[[str], Any] | None = None,
    ) -> None:
        self.gateway = gateway_service
        self.event_hub = event_hub
        self.disconnect_grace_seconds = max(0.0, disconnect_grace_seconds)
        self.retry_initial_seconds = max(0.01, retry_initial_seconds)
        self.retry_max_seconds = max(self.retry_initial_seconds, retry_max_seconds)
        self._connector = connector or websockets.connect
        self._lock = asyncio.Lock()
        self._subscriber_count = 0
        self._runner_task: asyncio.Task[None] | None = None
        self._delayed_stop_task: asyncio.Task[None] | None = None
        self._closed = False
        self._connection_attempts = 0
        self._active_upstream_connections = 0

    async def acquire(self) -> None:
        async with self._lock:
            if self._closed:
                raise RuntimeError("navigation websocket proxy is closed")
            self._subscriber_count += 1
            if self._delayed_stop_task:
                self._delayed_stop_task.cancel()
                self._delayed_stop_task = None
            if self._runner_task is None or self._runner_task.done():
                self._runner_task = asyncio.create_task(self._run(), name="robot-navigation-upstream-ws")

    async def release(self) -> None:
        async with self._lock:
            self._subscriber_count = max(0, self._subscriber_count - 1)
            if self._subscriber_count == 0 and self._runner_task and not self._runner_task.done():
                if self._delayed_stop_task is None or self._delayed_stop_task.done():
                    self._delayed_stop_task = asyncio.create_task(self._stop_after_grace())

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

    async def _stop_after_grace(self) -> None:
        try:
            await asyncio.sleep(self.disconnect_grace_seconds)
            async with self._lock:
                if self._subscriber_count == 0 and self._runner_task:
                    self._runner_task.cancel()
        except asyncio.CancelledError:
            raise

    async def _run(self) -> None:
        retry_delay = self.retry_initial_seconds
        try:
            while not self._closed and self._subscriber_count > 0:
                try:
                    await self._publish_rest_resync()
                    self._connection_attempts += 1
                    connection = self._connector(self._upstream_url())
                    if inspect.isawaitable(connection):
                        connection = await connection
                    async with connection as websocket:
                        self._active_upstream_connections = 1
                        retry_delay = self.retry_initial_seconds
                        async for raw_message in websocket:
                            payload = self._validate_message(raw_message)
                            self.event_hub.publish(
                                str(payload["type"]),
                                dict(payload["data"]),
                                channels=("navigation", "status"),
                                upstream_sequence=int(payload["sequence"]),
                            )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.event_hub.publish(
                        "navigation_upstream_error",
                        {"code": self._error_code(exc), "message": str(exc)},
                        channels=("navigation", "status"),
                    )
                    if self._subscriber_count <= 0 or self._closed:
                        break
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(self.retry_max_seconds, retry_delay * 2)
                finally:
                    self._active_upstream_connections = 0
        finally:
            self._active_upstream_connections = 0

    async def _publish_rest_resync(self) -> None:
        result = await asyncio.to_thread(self.gateway.state)
        self.event_hub.publish(
            "navigation_snapshot",
            result.data,
            channels=("navigation", "status"),
        )

    @staticmethod
    def _validate_message(raw_message: Any) -> dict[str, Any]:
        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode("utf-8")
        payload = json.loads(raw_message) if isinstance(raw_message, str) else raw_message
        if not isinstance(payload, dict):
            raise ValueError("ROBOT_GATEWAY_INVALID_RESPONSE")
        required = {"type", "sequence", "timestamp", "data", "provider", "real_motion_enabled"}
        if not required.issubset(payload) or not isinstance(payload["data"], dict):
            raise ValueError("ROBOT_GATEWAY_INVALID_RESPONSE")
        if payload["provider"] != "mock":
            raise ValueError("MOCK_PROVIDER_CONTRACT_VIOLATION")
        if payload["real_motion_enabled"] is not False:
            raise ValueError("REAL_MOTION_DISABLED")
        if not isinstance(payload["sequence"], int) or payload["sequence"] < 1:
            raise ValueError("ROBOT_GATEWAY_INVALID_RESPONSE")
        return payload

    def _upstream_url(self) -> str:
        parsed = urlparse(self.gateway.base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        return urlunparse((scheme, parsed.netloc, "/ws/navigation/state", "", "", ""))

    @staticmethod
    def _error_code(exc: Exception) -> str:
        message = str(exc)
        for code in (
            "MOCK_PROVIDER_CONTRACT_VIOLATION",
            "REAL_MOTION_DISABLED",
            "ROBOT_GATEWAY_INVALID_RESPONSE",
        ):
            if code in message:
                return code
        return "ROBOT_GATEWAY_UNAVAILABLE"

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
