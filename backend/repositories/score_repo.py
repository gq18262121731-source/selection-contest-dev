from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.repositories.sqlite_base import SQLiteRepositoryBase


class ScoreRepository(SQLiteRepositoryBase):
    """Store health score inference results."""

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS health_score_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    elderly_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    rule_health_score REAL NOT NULL,
                    model_health_score REAL NOT NULL,
                    final_health_score REAL NOT NULL,
                    risk_level TEXT NOT NULL,
                    risk_score_raw REAL NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def save_result(
        self,
        *,
        elderly_id: str,
        device_id: str,
        timestamp: datetime,
        result: dict[str, Any],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO health_score_results (
                    elderly_id,
                    device_id,
                    timestamp,
                    rule_health_score,
                    model_health_score,
                    final_health_score,
                    risk_level,
                    risk_score_raw,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    elderly_id,
                    device_id,
                    timestamp.isoformat(),
                    float(result["rule_health_score"]),
                    float(result["model_health_score"]),
                    float(result["final_health_score"]),
                    str(result["risk_level"]),
                    float(result["risk_score_raw"]),
                    self.dump_json(result),
                ),
            )

    def get_latest_by_device_ids(self, device_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Return latest structured score payload per device id."""

        normalized_ids = [str(device_id).strip() for device_id in device_ids if str(device_id).strip()]
        if not normalized_ids:
            return {}

        placeholders = ",".join("?" for _ in normalized_ids)
        query = f"""
            SELECT latest.device_id, latest.timestamp, latest.payload_json
            FROM health_score_results AS latest
            INNER JOIN (
                SELECT device_id, MAX(timestamp) AS max_timestamp
                FROM health_score_results
                WHERE device_id IN ({placeholders})
                GROUP BY device_id
            ) AS grouped
                ON latest.device_id = grouped.device_id
               AND latest.timestamp = grouped.max_timestamp
        """
        with self._connect() as connection:
            rows = connection.execute(query, normalized_ids).fetchall()

        results: dict[str, dict[str, Any]] = {}
        for row in rows:
            payload = self.load_json(row["payload_json"])
            if isinstance(payload, dict):
                results[str(row["device_id"])] = payload
        return results
