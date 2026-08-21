from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class WebSocketManager:
    """Simple in-memory websocket registry for health streams and alarms."""

    @staticmethod
    def _normalize_mac(device_mac: str) -> str:
        compact = "".join(ch for ch in device_mac if ch.isalnum()).upper()
        if len(compact) == 12:
            return ":".join(compact[i : i + 2] for i in range(0, 12, 2))
        return device_mac.upper()

    def __init__(self) -> None:
        self._health_channels: dict[str, set[WebSocket]] = defaultdict(set)
        self._alarm_channels: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect_health(self, device_mac: str, websocket: WebSocket) -> None:
        normalized = self._normalize_mac(device_mac)
        await websocket.accept()
        async with self._lock:
            self._health_channels[normalized].add(websocket)

    async def disconnect_health(self, device_mac: str, websocket: WebSocket) -> None:
        normalized = self._normalize_mac(device_mac)
        async with self._lock:
            self._health_channels[normalized].discard(websocket)

    async def connect_alarm(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._alarm_channels.add(websocket)

    async def disconnect_alarm(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._alarm_channels.discard(websocket)

    async def broadcast_health(self, device_mac: str, payload: dict[str, Any]) -> None:
        normalized = self._normalize_mac(device_mac)
        sockets = list(self._health_channels.get(normalized, set()))
        for socket in sockets:
            try:
                await socket.send_json(payload)
            except Exception:
                await self.disconnect_health(device_mac, socket)

    async def broadcast_alarm(self, payload: dict[str, Any]) -> None:
        sockets = list(self._alarm_channels)
        for socket in sockets:
            try:
                await socket.send_json(payload)
            except Exception:
                await self.disconnect_alarm(socket)

    async def broadcast_alarm_queue(self, payload: dict[str, Any]) -> None:
        sockets = list(self._alarm_channels)
        for socket in sockets:
            try:
                await socket.send_json(payload)
            except Exception:
                await self.disconnect_alarm(socket)

    async def broadcast_robot_event(self, payload: dict[str, Any]) -> None:
        sockets = list(self._alarm_channels)
        for socket in sockets:
            try:
                await socket.send_json(payload)
            except Exception:
                await self.disconnect_alarm(socket)
