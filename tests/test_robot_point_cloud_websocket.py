from __future__ import annotations

import asyncio
import json
import math
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.robot_point_cloud_ws import router
from backend.services.robot_navigation_event_hub import RobotNavigationEventHub
from backend.services.robot_point_cloud_hub import RobotPointCloudHub
from backend.services.robot_point_cloud_ws_proxy_service import RobotPointCloudWsProxyService


def stream_info(*, max_points: int = 4) -> dict:
    return {
        "type": "point_cloud_stream_info",
        "provider": "mock",
        "real_motion_enabled": False,
        "frame_id": "mock_lidar",
        "coordinate_frame": "map",
        "encoding": "json_xyz_intensity_v1",
        "target_fps": 5,
        "max_points": max_points,
        "queue_size": 2,
        "scenario": "classroom_default",
        "stream_status": "ready",
        "timestamp": "2026-07-23T10:00:00+08:00",
    }


def point_cloud_frame(sequence: int = 1, *, points: list | None = None) -> dict:
    values = points if points is not None else [[1.2, 0.4, 0.1, 0.72]]
    return {
        "type": "point_cloud_frame",
        "sequence": sequence,
        "timestamp": "2026-07-23T10:00:01+08:00",
        "provider": "mock",
        "real_motion_enabled": False,
        "frame_id": "mock_lidar",
        "coordinate_frame": "map",
        "scenario": "classroom_default",
        "point_count": len(values),
        "points": values,
        "robot_pose": {"x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0},
        "target_pose": None,
        "navigation_state": "idle",
        "control_owner": "NONE",
    }


class FakeUpstreamConnection:
    def __init__(self, messages=None, *, block_when_empty: bool = True):
        self.messages = list(messages or [])
        self.block_when_empty = block_when_empty
        self.sent: list[dict] = []
        self.closed = False
        self._blocker = asyncio.Event()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.messages:
            return json.dumps(self.messages.pop(0), allow_nan=True)
        if not self.block_when_empty:
            raise StopAsyncIteration
        await self._blocker.wait()
        raise StopAsyncIteration

    async def send(self, raw_message: str):
        self.sent.append(json.loads(raw_message))


async def wait_until(predicate, *, timeout: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    assert predicate()


def test_valid_upstream_info_and_frame_are_forwarded_without_point_rewrite():
    async def exercise():
        info = stream_info()
        frame = point_cloud_frame()
        connection = FakeUpstreamConnection([info, frame])
        urls = []

        def connector(url):
            urls.append(url)
            assert url == "ws://mock-gateway/ws/navigation/point-cloud"
            return connection

        hub = RobotPointCloudHub()
        proxy = RobotPointCloudWsProxyService("http://mock-gateway", hub, connector=connector)
        await proxy.acquire()
        await wait_until(lambda: hub.snapshot()[1] is not None)
        cached_info, cached_frame = hub.snapshot()
        assert cached_info["provider"] == "mock"
        assert cached_info["real_motion_enabled"] is False
        assert cached_frame["points"] == frame["points"]
        assert cached_frame["point_count"] == len(frame["points"])
        assert cached_frame["upstream_sequence"] == frame["sequence"]
        assert len(urls) == 1
        await proxy.close()
        assert proxy.has_running_task is False

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda frame: frame.update(provider="real"), "MOCK_PROVIDER_CONTRACT_VIOLATION"),
        (lambda frame: frame.update(real_motion_enabled=True), "REAL_MOTION_DISABLED"),
        (lambda frame: frame.update(point_count=2), "POINT_CLOUD_FRAME_INVALID"),
        (lambda frame: frame.update(points=[[math.nan, 0, 0, 1]]), "POINT_CLOUD_FRAME_INVALID"),
        (lambda frame: frame.update(point_count=5, points=[[0, 0, 0, 1]] * 5), "POINT_CLOUD_FRAME_INVALID"),
        (lambda frame: frame["robot_pose"].update(y=math.inf), "POINT_CLOUD_FRAME_INVALID"),
    ],
)
def test_invalid_upstream_frame_is_rejected_without_poisoning_latest_cache(mutate, expected_code):
    async def exercise():
        valid = point_cloud_frame(1)
        invalid = point_cloud_frame(2)
        mutate(invalid)
        connection = FakeUpstreamConnection([stream_info(max_points=4), valid, invalid])
        hub = RobotPointCloudHub(control_queue_size=16)
        subscription = hub.subscribe()
        proxy = RobotPointCloudWsProxyService("http://mock-gateway", hub, connector=lambda _: connection)
        await proxy.acquire()
        await wait_until(lambda: hub.snapshot()[1] is not None)
        await asyncio.sleep(0.03)
        assert hub.snapshot()[1]["sequence"] == 1
        errors = []
        while not subscription.control_queue.empty():
            message = subscription.control_queue.get_nowait()
            if message and message.get("type") == "error":
                errors.append(message)
        assert any(message["code"] == expected_code for message in errors)
        assert all(message["provider"] == "mock" for message in errors)
        await proxy.close()
        hub.unsubscribe(subscription)

    asyncio.run(exercise())


