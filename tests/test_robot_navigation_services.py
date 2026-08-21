from __future__ import annotations

from pathlib import Path

import pytest
import requests

from backend.models.robot_emergency_model import RobotDialogueIntent, RobotEmergencyCaseStatus
from backend.models.robot_navigation_model import (
    RobotControlOwner,
    RobotMapPoint,
    RobotMapPointStatus,
    RobotMapPointType,
    RobotNavigationExecutionState,
    RobotPatrolRoute,
    RobotPatrolRoutePoint,
    RobotPatrolRouteStatus,
    RobotSafetyChecks,
)
from backend.repositories.robot_emergency_repo import RobotEmergencyRepository
from backend.repositories.robot_map_repo import RobotMapRepository
from backend.repositories.robot_navigation_repo import RobotNavigationRepository
from backend.repositories.robot_task_repo import RobotTaskRepository
from backend.services.robot_emergency_service import RobotEmergencyService
from backend.services.robot_map_service import RobotMapService
from backend.services.robot_navigation_errors import RobotNavigationErrorCode, RobotNavigationServiceError
from backend.services.robot_navigation_gateway_service import RobotNavigationGatewayService
from backend.services.robot_navigation_service import RobotNavigationService, RobotNavigationStateCoordinator
from backend.services.robot_safety_interlock_service import RobotSafetyInterlockService


class FakeResponse:
    def __init__(self, payload=None, *, status_code: int = 200, json_error: bool = False):
        self.payload = payload
        self.status_code = status_code
        self.json_error = json_error

    def json(self):
        if self.json_error:
            raise ValueError("invalid json")
        return self.payload


class FakeSession:
    def __init__(self, *, payload=None, error: Exception | None = None):
        self.payload = payload or {
            "success": True,
            "code": "OK",
            "message": "ok",
            "data": {
                "provider": "mock",
                "real_motion_enabled": False,
                "session_id": "mapping_mock_1",
                "map_id": "gateway_map_mock",
            },
        }
        self.error = error
        self.calls: list[dict] = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if self.error:
            raise self.error
        if isinstance(self.payload, FakeResponse):
            return self.payload
        return FakeResponse(self.payload)


def ready_checks(**updates) -> RobotSafetyChecks:
    values = {
        "robot_online": True,
        "emergency_stop_clear": True,
        "localization_valid": True,
        "map_loaded": True,
        "path_plannable": True,
        "robot_stationary": True,
        "control_available": True,
    }
    values.update(updates)
    return RobotSafetyChecks(**values)


@pytest.fixture()
def services(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'robot_services.db'}"
    task_repo = RobotTaskRepository(database_url)
    map_repo = RobotMapRepository(database_url)
    navigation_repo = RobotNavigationRepository(database_url)
    emergency_repo = RobotEmergencyRepository(database_url)
    fake_session = FakeSession()
    gateway = RobotNavigationGatewayService("http://mock-gateway", session=fake_session)
    map_service = RobotMapService(map_repo)
    navigation = RobotNavigationService(task_repo, navigation_repo, map_service, gateway)
    emergency = RobotEmergencyService(emergency_repo, navigation)
    return {
        "database_url": database_url,
        "tasks": task_repo,
        "maps": map_repo,
        "events": navigation_repo,
        "emergencies": emergency_repo,
        "fake": fake_session,
        "gateway": gateway,
        "map_service": map_service,
        "navigation": navigation,
        "emergency": emergency,
    }


def prepare_active_map(services, *, include_home: bool = True, include_route: bool = True):
    maps = services["map_service"]
    item = maps.create_draft_map("照护区域", map_id="map_active")
    maps.mark_preview_ready(item.map_id)
    maps.activate_preview(item.map_id, replacement_confirmed=False)
    if include_home:
        maps.save_point(
            RobotMapPoint(
                point_id="home_1", map_id=item.map_id, name="返航点", point_type=RobotMapPointType.HOME,
                x=0, y=0, yaw=0,
            )
        )
    maps.save_point(
        RobotMapPoint(
            point_id="observation_a", map_id=item.map_id, name="A区观察点",
            point_type=RobotMapPointType.OBSERVATION, x=1, y=1, yaw=0,
            metadata={"area_id": "area_a"},
        )
    )
    if include_route:
        for index in range(2):
            maps.save_point(
                RobotMapPoint(
                    point_id=f"patrol_{index}", map_id=item.map_id, name=f"巡逻点{index}",
                    point_type=RobotMapPointType.PATROL, x=index + 2, y=2, yaw=0,
                )
            )
        maps.save_route(
            RobotPatrolRoute(
                route_id="route_1", map_id=item.map_id, name="夜间巡逻",
                status=RobotPatrolRouteStatus.VALID,
            ),
            [
                RobotPatrolRoutePoint(route_id="route_1", point_id="patrol_0", sequence=0),
                RobotPatrolRoutePoint(route_id="route_1", point_id="patrol_1", sequence=1),
            ],
        )
    return item


def create_task(services, suffix="1"):
    return services["navigation"].create_task(
        source_event_id=f"source_{suffix}", trace_id=f"trace_{suffix}",
        task_type="patrol", location="照护区域", task_id=f"task_{suffix}",
    )


def assert_error(code, call):
    with pytest.raises(RobotNavigationServiceError) as caught:
        call()
    assert caught.value.code == code
    assert caught.value.to_dict()["real_motion_enabled"] is False


def test_gateway_normalizes_request_id_and_accepts_mock_contract():
    session = FakeSession()
    gateway = RobotNavigationGatewayService("http://mock-gateway", session=session)
    result = gateway.start_mapping({"requestId": "req_1", "nested": {"requestId": "req_2"}})
    assert result.provider == "mock" and result.real_motion_enabled is False
    assert session.calls[0]["json"] == {"request_id": "req_1", "nested": {"request_id": "req_2"}}


def test_gateway_disabled_is_machine_readable():
    gateway = RobotNavigationGatewayService("http://mock-gateway", enabled=False, session=FakeSession())
    assert_error(RobotNavigationErrorCode.ROBOT_GATEWAY_UNAVAILABLE.value, gateway.state)


def test_gateway_timeout_is_machine_readable():
    gateway = RobotNavigationGatewayService("http://mock-gateway", session=FakeSession(error=requests.Timeout()))
    assert_error(RobotNavigationErrorCode.ROBOT_GATEWAY_TIMEOUT.value, gateway.state)


def test_gateway_rejects_non_json_response():
    gateway = RobotNavigationGatewayService(
        "http://mock-gateway", session=FakeSession(payload=FakeResponse(json_error=True))
    )
    assert_error(RobotNavigationErrorCode.ROBOT_GATEWAY_INVALID_RESPONSE.value, gateway.state)


def test_gateway_rejects_non_mock_provider():
    payload = {"data": {"provider": "real", "real_motion_enabled": False}}
    gateway = RobotNavigationGatewayService("http://mock-gateway", session=FakeSession(payload=payload))
    assert_error(RobotNavigationErrorCode.MOCK_PROVIDER_CONTRACT_VIOLATION.value, gateway.state)


@pytest.mark.parametrize("data", [{"provider": "mock"}, {"provider": "mock", "real_motion_enabled": True}])
def test_gateway_rejects_missing_or_true_real_motion_flag(data):
    gateway = RobotNavigationGatewayService("http://mock-gateway", session=FakeSession(payload={"data": data}))
    assert_error(RobotNavigationErrorCode.REAL_MOTION_DISABLED.value, gateway.state)


def test_navigation_safety_passes_all_required_checks():
    result = RobotSafetyInterlockService().check_navigation(ready_checks())
    assert result.passed is True and result.blocked_by == []
    assert result.provider == "mock" and result.real_motion_enabled is False


def test_navigation_safety_reports_stable_block_order():
    result = RobotSafetyInterlockService().check_navigation(
        ready_checks(
            robot_online=False,
            localization_valid=False,
            path_plannable=False,
            control_available=False,
        )
    )
    assert result.blocked_by == [
        "ROBOT_OFFLINE",
        "LOCALIZATION_INVALID",
        "PATH_NOT_PLANNABLE",
        "CONTROL_NOT_AVAILABLE",
    ]


def test_mapping_safety_does_not_require_localization_map_or_path():
    result = RobotSafetyInterlockService().check_mapping(
        ready_checks(localization_valid=False, map_loaded=False, path_plannable=False)
    )
    assert result.passed is True


def test_map_replacement_requires_confirmation_and_invalidates_old_points(services):
    first = prepare_active_map(services)
    maps = services["map_service"]
    second = maps.create_draft_map("新地图", map_id="map_second")
    maps.mark_preview_ready(second.map_id)
    assert_error(
        RobotNavigationErrorCode.MAP_REPLACEMENT_CONFIRMATION_REQUIRED.value,
        lambda: maps.activate_preview(second.map_id, replacement_confirmed=False),
    )
    maps.activate_preview(second.map_id, replacement_confirmed=True)
    assert services["maps"].get_map(first.map_id).status.value == "replaced"
    assert all(point.status == RobotMapPointStatus.INVALID for point in services["maps"].list_points(first.map_id))


def test_observation_point_is_unique_per_area_not_per_map(services):
    prepare_active_map(services)
    maps = services["map_service"]
    maps.save_point(
        RobotMapPoint(
            point_id="observation_b", map_id="map_active", name="B区观察点",
            point_type=RobotMapPointType.OBSERVATION, x=3, y=3, yaw=0,
            metadata={"area_id": "area_b"},
        )
    )
    assert maps.find_observation_point("map_active", "area_b").point_id == "observation_b"
    duplicate = RobotMapPoint(
        point_id="observation_a_2", map_id="map_active", name="A区重复点",
        point_type=RobotMapPointType.OBSERVATION, x=4, y=4, yaw=0,
        metadata={"area_id": "area_a"},
    )
    assert_error(RobotNavigationErrorCode.MAP_POINT_INVALID.value, lambda: maps.save_point(duplicate))


def test_patrol_start_writes_task_timeline_and_navigation_event_atomically(services):
    prepare_active_map(services)
    create_task(services)
    task = services["navigation"].start_patrol(
        task_id="task_1", route_id="route_1", request_id="patrol_req", checks=ready_checks()
    )
    assert task.execution_state == RobotNavigationExecutionState.NAVIGATING
    assert task.control_owner == RobotControlOwner.NAVIGATION
    assert task.provider == "mock" and task.real_motion_enabled is False
    assert len(services["tasks"].list_timeline("task_1")) == 3
    assert len(services["events"].list_for_task("task_1")) == 3


def test_safety_failure_blocks_task_and_never_calls_gateway(services):
    prepare_active_map(services)
    create_task(services)
    assert_error(
        RobotNavigationErrorCode.SAFETY_INTERLOCK_BLOCKED.value,
        lambda: services["navigation"].start_patrol(
            task_id="task_1", route_id="route_1", request_id="blocked_req",
            checks=ready_checks(localization_valid=False),
        ),
    )
    task = services["tasks"].get_task("task_1")
    assert task.status.value == "BLOCKED" and task.execution_state.value == "blocked"
    assert services["fake"].calls == []


def test_invalid_state_transition_is_rejected(services):
    create_task(services)
    assert_error(
        RobotNavigationErrorCode.INVALID_STATE_TRANSITION.value,
        lambda: services["navigation"].transition(
            "task_1", RobotNavigationExecutionState.COMPLETED, "invalid_req", "invalid"
        ),
    )


def test_pause_and_explicit_resume_rerun_safety(services):
    prepare_active_map(services)
    create_task(services)
    services["navigation"].start_patrol(task_id="task_1", route_id="route_1", request_id="start", checks=ready_checks())
    paused = services["navigation"].pause_task(task_id="task_1", request_id="pause")
    assert paused.execution_state == RobotNavigationExecutionState.PAUSED_ADMIN
    resumed = services["navigation"].resume_task(task_id="task_1", request_id="resume", checks=ready_checks())
    assert resumed.execution_state == RobotNavigationExecutionState.NAVIGATING
    assert services["events"].get_event("resume:safety") is not None


def test_gateway_task_id_is_persisted_and_reused_for_pause_and_resume(services):
    prepare_active_map(services)
    create_task(services)
    services["fake"].payload["data"]["task_id"] = "gateway_task_42"

    started = services["navigation"].start_patrol(
        task_id="task_1",
        route_id="route_1",
        request_id="start-gateway-id",
        checks=ready_checks(),
    )
    assert started.gateway_task_id == "gateway_task_42"

    services["navigation"].pause_task(task_id="task_1", request_id="pause-gateway-id")
    services["navigation"].resume_task(
        task_id="task_1",
        request_id="resume-gateway-id",
        checks=ready_checks(),
    )

    assert services["fake"].calls[-2]["url"].endswith("/api/navigation/tasks/gateway_task_42/pause")
    assert services["fake"].calls[-1]["url"].endswith("/api/navigation/tasks/gateway_task_42/resume")


def test_gateway_completed_resume_is_persisted_through_existing_states(services):
    prepare_active_map(services)
    create_task(services)
    services["fake"].payload["data"]["task_id"] = "gateway_task_43"
    services["navigation"].start_patrol(
        task_id="task_1",
        route_id="route_1",
        request_id="start-pending",
        checks=ready_checks(),
    )
    services["navigation"].manual_takeover(task_id="task_1", request_id="manual-takeover")
    services["navigation"].release_control(task_id="task_1", request_id="manual-release")
    services["fake"].payload["data"]["execution_state"] = "completed"

    completed = services["navigation"].resume_task(
        task_id="task_1",
        request_id="resume-completed",
        checks=ready_checks(),
    )

    assert completed.execution_state == RobotNavigationExecutionState.COMPLETED
    assert completed.status.value == "COMPLETED"
    assert [item.execution_state for item in services["events"].list_for_task("task_1")][-4:] == [
        RobotNavigationExecutionState.ARRIVED,
        RobotNavigationExecutionState.SAFETY_CHECKING,
        RobotNavigationExecutionState.RETURNING_HOME,
        RobotNavigationExecutionState.COMPLETED,
    ]


def test_manual_release_does_not_auto_resume(services):
    prepare_active_map(services)
    create_task(services)
    services["navigation"].start_patrol(task_id="task_1", route_id="route_1", request_id="start", checks=ready_checks())
    taken = services["navigation"].manual_takeover(task_id="task_1", request_id="take")
    assert taken.execution_state == RobotNavigationExecutionState.PAUSED_MANUAL
    released = services["navigation"].release_control(task_id="task_1", request_id="release")
    assert released.execution_state == RobotNavigationExecutionState.PAUSED_MANUAL
    assert released.control_owner == RobotControlOwner.NONE
    assert services["fake"].calls[-2]["json"] == {"request_id": "take"}
    assert services["fake"].calls[-1]["json"] == {"request_id": "release"}


def test_return_home_requires_home_point(services):
    prepare_active_map(services, include_home=False)
    task = create_task(services)
    services["navigation"].transition(task.task_id, RobotNavigationExecutionState.SAFETY_CHECKING, "s1", "safety")
    services["navigation"].transition(task.task_id, RobotNavigationExecutionState.NAVIGATING, "s2", "navigate")
    services["navigation"].transition(task.task_id, RobotNavigationExecutionState.ARRIVED, "s3", "arrived")
    assert_error(
        RobotNavigationErrorCode.HOME_POINT_NOT_FOUND.value,
        lambda: services["navigation"].return_home(
            task_id=task.task_id, request_id="return", checks=ready_checks(), reason="test"
        ),
    )


