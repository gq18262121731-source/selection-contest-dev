from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "robot_mock_demo.db"
FORMAL_DATABASE = (PROJECT_ROOT / "data" / "app.db").resolve()
DEMO_PREFIX = "robot-demo-"
STATIC_IDS = {
    "map_mock_0001",
    f"{DEMO_PREFIX}home",
    f"{DEMO_PREFIX}observation-elderly-activity",
    f"{DEMO_PREFIX}patrol-01",
    f"{DEMO_PREFIX}patrol-02",
    f"{DEMO_PREFIX}patrol-03",
    f"{DEMO_PREFIX}patrol-route",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safely clean isolated robot Mock demo records.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument(
        "--all-demo",
        action="store_true",
        help="Also remove the fixed map, points, and route so the database can be reseeded.",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def safe_database_path(value: Path) -> Path:
    resolved = value.expanduser().resolve()
    if resolved == FORMAL_DATABASE:
        raise SystemExit("Refusing to clean the formal data/app.db database.")
    if resolved.name != "robot_mock_demo.db":
        raise SystemExit("The cleanup tool only accepts a database named robot_mock_demo.db.")
    return resolved


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        is not None
    )


def count_tables(connection: sqlite3.Connection) -> dict[str, int]:
    result: dict[str, int] = {}
    for table in (
        "robot_maps",
        "robot_map_points",
        "robot_patrol_routes",
        "robot_patrol_route_points",
        "robot_tasks",
        "robot_task_timeline",
        "robot_observations",
        "robot_navigation_events",
        "robot_emergency_cases",
        "robot_dialogue_turns",
    ):
        result[table] = (
            int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            if table_exists(connection, table)
            else 0
        )
    return result


def placeholders(values: list[str]) -> str:
    return ",".join("?" for _ in values)


def clean(database: Path, *, all_demo: bool) -> dict[str, Any]:
    if not database.exists():
        return {
            "provider": "mock",
            "real_motion_enabled": False,
            "database": str(database),
            "before": {},
            "after": {},
            "deleted": {},
            "all_demo": all_demo,
            "message": "demo database does not exist",
        }

    with sqlite3.connect(str(database)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        before = count_tables(connection)
        task_ids = (
            [
                str(row["task_id"])
                for row in connection.execute(
                    """
                    SELECT task_id
                    FROM robot_tasks
                    WHERE source_event_id LIKE ?
                       OR trace_id LIKE ?
                       OR alarm_event_id LIKE ?
                    """,
                    (f"%{DEMO_PREFIX}%", f"%{DEMO_PREFIX}%", f"%{DEMO_PREFIX}%"),
                ).fetchall()
            ]
            if table_exists(connection, "robot_tasks")
            else []
        )
        incident_ids = (
            [
                str(row["incident_id"])
                for row in connection.execute(
                    "SELECT incident_id FROM robot_emergency_cases WHERE incident_id LIKE ?",
                    (f"{DEMO_PREFIX}%",),
                ).fetchall()
            ]
            if table_exists(connection, "robot_emergency_cases")
            else []
        )
        if incident_ids and table_exists(connection, "robot_emergency_cases"):
            linked_task_ids = [
                str(row["robot_task_id"])
                for row in connection.execute(
                    f"""
                    SELECT robot_task_id
                    FROM robot_emergency_cases
                    WHERE incident_id IN ({placeholders(incident_ids)})
                      AND robot_task_id IS NOT NULL
                    """,
                    incident_ids,
                ).fetchall()
            ]
            task_ids = sorted(set(task_ids + linked_task_ids))

        connection.execute("BEGIN IMMEDIATE")
        if incident_ids and table_exists(connection, "robot_dialogue_turns"):
            connection.execute(
                f"DELETE FROM robot_dialogue_turns WHERE incident_id IN ({placeholders(incident_ids)})",
                incident_ids,
            )
        if table_exists(connection, "robot_navigation_events"):
            clauses: list[str] = ["event_id LIKE ?"]
            values: list[str] = [f"{DEMO_PREFIX}%"]
            if task_ids:
                clauses.append(f"task_id IN ({placeholders(task_ids)})")
                values.extend(task_ids)
            if incident_ids:
                clauses.append(f"incident_id IN ({placeholders(incident_ids)})")
                values.extend(incident_ids)
            connection.execute(
                "DELETE FROM robot_navigation_events WHERE " + " OR ".join(clauses),
                values,
            )
        if incident_ids and table_exists(connection, "robot_emergency_cases"):
            connection.execute(
                f"DELETE FROM robot_emergency_cases WHERE incident_id IN ({placeholders(incident_ids)})",
                incident_ids,
            )
        if task_ids:
            for table in ("robot_observations", "robot_task_timeline"):
                if table_exists(connection, table):
                    connection.execute(
                        f"DELETE FROM {table} WHERE task_id IN ({placeholders(task_ids)})",
                        task_ids,
                    )
            connection.execute(
                f"DELETE FROM robot_tasks WHERE task_id IN ({placeholders(task_ids)})",
                task_ids,
            )

        if all_demo:
            route_ids = [f"{DEMO_PREFIX}patrol-route"]
            point_ids = [
                f"{DEMO_PREFIX}home",
                f"{DEMO_PREFIX}observation-elderly-activity",
                f"{DEMO_PREFIX}patrol-01",
                f"{DEMO_PREFIX}patrol-02",
                f"{DEMO_PREFIX}patrol-03",
            ]
            if table_exists(connection, "robot_patrol_route_points"):
                connection.execute(
                    f"DELETE FROM robot_patrol_route_points WHERE route_id IN ({placeholders(route_ids)})",
                    route_ids,
                )
            if table_exists(connection, "robot_patrol_routes"):
                connection.execute(
                    f"""
                    DELETE FROM robot_patrol_routes
                    WHERE route_id IN ({placeholders(route_ids)})
                      AND provider = 'mock'
                      AND real_motion_enabled = 0
                      AND json_extract(metadata_json, '$.demo') = 1
                    """,
                    route_ids,
                )
            if table_exists(connection, "robot_map_points"):
                connection.execute(
                    f"""
                    DELETE FROM robot_map_points
                    WHERE point_id IN ({placeholders(point_ids)})
                      AND provider = 'mock'
                      AND real_motion_enabled = 0
                      AND json_extract(metadata_json, '$.demo') = 1
                    """,
                    point_ids,
                )
            if table_exists(connection, "robot_maps"):
                connection.execute(
                    """
                    DELETE FROM robot_maps
                    WHERE map_id = ?
                      AND provider = 'mock'
                      AND real_motion_enabled = 0
                      AND json_extract(metadata_json, '$.demo') = 1
                    """,
                    ("map_mock_0001",),
                )
        connection.commit()
        after = count_tables(connection)

    deleted = {table: before.get(table, 0) - after.get(table, 0) for table in before}
    return {
        "provider": "mock",
        "real_motion_enabled": False,
        "database": str(database),
        "before": before,
        "after": after,
        "deleted": deleted,
        "all_demo": all_demo,
        "protected_formal_database": str(FORMAL_DATABASE),
        "fixed_ids": sorted(STATIC_IDS),
        "cleaned_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    args = parse_args()
    database = safe_database_path(args.database)
    summary = clean(database, all_demo=args.all_demo)
    payload = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
