from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock

from pydantic import ValidationError

from backend.models.alarm_model import AlarmLayer, AlarmPriority, AlarmRecord, AlarmType
from backend.models.analytics_model import HistoryBucket, SensorHistoryPoint
from backend.models.health_model import HealthSample, IngestionSource


logger = logging.getLogger(__name__)


class HealthDataRepository:
    """SQLite-backed persistence for sensor samples, scores, alerts, status, and rollups."""

    def __init__(self, *, database_url: str | None = None) -> None:
        self._database_path = self._resolve_sqlite_path(database_url)
        self._lock = RLock()
        self._initialize_storage()

    def persist_sample(self, sample: HealthSample) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO sensor_samples (
                    device_mac, timestamp, heart_rate, temperature, blood_oxygen,
                    blood_pressure, battery, steps, sos_flag, source, device_uuid,
                    ambient_temperature, surface_temperature, packet_type,
                    sos_value, sos_trigger, raw_packet_a, raw_packet_b, anomaly_score,
                    health_score, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sample.device_mac,
                    sample.timestamp.astimezone(timezone.utc).isoformat(),
                    sample.heart_rate,
                    sample.temperature,
                    sample.blood_oxygen,
                    sample.blood_pressure,
                    sample.battery,
                    sample.steps,
                    int(sample.sos_flag),
                    sample.source.value,
                    sample.device_uuid,
                    sample.ambient_temperature,
                    sample.surface_temperature,
                    sample.packet_type,
                    sample.sos_value,
                    sample.sos_trigger,
                    sample.raw_packet_a,
                    sample.raw_packet_b,
                    sample.anomaly_score,
                    sample.health_score,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()

    def persist_health_score(
        self,
        *,
        sample: HealthSample,
        risk_level: str,
        risk_flags: list[str],
        model_version: str,
        explanation: str | None = None,
    ) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO health_scores (
                    device_mac, timestamp, score, risk_level, risk_flags,
                    model_version, explanation, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sample.device_mac,
                    sample.timestamp.astimezone(timezone.utc).isoformat(),
                    sample.health_score,
                    risk_level,
                    json.dumps(risk_flags, ensure_ascii=False),
                    model_version,
                    explanation,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()

    def persist_alerts(self, alarms: list[AlarmRecord]) -> None:
        if not alarms:
            return
        with self._lock, self._connection() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO alert_events (
                    id, device_mac, alarm_type, alarm_layer, alarm_level,
                    message, acknowledged, anomaly_probability, metadata, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        alarm.id,
                        alarm.device_mac,
                        alarm.alarm_type.value,
                        alarm.alarm_layer.value,
                        int(alarm.alarm_level.value),
                        alarm.message,
                        int(alarm.acknowledged),
                        alarm.anomaly_probability,
                        json.dumps(alarm.metadata, ensure_ascii=False),
                        alarm.created_at.astimezone(timezone.utc).isoformat(),
                    )
                    for alarm in alarms
                ],
            )
            connection.commit()

    def acknowledge_alert(self, alarm_id: str) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE alert_events SET acknowledged = 1 WHERE id = ?",
                (alarm_id,),
            )
            connection.commit()

    def persist_device_status(
        self,
        *,
        device_mac: str,
        status: str,
        bind_status: str | None,
        source: str,
        changed_at: datetime,
    ) -> None:
        normalized_mac = device_mac.strip().upper()
        changed_at_iso = changed_at.astimezone(timezone.utc).isoformat()
        with self._lock, self._connection() as connection:
            latest = connection.execute(
                """
                SELECT status, bind_status
                FROM device_status_history
                WHERE device_mac = ?
                ORDER BY changed_at DESC
                LIMIT 1
                """,
                (normalized_mac,),
            ).fetchone()
            if latest and latest["status"] == status and latest["bind_status"] == (bind_status or ""):
                return
            connection.execute(
                """
                INSERT INTO device_status_history (
                    device_mac, status, bind_status, source, changed_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_mac,
                    status,
                    bind_status or "",
                    source,
                    changed_at_iso,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()

    def refresh_rollups_for_sample(self, *, device_mac: str, timestamp: datetime) -> None:
        normalized_mac = device_mac.strip().upper()
        bucket_hour = self._bucket_start(timestamp, HistoryBucket.HOUR)
        bucket_day = self._bucket_start(timestamp, HistoryBucket.DAY)
        self._refresh_rollup_bucket(
            table_name="sensor_hourly_rollups",
            device_mac=normalized_mac,
            bucket_start=bucket_hour,
            bucket=HistoryBucket.HOUR,
        )
        self._refresh_rollup_bucket(
            table_name="sensor_daily_rollups",
            device_mac=normalized_mac,
            bucket_start=bucket_day,
            bucket=HistoryBucket.DAY,
        )

    def list_samples(
        self,
        *,
        device_mac: str,
        start_at: datetime,
        end_at: datetime,
        limit: int = 2000,
    ) -> list[HealthSample]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM (
                    SELECT *
                    FROM sensor_samples
                    WHERE device_mac = ?
                      AND timestamp >= ?
                      AND timestamp <= ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ) recent_samples
                ORDER BY timestamp ASC
                """,
                (
                    device_mac.strip().upper(),
                    start_at.astimezone(timezone.utc).isoformat(),
                    end_at.astimezone(timezone.utc).isoformat(),
                    limit,
                ),
            ).fetchall()
        samples: list[HealthSample] = []
        for row in rows:
            sample = self._try_row_to_sample(row)
            if sample is not None:
                samples.append(sample)
        return samples

    def list_samples_by_devices(
        self,
        *,
        device_macs: list[str] | None,
        start_at: datetime,
        end_at: datetime,
        per_device_limit: int = 2048,
    ) -> dict[str, list[HealthSample]]:
        normalized_macs = [item.strip().upper() for item in (device_macs or []) if item.strip()]
        query = [
            "SELECT * FROM sensor_samples",
            "WHERE timestamp >= ? AND timestamp <= ?",
        ]
        params: list[object] = [
            start_at.astimezone(timezone.utc).isoformat(),
            end_at.astimezone(timezone.utc).isoformat(),
        ]
        if normalized_macs:
            placeholders = ",".join("?" for _ in normalized_macs)
            query.append(f"AND device_mac IN ({placeholders})")
            params.extend(normalized_macs)
        query.append("ORDER BY device_mac ASC, timestamp ASC")

        with self._lock, self._connection() as connection:
            rows = connection.execute("\n".join(query), tuple(params)).fetchall()

        grouped: dict[str, list[HealthSample]] = {}
        for row in rows:
            sample = self._try_row_to_sample(row)
            if sample is None:
                continue
            grouped.setdefault(sample.device_mac, []).append(sample)
        return {
            device_mac: samples[-per_device_limit:]
            for device_mac, samples in grouped.items()
            if samples
        }

    def list_health_scores(
        self,
        *,
        device_mac: str,
        start_at: datetime,
        end_at: datetime,
    ) -> list[dict[str, object]]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                """
                SELECT device_mac, timestamp, score, risk_level, risk_flags, model_version, explanation
                FROM health_scores
                WHERE device_mac = ?
                  AND timestamp >= ?
                  AND timestamp <= ?
                ORDER BY timestamp ASC
                """,
                (
                    device_mac.strip().upper(),
                    start_at.astimezone(timezone.utc).isoformat(),
                    end_at.astimezone(timezone.utc).isoformat(),
                ),
            ).fetchall()
        scores: list[dict[str, object]] = []
        for row in rows:
            try:
                risk_flags = json.loads(row["risk_flags"] or "[]")
            except json.JSONDecodeError:
                risk_flags = []
            scores.append(
                {
                    "device_mac": row["device_mac"],
                    "timestamp": row["timestamp"],
                    "health_score": row["score"],
                    "risk_level": row["risk_level"],
                    "risk_flags": risk_flags,
                    "model_version": row["model_version"],
                    "explanation": row["explanation"],
                }
            )
        return scores

    def list_alerts(
        self,
        *,
        device_macs: list[str] | None,
        start_at: datetime,
        end_at: datetime,
        active_only: bool = False,
    ) -> list[AlarmRecord]:
        normalized_macs = [item.strip().upper() for item in (device_macs or []) if item.strip()]
        query = [
            "SELECT * FROM alert_events",
            "WHERE created_at >= ? AND created_at <= ?",
        ]
        params: list[object] = [
            start_at.astimezone(timezone.utc).isoformat(),
            end_at.astimezone(timezone.utc).isoformat(),
        ]
        if normalized_macs:
            placeholders = ",".join("?" for _ in normalized_macs)
            query.append(f"AND device_mac IN ({placeholders})")
            params.extend(normalized_macs)
        if active_only:
            query.append("AND acknowledged = 0")
        query.append("ORDER BY created_at ASC")

        with self._lock, self._connection() as connection:
            rows = connection.execute("\n".join(query), tuple(params)).fetchall()
        return [self._row_to_alarm(row) for row in rows]

    def list_status_history(
        self,
        *,
        device_macs: list[str] | None,
        start_at: datetime,
        end_at: datetime,
    ) -> list[dict[str, object]]:
        normalized_macs = [item.strip().upper() for item in (device_macs or []) if item.strip()]
        query = [
            "SELECT device_mac, status, bind_status, source, changed_at",
            "FROM device_status_history",
            "WHERE changed_at >= ? AND changed_at <= ?",
        ]
        params: list[object] = [
            start_at.astimezone(timezone.utc).isoformat(),
            end_at.astimezone(timezone.utc).isoformat(),
        ]
        if normalized_macs:
            placeholders = ",".join("?" for _ in normalized_macs)
            query.append(f"AND device_mac IN ({placeholders})")
            params.extend(normalized_macs)
        query.append("ORDER BY changed_at ASC")

        with self._lock, self._connection() as connection:
            rows = connection.execute("\n".join(query), tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def purge_device_history_window(
        self,
        *,
        device_macs: list[str],
        start_at: datetime,
        end_at: datetime,
        status_source_prefixes: tuple[str, ...] = ("demo_overlay_",),
    ) -> dict[str, int]:
        normalized_macs = [item.strip().upper() for item in device_macs if item and item.strip()]
        if not normalized_macs:
            return {
                "sensor_samples": 0,
                "health_scores": 0,
                "status_history": 0,
                "hourly_rollups": 0,
                "daily_rollups": 0,
            }

        placeholders = ",".join("?" for _ in normalized_macs)
        start_iso = start_at.astimezone(timezone.utc).isoformat()
        end_iso = end_at.astimezone(timezone.utc).isoformat()
        bucket_hour_start = self._bucket_start(start_at, HistoryBucket.HOUR).astimezone(timezone.utc).isoformat()
        bucket_hour_end = self._bucket_start(end_at, HistoryBucket.HOUR).astimezone(timezone.utc).isoformat()
        bucket_day_start = self._bucket_start(start_at, HistoryBucket.DAY).astimezone(timezone.utc).isoformat()
        bucket_day_end = self._bucket_start(end_at, HistoryBucket.DAY).astimezone(timezone.utc).isoformat()

        deleted = {
            "sensor_samples": 0,
            "health_scores": 0,
            "status_history": 0,
            "hourly_rollups": 0,
            "daily_rollups": 0,
        }

        with self._lock, self._connection() as connection:
            sensor_cursor = connection.execute(
                f"""
                DELETE FROM sensor_samples
                WHERE device_mac IN ({placeholders})
                  AND timestamp >= ?
                  AND timestamp <= ?
                """,
                (*normalized_macs, start_iso, end_iso),
            )
            deleted["sensor_samples"] = sensor_cursor.rowcount or 0

            score_cursor = connection.execute(
                f"""
                DELETE FROM health_scores
                WHERE device_mac IN ({placeholders})
                  AND timestamp >= ?
                  AND timestamp <= ?
                """,
                (*normalized_macs, start_iso, end_iso),
            )
            deleted["health_scores"] = score_cursor.rowcount or 0

            if status_source_prefixes:
                status_prefix_sql = " OR ".join("source LIKE ?" for _ in status_source_prefixes)
                status_cursor = connection.execute(
                    f"""
                    DELETE FROM device_status_history
                    WHERE device_mac IN ({placeholders})
                      AND changed_at >= ?
                      AND changed_at <= ?
                      AND ({status_prefix_sql})
                    """,
                    (
                        *normalized_macs,
                        start_iso,
                        end_iso,
                        *(f"{prefix}%" for prefix in status_source_prefixes),
                    ),
                )
                deleted["status_history"] = status_cursor.rowcount or 0

            hourly_cursor = connection.execute(
                f"""
                DELETE FROM sensor_hourly_rollups
                WHERE device_mac IN ({placeholders})
                  AND bucket_start >= ?
                  AND bucket_start <= ?
                """,
                (*normalized_macs, bucket_hour_start, bucket_hour_end),
            )
            deleted["hourly_rollups"] = hourly_cursor.rowcount or 0

            daily_cursor = connection.execute(
                f"""
                DELETE FROM sensor_daily_rollups
                WHERE device_mac IN ({placeholders})
                  AND bucket_start >= ?
                  AND bucket_start <= ?
                """,
                (*normalized_macs, bucket_day_start, bucket_day_end),
            )
            deleted["daily_rollups"] = daily_cursor.rowcount or 0
            connection.commit()

        return deleted

    def list_rollup_points(
        self,
        *,
        device_mac: str,
        start_at: datetime,
        end_at: datetime,
        bucket: HistoryBucket,
    ) -> list[SensorHistoryPoint]:
        table_name = "sensor_hourly_rollups" if bucket == HistoryBucket.HOUR else "sensor_daily_rollups"
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM {table_name}
                WHERE device_mac = ?
                  AND bucket_start >= ?
                  AND bucket_start <= ?
                ORDER BY bucket_start ASC
                """,
                (
                    device_mac.strip().upper(),
                    start_at.astimezone(timezone.utc).isoformat(),
                    end_at.astimezone(timezone.utc).isoformat(),
                ),
            ).fetchall()
        return [
            SensorHistoryPoint(
                bucket_start=self._parse_datetime(row["bucket_start"]),
                bucket_end=self._parse_datetime(row["bucket_end"]),
                heart_rate=row["avg_heart_rate"],
                temperature=row["avg_temperature"],
                blood_oxygen=row["avg_blood_oxygen"],
                health_score=row["avg_health_score"],
                battery=row["avg_battery"],
                steps=row["avg_steps"],
                sos_count=int(row["sos_count"] or 0),
                sample_count=int(row["sample_count"] or 0),
                risk_level=row["risk_level"] or None,
            )
            for row in rows
        ]

    def _refresh_rollup_bucket(
        self,
        *,
        table_name: str,
        device_mac: str,
        bucket_start: datetime,
        bucket: HistoryBucket,
    ) -> None:
        bucket_end = bucket_start + (timedelta(hours=1) if bucket == HistoryBucket.HOUR else timedelta(days=1))
        with self._lock, self._connection() as connection:
            sample_rows = connection.execute(
                """
                SELECT *
                FROM sensor_samples
                WHERE device_mac = ?
                  AND timestamp >= ?
                  AND timestamp < ?
                ORDER BY timestamp ASC
                """,
                (
                    device_mac,
                    bucket_start.astimezone(timezone.utc).isoformat(),
                    bucket_end.astimezone(timezone.utc).isoformat(),
                ),
            ).fetchall()
            score_rows = connection.execute(
                """
                SELECT risk_level
                FROM health_scores
                WHERE device_mac = ?
                  AND timestamp >= ?
                  AND timestamp < ?
                """,
                (
                    device_mac,
                    bucket_start.astimezone(timezone.utc).isoformat(),
                    bucket_end.astimezone(timezone.utc).isoformat(),
                ),
            ).fetchall()

            if not sample_rows:
                connection.execute(
                    f"DELETE FROM {table_name} WHERE device_mac = ? AND bucket_start = ?",
                    (device_mac, bucket_start.astimezone(timezone.utc).isoformat()),
                )
                connection.commit()
                return

            heart_rates = [float(row["heart_rate"]) for row in sample_rows]
            temperatures = [float(row["temperature"]) for row in sample_rows]
            blood_oxygen_values = [float(row["blood_oxygen"]) for row in sample_rows]
            batteries = [float(row["battery"]) for row in sample_rows]
            step_values = [float(row["steps"]) for row in sample_rows if row["steps"] is not None]
            health_scores = [float(row["health_score"]) for row in sample_rows if row["health_score"] is not None]
            risk_levels = [str(row["risk_level"]) for row in score_rows if row["risk_level"]]
            connection.execute(
                f"""
                INSERT OR REPLACE INTO {table_name} (
                    device_mac, bucket_start, bucket_end,
                    avg_heart_rate, avg_temperature, avg_blood_oxygen,
                    avg_health_score, avg_battery, avg_steps,
                    sos_count, sample_count, risk_level, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_mac,
                    bucket_start.astimezone(timezone.utc).isoformat(),
                    bucket_end.astimezone(timezone.utc).isoformat(),
                    self._average(heart_rates),
                    self._average(temperatures),
                    self._average(blood_oxygen_values),
                    self._average(health_scores),
                    self._average(batteries),
                    self._average(step_values),
                    sum(1 for row in sample_rows if int(row["sos_flag"] or 0)),
                    len(sample_rows),
                    self._highest_risk_level(risk_levels),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()

    def _initialize_storage(self) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sensor_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_mac TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    heart_rate INTEGER NOT NULL,
                    temperature REAL NOT NULL,
                    blood_oxygen INTEGER NOT NULL,
                    blood_pressure TEXT,
                    battery INTEGER NOT NULL,
                    steps INTEGER,
                    sos_flag INTEGER NOT NULL DEFAULT 0,
                    source TEXT NOT NULL,
                    device_uuid TEXT,
                    ambient_temperature REAL,
                    surface_temperature REAL,
                    packet_type TEXT,
                    sos_value INTEGER,
                    sos_trigger TEXT,
                    raw_packet_a TEXT,
                    raw_packet_b TEXT,
                    anomaly_score REAL,
                    health_score INTEGER,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS health_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_mac TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    score INTEGER,
                    risk_level TEXT NOT NULL,
                    risk_flags TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    explanation TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS alert_events (
                    id TEXT PRIMARY KEY,
                    device_mac TEXT NOT NULL,
                    alarm_type TEXT NOT NULL,
                    alarm_layer TEXT NOT NULL,
                    alarm_level INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    acknowledged INTEGER NOT NULL DEFAULT 0,
                    anomaly_probability REAL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS device_status_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_mac TEXT NOT NULL,
                    status TEXT NOT NULL,
                    bind_status TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL,
                    changed_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sensor_hourly_rollups (
                    device_mac TEXT NOT NULL,
                    bucket_start TEXT NOT NULL,
                    bucket_end TEXT NOT NULL,
                    avg_heart_rate REAL,
                    avg_temperature REAL,
                    avg_blood_oxygen REAL,
                    avg_health_score REAL,
                    avg_battery REAL,
                    avg_steps REAL,
                    sos_count INTEGER NOT NULL DEFAULT 0,
                    sample_count INTEGER NOT NULL DEFAULT 0,
                    risk_level TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (device_mac, bucket_start)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sensor_daily_rollups (
                    device_mac TEXT NOT NULL,
                    bucket_start TEXT NOT NULL,
                    bucket_end TEXT NOT NULL,
                    avg_heart_rate REAL,
                    avg_temperature REAL,
                    avg_blood_oxygen REAL,
                    avg_health_score REAL,
                    avg_battery REAL,
                    avg_steps REAL,
                    sos_count INTEGER NOT NULL DEFAULT 0,
                    sample_count INTEGER NOT NULL DEFAULT 0,
                    risk_level TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (device_mac, bucket_start)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_sensor_samples_device_time ON sensor_samples(device_mac, timestamp DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_health_scores_device_time ON health_scores(device_mac, timestamp DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_alert_events_device_time ON alert_events(device_mac, created_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_status_history_device_time ON device_status_history(device_mac, changed_at DESC)"
            )
            self._ensure_column(connection, "sensor_samples", "sos_value", "INTEGER")
            self._ensure_column(connection, "sensor_samples", "sos_trigger", "TEXT")
            connection.commit()

    @contextmanager
    def _connection(self):
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def _row_to_sample(self, row: sqlite3.Row) -> HealthSample:
        source_value = row["source"] or IngestionSource.MOCK.value
        if source_value not in {item.value for item in IngestionSource}:
            source_value = IngestionSource.MOCK.value
        return HealthSample(
            device_mac=row["device_mac"],
            timestamp=self._parse_datetime(row["timestamp"]),
            heart_rate=int(row["heart_rate"]),
            temperature=float(row["temperature"]),
            blood_oxygen=int(row["blood_oxygen"]),
            blood_pressure=row["blood_pressure"],
            battery=int(row["battery"]),
            sos_flag=bool(row["sos_flag"]),
            source=IngestionSource(source_value),
            device_uuid=row["device_uuid"],
            ambient_temperature=row["ambient_temperature"],
            surface_temperature=row["surface_temperature"],
            steps=row["steps"],
            packet_type=row["packet_type"],
            sos_value=row["sos_value"],
            sos_trigger=row["sos_trigger"],
            raw_packet_a=row["raw_packet_a"],
            raw_packet_b=row["raw_packet_b"],
            anomaly_score=row["anomaly_score"],
            health_score=row["health_score"],
        )

    def _row_to_sample_lossy(self, row: sqlite3.Row) -> HealthSample:
        source_value = row["source"] or IngestionSource.MOCK.value
        if source_value not in {item.value for item in IngestionSource}:
            source_value = IngestionSource.MOCK.value
        return HealthSample.model_construct(
            device_mac=str(row["device_mac"]).upper(),
            timestamp=self._parse_datetime(row["timestamp"]),
            heart_rate=int(row["heart_rate"] or 0),
            temperature=float(row["temperature"] or 0.0),
            blood_oxygen=int(row["blood_oxygen"] or 0),
            blood_pressure=row["blood_pressure"],
            battery=int(row["battery"] or 0),
            sos_flag=bool(row["sos_flag"]),
            source=IngestionSource(source_value),
            device_uuid=row["device_uuid"],
            ambient_temperature=(
                float(row["ambient_temperature"]) if row["ambient_temperature"] is not None else None
            ),
            surface_temperature=(
                float(row["surface_temperature"]) if row["surface_temperature"] is not None else None
            ),
            steps=int(row["steps"]) if row["steps"] is not None else None,
            packet_type=row["packet_type"],
            sos_value=int(row["sos_value"]) if row["sos_value"] is not None else None,
            sos_trigger=row["sos_trigger"],
            raw_packet_a=row["raw_packet_a"],
            raw_packet_b=row["raw_packet_b"],
            anomaly_score=float(row["anomaly_score"]) if row["anomaly_score"] is not None else None,
            health_score=int(row["health_score"]) if row["health_score"] is not None else None,
        )

    def _try_row_to_sample(self, row: sqlite3.Row) -> HealthSample | None:
        try:
            return self._row_to_sample(row)
        except ValidationError:
            try:
                return self._row_to_sample_lossy(row)
            except (TypeError, ValueError):
                logger.warning(
                    "Skipping invalid persisted sample for %s at %s",
                    row["device_mac"],
                    row["timestamp"],
                )
                return None
        except (TypeError, ValueError):
            logger.warning(
                "Skipping invalid persisted sample for %s at %s",
                row["device_mac"],
                row["timestamp"],
            )
            return None

    def _row_to_alarm(self, row: sqlite3.Row) -> AlarmRecord:
        metadata_value = row["metadata"] or "{}"
        try:
            metadata = json.loads(metadata_value)
        except json.JSONDecodeError:
            metadata = {}
        return AlarmRecord(
            id=row["id"],
            device_mac=row["device_mac"],
            alarm_type=AlarmType(row["alarm_type"]),
            alarm_layer=AlarmLayer(row["alarm_layer"]),
            alarm_level=AlarmPriority(int(row["alarm_level"])),
            message=row["message"],
            created_at=self._parse_datetime(row["created_at"]),
            acknowledged=bool(row["acknowledged"]),
            anomaly_probability=row["anomaly_probability"],
            metadata=metadata if isinstance(metadata, dict) else {},
        )

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_definition: str,
    ) -> None:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name in columns:
            return
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )

    def _bucket_start(self, timestamp: datetime, bucket: HistoryBucket) -> datetime:
        value = timestamp.astimezone(timezone.utc)
        if bucket == HistoryBucket.DAY:
            return value.replace(hour=0, minute=0, second=0, microsecond=0)
        return value.replace(minute=0, second=0, microsecond=0)

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _average(values: list[float]) -> float | None:
        if not values:
            return None
        return sum(values) / len(values)

    @staticmethod
    def _highest_risk_level(values: list[str]) -> str | None:
        if not values:
            return None
        order = {"unknown": 0, "low": 1, "medium": 2, "high": 3}
        return max(values, key=lambda item: order.get(item, 0))

    @staticmethod
    def _resolve_sqlite_path(database_url: str | None) -> Path:
        if not database_url:
            return Path("data") / "app.db"
        prefix = "sqlite+aiosqlite:///"
        if database_url.startswith(prefix):
            return Path(database_url[len(prefix):])
        return Path("data") / "app.db"
