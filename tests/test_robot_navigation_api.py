from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import requests

from backend.api.robot_emergency_api import router as emergency_router
from backend.api.robot_navigation_api import router as navigation_router
from backend.dependencies import get_robot_navigation_application_service
from backend.models.robot_navigation_model import RobotMapPoint, RobotMapPointType
from backend.repositories.robot_emergency_repo import RobotEmergencyRepository
from backend.repositories.robot_map_repo import RobotMapRepository
from backend.repositories.robot_navigation_repo import RobotNavigationRepository
from backend.repositories.robot_task_repo import RobotTaskRepository
from backend.services.robot_emergency_service import RobotEmergencyService
from backend.services.robot_map_service import RobotMapService
from backend.services.robot_navigation_application_service import RobotNavigationApplicationService
from backend.services.robot_navigation_event_hub import RobotNavigationEventHub
from backend.services.robot_navigation_gateway_service import (
    RobotNavigationGatewayResult,
    RobotNavigationGatewayService,
)
from backend.services.robot_navigation_service import RobotNavigationService


class FakeResponse:
    status_code = 200

    def __init__(self, data):
        self._data = data

    def json(self):
        return {"success": True, "code": "OK", "message": "ok", "data": self._data}


class FakeNavigationSession:
    def __init__(self):
        self.calls = []
        self.provider = "mock"
        self.real_motion_enabled = False
        self.error = None
        self.state = {
            "robot_online": True,
            "emergency_stop_clear": True,
            "localization_valid": True,
            "map_loaded": True,
            "path_plannable": True,
            "robot_stationary": True,
            "control_available": True,
            "control_owner": "NONE",
            "mapping_state": "idle",
            "mock_scenario": "robot_ready",
            "safety_interlock": {
                "passed": False,
                "checks": {
                    "robot_online": False,
                    "emergency_stop_clear": False,
                    "localization_valid": False,
                    "map_loaded": False,
                    "path_plannable": False,
                    "robot_stationary": False,
                    "control_available": False,
                },
                "blocked_by": ["LOCALIZATION_INVALID", "MAP_NOT_LOADED"],
            },
        }

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.error is not None:
            raise self.error
        common = {"provider": self.provider, "real_motion_enabled": self.real_motion_enabled}
        if url.endswith("/api/navigation/state"):
            return FakeResponse({**common, **self.state})
        if url.endswith("/api/navigation/capabilities"):
            return FakeResponse({**common, "mapping": "mock", "navigation": "mock"})
        if url.endswith("/api/navigation/mapping/start"):
            return FakeResponse({**common, "session_id": "mapping_1", "map_id": "map_api"})
        return FakeResponse(common)


class FakeLegacyGateway:
    def status(self):
        return {"online": False, "status": "mock"}


def build_service(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'api.db'}"
    task_repo = RobotTaskRepository(database_url)
    map_repo = RobotMapRepository(database_url)
    navigation_repo = RobotNavigationRepository(database_url)
    emergency_repo = RobotEmergencyRepository(database_url)
    session = FakeNavigationSession()
    gateway = RobotNavigationGatewayService("http://mock-gateway", session=session)
    map_service = RobotMapService(map_repo)
    navigation = RobotNavigationService(task_repo, navigation_repo, map_service, gateway)
    emergency = RobotEmergencyService(emergency_repo, navigation)
    hub = RobotNavigationEventHub()
    service = RobotNavigationApplicationService(
        map_repository=map_repo,
        navigation_repository=navigation_repo,
        emergency_repository=emergency_repo,
        task_repository=task_repo,
        map_service=map_service,
        navigation_service=navigation,
        emergency_service=emergency,
        gateway_service=gateway,
        event_hub=hub,
        legacy_gateway_service=FakeLegacyGateway(),
    )
    app = FastAPI()
    app.include_router(navigation_router, prefix="/api/v1")
    app.include_router(emergency_router, prefix="/api/v1")
    app.dependency_overrides[get_robot_navigation_application_service] = lambda: service
    return TestClient(app), service, session


def activate_map(service: RobotNavigationApplicationService):
    item = service.map_service.create_draft_map("活动地图", map_id="map_active")
    service.map_service.mark_preview_ready(item.map_id)
    service.map_service.activate_preview(item.map_id, replacement_confirmed=False)


