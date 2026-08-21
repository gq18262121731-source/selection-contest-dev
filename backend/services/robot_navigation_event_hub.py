from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Literal


RobotChannel = Literal["status", "navigation", "emergency"]


@dataclass(frozen=True)
class RobotEventSubscription:
    subscription_id: int
    channel: RobotChannel
    queue: asyncio.Queue[dict[str, Any] | None]
    loop: asyncio.AbstractEventLoop
    incident_id: str | None = None


class RobotNavigationEventHub:
    """Bounded local fan-out for robot snapshots and incremental events."""

    def __init__(self, *, queue_size: int = 32) -> None:
        if queue_size < 1:
            raise ValueError("queue_size must be positive")
        self.queue_size = queue_size
        self._lock = RLock()
        self._subscriptions: dict[int, RobotEventSubscription] = {}
        self._next_subscription_id = 0
        self._sequence = 0
        self._closed = False

    def subscribe(self, channel: RobotChannel, *, incident_id: str | None = None) -> RobotEventSubscription:
        if channel == "emergency" and not incident_id:
            raise ValueError("incident_id is required for emergency subscriptions")
        loop = asyncio.get_running_loop()
        with self._lock:
            if self._closed:
                raise RuntimeError("robot navigation event hub is closed")
            self._next_subscription_id += 1
            subscription = RobotEventSubscription(
                subscription_id=self._next_subscription_id,
                channel=channel,
                incident_id=incident_id,
                queue=asyncio.Queue(maxsize=self.queue_size),
                loop=loop,
            )
            self._subscriptions[subscription.subscription_id] = subscription
            return subscription

    def unsubscribe(self, subscription: RobotEventSubscription) -> None:
        with self._lock:
            self._subscriptions.pop(subscription.subscription_id, None)

    def publish(
        self,
        event_type: str,
        data: dict[str, Any],
        *,
        channels: tuple[RobotChannel, ...] = ("navigation", "status"),
        incident_id: str | None = None,
        upstream_sequence: int | None = None,
    ) -> dict[str, Any]:
        event = self.make_event(
            event_type,
            data,
            upstream_sequence=upstream_sequence,
        )
        with self._lock:
            subscriptions = [
                item
                for item in self._subscriptions.values()
                if item.channel in channels
                and (
                    item.channel != "emergency"
                    or (incident_id is not None and item.incident_id == incident_id)
                )
            ]
        for subscription in subscriptions:
            subscription.loop.call_soon_threadsafe(self._offer_latest, subscription.queue, event)
        return event

    def make_event(
        self,
        event_type: str,
        data: dict[str, Any],
        *,
        upstream_sequence: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._sequence += 1
            sequence = self._sequence
        payload: dict[str, Any] = {
            "type": event_type,
            "sequence": sequence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": "mock",
            "real_motion_enabled": False,
            "data": data,
        }
        if upstream_sequence is not None:
            payload["upstream_sequence"] = upstream_sequence
        return payload

    def close(self) -> None:
        with self._lock:
            self._closed = True
            subscriptions = list(self._subscriptions.values())
            self._subscriptions.clear()
        for subscription in subscriptions:
            subscription.loop.call_soon_threadsafe(self._offer_latest, subscription.queue, None)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscriptions)

    def channel_subscriber_count(self, channel: RobotChannel) -> int:
        with self._lock:
            return sum(item.channel == channel for item in self._subscriptions.values())

    @property
    def current_sequence(self) -> int:
        with self._lock:
            return self._sequence

    @staticmethod
    def _offer_latest(
        queue: asyncio.Queue[dict[str, Any] | None],
        event: dict[str, Any] | None,
    ) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass
