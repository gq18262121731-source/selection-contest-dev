from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.robot_navigation_ws import router
from backend.services.robot_navigation_errors import RobotNavigationErrorCode, RobotNavigationServiceError
from backend.services.robot_navigation_event_hub import RobotNavigationEventHub
from backend.services.robot_navigation_gateway_service import RobotNavigationGatewayResult
from backend.services.robot_navigation_ws_proxy_service import RobotNavigationWsProxyService
from test_robot_navigation_api import activate_map, add_navigation_points, build_service


class SnapshotService:
    def status_snapshot(self):
        return {"provider": "mock", "real_motion_enabled": False, "status": "mock"}

    def navigation_snapshot(self):
        return {"provider": "mock", "real_motion_enabled": False, "execution_state": "created"}

    def emergency_bundle(self, incident_id):
        if incident_id == "missing":
            raise RobotNavigationServiceError(RobotNavigationErrorCode.INCIDENT_NOT_FOUND, "应急案例不存在")
        return {"provider": "mock", "real_motion_enabled": False, "incident_id": incident_id}


class LocalProxy:
    def __init__(self):
        self.acquire_calls = 0
        self.release_calls = 0
        self.active = 0

    async def acquire(self):
        self.acquire_calls += 1
        self.active += 1

    async def release(self):
        self.release_calls += 1
        self.active -= 1


def build_ws_client():
    app = FastAPI()
    app.include_router(router)
    hub = RobotNavigationEventHub(queue_size=4)
    proxy = LocalProxy()
    app.state.robot_navigation_application_service = SnapshotService()
    app.state.robot_navigation_event_hub = hub
    app.state.robot_navigation_ws_proxy_service = proxy
    return TestClient(app), hub, proxy


def test_status_websocket_sends_snapshot_before_incremental_event():
    client, hub, proxy = build_ws_client()
    with client.websocket_connect("/ws/robot/status") as websocket:
        snapshot = websocket.receive_json()
        assert snapshot["type"] == "robot_status_snapshot"
        assert snapshot["provider"] == "mock" and snapshot["real_motion_enabled"] is False
        hub.publish("task_paused", {"task_id": "task_1"}, channels=("status",))
        event = websocket.receive_json()
        assert event["type"] == "task_paused"
        assert event["sequence"] > snapshot["sequence"]
    assert proxy.acquire_calls == 1 and proxy.release_calls == 1 and proxy.active == 0


def test_navigation_websocket_reconnect_starts_with_fresh_snapshot():
    client, _, proxy = build_ws_client()
    with client.websocket_connect("/ws/robot/navigation") as first:
        first_snapshot = first.receive_json()
    with client.websocket_connect("/ws/robot/navigation") as second:
        second_snapshot = second.receive_json()
    assert first_snapshot["type"] == second_snapshot["type"] == "navigation_snapshot"
    assert second_snapshot["sequence"] > first_snapshot["sequence"]
    assert proxy.acquire_calls == 2 and proxy.release_calls == 2


def test_sync_message_returns_new_snapshot():
    client, _, _ = build_ws_client()
    with client.websocket_connect("/ws/robot/navigation") as websocket:
        first = websocket.receive_json()
        websocket.send_json({"type": "sync"})
        synced = websocket.receive_json()
    assert synced["type"] == "navigation_snapshot"
    assert synced["sequence"] > first["sequence"]


def test_two_navigation_clients_receive_same_event_and_disconnect_independently():
    client, hub, proxy = build_ws_client()
    with client.websocket_connect("/ws/robot/navigation") as first:
        first.receive_json()
        with client.websocket_connect("/ws/robot/navigation") as second:
            second.receive_json()
            hub.publish("task_resumed", {"task_id": "task_1"}, channels=("navigation",))
            assert first.receive_json()["type"] == "task_resumed"
            assert second.receive_json()["type"] == "task_resumed"
        assert proxy.active == 1
        hub.publish("task_cancelled", {"task_id": "task_1"}, channels=("navigation",))
        assert first.receive_json()["type"] == "task_cancelled"
    assert proxy.active == 0


def test_rest_operation_publishes_incremental_websocket_event(tmp_path):
    client, service, _ = build_service(tmp_path)
    activate_map(service)
    client.app.include_router(router)
    proxy = LocalProxy()
    client.app.state.robot_navigation_application_service = service
    client.app.state.robot_navigation_event_hub = service.event_hub
    client.app.state.robot_navigation_ws_proxy_service = proxy
    with client.websocket_connect("/ws/robot/navigation") as websocket:
        assert websocket.receive_json()["type"] == "navigation_snapshot"
        response = client.post(
            "/api/v1/robot/navigation/points",
            json={
                "point_id": "rest-point",
                "map_id": "map_active",
                "name": "REST点",
                "point_type": "patrol",
                "x": 1,
                "y": 1,
                "yaw": 0,
                "request_id": "rest-point-op",
            },
        )
        assert response.status_code == 201
        event = websocket.receive_json()
        assert event["type"] == "point_created"
        assert event["data"]["point_id"] == "rest-point"


