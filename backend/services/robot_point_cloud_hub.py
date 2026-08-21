from __future__ import annotations

import asyncio
from dataclasses import dataclass
from threading import RLock
from typing import Any

from backend.schemas.robot_point_cloud_schema import local_point_cloud_error


@dataclass
class RobotPointCloudSubscription:
    subscription_id: int
    control_queue: asyncio.Queue[dict[str, Any] | None]
    frame_queue: asyncio.Queue[dict[str, Any] | None]
    loop: asyncio.AbstractEventLoop
    dropped_frames: int = 0
    slow_notified: bool = False


class RobotPointCloudHub:
    """Latest-only point-cloud fan-out isolated from normal robot events."""

    def __init__(self, *, control_queue_size: int = 8) -> None:
        self.control_queue_size = max(2, control_queue_size)
        self._lock = RLock()
        self._subscriptions: dict[int, RobotPointCloudSubscription] = {}
        self._next_subscription_id = 0
        self._latest_stream_info: dict[str, Any] | None = None
        self._latest_frame: dict[str, Any] | None = None
        self._closed = False

    def subscribe(self) -> RobotPointCloudSubscription:
        loop = asyncio.get_running_loop()
        with self._lock:
            if self._closed:
                raise RuntimeError("robot point-cloud hub is closed")
            self._next_subscription_id += 1
            subscription = RobotPointCloudSubscription(
                subscription_id=self._next_subscription_id,
                control_queue=asyncio.Queue(maxsize=self.control_queue_size),
                frame_queue=asyncio.Queue(maxsize=1),
                loop=loop,
            )
            self._subscriptions[subscription.subscription_id] = subscription
            return subscription

    def unsubscribe(self, subscription: RobotPointCloudSubscription) -> None:
        with self._lock:
            self._subscriptions.pop(subscription.subscription_id, None)

    def snapshot(self) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        with self._lock:
            return self._latest_stream_info, self._latest_frame

    def publish_stream_info(self, message: dict[str, Any]) -> None:
        with self._lock:
            self._latest_stream_info = message
            subscriptions = list(self._subscriptions.values())
        for subscription in subscriptions:
            subscription.loop.call_soon_threadsafe(
                self._offer_control, subscription.control_queue, message
            )

    def publish_frame(self, message: dict[str, Any]) -> None:
        with self._lock:
            self._latest_frame = message
            subscriptions = list(self._subscriptions.values())
        for subscription in subscriptions:
            subscription.loop.call_soon_threadsafe(self._offer_frame, subscription, message)

    def publish_error(self, code: str, message: str) -> dict[str, Any]:
        payload = local_point_cloud_error(code, message)
        self.publish_control(payload)
        return payload

    def publish_control(self, message: dict[str, Any]) -> None:
        with self._lock:
            subscriptions = list(self._subscriptions.values())
        for subscription in subscriptions:
            subscription.loop.call_soon_threadsafe(
                self._offer_control, subscription.control_queue, message
            )

    def mark_frame_consumed(self, subscription: RobotPointCloudSubscription) -> None:
        subscription.slow_notified = False

    def close(self) -> None:
        with self._lock:
            self._closed = True
            subscriptions = list(self._subscriptions.values())
            self._subscriptions.clear()
            self._latest_stream_info = None
            self._latest_frame = None
        for subscription in subscriptions:
            subscription.loop.call_soon_threadsafe(
                self._offer_control, subscription.control_queue, None
            )

    @staticmethod
    def _offer_control(
        queue: asyncio.Queue[dict[str, Any] | None], message: dict[str, Any] | None
    ) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            pass

    @classmethod
    def _offer_frame(
        cls, subscription: RobotPointCloudSubscription, message: dict[str, Any]
    ) -> None:
        if subscription.frame_queue.full():
            try:
                subscription.frame_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            subscription.dropped_frames += 1
            if not subscription.slow_notified:
                cls._offer_control(
                    subscription.control_queue,
                    local_point_cloud_error(
                        "POINT_CLOUD_CLIENT_TOO_SLOW",
                        "客户端处理较慢，已丢弃旧点云帧并保留最新帧",
                    ),
                )
                subscription.slow_notified = True
        try:
            subscription.frame_queue.put_nowait(message)
        except asyncio.QueueFull:
            pass

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscriptions)

    @property
    def cached_frame_count(self) -> int:
        with self._lock:
            return int(self._latest_frame is not None)