def test_invalid_stream_encoding_prevents_frame_from_becoming_ready():
    async def exercise():
        info = stream_info()
        info["encoding"] = "binary_real_lidar"
        connection = FakeUpstreamConnection([info, point_cloud_frame()])
        hub = RobotPointCloudHub(control_queue_size=16)
        subscription = hub.subscribe()
        proxy = RobotPointCloudWsProxyService("http://mock-gateway", hub, connector=lambda _: connection)
        await proxy.acquire()
        await asyncio.sleep(0.05)
        assert hub.snapshot() == (None, None)
        codes = []
        while not subscription.control_queue.empty():
            message = subscription.control_queue.get_nowait()
            if message and message.get("type") == "error":
                codes.append(message["code"])
        assert "ROBOT_POINT_CLOUD_INVALID_MESSAGE" in codes
        assert "POINT_CLOUD_PROXY_NOT_READY" in codes
        await proxy.close()
        hub.unsubscribe(subscription)

    asyncio.run(exercise())


def test_upstream_ping_is_answered_but_not_forwarded_as_point_cloud():
    async def exercise():
        ping = {
            "type": "ping",
            "timestamp": "2026-07-23T10:00:02+08:00",
            "provider": "mock",
            "real_motion_enabled": False,
        }
        connection = FakeUpstreamConnection([stream_info(), ping, point_cloud_frame()])
        hub = RobotPointCloudHub()
        proxy = RobotPointCloudWsProxyService("http://mock-gateway", hub, connector=lambda _: connection)
        await proxy.acquire()
        await wait_until(lambda: hub.snapshot()[1] is not None)
        assert {"type": "pong"} in connection.sent
        await proxy.close()

    asyncio.run(exercise())


def test_multiple_subscribers_share_one_upstream_and_last_release_stops_it():
    async def exercise():
        connections = []

        def connector(_):
            connection = FakeUpstreamConnection([stream_info(), point_cloud_frame()])
            connections.append(connection)
            return connection

        proxy = RobotPointCloudWsProxyService(
            "http://mock-gateway",
            RobotPointCloudHub(),
            connector=connector,
            disconnect_grace_seconds=0.02,
        )
        await proxy.acquire()
        await proxy.acquire()
        await wait_until(lambda: proxy.active_upstream_connections == 1)
        assert len(connections) == 1
        await proxy.release()
        assert proxy.has_running_task is True
        await proxy.release()
        await asyncio.sleep(0.05)
        assert proxy.has_running_task is False
        assert connections[0].closed is True
        await proxy.close()

    asyncio.run(exercise())


def test_new_subscriber_inside_disconnect_grace_reuses_connection():
    async def exercise():
        connections = []

        def connector(_):
            connection = FakeUpstreamConnection([stream_info(), point_cloud_frame()])
            connections.append(connection)
            return connection

        proxy = RobotPointCloudWsProxyService(
            "http://mock-gateway",
            RobotPointCloudHub(),
            connector=connector,
            disconnect_grace_seconds=0.08,
        )
        await proxy.acquire()
        await wait_until(lambda: proxy.active_upstream_connections == 1)
        await proxy.release()
        await asyncio.sleep(0.02)
        await proxy.acquire()
        await asyncio.sleep(0.02)
        assert len(connections) == 1
        assert proxy.active_upstream_connections == 1
        await proxy.release()
        await proxy.close()

    asyncio.run(exercise())


