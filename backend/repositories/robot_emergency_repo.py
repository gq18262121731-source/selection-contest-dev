from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from backend.models.robot_emergency_model import (
    RobotDialogueIntent,
    RobotDialogueRole,
    RobotDialogueTurn,
    RobotEmergencyCase,
    RobotEmergencyCaseStatus,
    RobotEmergencyExecutionState,
    RobotEmergencyIncidentBundle,
)
from backend.models.robot_navigation_model import RobotControlOwner, RobotNavigationExecutionState
from backend.repositories.robot_navigation_repo import RobotNavigationRepository
from backend.repositories.sqlite_base import SQLiteRepositoryBase


class RobotEmergencyRepository(SQLiteRepositoryBase):
    """SQLite persistence and incident-level reads for robot emergency handling."""

    def __init__(self, database_url: str) -> None:
        self._lock = RLock()
        super().__init__(database_url)

    def save_case(
        self,
        case: RobotEmergencyCase,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> RobotEmergencyCase:
        case = case.model_copy(update={"updated_at": datetime.now(timezone.utc)})
        with self._lock, self.connection_scope(connection) as connection:
            connection.execute(
                """
                INSERT INTO robot_emergency_cases (
                    case_id, incident_id, robot_task_id, alarm_id, camera_id,
                    area_id, area_name, observation_point_id, home_point_id,
                    risk_level, fall_probability, status,
                    execution_state, navigation_state, control_owner, dialogue_intent,
                    provider, real_motion_enabled, acknowledged_by, acknowledged_at,
                    resolution, resolved_at, error_code, error_message, metadata_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(incident_id) DO UPDATE SET
                    robot_task_id = excluded.robot_task_id,
                    alarm_id = excluded.alarm_id,
                    camera_id = excluded.camera_id,
                    area_id = excluded.area_id,
                    area_name = excluded.area_name,
                    observation_point_id = excluded.observation_point_id,
                    home_point_id = excluded.home_point_id,
                    risk_level = excluded.risk_level,
                    fall_probability = excluded.fall_probability,
                    status = excluded.status,
                    execution_state = excluded.execution_state,
                    navigation_state = excluded.navigation_state,
                    control_owner = excluded.control_owner,
                    dialogue_intent = excluded.dialogue_intent,
                    provider = excluded.provider,
                    real_motion_enabled = excluded.real_motion_enabled,
                    acknowledged_by = excluded.acknowledged_by,
                    acknowledged_at = excluded.acknowledged_at,
                    resolution = excluded.resolution,
                    resolved_at = excluded.resolved_at,
                    error_code = excluded.error_code,
                    error_message = excluded.error_message,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                self._case_values(case),
            )
            row = connection.execute(
                "SELECT * FROM robot_emergency_cases WHERE incident_id = ?",
                (case.incident_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("saved emergency case disappeared")
        return self._row_to_case(row)

    def get_case_by_incident_id(
        self,
        incident_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> RobotEmergencyCase | None:
        with self._lock, self.connection_scope(connection) as connection:
            row = connection.execute(
                "SELECT * FROM robot_emergency_cases WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
        return self._row_to_case(row) if row else None

    def add_dialogue_turn(
        self,
        turn: RobotDialogueTurn,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> RobotDialogueTurn:
        with self._lock, self.connection_scope(connection) as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO robot_dialogue_turns (
                    turn_id, incident_id, robot_task_id, role, text, input_text,
                    intent, confidence, recommended_action, reply_text,
                    asr_status, tts_status, conversation_complete,
                    provider, real_motion_enabled, metadata_json, occurred_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    turn.turn_id,
                    turn.incident_id,
                    turn.robot_task_id,
                    turn.role.value,
                    turn.text,
                    turn.input_text,
                    turn.intent.value if turn.intent else None,
                    turn.confidence,
                    turn.recommended_action,
                    turn.reply_text,
                    turn.asr_status,
                    turn.tts_status,
                    int(turn.conversation_complete),
                    turn.provider,
                    int(turn.real_motion_enabled),
                    self.dump_json(turn.metadata),
                    self._format_datetime(turn.occurred_at),
                    self._format_datetime(turn.created_at),
                ),
            )
            if cursor.lastrowid:
                return turn.model_copy(update={"id": int(cursor.lastrowid)})
            row = connection.execute(
                "SELECT * FROM robot_dialogue_turns WHERE turn_id = ?",
                (turn.turn_id,),
            ).fetchone()
        return self._row_to_dialogue_turn(row) if row else turn

    def list_dialogue_turns(self, incident_id: str) -> list[RobotDialogueTurn]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM robot_dialogue_turns
                WHERE incident_id = ?
                ORDER BY occurred_at ASC, id ASC
                """,
                (incident_id,),
            ).fetchall()
        return [self._row_to_dialogue_turn(row) for row in rows]

    def list_cases(self) -> list[RobotEmergencyCase]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM robot_emergency_cases ORDER BY created_at ASC, case_id ASC"
            ).fetchall()
        return [self._row_to_case(row) for row in rows]

    def get_incident_bundle(self, incident_id: str) -> RobotEmergencyIncidentBundle | None:
        case = self.get_case_by_incident_id(incident_id)
        if case is None:
            return None
        dialogue_turns = self.list_dialogue_turns(incident_id)
        with self._lock, self._connect() as connection:
            table_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                ("robot_navigation_events",),
            ).fetchone()
            if table_exists:
                rows = connection.execute(
                    """
                    SELECT * FROM robot_navigation_events
                    WHERE incident_id = ? OR (? IS NOT NULL AND task_id = ?)
                    ORDER BY sequence ASC, occurred_at ASC, id ASC
                    """,
                    (incident_id, case.robot_task_id, case.robot_task_id),
                ).fetchall()
            else:
                rows = []
        return RobotEmergencyIncidentBundle(
            incident_id=incident_id,
            emergency_case=case,
            robot_task_id=case.robot_task_id,
            navigation_events=[RobotNavigationRepository.row_to_event(row) for row in rows],
            dialogue_turns=dialogue_turns,
        )

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS robot_emergency_cases (
                    case_id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL UNIQUE,
                    robot_task_id TEXT,
                    alarm_id TEXT,
                    camera_id TEXT,
                    area_id TEXT,
                    area_name TEXT,
                    observation_point_id TEXT,
                    home_point_id TEXT,
                    risk_level TEXT NOT NULL DEFAULT 'unknown',
                    fall_probability REAL,
                    status TEXT NOT NULL DEFAULT 'open',
                    execution_state TEXT NOT NULL,
                    navigation_state TEXT NOT NULL,
                    control_owner TEXT NOT NULL DEFAULT 'NONE',
                    dialogue_intent TEXT,
                    provider TEXT NOT NULL DEFAULT 'mock' CHECK(provider = 'mock'),
                    real_motion_enabled INTEGER NOT NULL DEFAULT 0 CHECK(real_motion_enabled = 0),
                    acknowledged_by TEXT,
                    acknowledged_at TEXT,
                    resolution TEXT,
                    resolved_at TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(robot_task_id) REFERENCES robot_tasks(task_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS robot_dialogue_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    turn_id TEXT NOT NULL UNIQUE,
                    incident_id TEXT NOT NULL,
                    robot_task_id TEXT,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL DEFAULT '',
                    input_text TEXT,
                    intent TEXT,
                    confidence REAL,
                    recommended_action TEXT,
                    reply_text TEXT,
                    asr_status TEXT,
                    tts_status TEXT,
                    conversation_complete INTEGER NOT NULL DEFAULT 0,
                    provider TEXT NOT NULL DEFAULT 'mock' CHECK(provider = 'mock'),
                    real_motion_enabled INTEGER NOT NULL DEFAULT 0 CHECK(real_motion_enabled = 0),
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    occurred_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(incident_id) REFERENCES robot_emergency_cases(incident_id),
                    FOREIGN KEY(robot_task_id) REFERENCES robot_tasks(task_id)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_robot_emergency_cases_task_id "
                "ON robot_emergency_cases(robot_task_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_robot_dialogue_turns_incident_time "
                "ON robot_dialogue_turns(incident_id, occurred_at, id)"
            )
            connection.commit()

    def _case_values(self, item: RobotEmergencyCase) -> tuple[Any, ...]:
        return (
            item.case_id,
            item.incident_id,
            item.robot_task_id,
            item.alarm_id,
            item.camera_id,
            item.area_id,
            item.area_name,
            item.observation_point_id,
            item.home_point_id,
            item.risk_level,
            item.fall_probability,
            item.status.value,
            item.execution_state.value,
            item.navigation_state.value,
            item.control_owner.value,
            item.dialogue_intent.value if item.dialogue_intent else None,
            item.provider,
            int(item.real_motion_enabled),
            item.acknowledged_by,
            self._format_datetime(item.acknowledged_at),
            item.resolution,
            self._format_datetime(item.resolved_at),
            item.error_code,
            item.error_message,
            self.dump_json(item.metadata),
            self._format_datetime(item.created_at),
            self._format_datetime(item.updated_at),
        )

    def _row_to_case(self, row: sqlite3.Row) -> RobotEmergencyCase:
        return RobotEmergencyCase(
            case_id=row["case_id"],
            incident_id=row["incident_id"],
            robot_task_id=row["robot_task_id"],
            alarm_id=row["alarm_id"],
            camera_id=row["camera_id"],
            area_id=row["area_id"],
            area_name=row["area_name"],
            observation_point_id=row["observation_point_id"],
            home_point_id=row["home_point_id"],
            risk_level=row["risk_level"] or "unknown",
            fall_probability=float(row["fall_probability"]) if row["fall_probability"] is not None else None,
            status=RobotEmergencyCaseStatus(row["status"]),
            execution_state=RobotEmergencyExecutionState(row["execution_state"]),
            navigation_state=RobotNavigationExecutionState(row["navigation_state"]),
            control_owner=RobotControlOwner(row["control_owner"]),
            dialogue_intent=RobotDialogueIntent(row["dialogue_intent"]) if row["dialogue_intent"] else None,
            provider=row["provider"],
            real_motion_enabled=bool(row["real_motion_enabled"]),
            acknowledged_by=row["acknowledged_by"],
            acknowledged_at=self._parse_datetime(row["acknowledged_at"]),
            resolution=row["resolution"],
            resolved_at=self._parse_datetime(row["resolved_at"]),
            error_code=row["error_code"],
            error_message=row["error_message"],
            metadata=self.load_json(row["metadata_json"]),
            created_at=self._parse_datetime(row["created_at"]),
            updated_at=self._parse_datetime(row["updated_at"]),
        )

    def _row_to_dialogue_turn(self, row: sqlite3.Row) -> RobotDialogueTurn:
        return RobotDialogueTurn(
            id=int(row["id"]),
            turn_id=row["turn_id"],
            incident_id=row["incident_id"],
            robot_task_id=row["robot_task_id"],
            role=RobotDialogueRole(row["role"]),
            text=row["text"] or "",
            input_text=row["input_text"],
            intent=RobotDialogueIntent(row["intent"]) if row["intent"] else None,
            confidence=float(row["confidence"]) if row["confidence"] is not None else None,
            recommended_action=row["recommended_action"],
            reply_text=row["reply_text"],
            asr_status=row["asr_status"],
            tts_status=row["tts_status"],
            conversation_complete=bool(row["conversation_complete"]),
            provider=row["provider"],
            real_motion_enabled=bool(row["real_motion_enabled"]),
            metadata=self.load_json(row["metadata_json"]),
            occurred_at=self._parse_datetime(row["occurred_at"]),
            created_at=self._parse_datetime(row["created_at"]),
        )

    @staticmethod
    def _format_datetime(value: datetime | None) -> str | None:
        if value is None:
            return None
        normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return normalized.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if value is None:
            return None
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
