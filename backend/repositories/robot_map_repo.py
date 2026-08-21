from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Sequence

from backend.models.robot_navigation_model import (
    RobotMap,
    RobotMapPoint,
    RobotMapPointStatus,
    RobotMapPointType,
    RobotMapStatus,
    RobotPatrolRoute,
    RobotPatrolRoutePoint,
    RobotPatrolRouteStatus,
)
from backend.repositories.sqlite_base import SQLiteRepositoryBase


class RobotMapRepository(SQLiteRepositoryBase):
    """SQLite persistence for Mock map, point, and patrol-route metadata."""

    def __init__(self, database_url: str) -> None:
        self._lock = RLock()
        super().__init__(database_url)

    def create_map(self, robot_map: RobotMap) -> RobotMap:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO robot_maps (
                    map_id, name, status, revision, provider, real_motion_enabled,
                    metadata_json, created_at, updated_at, activated_at, replaced_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._map_values(robot_map),
            )
            connection.commit()
        return robot_map

    def update_map(self, robot_map: RobotMap) -> RobotMap:
        robot_map = robot_map.model_copy(update={"updated_at": datetime.now(timezone.utc)})
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE robot_maps
                SET name = ?, status = ?, revision = ?, provider = ?,
                    real_motion_enabled = ?, metadata_json = ?, updated_at = ?,
                    activated_at = ?, replaced_at = ?
                WHERE map_id = ?
                """,
                (
                    robot_map.name,
                    robot_map.status.value,
                    robot_map.revision,
                    robot_map.provider,
                    int(robot_map.real_motion_enabled),
                    self.dump_json(robot_map.metadata),
                    self._format_datetime(robot_map.updated_at),
                    self._format_datetime(robot_map.activated_at),
                    self._format_datetime(robot_map.replaced_at),
                    robot_map.map_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("MAP_NOT_FOUND")
            connection.commit()
        return robot_map

    def get_map(self, map_id: str) -> RobotMap | None:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT * FROM robot_maps WHERE map_id = ?", (map_id,)).fetchone()
        return self._row_to_map(row) if row else None

    def get_active_map(self) -> RobotMap | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM robot_maps WHERE status = ? ORDER BY activated_at DESC LIMIT 1",
                (RobotMapStatus.ACTIVE.value,),
            ).fetchone()
        return self._row_to_map(row) if row else None

    def list_maps(self) -> list[RobotMap]:
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT * FROM robot_maps ORDER BY created_at ASC").fetchall()
        return [self._row_to_map(row) for row in rows]

    def activate_map(self, map_id: str) -> RobotMap:
        now = self._format_datetime(datetime.now(timezone.utc))
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            target = connection.execute("SELECT * FROM robot_maps WHERE map_id = ?", (map_id,)).fetchone()
            if target is None:
                raise ValueError("MAP_NOT_FOUND")
            target_status = RobotMapStatus(target["status"])
            if target_status == RobotMapStatus.ACTIVE:
                connection.commit()
                return self._row_to_map(target)
            if target_status not in {RobotMapStatus.DRAFT, RobotMapStatus.PREVIEW}:
                raise ValueError("MAP_STATE_CONFLICT")

            replaced_ids = [
                row["map_id"]
                for row in connection.execute(
                    "SELECT map_id FROM robot_maps WHERE status = ? AND map_id <> ?",
                    (RobotMapStatus.ACTIVE.value, map_id),
                ).fetchall()
            ]
            if replaced_ids:
                placeholders = ",".join("?" for _ in replaced_ids)
                connection.execute(
                    f"UPDATE robot_maps SET status = ?, replaced_at = ?, updated_at = ? "
                    f"WHERE map_id IN ({placeholders})",
                    (RobotMapStatus.REPLACED.value, now, now, *replaced_ids),
                )
                connection.execute(
                    f"UPDATE robot_map_points SET status = ?, invalidated_at = ?, updated_at = ? "
                    f"WHERE map_id IN ({placeholders}) AND status <> ?",
                    (
                        RobotMapPointStatus.INVALID.value,
                        now,
                        now,
                        *replaced_ids,
                        RobotMapPointStatus.INVALID.value,
                    ),
                )
                connection.execute(
                    f"UPDATE robot_patrol_routes SET status = ?, updated_at = ? "
                    f"WHERE map_id IN ({placeholders}) AND status <> ?",
                    (
                        RobotPatrolRouteStatus.INVALID.value,
                        now,
                        *replaced_ids,
                        RobotPatrolRouteStatus.INVALID.value,
                    ),
                )

            connection.execute(
                """
                UPDATE robot_maps
                SET status = ?, activated_at = ?, replaced_at = NULL, updated_at = ?
                WHERE map_id = ?
                """,
                (RobotMapStatus.ACTIVE.value, now, now, map_id),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM robot_maps WHERE map_id = ?", (map_id,)).fetchone()
        if row is None:
            raise RuntimeError("activated map disappeared")
        return self._row_to_map(row)

    def save_point(self, point: RobotMapPoint) -> RobotMapPoint:
        with self._lock, self._connect() as connection:
            if connection.execute("SELECT 1 FROM robot_maps WHERE map_id = ?", (point.map_id,)).fetchone() is None:
                raise ValueError("MAP_NOT_FOUND")
            connection.execute(
                """
                INSERT INTO robot_map_points (
                    point_id, map_id, name, point_type, x, y, yaw, status,
                    provider, real_motion_enabled, metadata_json,
                    created_at, updated_at, invalidated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(point_id) DO UPDATE SET
                    map_id = excluded.map_id,
                    name = excluded.name,
                    point_type = excluded.point_type,
                    x = excluded.x,
                    y = excluded.y,
                    yaw = excluded.yaw,
                    status = excluded.status,
                    provider = excluded.provider,
                    real_motion_enabled = excluded.real_motion_enabled,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at,
                    invalidated_at = excluded.invalidated_at
                """,
                self._point_values(point),
            )
            connection.commit()
        return point

    def get_point(self, point_id: str) -> RobotMapPoint | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM robot_map_points WHERE point_id = ?",
                (point_id,),
            ).fetchone()
        return self._row_to_point(row) if row else None

    def list_points(self, map_id: str, *, include_invalid: bool = True) -> list[RobotMapPoint]:
        query = "SELECT * FROM robot_map_points WHERE map_id = ?"
        params: list[Any] = [map_id]
        if not include_invalid:
            query += " AND status = ?"
            params.append(RobotMapPointStatus.VALID.value)
        query += " ORDER BY created_at ASC, point_id ASC"
        with self._lock, self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._row_to_point(row) for row in rows]

    def save_route(
        self,
        route: RobotPatrolRoute,
        points: Sequence[RobotPatrolRoutePoint],
    ) -> RobotPatrolRoute:
        ordered = sorted(points, key=lambda item: item.sequence)
        if len({item.sequence for item in ordered}) != len(ordered):
            raise ValueError("ROUTE_SEQUENCE_CONFLICT")
        if len({item.point_id for item in ordered}) != len(ordered):
            raise ValueError("ROUTE_POINT_DUPLICATE")
        if any(item.route_id != route.route_id for item in ordered):
            raise ValueError("ROUTE_ID_MISMATCH")

        with self._lock, self._connect() as connection:
            map_row = connection.execute("SELECT 1 FROM robot_maps WHERE map_id = ?", (route.map_id,)).fetchone()
            if map_row is None:
                raise ValueError("MAP_NOT_FOUND")
            for item in ordered:
                point_row = connection.execute(
                    "SELECT map_id, status FROM robot_map_points WHERE point_id = ?",
                    (item.point_id,),
                ).fetchone()
                if point_row is None:
                    raise ValueError("MAP_POINT_NOT_FOUND")
                if point_row["map_id"] != route.map_id or point_row["status"] != RobotMapPointStatus.VALID.value:
                    raise ValueError("MAP_POINTS_INVALID")
            connection.execute(
                """
                INSERT INTO robot_patrol_routes (
                    route_id, map_id, name, status, provider, real_motion_enabled,
                    metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(route_id) DO UPDATE SET
                    map_id = excluded.map_id,
                    name = excluded.name,
                    status = excluded.status,
                    provider = excluded.provider,
                    real_motion_enabled = excluded.real_motion_enabled,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                self._route_values(route),
            )
            connection.execute("DELETE FROM robot_patrol_route_points WHERE route_id = ?", (route.route_id,))
            connection.executemany(
                """
                INSERT INTO robot_patrol_route_points (
                    route_id, point_id, sequence, provider,
                    real_motion_enabled, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.route_id,
                        item.point_id,
                        item.sequence,
                        item.provider,
                        int(item.real_motion_enabled),
                        self.dump_json(item.metadata),
                    )
                    for item in ordered
                ],
            )
            connection.commit()
        return route

    def get_route(self, route_id: str) -> tuple[RobotPatrolRoute, list[RobotPatrolRoutePoint]] | None:
        with self._lock, self._connect() as connection:
            route_row = connection.execute(
                "SELECT * FROM robot_patrol_routes WHERE route_id = ?",
                (route_id,),
            ).fetchone()
            if route_row is None:
                return None
            point_rows = connection.execute(
                "SELECT * FROM robot_patrol_route_points WHERE route_id = ? ORDER BY sequence ASC",
                (route_id,),
            ).fetchall()
        route = self._row_to_route(route_row)
        points = [
            RobotPatrolRoutePoint(
                id=row["id"],
                route_id=row["route_id"],
                point_id=row["point_id"],
                sequence=int(row["sequence"]),
                provider=row["provider"],
                real_motion_enabled=bool(row["real_motion_enabled"]),
                metadata=self.load_json(row["metadata_json"]),
            )
            for row in point_rows
        ]
        return route, points

    def list_routes(self, map_id: str | None = None) -> list[RobotPatrolRoute]:
        query = "SELECT * FROM robot_patrol_routes"
        params: tuple[Any, ...] = ()
        if map_id:
            query += " WHERE map_id = ?"
            params = (map_id,)
        query += " ORDER BY created_at ASC, route_id ASC"
        with self._lock, self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_route(row) for row in rows]

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS robot_maps (
                    map_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 1,
                    provider TEXT NOT NULL DEFAULT 'mock' CHECK(provider = 'mock'),
                    real_motion_enabled INTEGER NOT NULL DEFAULT 0 CHECK(real_motion_enabled = 0),
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    activated_at TEXT,
                    replaced_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_robot_maps_single_active
                ON robot_maps(status) WHERE status = 'active'
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS robot_map_points (
                    point_id TEXT PRIMARY KEY,
                    map_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    point_type TEXT NOT NULL,
                    x REAL NOT NULL,
                    y REAL NOT NULL,
                    yaw REAL NOT NULL,
                    status TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'mock' CHECK(provider = 'mock'),
                    real_motion_enabled INTEGER NOT NULL DEFAULT 0 CHECK(real_motion_enabled = 0),
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    invalidated_at TEXT,
                    FOREIGN KEY(map_id) REFERENCES robot_maps(map_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS robot_patrol_routes (
                    route_id TEXT PRIMARY KEY,
                    map_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'mock' CHECK(provider = 'mock'),
                    real_motion_enabled INTEGER NOT NULL DEFAULT 0 CHECK(real_motion_enabled = 0),
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(map_id) REFERENCES robot_maps(map_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS robot_patrol_route_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    route_id TEXT NOT NULL,
                    point_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'mock' CHECK(provider = 'mock'),
                    real_motion_enabled INTEGER NOT NULL DEFAULT 0 CHECK(real_motion_enabled = 0),
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(route_id) REFERENCES robot_patrol_routes(route_id),
                    FOREIGN KEY(point_id) REFERENCES robot_map_points(point_id),
                    UNIQUE(route_id, sequence),
                    UNIQUE(route_id, point_id)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_robot_map_points_map_status ON robot_map_points(map_id, status)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_robot_patrol_routes_map_status ON robot_patrol_routes(map_id, status)"
            )
            connection.commit()

    def _map_values(self, item: RobotMap) -> tuple[Any, ...]:
        return (
            item.map_id,
            item.name,
            item.status.value,
            item.revision,
            item.provider,
            int(item.real_motion_enabled),
            self.dump_json(item.metadata),
            self._format_datetime(item.created_at),
            self._format_datetime(item.updated_at),
            self._format_datetime(item.activated_at),
            self._format_datetime(item.replaced_at),
        )

    def _point_values(self, item: RobotMapPoint) -> tuple[Any, ...]:
        return (
            item.point_id,
            item.map_id,
            item.name,
            item.point_type.value,
            item.x,
            item.y,
            item.yaw,
            item.status.value,
            item.provider,
            int(item.real_motion_enabled),
            self.dump_json(item.metadata),
            self._format_datetime(item.created_at),
            self._format_datetime(item.updated_at),
            self._format_datetime(item.invalidated_at),
        )

    def _route_values(self, item: RobotPatrolRoute) -> tuple[Any, ...]:
        return (
            item.route_id,
            item.map_id,
            item.name,
            item.status.value,
            item.provider,
            int(item.real_motion_enabled),
            self.dump_json(item.metadata),
            self._format_datetime(item.created_at),
            self._format_datetime(item.updated_at),
        )

    def _row_to_map(self, row: sqlite3.Row) -> RobotMap:
        return RobotMap(
            map_id=row["map_id"],
            name=row["name"],
            status=RobotMapStatus(row["status"]),
            revision=int(row["revision"]),
            provider=row["provider"],
            real_motion_enabled=bool(row["real_motion_enabled"]),
            metadata=self.load_json(row["metadata_json"]),
            created_at=self._parse_datetime(row["created_at"]),
            updated_at=self._parse_datetime(row["updated_at"]),
            activated_at=self._parse_datetime(row["activated_at"]),
            replaced_at=self._parse_datetime(row["replaced_at"]),
        )

    def _row_to_point(self, row: sqlite3.Row) -> RobotMapPoint:
        return RobotMapPoint(
            point_id=row["point_id"],
            map_id=row["map_id"],
            name=row["name"],
            point_type=RobotMapPointType(row["point_type"]),
            x=float(row["x"]),
            y=float(row["y"]),
            yaw=float(row["yaw"]),
            status=RobotMapPointStatus(row["status"]),
            provider=row["provider"],
            real_motion_enabled=bool(row["real_motion_enabled"]),
            metadata=self.load_json(row["metadata_json"]),
            created_at=self._parse_datetime(row["created_at"]),
            updated_at=self._parse_datetime(row["updated_at"]),
            invalidated_at=self._parse_datetime(row["invalidated_at"]),
        )

    def _row_to_route(self, row: sqlite3.Row) -> RobotPatrolRoute:
        return RobotPatrolRoute(
            route_id=row["route_id"],
            map_id=row["map_id"],
            name=row["name"],
            status=RobotPatrolRouteStatus(row["status"]),
            provider=row["provider"],
            real_motion_enabled=bool(row["real_motion_enabled"]),
            metadata=self.load_json(row["metadata_json"]),
            created_at=self._parse_datetime(row["created_at"]),
            updated_at=self._parse_datetime(row["updated_at"]),
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