def test_slow_client_drops_old_frame_while_fast_client_keeps_receiving():
    async def exercise():
        hub = RobotPointCloudHub()
        slow = hub.subscribe()
        fast = hub.subscribe()
        hub.publish_frame(point_cloud_frame(1))
        await asyncio.sleep(0)
        first_fast = await fast.frame_queue.get()
        hub.mark_frame_consumed(fast)
        assert first_fast["sequence"] == 1
        hub.publish_frame(point_cloud_frame(2))
        await asyncio.sleep(0)
        second_fast = await fast.frame_queue.get()
        hub.mark_frame_consumed(fast)
        assert second_fast["sequence"] == 2
        hub.publish_frame(point_cloud_frame(3))
        await asyncio.sleep(0)
        third_fast = await fast.frame_queue.get()
        assert third_fast["sequence"] == 3
        assert (await slow.frame_queue.get())["sequence"] == 3
        slow_error = await slow.control_queue.get()
        assert slow_error["code"] == "POINT_CLOUD_CLIENT_TOO_SLOW"
        assert slow.dropped_frames == 2
        assert hub.cached_frame_count == 1
        assert hub.snapshot()[1]["sequence"] == 3
        hub.unsubscribe(slow)
        hub.unsubscribe(fast)

    asyncio.run(exercise())


def test_control_messages_are_not_squeezed_out_by_large_frames():
    async def exercise():
        hub = RobotPointCloudHub()
        subscription = hub.subscribe()
        hub.publish_frame(point_cloud_frame(1))
        hub.publish_frame(point_cloud_frame(2))
        hub.publish_error("ROBOT_POINT_CLOUD_UPSTREAM_UNAVAILABLE", "offline")
        await asyncio.sleep(0)
        assert (await subscription.frame_queue.get())["sequence"] == 2
        controls = [subscription.control_queue.get_nowait() for _ in range(subscription.control_queue.qsize())]
        assert any(item["code"] == "ROBOT_POINT_CLOUD_UPSTREAM_UNAVAILABLE" for item in controls)
        hub.unsubscribe(subscription)

    asyncio.run(exercise())


def test_two_clients_receive_same_frame_and_one_disconnect_does_not_affect_other():
    async def exercise():
        hub = RobotPointCloudHub()
        first = hub.subscribe()
        second = hub.subscribe()
        hub.publish_frame(point_cloud_frame(1))
        await asyncio.sleep(0)
        assert (await first.frame_queue.get())["sequence"] == 1
        assert (await second.frame_queue.get())["sequence"] == 1
        hub.mark_frame_consumed(first)
        hub.unsubscribe(second)
        hub.publish_frame(point_cloud_frame(2))
        await asyncio.sleep(0)
        assert (await first.frame_queue.get())["sequence"] == 2
        assert hub.subscriber_count == 1
        hub.unsubscribe(first)

    asyncio.run(exercise())


def test_structured_upstream_error_is_forwarded_and_later_frame_still_arrives():
    async def exercise():
        upstream_error = {
            "type": "error",
            "code": "POINT_CLOUD_STREAM_UNAVAILABLE",
            "message": "mock stream temporarily unavailable",
            "provider": "mock",
            "real_motion_enabled": False,
            "timestamp": "2026-07-23T10:00:02+08:00",
        }
        connection = FakeUpstreamConnection(
            [stream_info(), upstream_error, point_cloud_frame(2)]
        )
        hub = RobotPointCloudHub(control_queue_size=16)
        subscription = hub.subscribe()
        proxy = RobotPointCloudWsProxyService(
            "http://mock-gateway", hub, connector=lambda _: connection
        )
        await proxy.acquire()
        await wait_until(lambda: hub.snapshot()[1] is not None)
        assert hub.snapshot()[1]["sequence"] == 2
        controls = [
            subscription.control_queue.get_nowait()
            for _ in range(subscription.control_queue.qsize())
        ]
        assert any(
            message.get("code") == "POINT_CLOUD_STREAM_UNAVAILABLE"
            for message in controls
        )
        await proxy.close()
        hub.unsubscribe(subscription)

    asyncio.run(exercise())