def add_navigation_points(client: TestClient):
    common = {"map_id": "map_active", "yaw": 0, "request_id": "point-op"}
    for payload in (
        {**common, "request_id": "home-op", "point_id": "home", "name": "返航点", "point_type": "home", "x": 0, "y": 0},
        {**common, "request_id": "obs-op", "point_id": "obs", "name": "观察点", "point_type": "observation", "x": 1, "y": 1, "metadata": {"area_id": "area_a"}},
        {**common, "request_id": "patrol-1-op", "point_id": "p1", "name": "巡逻点1", "point_type": "patrol", "x": 2, "y": 1},
        {**common, "request_id": "patrol-2-op", "point_id": "p2", "name": "巡逻点2", "point_type": "patrol", "x": 3, "y": 1},
    ):
        assert client.post("/api/v1/robot/navigation/points", json=payload).status_code == 201


def add_navigation_route(client: TestClient, *, route_id: str = "route_effective"):
    add_navigation_points(client)
    response = client.post(
        "/api/v1/robot/navigation/routes",
        json={
            "route_id": route_id,
            "map_id": "map_active",
            "name": "有效安全快照路线",
            "point_ids": ["p1", "p2"],
            "request_id": f"{route_id}-create",
        },
    )
    assert response.status_code == 201


def test_capabilities_state_and_diagnostics_use_new_envelope(tmp_path):
    client, _, _ = build_service(tmp_path)
    for path in (
        "/api/v1/robot/navigation/capabilities",
        "/api/v1/robot/navigation/state",
        "/api/v1/robot/status/diagnostics",
    ):
        response = client.get(path)
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True and body["code"] == "OK"
        assert body["data"]["provider"] == "mock"
        assert body["data"]["real_motion_enabled"] is False


def test_ready_gateway_and_active_map_share_one_effective_snapshot_for_state_and_patrol(tmp_path):
    client, service, _ = build_service(tmp_path)
    activate_map(service)
    add_navigation_route(client)

    state = client.get("/api/v1/robot/navigation/state").json()["data"]
    expected = {
        "robot_online": True,
        "emergency_stop_clear": True,
        "localization_valid": True,
        "map_loaded": True,
        "path_plannable": True,
        "robot_stationary": True,
        "control_available": True,
    }
    assert {name: state[name] for name in expected} == expected
    assert state["safety_interlock"]["checks"] == expected
    assert state["safety_interlock"]["passed"] is True
    assert state["state_fresh"] is True

    started = client.post(
        "/api/v1/robot/navigation/routes/route_effective/start",
        json={"request_id": "effective-ready-start"},
    )
    assert started.status_code == 201
    assert started.json()["data"]["execution_state"] == "navigating"


def test_effective_map_requires_gateway_and_main_system_active_map(tmp_path):
    client, service, session = build_service(tmp_path)

    without_local_map = client.get("/api/v1/robot/navigation/state").json()["data"]
    assert without_local_map["map_loaded"] is False
    blocked = client.post(
        "/api/v1/robot/navigation/routes/missing/start",
        json={"request_id": "no-local-map-start"},
    )
    assert blocked.status_code == 409
    assert "MAP_NOT_LOADED" in blocked.json()["data"]["blocked_by"]

    activate_map(service)
    session.state["map_loaded"] = False
    without_gateway_map = client.get("/api/v1/robot/navigation/state").json()["data"]
    assert without_gateway_map["map_loaded"] is False

    session.state["map_loaded"] = True
    with_both_maps = client.get("/api/v1/robot/navigation/state").json()["data"]
    assert with_both_maps["map_loaded"] is True


@pytest.mark.parametrize(
    ("field", "blocked_code"),
    [
        ("localization_valid", "LOCALIZATION_INVALID"),
        ("map_loaded", "MAP_NOT_LOADED"),
    ],
)
def test_gateway_scenario_change_is_immediate_in_state_and_patrol_preflight(
    tmp_path,
    field,
    blocked_code,
):
    client, service, session = build_service(tmp_path)
    activate_map(service)
    add_navigation_route(client, route_id=f"route-{field}")
    session.state[field] = False
    session.state["mock_scenario"] = (
        "localization_invalid" if field == "localization_valid" else "map_not_loaded"
    )

    state = client.get("/api/v1/robot/navigation/state").json()["data"]
    assert state[field] is False
    response = client.post(
        f"/api/v1/robot/navigation/routes/route-{field}/start",
        json={"request_id": f"{field}-blocked-start"},
    )
    assert response.status_code == 409
    assert blocked_code in response.json()["data"]["blocked_by"]


