from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from backend.models.robot_navigation_model import (
    RobotControlOwner,
    RobotNavigationEvent,
    RobotNavigationExecutionState,
)
from backend.repositories.sqlite_base import SQLiteRepositoryBase


class RobotNavigationRepository(SQLiteRepositoryBase):
    """Append-only navigation event persistence for Mock execution history."""

    def __init__(self, database_url: str) -> None:
        self._lock = RLock()
        super().__init__(database_url)

    def add_event(
        self,
        event: RobotNavigationEvent,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> RobotNavigationEvent:
        with self._lock, self.connection_scope(connection) as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO robot_navigation_events (
                    event_id, task_id, incident_id, event_type, execution_state,
                    navigation_state, x, y, yaw, control_owner, error_code,
                    provider, real_motion_enabled, sequence, message,
                    metadata_json, occurred_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.task_id,
                    event.incident_id,
                    event.event_type,
                    event.execution_state,
                    event.navigation_state.value if event.navigation_state else None,
                    event.x,
                    event.y,
                    event.yaw,
                    event.control_owner.value,
                    event.error_code,
                    event.provider,
                    int(event.real_motion_enabled),
                    event.sequence,
                    event.message,
                    self.dump_json(event.metadata),
                    self._format_datetime(event.occurred_at),
                    self._format_datetime(event.created_at),
                ),
            )
            if cursor.lastrowid:
                return event.model_copy(update={"id": int(cursor.lastrowid)})
            row = connection.execute(
                "SELECT * FROM robot_navigation_events WHERE event_id = ?",
                (event.event_id,),
            ).fetchone()
        return self.row_to_event(row) if row else event

    def get_event(
        self,
        event_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> RobotNavigationEvent | None:
        with self._lock, self.connection_scope(connection) as connection:
            row = connection.execute(
                "SELECT * FROM robot_navigation_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return self.row_to_event(row) if row else None

    def list_for_task(self, task_id: str) -> list[RobotNavigationEvent]:
        return self._list("task_id = ?", (task_id,))

    def list_for_incident(self, incident_id: str) -> list[RobotNavigationEvent]:
        return self._list("incident_id = ?", (incident_id,))

    def _list(self, where: str, params: tuple[Any, ...]) -> list[RobotNavigationEvent]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM robot_navigation_events WHERE {where} "
                "ORDER BY sequence ASC, occurred_at ASC, id ASC",
                params,
            ).fetchall()
        return [self.row_to_event(row) for row in rows]

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS robot_navigation_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    task_id TEXT,
                    incident_id TEXT,
                    event_type TEXT NOT NULL,
                    execution_state TEXT,
                    navigation_state TEXT,
                    x REAL,
                    y REAL,
                    yaw REAL,
                    control_owner TEXT NOT NULL DEFAULT 'NONE',
                    error_code TEXT,
                    provider TEXT NOT NULL DEFAULT 'mock' CHECK(provider = 'mock'),
                    real_motion_enabled INTEGER NOT NULL DEFAULT 0 CHECK(real_motion_enabled = 0),
                    sequence INTEGER NOT NULL DEFAULT 0,
                    message TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    occurred_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES robot_tasks(task_id)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_robot_navigation_events_task_sequence "
                "ON robot_navigation_events(task_id, sequence, id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_robot_navigation_events_incident_sequence "
                "ON robot_navigation_events(incident_id, sequence, id)"
            )
            connection.commit()

    @classmethod
    def row_to_event(cls, row: sqlite3.Row) -> RobotNavigationEvent:
        return RobotNavigationEvent(
            id=int(row["id"]),
            event_id=row["event_id"],
            task_id=row["task_id"],
            incident_id=row["incident_id"],
            event_type=row["event_type"],
            execution_state=RobotNavigationExecutionState(row["execution_state"]) if row["execution_state"] else None,
            navigation_state=RobotNavigationExecutionState(row["navigation_state"]) if row["navigation_state"] else None,
            x=float(row["x"]) if row["x"] is not None else None,
            y=float(row["y"]) if row["y"] is not None else None,
            yaw=float(row["yaw"]) if row["yaw"] is not None else None,
            control_owner=RobotControlOwner(row["control_owner"]),
            error_code=row["error_code"],
            provider=row["provider"],
            real_motion_enabled=bool(row["real_motion_enabled"]),
            sequence=int(row["sequence"]),
            message=row["message"] or "",
            metadata=cls.load_json(row["metadata_json"]),
            occurred_at=cls._parse_datetime(row["occurred_at"]),
            created_at=cls._parse_datetime(row["created_at"]),
        )

    @staticmethod
    def _format_datetime(value: datetime) -> str:
        normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return normalized.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
