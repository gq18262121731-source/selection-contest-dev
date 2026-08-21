from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.repositories.sqlite_base import SQLiteRepositoryBase


class WarningRepository(SQLiteRepositoryBase):
    """Store warning evaluation results."""

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS warning_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    evaluated_at TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    recommendation_code TEXT NOT NULL,
                    trigger_reasons_json TEXT NOT NULL,
                    abnormal_tags_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def save_result(
        self,
        *,
        evaluated_at: datetime,
        risk_level: str,
        recommendation_code: str,
        trigger_reasons: list[str],
        abnormal_tags: list[str],
        payload: dict[str, Any],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO warning_results (
                    evaluated_at,
                    risk_level,
                    recommendation_code,
                    trigger_reasons_json,
                    abnormal_tags_json,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    evaluated_at.isoformat(),
                    risk_level,
                    recommendation_code,
                    self.dump_json({"trigger_reasons": trigger_reasons}),
                    self.dump_json({"abnormal_tags": abnormal_tags}),
                    self.dump_json(payload),
                ),
            )