def test_upstream_disconnect_reconnects_sends_sync_and_recovers_latest_frame():
    async def exercise():
        first = FakeUpstreamConnection(
            [stream_info(), point_cloud_frame(1)], block_when_empty=False
        )
        second = FakeUpstreamConnection([stream_info(), point_cloud_frame(2)])
        connections = [first, second]
        calls = []

        def connector(_):
            calls.append(len(calls))
            return connections[min(len(calls) - 1, 1)]

        hub = RobotPointCloudHub(control_queue_size=16)
        subscription = hub.subscribe()
        proxy = RobotPointCloudWsProxyService(
            "http://mock-gateway",
            hub,
            connector=connector,
            retry_initial_seconds=0.01,
            retry_max_seconds=0.02,
        )
        await proxy.acquire()
        await wait_until(lambda: hub.snapshot()[1] is not None and hub.snapshot()[1]["sequence"] == 2)
        assert proxy.connection_attempts >= 2
        assert {"type": "sync"} in second.sent
        controls = []
        while not subscription.control_queue.empty():
            controls.append(subscription.control_queue.get_nowait())
        assert any(item.get("connection_state") == "disconnected" for item in controls)
        assert proxy.active_upstream_connections == 1
        await proxy.close()
        hub.unsubscribe(subscription)
        assert proxy.has_running_task is False

    asyncio.run(exercise())


def test_timeout_is_structured_and_does_not_close_local_hub():
    async def exercise():
        hub = RobotPointCloudHub(control_queue_size=16)
        subscription = hub.subscribe()

        def connector(_):
            raise asyncio.TimeoutError()

        proxy = RobotPointCloudWsProxyService(
            "http://mock-gateway", hub, connector=connector, retry_initial_seconds=1
        )
        await proxy.acquire()
        await wait_until(lambda: subscription.control_queue.qsize() >= 3)
        messages = [subscription.control_queue.get_nowait() for _ in range(subscription.control_queue.qsize())]
        assert any(item.get("code") == "ROBOT_POINT_CLOUD_UPSTREAM_TIMEOUT" for item in messages)
        assert hub.subscriber_count == 1
        await proxy.close()
        hub.unsubscribe(subscription)

    asyncio.run(exercise())


class PublishingProxy:
    def __init__(self, hub: RobotPointCloudHub):
        self.hub = hub
        self.acquires = 0
        self.releases = 0
        self.syncs = 0

    async def acquire(self):
        self.acquires += 1
        if self.hub.snapshot()[0] is None:
            self.hub.publish_stream_info(stream_info())
            self.hub.publish_frame(point_cloud_frame())

    async def release(self):
        self.releases += 1

    async def request_sync(self):
        self.syncs += 1
        return True


def build_websocket_client(*, prefill: bool = False):
    hub = RobotPointCloudHub()
    if prefill:
        hub.publish_stream_info(stream_info())
        hub.publish_frame(point_cloud_frame())
    proxy = PublishingProxy(hub)
    app = FastAPI()
    app.state.robot_point_cloud_hub = hub
    app.state.robot_point_cloud_ws_proxy_service = proxy
    app.include_router(router)
    return TestClient(app), hub, proxy


def receive_until_type(websocket, message_type: str, limit: int = 10):
    for _ in range(limit):
        message = websocket.receive_json()
        if message.get("type") == message_type:
            return message
    raise AssertionError(f"did not receive {message_type}")


def test_local_websocket_sends_cached_info_then_latest_frame_and_sync_replays_both():
    client, _, proxy = build_websocket_client(prefill=True)
    with client.websocket_connect("/ws/robot/point-cloud") as websocket:
        info = websocket.receive_json()
        frame = websocket.receive_json()
        assert info["type"] == "point_cloud_stream_info"
        assert frame["type"] == "point_cloud_frame"
        assert frame["provider"] == "mock" and frame["real_motion_enabled"] is False
        websocket.send_json({"type": "sync"})
        assert websocket.receive_json()["type"] == "point_cloud_stream_info"
        assert websocket.receive_json()["type"] == "point_cloud_frame"
        assert proxy.syncs == 1
    assert proxy.acquires == 1 and proxy.releases == 1


