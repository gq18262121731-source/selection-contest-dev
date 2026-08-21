from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.models.robot_emergency_model import (
    RobotDialogueIntent,
    RobotDialogueRole,
    RobotDialogueTurn,
    RobotEmergencyCase,
    RobotEmergencyExecutionState,
)
from backend.models.robot_model import RobotTask, RobotTaskStatus
from backend.models.robot_navigation_model import (
    RobotControlOwner,
    RobotMap,
    RobotMapPoint,
    RobotMapPointStatus,
    RobotMapPointType,
    RobotMapStatus,
    RobotNavigationCapability,
    RobotNavigationEvent,
    RobotNavigationExecutionState,
    RobotPatrolRoute,
    RobotPatrolRoutePoint,
    RobotPatrolRouteStatus,
)
from backend.repositories.robot_emergency_repo import RobotEmergencyRepository
from backend.repositories.robot_map_repo import RobotMapRepository
from backend.repositories.robot_navigation_repo import RobotNavigationRepository
from backend.repositories.robot_task_repo import RobotTaskRepository


EXPECTED_TABLES = {
    "robot_maps",
    "robot_map_points",
    "robot_patrol_routes",
    "robot_patrol_route_points",
    "robot_emergency_cases",
    "robot_dialogue_turns",
    "robot_navigation_events",
}


def _database(tmp_path: Path) -> tuple[Path, str]:
    path = tmp_path / "robot-domain.db"
    return path, f"sqlite+aiosqlite:///{path.as_posix()}"


def _initialize_all(database_url: str) -> tuple[RobotMapRepository, RobotNavigationRepository, RobotEmergencyRepository]:
    return (
        RobotMapRepository(database_url),
        RobotNavigationRepository(database_url),
        RobotEmergencyRepository(database_url),
    )


def test_new_tables_initialize_idempotently_without_changing_robot_tasks(tmp_path: Path) -> None:
    path, database_url = _database(tmp_path)
    task_repo = RobotTaskRepository(database_url)
    task = RobotTask(
        task_id="task-existing",
        source_event_id="incident-existing",
        trace_id="trace-existing",
        status=RobotTaskStatus.BLOCKED,
    )
    task_repo.create_task(task)

    _initialize_all(database_url)
    _initialize_all(database_url)

    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        status = connection.execute(
            "SELECT status FROM robot_tasks WHERE task_id = ?",
            (task.task_id,),
        ).fetchone()
    assert EXPECTED_TABLES <= tables
    assert status == (RobotTaskStatus.BLOCKED.value,)
    assert RobotTaskRepository(database_url).get_task(task.task_id) == task


def test_map_points_and_route_round_trip_with_metadata(tmp_path: Path) -> None:
    _path, database_url = _database(tmp_path)
    map_repo = RobotMapRepository(database_url)
    robot_map = RobotMap(
        map_id="map-001",
        name="养老活动区",
        metadata={"nested": {"labels": ["演示", "一层"]}},
    )
    map_repo.create_map(robot_map)
    home = RobotMapPoint(
        point_id="home-001",
        map_id=robot_map.map_id,
        name="待命区",
        point_type=RobotMapPointType.HOME,
        x=0.0,
        y=0.0,
        yaw=0.0,
        metadata={"color": "green"},
    )
    patrol = RobotMapPoint(
        point_id="patrol-001",
        map_id=robot_map.map_id,
        name="巡检点",
        point_type=RobotMapPointType.PATROL,
        x=1.2,
        y=2.4,
        yaw=1.57,
    )
    map_repo.save_point(home)
    map_repo.save_point(patrol)
    route = RobotPatrolRoute(
        route_id="route-001",
        map_id=robot_map.map_id,
        name="日常巡检",
        status=RobotPatrolRouteStatus.ACTIVE,
        metadata={"schedule": ["09:00", "15:00"]},
    )
    route_points = [
        RobotPatrolRoutePoint(route_id=route.route_id, point_id=home.point_id, sequence=0),
        RobotPatrolRoutePoint(
            route_id=route.route_id,
            point_id=patrol.point_id,
            sequence=1,
            metadata={"label": "活动区"},
        ),
    ]
    map_repo.save_route(route, route_points)

    stored_map = map_repo.get_map(robot_map.map_id)
    stored_route = map_repo.get_route(route.route_id)
    assert stored_map is not None
    assert stored_map.metadata == robot_map.metadata
    assert [item.point_id for item in map_repo.list_points(robot_map.map_id)] == [home.point_id, patrol.point_id]
    assert stored_route is not None
    assert stored_route[0].metadata == route.metadata
    assert stored_route[1][1].metadata == {"label": "活动区"}
    assert stored_route[1][1].provider == "mock"
    assert stored_route[1][1].real_motion_enabled is False


