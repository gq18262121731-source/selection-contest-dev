from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.models.robot_model import RobotTask, RobotTaskStatus
from backend.models.robot_navigation_model import (
    RobotControlOwner,
    RobotMap,
    RobotMapPoint,
    RobotMapPointType,
    RobotMapStatus,
    RobotNavigationCapability,
    RobotNavigationEvent,
    RobotNavigationExecutionState,
    RobotNavigationState,
    RobotPatrolRoute,
    RobotPatrolRoutePoint,
    RobotPatrolRouteStatus,
)
from backend.models.robot_emergency_model import (
    RobotDialogueIntent,
    RobotDialogueRole,
    RobotDialogueTurn,
    RobotEmergencyCase,
    RobotEmergencyCaseStatus,
)
from backend.repositories.robot_emergency_repo import RobotEmergencyRepository
from backend.repositories.robot_map_repo import RobotMapRepository
from backend.repositories.robot_navigation_repo import RobotNavigationRepository
from backend.repositories.robot_task_repo import RobotTaskRepository


def _database_url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{(tmp_path / 'robot-navigation.db').as_posix()}"


def test_mock_models_reject_real_motion_enabled() -> None:
    assert RobotNavigationState().real_motion_enabled is False
    with pytest.raises(ValidationError):
        RobotNavigationCapability(real_motion_enabled=True)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        RobotMap(name="invalid", real_motion_enabled=True)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        RobotTask(
            task_id="invalid_real_task",
            source_event_id="invalid_real_event",
            trace_id="invalid_real_trace",
            real_motion_enabled=True,  # type: ignore[arg-type]
        )