def test_stale_gateway_fetch_fails_closed_for_state_and_operation(tmp_path):
    client, service, session = build_service(tmp_path)
    activate_map(service)
    add_navigation_route(client, route_id="route-stale")
    stale_result = RobotNavigationGatewayResult(
        data={
            "provider": "mock",
            "real_motion_enabled": False,
            **session.state,
        },
        fetched_at=datetime.now(timezone.utc) - timedelta(seconds=30),
    )
    service.gateway.state = lambda: stale_result

    state = client.get("/api/v1/robot/navigation/state").json()["data"]
    assert state["state_fresh"] is False
    assert state["state_age_ms"] >= 30_000
    assert all(
        state[name] is False
        for name in (
            "robot_online",
            "emergency_stop_clear",
            "localization_valid",
            "map_loaded",
            "path_plannable",
            "robot_stationary",
            "control_available",
        )
    )
    blocked = client.post(
        "/api/v1/robot/navigation/routes/route-stale/start",
        json={"request_id": "stale-start"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["data"]["blocked_by"][0] == "ROBOT_OFFLINE"


def test_patrol_emergency_resume_and_return_home_use_the_same_effective_resolver(tmp_path):
    client, service, _ = build_service(tmp_path)
    activate_map(service)
    add_navigation_route(client, route_id="route-shared-resolver")
    resolver_calls = []
    original_resolve = service.safety_state_resolver.resolve

    def tracked_resolve(*args, **kwargs):
        resolver_calls.append(args[0])
        return original_resolve(*args, **kwargs)

    service.safety_state_resolver.resolve = tracked_resolve

    started = client.post(
        "/api/v1/robot/navigation/routes/route-shared-resolver/start",
        json={"request_id": "shared-start"},
    )
    assert started.status_code == 201
    patrol_task_id = started.json()["data"]["task_id"]
    assert client.post(
        f"/api/v1/robot/navigation/tasks/{patrol_task_id}/pause",
        json={"request_id": "shared-pause"},
    ).status_code == 200
    assert client.post(
        f"/api/v1/robot/navigation/tasks/{patrol_task_id}/resume",
        json={"request_id": "shared-resume"},
    ).status_code == 200

    dispatched = client.post(
        "/api/v1/robot/emergency/shared-incident/dispatch",
        json={"area_id": "area_a", "area_name": "A区", "request_id": "shared-dispatch"},
    )
    assert dispatched.status_code == 201
    service.emergency.begin_dialogue(
        incident_id="shared-incident",
        operation_id="shared-dialogue-begin",
    )
    assert client.post(
        "/api/v1/robot/emergency/shared-incident/escalate",
        json={
            "request_id": "shared-dialogue",
            "turn_id": "shared-turn",
            "intent": "safe_response",
            "input_text": "我没事",
        },
    ).status_code == 200
    assert client.post(
        "/api/v1/robot/emergency/shared-incident/acknowledge",
        json={"request_id": "shared-ack", "admin_id": "admin"},
    ).status_code == 200
    returned = client.post(
        "/api/v1/robot/emergency/shared-incident/resolve-and-return",
        json={"request_id": "shared-return", "resolution": "管理员确认安全"},
    )
    assert returned.status_code == 200
    assert returned.json()["data"]["execution_state"] == "returning_home"
    assert len(resolver_calls) == 4


def test_mapping_start_stop_preview_and_save(tmp_path):
    client, _, _ = build_service(tmp_path)
    assert client.get("/api/v1/robot/navigation/state").json()["data"]["map_loaded"] is False
    started = client.post(
        "/api/v1/robot/navigation/mapping/start",
        json={"session_name": "教室", "request_id": "mapping-start"},
    )
    assert started.status_code == 201
    assert started.json()["data"]["map"]["map_id"] == "map_api"
    stopped = client.post(
        "/api/v1/robot/navigation/mapping/stop",
        json={"map_id": "map_api", "session_id": "mapping_1", "request_id": "mapping-stop"},
    )
    assert stopped.status_code == 200
    preview = client.post(
        "/api/v1/robot/navigation/maps/preview",
        json={"map_id": "map_api", "metadata": {"approved": True}, "request_id": "preview"},
    )
    assert preview.status_code == 200
    saved = client.post(
        "/api/v1/robot/navigation/maps/save",
        json={"map_id": "map_api", "session_id": "mapping_1", "name": "教室", "replace_confirmed": False, "request_id": "save"},
    )
    assert saved.status_code == 200
    assert client.get("/api/v1/robot/navigation/maps/active").json()["data"]["status"] == "active"
    assert client.get("/api/v1/robot/navigation/state").json()["data"]["map_loaded"] is True


def test_mapping_write_replays_do_not_repeat_gateway_calls_or_events(tmp_path):
    client, service, session = build_service(tmp_path)
    start_body = {"session_name": "幂等建图", "request_id": "mapping-replay"}
    first = client.post("/api/v1/robot/navigation/mapping/start", json=start_body)
    assert first.status_code == 201
    gateway_calls = len(session.calls)
    event_sequence = service.event_hub.current_sequence
    replay = client.post("/api/v1/robot/navigation/mapping/start", json=start_body)
    assert replay.status_code == 200
    assert replay.json()["data"] == first.json()["data"]
    assert len(session.calls) == gateway_calls
    assert service.event_hub.current_sequence == event_sequence

    stop_body = {"map_id": "map_api", "session_id": "mapping_1", "request_id": "mapping-stop-replay"}
    assert client.post("/api/v1/robot/navigation/mapping/stop", json=stop_body).status_code == 200
    gateway_calls = len(session.calls)
    event_sequence = service.event_hub.current_sequence
    assert client.post("/api/v1/robot/navigation/mapping/stop", json=stop_body).status_code == 200
    assert len(session.calls) == gateway_calls
    assert service.event_hub.current_sequence == event_sequence


def test_point_crud_and_idempotent_replay(tmp_path):
    client, service, _ = build_service(tmp_path)
    activate_map(service)
    payload = {
        "point_id": "p1", "map_id": "map_active", "name": "巡逻点", "point_type": "patrol",
        "x": 1, "y": 2, "yaw": 0, "request_id": "create-p1",
    }
    first = client.post("/api/v1/robot/navigation/points", json=payload)
    replay = client.post("/api/v1/robot/navigation/points", json=payload)
    assert first.status_code == 201 and replay.status_code == 200
    updated = client.put(
        "/api/v1/robot/navigation/points/p1",
        json={"name": "巡逻点A", "x": 2.5, "request_id": "update-p1"},
    )
    assert updated.status_code == 200 and updated.json()["data"]["x"] == 2.5
    deleted = client.delete("/api/v1/robot/navigation/points/p1?request_id=delete-p1")
    assert deleted.status_code == 200 and deleted.json()["data"]["status"] == "invalid"


def test_same_operation_id_with_different_point_body_conflicts(tmp_path):
    client, service, _ = build_service(tmp_path)
    activate_map(service)
    base = {
        "point_id": "p1", "map_id": "map_active", "name": "A", "point_type": "patrol",
        "x": 1, "y": 2, "yaw": 0, "request_id": "same-op",
    }
    assert client.post("/api/v1/robot/navigation/points", json=base).status_code == 201
    changed = client.post("/api/v1/robot/navigation/points", json={**base, "x": 9})
    assert changed.status_code == 409
    assert changed.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_route_create_preserves_point_order_and_patrol_starts(tmp_path):
    client, service, _ = build_service(tmp_path)
    activate_map(service)
    add_navigation_points(client)
    route = client.post(
        "/api/v1/robot/navigation/routes",
        json={"route_id": "route_1", "map_id": "map_active", "name": "路线", "point_ids": ["p2", "p1"], "request_id": "route-op"},
    )
    assert route.status_code == 201
    assert [item["point_id"] for item in route.json()["data"]["points"]] == ["p2", "p1"]
    started = client.post(
        "/api/v1/robot/navigation/routes/route_1/start",
        json={"request_id": "patrol-start"},
    )
    assert started.status_code == 201
    assert started.json()["data"]["execution_state"] == "navigating"


def test_patrol_task_controls_history_and_idempotent_replay(tmp_path):
    client, service, session = build_service(tmp_path)
    activate_map(service)
    add_navigation_points(client)
    route_body = {
        "route_id": "route_controls",
        "map_id": "map_active",
        "name": "控制回归路线",
        "point_ids": ["p1", "p2"],
        "request_id": "route-controls-op",
    }
    assert client.post("/api/v1/robot/navigation/routes", json=route_body).status_code == 201
    assert client.post("/api/v1/robot/navigation/routes", json=route_body).status_code == 200

    start_body = {"request_id": "patrol-controls"}
    started = client.post("/api/v1/robot/navigation/routes/route_controls/start", json=start_body)
    task_id = started.json()["data"]["task_id"]
    gateway_calls = len(session.calls)
    replay = client.post("/api/v1/robot/navigation/routes/route_controls/start", json=start_body)
    assert replay.status_code == 200
    assert len(session.calls) == gateway_calls
    assert len(service.tasks.list_tasks()) == 1

    operations = (
        ("pause", "task-pause", "paused_admin"),
        ("resume", "task-resume", "navigating"),
        ("manual-acquire", "manual-acquire", "paused_manual"),
        ("manual-release", "manual-release", "paused_manual"),
        ("resume", "task-resume-after-manual", "navigating"),
        ("stop", "task-stop", "cancelled"),
    )
    for operation, request_id, expected_state in operations:
        response = client.post(
            f"/api/v1/robot/navigation/tasks/{task_id}/{operation}",
            json={"request_id": request_id},
        )
        assert response.status_code == 200
        assert response.json()["data"]["execution_state"] == expected_state

    gateway_calls = len(session.calls)
    event_count = len(service.navigation_events.list_for_task(task_id))
    replay = client.post(
        f"/api/v1/robot/navigation/tasks/{task_id}/stop",
        json={"request_id": "task-stop"},
    )
    assert replay.status_code == 200
    assert len(session.calls) == gateway_calls
    assert len(service.navigation_events.list_for_task(task_id)) == event_count

    timeline = client.get(f"/api/v1/robot/navigation/tasks/{task_id}/timeline")
    events = client.get(f"/api/v1/robot/tasks/{task_id}/navigation-events")
    assert timeline.status_code == 200 and timeline.json()["data"]
    assert events.status_code == 200 and events.json()["data"]


def test_route_rejects_point_from_another_map(tmp_path):
    client, service, _ = build_service(tmp_path)
    activate_map(service)
    second = service.map_service.create_draft_map("其他地图", map_id="map_other")
    service.map_service.mark_preview_ready(second.map_id)
    service.map_service.save_point(
        RobotMapPoint(
            point_id="foreign_point",
            map_id=second.map_id,
            name="跨地图点",
            point_type=RobotMapPointType.PATROL,
            x=1,
            y=1,
            yaw=0,
        )
    )
    response = client.post(
        "/api/v1/robot/navigation/routes",
        json={
            "route_id": "cross_map_route",
            "map_id": "map_active",
            "name": "非法跨地图路线",
            "point_ids": ["foreign_point"],
            "request_id": "cross-map-op",
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "MAP_POINT_INVALID"


def test_route_rejects_duplicate_points_and_extra_control_fields(tmp_path):
    client, service, _ = build_service(tmp_path)
    activate_map(service)
    response = client.post(
        "/api/v1/robot/navigation/routes",
        json={"route_id": "r", "map_id": "map_active", "name": "重复", "point_ids": ["p1", "p1"], "request_id": "r-op"},
    )
    assert response.status_code == 422
    response = client.post(
        "/api/v1/robot/navigation/mapping/start",
        json={"session_name": "非法", "request_id": "bad", "cmd_vel": 1.0},
    )
    assert response.status_code == 422


def test_non_finite_point_coordinate_is_rejected(tmp_path):
    client, service, _ = build_service(tmp_path)
    activate_map(service)
    response = client.post(
        "/api/v1/robot/navigation/points",
        json={"point_id": "bad", "map_id": "map_active", "name": "坏点", "point_type": "patrol", "x": "NaN", "y": 0, "yaw": 0, "request_id": "bad-point"},
    )
    assert response.status_code == 422


def test_upstream_provider_violation_maps_to_502_without_local_resource(tmp_path):
    client, service, session = build_service(tmp_path)
    session.provider = "real"
    response = client.post(
        "/api/v1/robot/navigation/mapping/start",
        json={"session_name": "拒绝", "request_id": "provider-bad"},
    )
    assert response.status_code == 502
    assert response.json()["code"] == "MOCK_PROVIDER_CONTRACT_VIOLATION"
    assert service.maps.list_maps() == []


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (requests.ConnectionError("offline"), 503, "ROBOT_GATEWAY_UNAVAILABLE"),
        (requests.Timeout("slow"), 504, "ROBOT_GATEWAY_TIMEOUT"),
    ],
)
def test_upstream_transport_errors_have_stable_http_mapping(tmp_path, error, expected_status, expected_code):
    client, service, session = build_service(tmp_path)
    session.error = error
    response = client.post(
        "/api/v1/robot/navigation/mapping/start",
        json={"session_name": "不可用网关", "request_id": f"transport-{expected_status}"},
    )
    assert response.status_code == expected_status
    assert response.json()["code"] == expected_code
    assert service.maps.list_maps() == []


def test_emergency_dispatch_acknowledge_and_bundle(tmp_path):
    client, service, _ = build_service(tmp_path)
    activate_map(service)
    add_navigation_points(client)
    dispatched = client.post(
        "/api/v1/robot/emergency/incident_1/dispatch",
        json={"area_id": "area_a", "area_name": "A区", "request_id": "dispatch-1"},
    )
    assert dispatched.status_code == 201
    acknowledged = client.post(
        "/api/v1/robot/emergency/incident_1/acknowledge",
        json={"admin_id": "admin", "request_id": "ack-1"},
    )
    assert acknowledged.status_code == 200
    detail = client.get("/api/v1/robot/emergency/incident_1")
    assert detail.status_code == 200
    assert detail.json()["data"]["incident_id"] == "incident_1"


def test_emergency_dispatch_replay_does_not_duplicate_task_or_gateway_call(tmp_path):
    client, service, session = build_service(tmp_path)
    activate_map(service)
    add_navigation_points(client)
    body = {"area_id": "area_a", "area_name": "A区", "request_id": "dispatch-replay"}
    first = client.post("/api/v1/robot/emergency/incident_replay/dispatch", json=body)
    gateway_calls = len(session.calls)
    event_sequence = service.event_hub.current_sequence
    replay = client.post("/api/v1/robot/emergency/incident_replay/dispatch", json=body)
    assert first.status_code == 201 and replay.status_code == 200
    assert len(service.tasks.list_tasks()) == 1
    assert len(session.calls) == gateway_calls
    assert service.event_hub.current_sequence == event_sequence


def test_repeated_incident_with_different_area_is_idempotency_conflict(tmp_path):
    client, service, _ = build_service(tmp_path)
    activate_map(service)
    add_navigation_points(client)
    first = client.post(
        "/api/v1/robot/emergency/incident_conflict/dispatch",
        json={"area_id": "area_a", "area_name": "A区", "request_id": "dispatch-a"},
    )
    assert first.status_code == 201
    second = client.post(
        "/api/v1/robot/emergency/incident_conflict/dispatch",
        json={"area_id": "area_b", "area_name": "B区", "request_id": "dispatch-b"},
    )
    assert second.status_code == 409
    assert second.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert len(service.tasks.list_tasks()) == 1


def test_missing_emergency_incident_returns_stable_404(tmp_path):
    client, _, _ = build_service(tmp_path)
    response = client.get("/api/v1/robot/emergency/missing")
    assert response.status_code == 404
    assert response.json()["code"] == "INCIDENT_NOT_FOUND"


def test_no_request_can_override_mock_invariants(tmp_path):
    client, service, _ = build_service(tmp_path)
    activate_map(service)
    response = client.post(
        "/api/v1/robot/navigation/points",
        json={
            "point_id": "p", "map_id": "map_active", "name": "点", "point_type": "patrol",
            "x": 0, "y": 0, "yaw": 0, "request_id": "override",
            "provider": "real", "real_motion_enabled": True,
        },
    )
    assert response.status_code == 422
