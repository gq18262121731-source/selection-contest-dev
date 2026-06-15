from __future__ import annotations

from datetime import datetime, timezone

from backend.models.auth_model import SessionUser
from backend.models.notification_model import MobilePushDeviceRecord, MobilePushDeviceUpsertRequest
from backend.repositories.sqlite_base import SQLiteRepositoryBase


class MobilePushDeviceRepository(SQLiteRepositoryBase):
    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS mobile_push_devices (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    family_id TEXT,
                    community_id TEXT,
                    installation_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    push_token TEXT NOT NULL,
                    notifications_enabled INTEGER NOT NULL DEFAULT 1,
                    remote_push_ready INTEGER NOT NULL DEFAULT 0,
                    app_version TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    revoked_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_mobile_push_devices_installation_active
                ON mobile_push_devices (installation_id)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_mobile_push_devices_user_active
                ON mobile_push_devices (user_id, revoked_at)
                """
            )
            connection.commit()

    def upsert_for_user(
        self,
        *,
        user: SessionUser,
        payload: MobilePushDeviceUpsertRequest,
    ) -> MobilePushDeviceRecord:
        existing = self.get_by_installation(payload.installation_id)
        now = datetime.now(timezone.utc)
        record = MobilePushDeviceRecord(
            id=existing.id if existing is not None else MobilePushDeviceRecord(user_id=user.id, role=user.role, installation_id=payload.installation_id, provider=payload.provider, platform=payload.platform, push_token=payload.push_token).id,
            user_id=user.id,
            role=user.role,
            family_id=user.family_id,
            community_id=user.community_id,
            installation_id=payload.installation_id,
            provider=payload.provider,
            platform=payload.platform,
            push_token=payload.push_token,
            notifications_enabled=payload.notifications_enabled,
            remote_push_ready=payload.remote_push_ready,
            app_version=payload.app_version,
            metadata=payload.metadata,
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
            revoked_at=None,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO mobile_push_devices (
                    id, user_id, role, family_id, community_id, installation_id,
                    provider, platform, push_token, notifications_enabled, remote_push_ready,
                    app_version, metadata_json, created_at, updated_at, revoked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(installation_id) DO UPDATE SET
                    user_id=excluded.user_id,
                    role=excluded.role,
                    family_id=excluded.family_id,
                    community_id=excluded.community_id,
                    provider=excluded.provider,
                    platform=excluded.platform,
                    push_token=excluded.push_token,
                    notifications_enabled=excluded.notifications_enabled,
                    remote_push_ready=excluded.remote_push_ready,
                    app_version=excluded.app_version,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at,
                    revoked_at=NULL
                """,
                (
                    record.id,
                    record.user_id,
                    record.role.value,
                    record.family_id,
                    record.community_id,
                    record.installation_id,
                    record.provider.value,
                    record.platform.value,
                    record.push_token,
                    int(record.notifications_enabled),
                    int(record.remote_push_ready),
                    record.app_version,
                    self.dump_json(record.metadata),
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                    record.revoked_at.isoformat() if record.revoked_at else None,
                ),
            )
            connection.commit()
        return record

    def list_active_for_user(self, user_id: str) -> list[MobilePushDeviceRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM mobile_push_devices
                WHERE user_id = ? AND revoked_at IS NULL
                ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def list_active_for_users(self, user_ids: list[str]) -> list[MobilePushDeviceRecord]:
        normalized = [user_id.strip() for user_id in user_ids if user_id and user_id.strip()]
        if not normalized:
            return []
        placeholders = ",".join("?" for _ in normalized)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM mobile_push_devices
                WHERE revoked_at IS NULL AND user_id IN ({placeholders})
                ORDER BY updated_at DESC
                """,
                tuple(normalized),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def revoke_for_user_installation(self, *, user_id: str, installation_id: str) -> MobilePushDeviceRecord | None:
        existing = self.get_by_user_and_installation(user_id=user_id, installation_id=installation_id)
        if existing is None:
            return None
        revoked = existing.model_copy(update={"revoked_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE mobile_push_devices
                SET revoked_at = ?, updated_at = ?
                WHERE user_id = ? AND installation_id = ?
                """,
                (
                    revoked.revoked_at.isoformat() if revoked.revoked_at else None,
                    revoked.updated_at.isoformat(),
                    user_id,
                    installation_id,
                ),
            )
            connection.commit()
        return revoked

    def get_by_installation(self, installation_id: str) -> MobilePushDeviceRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM mobile_push_devices
                WHERE installation_id = ?
                LIMIT 1
                """,
                (installation_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def get_by_user_and_installation(self, *, user_id: str, installation_id: str) -> MobilePushDeviceRecord | None:
        record = self.get_by_installation(installation_id)
        if record is None or record.user_id != user_id:
            return None
        return record

    def _row_to_record(self, row) -> MobilePushDeviceRecord:
        return MobilePushDeviceRecord(
            id=row["id"],
            user_id=row["user_id"],
            role=row["role"],
            family_id=row["family_id"],
            community_id=row["community_id"],
            installation_id=row["installation_id"],
            provider=row["provider"],
            platform=row["platform"],
            push_token=row["push_token"],
            notifications_enabled=bool(row["notifications_enabled"]),
            remote_push_ready=bool(row["remote_push_ready"]),
            app_version=row["app_version"],
            metadata=self.load_json(row["metadata_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            revoked_at=datetime.fromisoformat(row["revoked_at"]) if row["revoked_at"] else None,
        )