def test_gateway_failure_keeps_locally_traceable_blocked_task(services):
    prepare_active_map(services)
    create_task(services)
    services["fake"].error = requests.ConnectionError("offline")
    assert_error(
        RobotNavigationErrorCode.ROBOT_GATEWAY_UNAVAILABLE.value,
        lambda: services["navigation"].start_patrol(
            task_id="task_1", route_id="route_1", request_id="offline_req", checks=ready_checks()
        ),
    )
    task = services["tasks"].get_task("task_1")
    assert task.execution_state == RobotNavigationExecutionState.BLOCKED
    assert task.error_code == RobotNavigationErrorCode.ROBOT_GATEWAY_UNAVAILABLE.value


def test_same_incident_is_idempotent_and_does_not_duplicate_task(services):
    prepare_active_map(services)
    first = services["emergency"].create_and_dispatch(
        incident_id="incident_1", area_id="area_a", area_name="A区",
        request_id="incident_req", checks=ready_checks(),
    )
    call_count = len(services["fake"].calls)
    second = services["emergency"].create_and_dispatch(
        incident_id="incident_1", area_id="area_a", area_name="A区",
        request_id="incident_req_2", checks=ready_checks(),
    )
    assert first.case_id == second.case_id and first.robot_task_id == second.robot_task_id
    assert len(services["tasks"].list_tasks()) == 1
    assert len(services["fake"].calls) == call_count


def test_missing_area_mapping_prevents_emergency_task_creation(services):
    prepare_active_map(services)
    assert_error(
        RobotNavigationErrorCode.OBSERVATION_POINT_NOT_FOUND.value,
        lambda: services["emergency"].create_and_dispatch(
            incident_id="incident_missing", area_id="area_missing", area_name="未知区",
            request_id="missing_req", checks=ready_checks(),
        ),
    )
    assert services["tasks"].list_tasks() == []


def test_safe_dialogue_waits_for_admin_confirmation(services):
    prepare_active_map(services)
    case = services["emergency"].create_and_dispatch(
        incident_id="incident_safe", area_id="area_a", area_name="A区",
        request_id="dispatch_safe", checks=ready_checks(),
    )
    services["emergency"].begin_dialogue(incident_id=case.incident_id, operation_id="dialogue_begin")
    updated = services["emergency"].record_dialogue_result(
        incident_id=case.incident_id, turn_id="turn_safe",
        intent=RobotDialogueIntent.SAFE_RESPONSE, input_text="我没事", confidence=0.98,
    )
    assert updated.execution_state == RobotNavigationExecutionState.WAITING_ADMIN_CONFIRMATION
    assert updated.status == RobotEmergencyCaseStatus.ACTIVE
    assert len(services["emergencies"].list_dialogue_turns(case.incident_id)) == 1


def test_help_dialogue_escalates_case(services):
    prepare_active_map(services)
    case = services["emergency"].create_and_dispatch(
        incident_id="incident_help", area_id="area_a", area_name="A区",
        request_id="dispatch_help", checks=ready_checks(),
    )
    services["emergency"].begin_dialogue(incident_id=case.incident_id, operation_id="dialogue_help")
    updated = services["emergency"].record_dialogue_result(
        incident_id=case.incident_id, turn_id="turn_help", intent=RobotDialogueIntent.NEED_HELP,
    )
    assert updated.status == RobotEmergencyCaseStatus.ESCALATED
    assert updated.execution_state == RobotNavigationExecutionState.HELP_REQUESTED