def test_local_websocket_receives_new_stream_and_frame_and_reconnect_gets_cache_first():
    client, _, proxy = build_websocket_client()
    with client.websocket_connect("/ws/robot/point-cloud") as first:
        info = receive_until_type(first, "point_cloud_stream_info")
        frame = receive_until_type(first, "point_cloud_frame")
        assert info["provider"] == "mock"
        assert frame["point_count"] == len(frame["points"])
    with client.websocket_connect("/ws/robot/point-cloud") as second:
        assert second.receive_json()["type"] == "point_cloud_stream_info"
        assert second.receive_json()["type"] == "point_cloud_frame"
    assert proxy.acquires == 2 and proxy.releases == 2


def test_local_client_cannot_upload_or_override_point_cloud_state():
    client, hub, _ = build_websocket_client(prefill=True)
    original = deepcopy(hub.snapshot())
    with client.websocket_connect("/ws/robot/point-cloud") as websocket:
        websocket.receive_json()
        websocket.receive_json()
        websocket.send_json(
            {
                "type": "point_cloud_frame",
                "points": [[9, 9, 9, 9]],
                "provider": "real",
                "real_motion_enabled": True,
                "cmd_vel": 1,
            }
        )
        error = websocket.receive_json()
        assert error["type"] == "error"
        assert error["code"] == "ROBOT_POINT_CLOUD_INVALID_MESSAGE"
    assert hub.snapshot() == original


def test_point_cloud_hub_is_isolated_from_navigation_hub_and_sqlite():
    async def exercise():
        navigation_hub = RobotNavigationEventHub()
        navigation_subscription = navigation_hub.subscribe("navigation")
        point_cloud_hub = RobotPointCloudHub()
        point_cloud_hub.publish_frame(point_cloud_frame())
        await asyncio.sleep(0)
        assert navigation_subscription.queue.empty()
        assert point_cloud_hub.cached_frame_count == 1
        navigation_hub.unsubscribe(navigation_subscription)

    asyncio.run(exercise())
    sources = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in (
            "backend/services/robot_point_cloud_hub.py",
            "backend/services/robot_point_cloud_ws_proxy_service.py",
            "backend/api/robot_point_cloud_ws.py",
        )
    )
    assert "sqlite" not in sources.lower()
    assert "robot_navigation_event_hub" not in sources.lower()


def test_new_point_cloud_modules_have_no_real_robot_or_motion_path():
    sources = "\n".join(
        Path(path).read_text(encoding="utf-8").lower()
        for path in (
            "backend/schemas/robot_point_cloud_schema.py",
            "backend/services/robot_point_cloud_hub.py",
            "backend/services/robot_point_cloud_ws_proxy_service.py",
            "backend/api/robot_point_cloud_ws.py",
        )
    )
    for forbidden in (
        "192.168.",
        "8093",
        "unitree",
        "cyclonedds",
        "rclpy",
        "cmd_vel",
        "robot_service.move",
        "adapter.move",
    ):
        assert forbidden not in sources
    assert "logger" not in sources


def test_hub_and_proxy_close_clear_subscribers_cache_and_tasks():
    async def exercise():
        hub = RobotPointCloudHub()
        subscription = hub.subscribe()
        hub.publish_stream_info(stream_info())
        hub.publish_frame(point_cloud_frame())
        proxy = RobotPointCloudWsProxyService(
            "http://mock-gateway",
            hub,
            connector=lambda _: FakeUpstreamConnection([stream_info(), point_cloud_frame()]),
        )
        await proxy.acquire()
        await wait_until(lambda: proxy.active_upstream_connections == 1)
        await proxy.close()
        hub.close()
        await asyncio.sleep(0)
        assert proxy.has_running_task is False
        assert proxy.subscriber_count == 0
        assert hub.subscriber_count == 0
        assert hub.snapshot() == (None, None)
        controls = [
            subscription.control_queue.get_nowait()
            for _ in range(subscription.control_queue.qsize())
        ]
        assert controls[-1] is None

    asyncio.run(exercise())
