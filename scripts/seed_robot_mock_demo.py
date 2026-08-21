from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "robot_mock_demo.db"
FORMAL_DATABASE = (PROJECT_ROOT / "data" / "app.db").resolve()
DEMO_PREFIX = "robot-demo-"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.models.robot_navigation_model import (  # noqa: E402
    RobotMap,
    RobotMapPoint,
    RobotMapPointType,
    RobotMapStatus,
    RobotPatrolRoute,
    RobotPatrolRoutePoint,
    RobotPatrolRouteStatus,
)
from backend.repositories.robot_emergency_repo import RobotEmergencyRepository  # noqa: E402
from backend.repositories.robot_map_repo import RobotMapRepository  # noqa: E402
from backend.repositories.robot_navigation_repo import RobotNavigationRepository  # noqa: E402
from backend.repositories.robot_task_repo import RobotTaskRepository  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed the isolated robot Mock demonstration database.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--map-id", default="map_mock_0001")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def safe_database_path(value: Path) -> Path:
    resolved = value.expanduser().resolve()
    if resolved == FORMAL_DATABASE:
        raise SystemExit("Refusing to seed the formal data/app.db database.")
    if resolved.name != "robot_mock_demo.db":
        raise SystemExit("The demo seed only accepts a database named robot_mock_demo.db.")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def metadata(kind: str, **values: Any) -> dict[str, Any]:
    return {
        "demo": True,
        "demo_id_prefix": DEMO_PREFIX,
        "demo_kind": kind,
        "camera_id": "camera_01",
        "area_id": "elderly_activity_area",
        "area_name": "养老活动区",
        **values,
    }


def ensure_no_unfinished_demo_tasks(database: Path) -> None:
    if not database.exists():
        return
    with sqlite3.connect(str(database)) as connection:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='robot_tasks'"
        ).fetchone()
        if not exists:
            return
        unfinished = connection.execute(
            """
            SELECT task_id, status
            FROM robot_tasks
            WHERE source_event_id LIKE ?
              AND status NOT IN ('COMPLETED', 'FAILED', 'CANCELLED')
            ORDER BY created_at
            """,
            (f"{DEMO_PREFIX}%",),
        ).fetchall()
    if unfinished:
        detail = ", ".join(f"{task_id}:{status}" for task_id, status in unfinished)
        raise SystemExit(
            "Unfinished Mock demo tasks exist. Run cleanup_robot_mock_demo.py first: " + detail
        )


def seed(database: Path, map_id: str) -> dict[str, Any]:
    database_url = f"sqlite:///{database.as_posix()}"
    task_repository = RobotTaskRepository(database_url)
    map_repository = RobotMapRepository(database_url)
    RobotNavigationRepository(database_url)
    RobotEmergencyRepository(database_url)

    ensure_no_unfinished_demo_tasks(database)
    now = datetime.now(timezone.utc)
    existing_active = map_repository.get_active_map()
    if existing_active and existing_active.map_id != map_id and not existing_active.metadata.get("demo"):
        raise SystemExit("Refusing to replace a non-demo active map in the demonstration database.")

    robot_map = RobotMap(
        map_id=map_id,
        name="养老活动区演示地图",
        status=RobotMapStatus.ACTIVE,
        revision=1,
        metadata=metadata("map", gateway_map_id=map_id),
        activated_at=now,
    )
    existing_map = map_repository.get_map(map_id)
    if existing_map is None:
        map_repository.create_map(robot_map)
    else:
        map_repository.update_map(
            existing_map.model_copy(
                update={
                    "name": robot_map.name,
                    "status": RobotMapStatus.ACTIVE,
                    "metadata": robot_map.metadata,
                    "activated_at": existing_map.activated_at or now,
                    "replaced_at": None,
                }
            )
        )

    points = [
        RobotMapPoint(
            point_id=f"{DEMO_PREFIX}home",
            map_id=map_id,
            name="机器人待命点",
            point_type=RobotMapPointType.HOME,
            x=1.0,
            y=1.0,
            yaw=0.0,
            metadata=metadata("home"),
        ),
        RobotMapPoint(
            point_id=f"{DEMO_PREFIX}observation-elderly-activity",
            map_id=map_id,
            name="活动区观察点",
            point_type=RobotMapPointType.OBSERVATION,
            x=6.0,
            y=3.0,
            yaw=1.57,
            metadata=metadata("observation", observation_mapping=True),
        ),
        RobotMapPoint(
            point_id=f"{DEMO_PREFIX}patrol-01",
            map_id=map_id,
            name="客厅巡逻点",
            point_type=RobotMapPointType.PATROL,
            x=2.0,
            y=1.5,
            yaw=0.0,
            metadata=metadata("patrol", sequence=1),
        ),
        RobotMapPoint(
            point_id=f"{DEMO_PREFIX}patrol-02",
            map_id=map_id,
            name="走廊巡逻点",
            point_type=RobotMapPointType.PATROL,
            x=4.0,
            y=2.5,
            yaw=0.4,
            metadata=metadata("patrol", sequence=2),
        ),
        RobotMapPoint(
            point_id=f"{DEMO_PREFIX}patrol-03",
            map_id=map_id,
            name="门口巡逻点",
            point_type=RobotMapPointType.PATROL,
            x=7.0,
            y=4.0,
            yaw=3.14,
            metadata=metadata("patrol", sequence=3),
        ),
    ]
    for point in points:
        map_repository.save_point(point)

    route_id = f"{DEMO_PREFIX}patrol-route"
    patrol_ids = [point.point_id for point in points if point.point_type == RobotMapPointType.PATROL]
    route = RobotPatrolRoute(
        route_id=route_id,
        map_id=map_id,
        name="日常巡查路线",
        status=RobotPatrolRouteStatus.ACTIVE,
        metadata=metadata("route"),
    )
    map_repository.save_route(
        route,
        [
            RobotPatrolRoutePoint(
                route_id=route_id,
                point_id=point_id,
                sequence=index,
                metadata=metadata("route_point"),
            )
            for index, point_id in enumerate(patrol_ids)
        ],
    )

    summary = {
        "provider": "mock",
        "real_motion_enabled": False,
        "database": str(database),
        "map_id": map_id,
        "point_ids": [point.point_id for point in points],
        "route_id": route_id,
        "camera_id": "camera_01",
        "area_id": "elderly_activity_area",
        "unfinished_demo_tasks": len(
            [
                task
                for task in task_repository.list_tasks(limit=1000)
                if task.source_event_id.startswith(DEMO_PREFIX)
                and task.status.value not in {"COMPLETED", "FAILED", "CANCELLED"}
            ]
        ),
        "seeded_at": now.isoformat(),
    }
    if summary["unfinished_demo_tasks"] != 0:
        raise SystemExit("The seeded database contains unfinished old Mock tasks.")
    return summary


def main() -> int:
    args = parse_args()
    database = safe_database_path(args.database)
    summary = seed(database, args.map_id)
    payload = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