def test_robot_task_auxiliary_fields_survive_repository_restart(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    repository = RobotTaskRepository(database_url)
    repository.create_task(
        RobotTask(
            task_id="navigation_task_001",
            source_event_id="navigation_event_001",
            trace_id="navigation_trace_001",
            execution_state=RobotNavigationExecutionState.NAVIGATING,
            control_owner=RobotControlOwner.NAVIGATION,
            provider="mock",
        )
    )

    restored = RobotTaskRepository(database_url).get_task("navigation_task_001")

    assert restored is not None
    assert restored.execution_state == RobotNavigationExecutionState.NAVIGATING
    assert restored.control_owner == RobotControlOwner.NAVIGATION
    assert restored.provider == "mock"
    assert restored.real_motion_enabled is False


def test_repository_initialization_is_idempotent_and_creates_expected_tables(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)

    for _ in range(2):
        RobotMapRepository(database_url)
        RobotNavigationRepository(database_url)
        RobotEmergencyRepository(database_url)

    with sqlite3.connect(tmp_path / "robot-navigation.db") as connection:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
    assert {
        "robot_maps",
        "robot_map_points",
        "robot_patrol_routes",
        "robot_patrol_route_points",
        "robot_navigation_events",
        "robot_emergency_cases",
        "robot_dialogue_turns",
    }.issubset(tables)


def test_map_points_and_route_survive_repository_restart(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    repository = RobotMapRepository(database_url)
    saved_map = repository.create_map(
        RobotMap(
            map_id="map_mock_default",
            name="演示区地图",
            status=RobotMapStatus.DRAFT,
            metadata={"revision": 1},
        )
    )
    home = repository.save_point(
        RobotMapPoint(
            point_id="robot_home",
            map_id=saved_map.map_id,
            name="待命区",
            point_type=RobotMapPointType.HOME,
            x=0.0,
            y=0.0,
            yaw=0.0,
        )
    )
    observation = repository.save_point(
        RobotMapPoint(
            point_id="fall_observation_point",
            map_id=saved_map.map_id,
            name="养老活动区观察点",
            point_type=RobotMapPointType.OBSERVATION,
            x=1.2,
            y=2.4,
            yaw=1.57,
        )
    )
    repository.save_route(
        RobotPatrolRoute(
            route_id="route_demo",
            name="演示路线",
            map_id=saved_map.map_id,
            status=RobotPatrolRouteStatus.VALID,
        ),
        [
            RobotPatrolRoutePoint(route_id="route_demo", point_id=observation.point_id, sequence=0),
            RobotPatrolRoutePoint(route_id="route_demo", point_id=home.point_id, sequence=1),
        ],
    )
    repository.activate_map(saved_map.map_id)

    restarted = RobotMapRepository(database_url)
    restored_map = restarted.get_active_map()
    restored_route_bundle = restarted.get_route("route_demo")

    assert restored_map is not None
    assert restored_map.map_id == "map_mock_default"
    assert restored_map.provider == "mock"
    assert restored_map.real_motion_enabled is False
    assert [point.point_id for point in restarted.list_points(saved_map.map_id)] == [
        "robot_home",
        "fall_observation_point",
    ]
    assert restored_route_bundle is not None
    restored_route, restored_route_points = restored_route_bundle
    assert [point.point_id for point in restored_route_points] == ["fall_observation_point", "robot_home"]
    assert restored_route.real_motion_enabled is False


def test_navigation_events_survive_repository_restart(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    repository = RobotNavigationRepository(database_url)
    saved = repository.add_event(
        RobotNavigationEvent(
            event_id="navigation_event_001",
            task_id="task_001",
            incident_id="incident_001",
            event_type="navigation.started",
            execution_state=RobotNavigationExecutionState.NAVIGATING,
            navigation_state=RobotNavigationExecutionState.NAVIGATING,
            x=1.0,
            y=2.0,
            yaw=0.5,
            control_owner=RobotControlOwner.NAVIGATION,
            error_code=None,
            metadata={"scenario": "navigation_success"},
        )
    )

    restarted = RobotNavigationRepository(database_url)
    events = restarted.list_for_task("task_001")

    assert saved.id is not None
    assert len(events) == 1
    assert events[0].execution_state == RobotNavigationExecutionState.NAVIGATING
    assert events[0].control_owner == RobotControlOwner.NAVIGATION
    assert (events[0].x, events[0].y, events[0].yaw) == (1.0, 2.0, 0.5)
    assert events[0].provider == "mock"
    assert events[0].real_motion_enabled is False


def test_emergency_case_upsert_and_dialogue_survive_repository_restart(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    repository = RobotEmergencyRepository(database_url)
    original = repository.save_case(
        RobotEmergencyCase(
            case_id="case_001",
            incident_id="incident_001",
            robot_task_id="task_001",
            camera_id="camera_01",
            area_id="elderly_activity_area",
            area_name="养老活动区",
            observation_point_id="fall_observation_point",
            home_point_id="robot_home",
            risk_level="high",
            fall_probability=0.96,
        )
    )
    repository.save_case(
        original.model_copy(
            update={
                "execution_state": RobotNavigationExecutionState.WAITING_RESPONSE,
                "navigation_state": RobotNavigationExecutionState.WAITING_RESPONSE,
                "status": RobotEmergencyCaseStatus.ACTIVE,
            }
        )
    )
    repository.add_dialogue_turn(
        RobotDialogueTurn(
            turn_id="turn_001",
            incident_id="incident_001",
            robot_task_id="task_001",
            role=RobotDialogueRole.USER,
            text="我没事",
            input_text="我没事",
            intent=RobotDialogueIntent.SAFE_RESPONSE,
            confidence=0.95,
            reply_text="请保持原位，等待管理员确认。",
            asr_status="mock_completed",
            tts_status="mock_completed",
        )
    )

    restarted = RobotEmergencyRepository(database_url)
    restored = restarted.get_case_by_incident_id("incident_001")
    dialogue = restarted.list_dialogue_turns("incident_001")

    assert restored is not None
    assert restored.case_id == "case_001"
    assert restored.execution_state == RobotNavigationExecutionState.WAITING_RESPONSE
    assert restored.status == RobotEmergencyCaseStatus.ACTIVE
    assert restored.risk_level == "high"
    assert restored.fall_probability == 0.96
    assert restored.real_motion_enabled is False
    assert [turn.turn_id for turn in dialogue] == ["turn_001"]
    assert dialogue[0].intent == RobotDialogueIntent.SAFE_RESPONSE
    assert dialogue[0].asr_status == "mock_completed"
    assert dialogue[0].tts_status == "mock_completed"
    assert dialogue[0].real_motion_enabled is False


def test_robot_task_repository_adds_auxiliary_columns_to_legacy_table(tmp_path: Path) -> None:
    database_path = tmp_path / "robot-navigation.db"
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE robot_tasks (
                task_id TEXT PRIMARY KEY,
                gateway_task_id TEXT,
                source_event_id TEXT NOT NULL UNIQUE,
                trace_id TEXT NOT NULL,
                alarm_event_id TEXT,
                elder_id TEXT NOT NULL DEFAULT '',
                elder_name TEXT NOT NULL DEFAULT '',
                robot_id TEXT,
                task_type TEXT NOT NULL DEFAULT 'confirm_fall',
                location TEXT NOT NULL DEFAULT 'unknown',
                risk_level TEXT NOT NULL DEFAULT 'unknown',
                status TEXT NOT NULL,
                current_step TEXT NOT NULL,
                outcome TEXT,
                last_sequence INTEGER NOT NULL DEFAULT 0,
                error_code TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO robot_tasks (
                task_id, source_event_id, trace_id, status, current_step,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("legacy_task", "legacy_event", "legacy_trace", "QUEUED", "RECEIVED", now, now),
        )
        connection.commit()

    repository = RobotTaskRepository(_database_url(tmp_path))
    task = repository.get_task("legacy_task")
    with sqlite3.connect(database_path) as connection:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(robot_tasks)")}

    assert {"execution_state", "control_owner", "provider", "real_motion_enabled"}.issubset(columns)
    assert task is not None
    assert task.status == RobotTaskStatus.QUEUED
    assert task.execution_state is None
    assert task.control_owner == RobotControlOwner.NONE
    assert task.provider is None
    assert task.real_motion_enabled is False


def test_sqlite_rejects_real_motion_for_mock_domain_tables(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    RobotMapRepository(database_url)
    with sqlite3.connect(tmp_path / "robot-navigation.db") as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO robot_maps (
                    map_id, name, status, revision, provider,
                    real_motion_enabled, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "invalid_real_map",
                    "invalid",
                    "draft",
                    1,
                    "mock",
                    1,
                    "{}",
                    datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