def test_navigation_websocket_snapshot_matches_rest_effective_safety_fields(tmp_path):
    client, service, _ = build_service(tmp_path)
    activate_map(service)
    client.app.include_router(router)
    client.app.state.robot_navigation_application_service = service
    client.app.state.robot_navigation_event_hub = service.event_hub
    client.app.state.robot_navigation_ws_proxy_service = LocalProxy()
    names = (
        "robot_online",
        "emergency_stop_clear",
        "localization_valid",
        "map_loaded",
        "path_plannable",
        "robot_stationary",
        "control_available",
    )
    rest = client.get("/api/v1/robot/navigation/state").json()["data"]
    with client.websocket_connect("/ws/robot/navigation") as websocket:
        ws = websocket.receive_json()["data"]
    assert {name: ws[name] for name in names} == {name: rest[name] for name in names}
    assert ws["safety_interlock"]["checks"] == rest["safety_interlock"]["checks"]


def test_emergency_websocket_isolates_incidents():
    client, hub, _ = build_ws_client()
    with client.websocket_connect("/ws/robot/emergency/incident_a") as websocket:
        assert websocket.receive_json()["data"]["incident_id"] == "incident_a"
        hub.publish(
            "emergency_dispatched",
            {"incident_id": "incident_b"},
            channels=("emergency",),
            incident_id="incident_b",
        )
        hub.publish(
            "emergency_acknowledged",
            {"incident_id": "incident_a"},
            channels=("emergency",),
            incident_id="incident_a",
        )
        event = websocket.receive_json()
        assert event["type"] == "emergency_acknowledged"
        assert event["data"]["incident_id"] == "incident_a"


def test_mock_dialogue_start_publishes_three_emergency_incremental_events(tmp_path):
    client, service, _ = build_service(tmp_path)
    activate_map(service)
    add_navigation_points(client)
    assert client.post(
        "/api/v1/robot/emergency/ws-dialogue/dispatch",
        json={"area_id": "area_a", "area_name": "A区", "request_id": "ws-dispatch"},
    ).status_code == 201
    client.app.include_router(router)
    client.app.state.robot_navigation_application_service = service
    client.app.state.robot_navigation_event_hub = service.event_hub

    with client.websocket_connect("/ws/robot/emergency/ws-dialogue") as websocket:
        assert websocket.receive_json()["type"] == "emergency_snapshot"
        response = client.post(
            "/api/v1/robot/emergency/ws-dialogue/mock/dialogue/start",
            json={"request_id": "ws-dialogue-start"},
        )
        assert response.status_code == 200
        events = [websocket.receive_json() for _ in range(3)]

    assert [event["type"] for event in events] == [
        "task_arrived",
        "voice_prompting",
        "waiting_response",
    ]
    assert all(event["provider"] == "mock" for event in events)
    assert all(event["real_motion_enabled"] is False for event in events)
    assert all(
        event["data"]["emergency_case"]["execution_state"] == "waiting_response"
        for event in events
    )


def test_mock_return_complete_publishes_completion_events(tmp_path):
    client, service, _ = build_service(tmp_path)
    activate_map(service)
    add_navigation_points(client)
    incident_id = "ws-return"
    assert client.post(
        f"/api/v1/robot/emergency/{incident_id}/dispatch",
        json={"area_id": "area_a", "area_name": "A区", "request_id": "ws-return-dispatch"},
    ).status_code == 201
    assert client.post(
        f"/api/v1/robot/emergency/{incident_id}/mock/dialogue/start",
        json={"request_id": "ws-return-dialogue"},
    ).status_code == 200
    assert client.post(
        f"/api/v1/robot/emergency/{incident_id}/escalate",
        json={"request_id": "ws-return-safe", "turn_id": "ws-turn", "intent": "safe_response"},
    ).status_code == 200
    assert client.post(
        f"/api/v1/robot/emergency/{incident_id}/acknowledge",
        json={"request_id": "ws-return-ack", "admin_id": "admin"},
    ).status_code == 200
    assert client.post(
        f"/api/v1/robot/emergency/{incident_id}/resolve-and-return",
        json={"request_id": "ws-return-start", "resolution": "安全"},
    ).status_code == 200
    client.app.include_router(router)
    client.app.state.robot_navigation_application_service = service
    client.app.state.robot_navigation_event_hub = service.event_hub

    with client.websocket_connect(f"/ws/robot/emergency/{incident_id}") as websocket:
        assert websocket.receive_json()["type"] == "emergency_snapshot"
        response = client.post(
            f"/api/v1/robot/emergency/{incident_id}/mock/return/complete",
            json={"request_id": "ws-return-complete"},
        )
        assert response.status_code == 200
        events = [websocket.receive_json() for _ in range(2)]

    assert [event["type"] for event in events] == [
        "return_home_completed",
        "emergency_completed",
    ]
    assert all(
        event["data"]["emergency_case"]["execution_state"] == "completed"
        for event in events
    )


def test_missing_emergency_sends_structured_error_and_closes():
    client, _, _ = build_ws_client()
    with client.websocket_connect("/ws/robot/emergency/missing") as websocket:
        error = websocket.receive_json()
        assert error["type"] == "error"
        assert error["data"]["code"] == "INCIDENT_NOT_FOUND"


