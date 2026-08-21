from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from backend.models.robot_model import (
    RobotObservation,
    RobotTask,
    RobotTaskOutcome,
    RobotTaskStatus,
    RobotTaskStep,
    RobotTaskTimeline,
)
from backend.repositories.sqlite_base import SQLiteRepositoryBase


class RobotTaskRepository(SQLiteRepositoryBase):
    """SQLite persistence for main-system robot tasks."""

    def __init__(self, database_url: str) -> None:
        self._lock = RLock()
        super().__init__(database_url)

    def create_task(
        self,
        task: RobotTask,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> RobotTask:
        with self._lock, self.connection_scope(connection) as connection:
            connection.execute(
                """
                INSERT INTO robot_tasks (
                    task_id, gateway_task_id, source_event_id, trace_id,
                    alarm_event_id, elder_id, elder_name, robot_id, task_type,
                    location, risk_level, status, current_step, outcome,
                    last_sequence, error_code, error_message,
                    execution_state, control_owner, provider, real_motion_enabled,
                    created_at, started_at, completed_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._task_values(task),
            )
        return task

    def get_task(
        self,
        task_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> RobotTask | None:
        with self._lock, self.connection_scope(connection) as connection:
            row = connection.execute(
                "SELECT * FROM robot_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._row_to_task(row) if row else None

    def get_by_source_event_id(
        self,
        source_event_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> RobotTask | None:
        with self._lock, self.connection_scope(connection) as connection:
            row = connection.execute(
                "SELECT * FROM robot_tasks WHERE source_event_id = ?",
                (source_event_id,),
            ).fetchone()
        return self._row_to_task(row) if row else None

    def find_for_callback(
        self,
        *,
        external_task_id: str | None,
        gateway_task_id: str | None,
        source_event_id: str | None,
    ) -> RobotTask | None:
        with self._lock, self._connect() as connection:
            if external_task_id:
                row = connection.execute(
                    "SELECT * FROM robot_tasks WHERE task_id = ?",
                    (external_task_id,),
                ).fetchone()
                if row:
                    return self._row_to_task(row)
            if gateway_task_id:
                row = connection.execute(
                    "SELECT * FROM robot_tasks WHERE gateway_task_id = ?",
                    (gateway_task_id,),
                ).fetchone()
                if row:
                    return self._row_to_task(row)
            if source_event_id:
                row = connection.execute(
                    "SELECT * FROM robot_tasks WHERE source_event_id = ?",
                    (source_event_id,),
                ).fetchone()
                if row:
                    return self._row_to_task(row)
        return None

    def list_tasks(
        self,
        *,
        status: str | None = None,
        elder_id: str | None = None,
        outcome: str | None = None,
        limit: int = 100,
    ) -> list[RobotTask]:
        query = ["SELECT * FROM robot_tasks WHERE 1 = 1"]
        params: list[Any] = []
        if status:
            query.append("AND status = ?")
            params.append(status)
        if elder_id:
            query.append("AND elder_id = ?")
            params.append(elder_id)
        if outcome:
            query.append("AND outcome = ?")
            params.append(outcome)
        query.append("ORDER BY created_at DESC LIMIT ?")
        params.append(max(1, min(500, int(limit))))
        with self._lock, self._connect() as connection:
            rows = connection.execute("\n".join(query), tuple(params)).fetchall()
        return [self._row_to_task(row) for row in rows]

    def update_task(
        self,
        task: RobotTask,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> RobotTask:
        task = task.model_copy(update={"updated_at": datetime.now(timezone.utc)})
        with self._lock, self.connection_scope(connection) as connection:
            connection.execute(
                """
                UPDATE robot_tasks
                SET gateway_task_id = ?,
                    source_event_id = ?,
                    trace_id = ?,
                    alarm_event_id = ?,
                    elder_id = ?,
                    elder_name = ?,
                    robot_id = ?,
                    task_type = ?,
                    location = ?,
                    risk_level = ?,
                    status = ?,
                    current_step = ?,
                    outcome = ?,
                    last_sequence = ?,
                    error_code = ?,
                    error_message = ?,
                    execution_state = ?,
                    control_owner = ?,
                    provider = ?,
                    real_motion_enabled = ?,
                    created_at = ?,
                    started_at = ?,
                    completed_at = ?,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (*self._task_values(task)[1:], task.task_id),
            )
        return task

    def get_timeline_by_callback_id(
        self,
        callback_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> RobotTaskTimeline | None:
        with self._lock, self.connection_scope(connection) as connection:
            row = connection.execute(
                "SELECT * FROM robot_task_timeline WHERE callback_id = ?",
                (callback_id,),
            ).fetchone()
        return self._row_to_timeline(row) if row else None

    def add_timeline(
        self,
        item: RobotTaskTimeline,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> RobotTaskTimeline:
        with self._lock, self.connection_scope(connection) as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO robot_task_timeline (
                    task_id, callback_id, sequence, status, step, message,
                    occurred_at, payload, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.task_id,
                    item.callback_id,
                    item.sequence,
                    item.status.value,
                    item.step.value,
                    item.message,
                    self._format_datetime(item.occurred_at),
                    self.dump_json(item.payload),
                    self._format_datetime(item.created_at),
                ),
            )
            if cursor.lastrowid:
                return item.model_copy(update={"id": int(cursor.lastrowid)})
            if item.callback_id:
                row = connection.execute(
                    "SELECT * FROM robot_task_timeline WHERE callback_id = ?",
                    (item.callback_id,),
                ).fetchone()
                if row:
                    return self._row_to_timeline(row)
        return item

    def list_timeline(self, task_id: str) -> list[RobotTaskTimeline]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM robot_task_timeline
                WHERE task_id = ?
                ORDER BY sequence ASC, occurred_at ASC, id ASC
                """,
                (task_id,),
            ).fetchall()
        return [self._row_to_timeline(row) for row in rows]

    def save_observation(self, observation: RobotObservation) -> RobotObservation:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO robot_observations (
                    task_id, snapshot_url, camera_available, voice_available,
                    response_type, transcript, observed_at, raw_payload, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    snapshot_url = excluded.snapshot_url,
                    camera_available = excluded.camera_available,
                    voice_available = excluded.voice_available,
                    response_type = excluded.response_type,
                    transcript = excluded.transcript,
                    observed_at = excluded.observed_at,
                    raw_payload = excluded.raw_payload
                """,
                (
                    observation.task_id,
                    observation.snapshot_url,
                    self._nullable_bool(observation.camera_available),
                    self._nullable_bool(observation.voice_available),
                    observation.response_type.value if observation.response_type else None,
                    observation.transcript,
                    self._format_datetime(observation.observed_at),
                    self.dump_json(observation.raw_payload),
                    self._format_datetime(observation.created_at),
                ),
            )
            connection.commit()
            row_id = cursor.lastrowid or observation.id
        return observation.model_copy(update={"id": row_id})

    def get_observation(self, task_id: str) -> RobotObservation | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM robot_observations WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._row_to_observation(row) if row else None

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS robot_tasks (
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
                    execution_state TEXT,
                    control_owner TEXT NOT NULL DEFAULT 'NONE',
                    provider TEXT,
                    real_motion_enabled INTEGER NOT NULL DEFAULT 0 CHECK(real_motion_enabled = 0),
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._ensure_task_columns(connection)
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS robot_task_timeline (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    callback_id TEXT UNIQUE,
                    sequence INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    step TEXT NOT NULL,
                    message TEXT NOT NULL DEFAULT '',
                    occurred_at TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES robot_tasks(task_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS robot_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL UNIQUE,
                    snapshot_url TEXT,
                    camera_available INTEGER,
                    voice_available INTEGER,
                    response_type TEXT,
                    transcript TEXT,
                    observed_at TEXT NOT NULL,
                    raw_payload TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES robot_tasks(task_id)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_robot_tasks_status_created ON robot_tasks(status, created_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_robot_tasks_gateway_task_id ON robot_tasks(gateway_task_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_robot_timeline_task_sequence ON robot_task_timeline(task_id, sequence ASC)"
            )
            connection.commit()

    def _task_values(self, task: RobotTask) -> tuple[Any, ...]:
        return (
            task.task_id,
            task.gateway_task_id,
            task.source_event_id,
            task.trace_id,
            task.alarm_event_id,
            task.elder_id,
            task.elder_name,
            task.robot_id,
            task.task_type,
            task.location,
            task.risk_level,
            task.status.value,
            task.current_step.value,
            task.outcome.value if task.outcome else None,
            task.last_sequence,
            task.error_code,
            task.error_message,
            task.execution_state.value if task.execution_state else None,
            task.control_owner.value,
            task.provider,
            0,
            self._format_datetime(task.created_at),
            self._format_datetime(task.started_at),
            self._format_datetime(task.completed_at),
            self._format_datetime(task.updated_at),
        )

    def _row_to_task(self, row: sqlite3.Row) -> RobotTask:
        return RobotTask(
            task_id=row["task_id"],
            gateway_task_id=row["gateway_task_id"],
            source_event_id=row["source_event_id"],
            trace_id=row["trace_id"],
            alarm_event_id=row["alarm_event_id"],
            elder_id=row["elder_id"] or "",
            elder_name=row["elder_name"] or "",
            robot_id=row["robot_id"],
            task_type=row["task_type"] or "confirm_fall",
            location=row["location"] or "unknown",
            risk_level=row["risk_level"] or "unknown",
            status=RobotTaskStatus(row["status"]),
            current_step=RobotTaskStep(row["current_step"]),
            outcome=RobotTaskOutcome(row["outcome"]) if row["outcome"] else None,
            last_sequence=int(row["last_sequence"] or 0),
            error_code=row["error_code"],
            error_message=row["error_message"],
            execution_state=row["execution_state"],
            control_owner=row["control_owner"] or "NONE",
            provider=row["provider"],
            real_motion_enabled=bool(row["real_motion_enabled"]),
            created_at=self._parse_datetime(row["created_at"]),
            started_at=self._parse_datetime(row["started_at"]) if row["started_at"] else None,
            completed_at=self._parse_datetime(row["completed_at"]) if row["completed_at"] else None,
            updated_at=self._parse_datetime(row["updated_at"]),
        )

    def _row_to_timeline(self, row: sqlite3.Row) -> RobotTaskTimeline:
        return RobotTaskTimeline(
            id=row["id"],
            task_id=row["task_id"],
            callback_id=row["callback_id"],
            sequence=int(row["sequence"] or 0),
            status=RobotTaskStatus(row["status"]),
            step=RobotTaskStep(row["step"]),
            message=row["message"] or "",
            occurred_at=self._parse_datetime(row["occurred_at"]),
            payload=self.load_json(row["payload"]),
            created_at=self._parse_datetime(row["created_at"]),
        )

    @staticmethod
    def _ensure_task_columns(connection: sqlite3.Connection) -> None:
        columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(robot_tasks)")}
        additions = {
            "execution_state": "TEXT",
            "control_owner": "TEXT NOT NULL DEFAULT 'NONE'",
            "provider": "TEXT",
            "real_motion_enabled": "INTEGER NOT NULL DEFAULT 0 CHECK(real_motion_enabled = 0)",
        }
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(f"ALTER TABLE robot_tasks ADD COLUMN {name} {definition}")

    def _row_to_observation(self, row: sqlite3.Row) -> RobotObservation:
        return RobotObservation(
            id=row["id"],
            task_id=row["task_id"],
            snapshot_url=row["snapshot_url"],
            camera_available=self._bool_or_none(row["camera_available"]),
            voice_available=self._bool_or_none(row["voice_available"]),
            response_type=RobotTaskOutcome(row["response_type"]) if row["response_type"] else None,
            transcript=row["transcript"],
            observed_at=self._parse_datetime(row["observed_at"]),
            raw_payload=self.load_json(row["raw_payload"]),
            created_at=self._parse_datetime(row["created_at"]),
        )

    @staticmethod
    def _format_datetime(value: datetime | None) -> str | None:
        if value is None:
            return None
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    @staticmethod
    def _nullable_bool(value: bool | None) -> int | None:
        if value is None:
            return None
        return 1 if value else 0

    @staticmethod
    def _bool_or_none(value: Any) -> bool | None:
        if value is None:
            return None
        return bool(value)