def test_safe_case_cannot_return_before_admin_acknowledgement(services):
    prepare_active_map(services)
    case = services["emergency"].create_and_dispatch(
        incident_id="incident_ack", area_id="area_a", area_name="A区",
        request_id="dispatch_ack", checks=ready_checks(),
    )
    services["emergency"].begin_dialogue(incident_id=case.incident_id, operation_id="dialogue_ack")
    services["emergency"].record_dialogue_result(
        incident_id=case.incident_id, turn_id="turn_ack", intent=RobotDialogueIntent.SAFE_RESPONSE,
    )
    assert_error(
        RobotNavigationErrorCode.INCIDENT_STATE_CONFLICT.value,
        lambda: services["emergency"].resolve_and_return(
            incident_id=case.incident_id, request_id="return_ack", checks=ready_checks()
        ),
    )


def test_confirmed_safe_case_returns_and_completes(services):
    prepare_active_map(services)
    case = services["emergency"].create_and_dispatch(
        incident_id="incident_return", area_id="area_a", area_name="A区",
        request_id="dispatch_return", checks=ready_checks(),
    )
    services["emergency"].begin_dialogue(incident_id=case.incident_id, operation_id="dialogue_return")
    services["emergency"].record_dialogue_result(
        incident_id=case.incident_id, turn_id="turn_return", intent=RobotDialogueIntent.SAFE_RESPONSE,
    )
    services["emergency"].acknowledge(incident_id=case.incident_id, admin_id="admin_1")
    returning = services["emergency"].resolve_and_return(
        incident_id=case.incident_id, request_id="return_req", checks=ready_checks()
    )
    assert returning.execution_state == RobotNavigationExecutionState.RETURNING_HOME
    completed = services["emergency"].complete_return(
        incident_id=case.incident_id, operation_id="return_complete", resolution="老人安全"
    )
    assert completed.status == RobotEmergencyCaseStatus.RESOLVED


def test_navigation_transaction_rolls_back_task_and_timeline_when_event_write_fails(services, monkeypatch):
    create_task(services)

    def fail(*args, **kwargs):
        raise RuntimeError("event write failed")

    monkeypatch.setattr(services["events"], "add_event", fail)
    with pytest.raises(RuntimeError):
        services["navigation"].transition(
            "task_1", RobotNavigationExecutionState.SAFETY_CHECKING, "rollback_op", "safety"
        )
    task = services["tasks"].get_task("task_1")
    assert task.execution_state == RobotNavigationExecutionState.CREATED
    assert services["tasks"].list_timeline("task_1") == []


def test_emergency_creation_rolls_back_task_when_case_write_fails(services, monkeypatch):
    prepare_active_map(services)

    def fail(*args, **kwargs):
        raise RuntimeError("case write failed")

    monkeypatch.setattr(services["emergencies"], "save_case", fail)
    with pytest.raises(RuntimeError):
        services["emergency"].create_and_dispatch(
            incident_id="incident_rollback", area_id="area_a", area_name="A区",
            request_id="rollback_req", checks=ready_checks(),
        )
    assert services["tasks"].get_by_source_event_id("robot-emergency:incident_rollback") is None
    assert services["events"].get_event("incident_rollback:created") is None


def test_no_real_motion_or_legacy_motion_call_path_is_present(services):
    prepare_active_map(services)
    create_task(services)
    services["navigation"].start_patrol(
        task_id="task_1", route_id="route_1", request_id="proof_req", checks=ready_checks()
    )
    assert all(call["url"].startswith("http://mock-gateway/api/navigation/") for call in services["fake"].calls)
    source = Path("backend/services/robot_navigation_service.py").read_text(encoding="utf-8")
    assert "robot_service.move" not in source
    assert "/api/robot/move" not in source
    assert ":8090" not in source
    assert all(task.real_motion_enabled is False for task in services["tasks"].list_tasks())


def test_state_coordinator_declares_all_formal_states():
    declared = set(RobotNavigationStateCoordinator.ALLOWED)
    assert declared == set(RobotNavigationExecutionState)
