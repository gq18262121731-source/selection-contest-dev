from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.repositories.sqlite_base import SQLiteRepositoryBase


class WearableRepository(SQLiteRepositoryBase):
    """Store normalized wearable input events."""

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS wearable_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    elderly_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def save_event(
        self,
        *,
        elderly_id: str,
        device_id: str,
        timestamp: datetime,
        payload: dict[str, Any],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO wearable_events (elderly_id, device_id, timestamp, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (elderly_id, device_id, timestamp.isoformat(), self.dump_json(payload)),
            )