def test_activating_new_map_replaces_old_map_and_invalidates_history(tmp_path: Path) -> None:
    _path, database_url = _database(tmp_path)
    repo = RobotMapRepository(database_url)
    first = RobotMap(map_id="map-old", name="旧地图")
    second = RobotMap(map_id="map-new", name="新地图")
    repo.create_map(first)
    repo.save_point(
        RobotMapPoint(
            point_id="old-observation",
            map_id=first.map_id,
            name="旧观察点",
            point_type=RobotMapPointType.OBSERVATION,
            x=1.0,
            y=1.0,
            yaw=0.0,
        )
    )
    repo.save_route(
        RobotPatrolRoute(
            route_id="old-route",
            map_id=first.map_id,
            name="旧路线",
            status=RobotPatrolRouteStatus.ACTIVE,
        ),
        [RobotPatrolRoutePoint(route_id="old-route", point_id="old-observation", sequence=0)],
    )
    repo.activate_map(first.map_id)
    repo.create_map(second)
    repo.save_point(
        RobotMapPoint(
            point_id="new-home",
            map_id=second.map_id,
            name="新待命点",
            point_type=RobotMapPointType.HOME,
            x=0.0,
            y=0.0,
            yaw=0.0,
        )
    )

    activated = repo.activate_map(second.map_id)

    assert activated.status == RobotMapStatus.ACTIVE
    assert repo.get_active_map() == activated
    assert repo.get_map(first.map_id).status == RobotMapStatus.REPLACED  # type: ignore[union-attr]
    old_point = repo.get_point("old-observation")
    assert old_point is not None
    assert old_point.status == RobotMapPointStatus.INVALID
    assert old_point.invalidated_at is not None
    assert len(repo.list_points(first.map_id, include_invalid=True)) == 1
    assert repo.list_points(first.map_id, include_invalid=False) == []
    old_route = repo.get_route("old-route")
    assert old_route is not None
    assert old_route[0].status == RobotPatrolRouteStatus.INVALID


def test_incident_bundle_links_case_task_events_and_dialogue(tmp_path: Path) -> None:
    _path, database_url = _database(tmp_path)
    task_repo = RobotTaskRepository(database_url)
    _map_repo, navigation_repo, emergency_repo = _initialize_all(database_url)
    task = RobotTask(
        task_id="task-incident-001",
        source_event_id="incident-001",
        trace_id="trace-001",
    )
    task_repo.create_task(task)
    emergency_repo.save_case(
        RobotEmergencyCase(
            case_id="case-001",
            incident_id="incident-001",
            robot_task_id=task.task_id,
            alarm_id="alarm-001",
            camera_id="camera-01",
            area_id="elderly_activity_area",
            observation_point_id="observation-001",
            home_point_id="home-001",
            execution_state=RobotEmergencyExecutionState.NAVIGATING,
            navigation_state=RobotNavigationExecutionState.NAVIGATING,
            control_owner=RobotControlOwner.NAVIGATION,
            metadata={"source": {"fall_prob": 0.96}},
        )
    )
    navigation_repo.add_event(
        RobotNavigationEvent(
            event_id="nav-event-001",
            task_id=task.task_id,
            incident_id="incident-001",
            event_type="navigation.updated",
            execution_state=RobotNavigationExecutionState.NAVIGATING,
            navigation_state=RobotNavigationExecutionState.NAVIGATING,
            control_owner=RobotControlOwner.NAVIGATION,
            sequence=1,
            metadata={"path": ["home-001", "observation-001"]},
        )
    )
    emergency_repo.add_dialogue_turn(
        RobotDialogueTurn(
            turn_id="turn-001",
            incident_id="incident-001",
            robot_task_id=task.task_id,
            role=RobotDialogueRole.USER,
            text="需要帮助",
            intent=RobotDialogueIntent.NEED_HELP,
            confidence=1.0,
            conversation_complete=True,
            metadata={"source": "mock-script"},
        )
    )

    bundle = emergency_repo.get_incident_bundle("incident-001")

    assert bundle is not None
    assert bundle.robot_task_id == task.task_id
    assert bundle.emergency_case.metadata == {"source": {"fall_prob": 0.96}}
    assert bundle.navigation_events[0].metadata == {"path": ["home-001", "observation-001"]}
    assert bundle.dialogue_turns[0].metadata == {"source": "mock-script"}
    assert bundle.provider == "mock"
    assert bundle.real_motion_enabled is False


def test_data_survives_sqlite_reopen_and_mock_invariant_is_enforced(tmp_path: Path) -> None:
    _path, database_url = _database(tmp_path)
    map_repo, navigation_repo, emergency_repo = _initialize_all(database_url)
    map_repo.create_map(RobotMap(map_id="map-persisted", name="持久化地图"))
    map_repo.activate_map("map-persisted")
    navigation_repo.add_event(
        RobotNavigationEvent(
            event_id="event-persisted",
            event_type="navigation.created",
            navigation_state=RobotNavigationExecutionState.CREATED,
        )
    )
    emergency_repo.save_case(
        RobotEmergencyCase(case_id="case-persisted", incident_id="incident-persisted")
    )

    reopened_map, reopened_navigation, reopened_emergency = _initialize_all(database_url)

    assert reopened_map.get_active_map().map_id == "map-persisted"  # type: ignore[union-attr]
    assert reopened_navigation.get_event("event-persisted") is not None
    assert reopened_emergency.get_case_by_incident_id("incident-persisted") is not None
    assert RobotNavigationCapability().real_motion_enabled is False
    with pytest.raises(ValidationError):
        RobotNavigationCapability(real_motion_enabled=True)  # type: ignore[arg-type]