def test_event_hub_queue_is_bounded_and_keeps_latest():
    async def exercise():
        hub = RobotNavigationEventHub(queue_size=2)
        subscription = hub.subscribe("navigation")
        for index in range(5):
            hub.publish(f"event_{index}", {"index": index}, channels=("navigation",))
        await asyncio.sleep(0)
        events = [subscription.queue.get_nowait(), subscription.queue.get_nowait()]
        hub.unsubscribe(subscription)
        assert [event["data"]["index"] for event in events] == [3, 4]
        assert hub.subscriber_count == 0

    asyncio.run(exercise())


class FakeGateway:
    base_url = "http://mock-gateway"

    def state(self):
        return RobotNavigationGatewayResult(
            data={"provider": "mock", "real_motion_enabled": False, "execution_state": "created"}
        )


class FakeUpstreamConnection:
    def __init__(self, messages=None):
        self.messages = list(messages or [])
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.messages:
            return self.messages.pop(0)
        await asyncio.Event().wait()
        raise StopAsyncIteration


class FiniteUpstreamConnection(FakeUpstreamConnection):
    async def __anext__(self):
        if self.messages:
            return self.messages.pop(0)
        raise StopAsyncIteration


def test_proxy_reuses_single_upstream_connection_and_releases_task():
    async def exercise():
        hub = RobotNavigationEventHub()
        connections = []

        def connector(url):
            connection = FakeUpstreamConnection()
            connections.append((url, connection))
            return connection

        proxy = RobotNavigationWsProxyService(
            FakeGateway(), hub, connector=connector, disconnect_grace_seconds=0.01
        )
        await proxy.acquire()
        await proxy.acquire()
        await asyncio.sleep(0.03)
        assert len(connections) == 1
        assert proxy.active_upstream_connections == 1
        await proxy.release()
        assert proxy.has_running_task is True
        await proxy.release()
        await asyncio.sleep(0.04)
        assert proxy.has_running_task is False
        assert connections[0][1].closed is True
        await proxy.close()

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("provider", "real_motion_enabled", "expected_code"),
    [
        ("real", False, "MOCK_PROVIDER_CONTRACT_VIOLATION"),
        ("mock", True, "REAL_MOTION_DISABLED"),
    ],
)
def test_proxy_rejects_invalid_upstream_contract(provider, real_motion_enabled, expected_code):
    async def exercise():
        hub = RobotNavigationEventHub(queue_size=8)
        subscription = hub.subscribe("navigation")
        message = json.dumps(
            {
                "type": "navigation_updated",
                "sequence": 1,
                "timestamp": "2026-07-23T00:00:00+08:00",
                "provider": provider,
                "real_motion_enabled": real_motion_enabled,
                "data": {},
            }
        )
        proxy = RobotNavigationWsProxyService(
            FakeGateway(),
            hub,
            connector=lambda url: FakeUpstreamConnection([message]),
            retry_initial_seconds=1,
        )
        await proxy.acquire()
        snapshot = await asyncio.wait_for(subscription.queue.get(), timeout=1)
        error = await asyncio.wait_for(subscription.queue.get(), timeout=1)
        assert snapshot["type"] == "navigation_snapshot"
        assert error["type"] == "navigation_upstream_error"
        assert error["data"]["code"] == expected_code
        await proxy.close()
        hub.unsubscribe(subscription)
        assert proxy.has_running_task is False

    asyncio.run(exercise())


def test_proxy_is_not_started_until_first_subscriber():
    async def exercise():
        proxy = RobotNavigationWsProxyService(FakeGateway(), RobotNavigationEventHub())
        assert proxy.connection_attempts == 0
        assert proxy.has_running_task is False
        await proxy.close()

    asyncio.run(exercise())


def test_proxy_reconnects_with_rest_resync_and_keeps_single_active_connection():
    async def exercise():
        hub = RobotNavigationEventHub(queue_size=16)
        subscription = hub.subscribe("navigation")
        connections = []

        def connector(url):
            connection = FiniteUpstreamConnection() if not connections else FakeUpstreamConnection()
            connections.append(connection)
            return connection

        proxy = RobotNavigationWsProxyService(
            FakeGateway(),
            hub,
            connector=connector,
            retry_initial_seconds=0.01,
            disconnect_grace_seconds=0.01,
        )
        await proxy.acquire()
        for _ in range(50):
            if proxy.connection_attempts >= 2 and proxy.active_upstream_connections == 1:
                break
            await asyncio.sleep(0.01)
        assert proxy.connection_attempts >= 2
        assert proxy.active_upstream_connections == 1
        await asyncio.sleep(0)
        snapshots = []
        while not subscription.queue.empty():
            event = subscription.queue.get_nowait()
            if event and event["type"] == "navigation_snapshot":
                snapshots.append(event)
        assert len(snapshots) >= 2
        await proxy.release()
        await asyncio.sleep(0.03)
        await proxy.close()
        hub.unsubscribe(subscription)
        assert proxy.has_running_task is False

    asyncio.run(exercise())
