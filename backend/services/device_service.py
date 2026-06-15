from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import sqlite3
from threading import RLock

from backend.models.device_bind_model import (
    DeviceBindLogRecord,
    DeviceBindRequest,
    DeviceRebindRequest,
    DeviceUnbindRequest,
)
from backend.models.device_model import (
    DeviceActivationState,
    DeviceBindStatus,
    DeviceIngestMode,
    DeviceRecord,
    DeviceRegisterRequest,
    DeviceStatus,
)
from backend.models.user_model import UserRole
from backend.services.user_service import UserService


class DeviceService:
    """Tracks device registration, ownership and bind history with SQLite persistence."""

    def __init__(self, user_service: UserService | None = None, *, database_url: str | None = None) -> None:
        self._devices: OrderedDict[str, DeviceRecord] = OrderedDict()
        self._bind_logs: list[DeviceBindLogRecord] = []
        self._active_serial_target_mac: str | None = None
        self._user_service = user_service
        self._database_path = self._resolve_sqlite_path(database_url)
        self._lock = RLock()
        self._initialize_storage()
        self._load_from_storage()

    def seed_devices(self, devices: list[DeviceRecord]) -> None:
        with self._lock:
            for device in devices:
                if device.mac_address in self._devices:
                    continue
                self._devices[device.mac_address] = device
                self._upsert_device(device)

    def list_devices(self) -> list[DeviceRecord]:
        with self._lock:
            return list(self._devices.values())

    @staticmethod
    def _normalize_mac(mac_address: str) -> str:
        compact = "".join(ch for ch in mac_address if ch.isalnum()).upper()
        if len(compact) == 12:
            return ":".join(compact[i : i + 2] for i in range(0, 12, 2))
        return mac_address.upper()

    def get_device(self, mac_address: str) -> DeviceRecord | None:
        with self._lock:
            normalized = self._normalize_mac(mac_address)
            return self._devices.get(normalized)

    def get_active_serial_target(self) -> DeviceRecord | None:
        with self._lock:
            if not self._active_serial_target_mac:
                return None
            return self._devices.get(self._active_serial_target_mac)

    def get_active_serial_target_mac(self) -> str | None:
        with self._lock:
            return self._active_serial_target_mac

    def refresh_active_serial_target(self) -> DeviceRecord | None:
        with self._lock:
            return self._refresh_active_serial_target_locked()

    def set_active_serial_target(self, mac_address: str) -> tuple[DeviceRecord, str | None]:
        with self._lock:
            device = self.get_device(mac_address)
            if device is None:
                raise ValueError("DEVICE_NOT_FOUND")
            if device.ingest_mode != DeviceIngestMode.SERIAL:
                raise ValueError("DEVICE_NOT_SERIAL")
            if device.bind_status == DeviceBindStatus.DISABLED:
                raise ValueError("DEVICE_DISABLED")
            previous_target_mac = self._active_serial_target_mac
            target = self._set_active_serial_target_locked(device.mac_address)
            if target is None:
                raise ValueError("DEVICE_NOT_SERIAL")
            return target, previous_target_mac

    def register_device(self, payload: DeviceRegisterRequest, *, operator_id: str | None = None) -> DeviceRecord:
        with self._lock:
            existing = self.get_device(payload.mac_address)
            if existing:
                raise ValueError("DEVICE_ALREADY_EXISTS")
            device_name = payload.device_name.strip() or "T10-WATCH"
            if payload.user_id:
                self._validate_binding_target(payload.user_id)
                if payload.ingest_mode == DeviceIngestMode.SERIAL:
                    self._detach_conflicting_mock_devices(
                        user_id=payload.user_id,
                        device_name=device_name,
                        operator_id=operator_id,
                        reason="serial_device_override",
                    )
                self._ensure_unique_model_per_target_user(payload.user_id, device_name)
                bind_status = DeviceBindStatus.BOUND
                user_id = payload.user_id
            else:
                bind_status = DeviceBindStatus.UNBOUND
                user_id = None
            record = DeviceRecord(
                mac_address=payload.mac_address,
                device_name=device_name,
                model_code=payload.model_code,
                ingest_mode=payload.ingest_mode,
                service_uuid=payload.service_uuid,
                device_uuid=payload.device_uuid,
                user_id=user_id,
                status=DeviceStatus.PENDING,
                activation_state=DeviceActivationState.PENDING,
                bind_status=bind_status,
            )
            self._devices[record.mac_address] = record
            self._upsert_device(record)
            if record.ingest_mode == DeviceIngestMode.SERIAL:
                self._set_active_serial_target_locked(record.mac_address)
            if payload.user_id:
                log = DeviceBindLogRecord(
                    device_id=record.id,
                    old_user_id=None,
                    new_user_id=payload.user_id,
                    action_type="bind",
                    operator_id=operator_id,
                )
                self._bind_logs.append(log)
                self._insert_bind_log(log)
            return self._devices[record.mac_address]

    def ensure_device(
        self,
        mac_address: str,
        device_name: str = "T10-WATCH",
        *,
        ingest_mode: DeviceIngestMode = DeviceIngestMode.SERIAL,
    ) -> DeviceRecord:
        with self._lock:
            existing = self.get_device(mac_address)
            if existing:
                return existing
            request = DeviceRegisterRequest(
                mac_address=mac_address,
                device_name=device_name,
                ingest_mode=ingest_mode,
            )
            return self.register_device(request)

    def update_status(self, mac_address: str, status: DeviceStatus) -> DeviceRecord | None:
        with self._lock:
            device = self.get_device(mac_address)
            if not device:
                return None
            activation_state = device.activation_state
            if status in {DeviceStatus.ONLINE, DeviceStatus.WARNING}:
                activation_state = DeviceActivationState.ACTIVE
            updated = device.model_copy(update={"status": status, "activation_state": activation_state})
            self._devices[mac_address.upper()] = updated
            self._upsert_device(updated)
            return updated

    def mark_seen(
        self,
        mac_address: str,
        *,
        seen_at: datetime,
        packet_type: str | None,
        status: DeviceStatus = DeviceStatus.ONLINE,
    ) -> DeviceRecord | None:
        with self._lock:
            device = self.get_device(mac_address)
            if not device:
                return None
            updated = device.model_copy(
                update={
                    "status": status,
                    "activation_state": DeviceActivationState.ACTIVE,
                    "last_seen_at": seen_at,
                    "last_packet_type": packet_type or device.last_packet_type,
                }
            )
            self._devices[updated.mac_address] = updated
            self._upsert_device(updated)
            return updated

    def bind_device(self, payload: DeviceBindRequest) -> DeviceBindLogRecord:
        with self._lock:
            device = self.get_device(payload.mac_address)
            if device is None:
                raise ValueError("DEVICE_NOT_FOUND")
            self._validate_binding_target(payload.target_user_id)
            if device.user_id and device.user_id != payload.target_user_id:
                raise ValueError("DEVICE_ALREADY_BOUND")
            if device.user_id == payload.target_user_id and device.bind_status == DeviceBindStatus.BOUND:
                raise ValueError("DEVICE_ALREADY_BOUND_TO_TARGET")
            if device.ingest_mode == DeviceIngestMode.SERIAL:
                self._detach_conflicting_mock_devices(
                    user_id=payload.target_user_id,
                    device_name=device.device_name,
                    operator_id=payload.operator_id,
                    reason="serial_device_override",
                    current_device_id=device.id,
                )
            self._ensure_unique_model_per_target_user(
                payload.target_user_id,
                device.device_name,
                current_device_id=device.id,
            )
            update_data = {
                "user_id": payload.target_user_id,
                "bind_status": DeviceBindStatus.BOUND,
            }
            if payload.new_ingest_mode and device.ingest_mode != payload.new_ingest_mode:
                update_data["ingest_mode"] = payload.new_ingest_mode

            updated = device.model_copy(update=update_data)
            self._devices[updated.mac_address] = updated
            self._upsert_device(updated)
            if updated.ingest_mode == DeviceIngestMode.SERIAL:
                self._set_active_serial_target_locked(updated.mac_address)
            elif device.ingest_mode == DeviceIngestMode.SERIAL:
                self._refresh_active_serial_target_locked()
            log = DeviceBindLogRecord(
                device_id=device.id,
                old_user_id=device.user_id,
                new_user_id=payload.target_user_id,
                action_type="bind",
                operator_id=payload.operator_id,
            )
            self._bind_logs.append(log)
            self._insert_bind_log(log)
            return log

    def unbind_device(self, payload: DeviceUnbindRequest) -> DeviceBindLogRecord:
        with self._lock:
            device = self.get_device(payload.mac_address)
            if device is None:
                raise ValueError("DEVICE_NOT_FOUND")
            if device.user_id is None and device.bind_status != DeviceBindStatus.BOUND:
                raise ValueError("DEVICE_NOT_BOUND")
            update: dict[str, object] = {
                "user_id": None,
                "bind_status": DeviceBindStatus.UNBOUND,
            }
            if device.ingest_mode == DeviceIngestMode.SERIAL:
                update["status"] = DeviceStatus.PENDING
                update["activation_state"] = DeviceActivationState.PENDING
            updated = device.model_copy(update=update)
            self._devices[updated.mac_address] = updated
            self._upsert_device(updated)
            if updated.ingest_mode == DeviceIngestMode.SERIAL:
                self._refresh_active_serial_target_locked()
            log = DeviceBindLogRecord(
                device_id=updated.id,
                old_user_id=device.user_id,
                new_user_id=None,
                action_type="unbind",
                operator_id=payload.operator_id,
                reason=payload.reason,
            )
            self._bind_logs.append(log)
            self._insert_bind_log(log)
            return log

    def rebind_device(self, payload: DeviceRebindRequest) -> DeviceBindLogRecord:
        with self._lock:
            device = self.get_device(payload.mac_address)
            if device is None:
                raise ValueError("DEVICE_NOT_FOUND")
            if device.user_id is None or device.bind_status != DeviceBindStatus.BOUND:
                raise ValueError("DEVICE_NOT_BOUND")
            self._validate_binding_target(payload.new_user_id)
            if device.user_id == payload.new_user_id:
                raise ValueError("DEVICE_ALREADY_BOUND_TO_TARGET")
            if device.ingest_mode == DeviceIngestMode.SERIAL:
                self._detach_conflicting_mock_devices(
                    user_id=payload.new_user_id,
                    device_name=device.device_name,
                    operator_id=payload.operator_id,
                    reason="serial_device_override",
                    current_device_id=device.id,
                )
            self._ensure_unique_model_per_target_user(
                payload.new_user_id,
                device.device_name,
                current_device_id=device.id,
            )
            updated = device.model_copy(update={"user_id": payload.new_user_id, "bind_status": DeviceBindStatus.BOUND})
            self._devices[updated.mac_address] = updated
            self._upsert_device(updated)
            if updated.ingest_mode == DeviceIngestMode.SERIAL:
                self._set_active_serial_target_locked(updated.mac_address)
            elif device.ingest_mode == DeviceIngestMode.SERIAL:
                self._refresh_active_serial_target_locked()
            log = DeviceBindLogRecord(
                device_id=updated.id,
                old_user_id=device.user_id,
                new_user_id=payload.new_user_id,
                action_type="rebind",
                operator_id=payload.operator_id,
                reason=payload.reason,
            )
            self._bind_logs.append(log)
            self._insert_bind_log(log)
            return log

    def list_bind_logs(self, mac_address: str | None = None) -> list[DeviceBindLogRecord]:
        with self._lock:
            if mac_address is None:
                return list(self._bind_logs)
            device = self.get_device(mac_address)
            if device is None:
                return []
            return [log for log in self._bind_logs if log.device_id == device.id]

    def delete_device(self, mac_address: str) -> DeviceRecord:
        with self._lock:
            device = self.get_device(mac_address)
            if device is None:
                raise ValueError("DEVICE_NOT_FOUND")
            active_target_deleted = device.mac_address == self._active_serial_target_mac
            self._devices.pop(device.mac_address, None)
            self._bind_logs = [log for log in self._bind_logs if log.device_id != device.id]
            self._delete_device(device.id)
            self._delete_bind_logs(device.id)
            if active_target_deleted:
                self._refresh_active_serial_target_locked()
            return device

    def reset(self) -> None:
        with self._lock:
            self._devices.clear()
            self._bind_logs.clear()
            self._active_serial_target_mac = None
            with self._connection() as connection:
                connection.execute("DELETE FROM device_bind_logs")
                connection.execute("DELETE FROM devices")
                connection.commit()

    def _validate_binding_target(self, user_id: str) -> None:
        if self._user_service is None:
            return
        user = self._user_service.get_user(user_id)
        if user is None and self._is_demo_elder_user_id(user_id):
            return
        if user is None:
            raise ValueError("USER_NOT_FOUND")
        if user.role != UserRole.ELDER:
            raise ValueError("INVALID_BIND_TARGET_ROLE")

    def _ensure_unique_model_per_target_user(
        self,
        user_id: str,
        device_name: str,
        *,
        current_device_id: str | None = None,
    ) -> None:
        normalized_name = self._normalize_device_name(device_name)
        for device in self._devices.values():
            if device.user_id != user_id or device.bind_status != DeviceBindStatus.BOUND:
                continue
            if current_device_id and device.id == current_device_id:
                continue
            if self._normalize_device_name(device.device_name) == normalized_name:
                raise ValueError("TARGET_USER_ALREADY_HAS_DEVICE_OF_SAME_MODEL")

    def _detach_conflicting_mock_devices(
        self,
        *,
        user_id: str,
        device_name: str,
        operator_id: str | None,
        reason: str,
        current_device_id: str | None = None,
    ) -> None:
        normalized_name = self._normalize_device_name(device_name)
        for device in list(self._devices.values()):
            if device.user_id != user_id or device.bind_status != DeviceBindStatus.BOUND:
                continue
            if current_device_id and device.id == current_device_id:
                continue
            if device.ingest_mode != DeviceIngestMode.MOCK:
                continue
            if self._normalize_device_name(device.device_name) != normalized_name:
                continue
            updated = device.model_copy(update={"user_id": None, "bind_status": DeviceBindStatus.UNBOUND})
            self._devices[updated.mac_address] = updated
            self._upsert_device(updated)
            if updated.ingest_mode == DeviceIngestMode.SERIAL:
                self._refresh_active_serial_target_locked()
            log = DeviceBindLogRecord(
                device_id=updated.id,
                old_user_id=device.user_id,
                new_user_id=None,
                action_type="unbind",
                operator_id=operator_id,
                reason=reason,
            )
            self._bind_logs.append(log)
            self._insert_bind_log(log)

    @staticmethod
    def _normalize_device_name(device_name: str) -> str:
        return device_name.strip().upper()

    @staticmethod
    def _is_demo_elder_user_id(user_id: str) -> bool:
        normalized = user_id.strip().lower()
        if normalized.startswith("elder-"):
            return normalized.removeprefix("elder-").isdigit()
        if not normalized.startswith("elder"):
            return False
        suffix = normalized.removeprefix("elder")
        family_part, separator, elder_part = suffix.partition("_")
        return bool(separator) and family_part.isdigit() and elder_part.isdigit()

    def _initialize_storage(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY,
                    mac_address TEXT NOT NULL UNIQUE,
                    device_name TEXT NOT NULL,
                    model_code TEXT NOT NULL DEFAULT 't10_v3',
                    ingest_mode TEXT NOT NULL DEFAULT 'serial',
                    service_uuid TEXT NOT NULL DEFAULT '',
                    device_uuid TEXT NOT NULL DEFAULT '',
                    user_id TEXT,
                    status TEXT NOT NULL,
                    activation_state TEXT NOT NULL DEFAULT 'pending',
                    bind_status TEXT NOT NULL,
                    last_seen_at TEXT,
                    last_packet_type TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._ensure_table_columns(
                connection,
                "devices",
                {
                    "model_code": "TEXT NOT NULL DEFAULT 't10_v3'",
                    "ingest_mode": "TEXT NOT NULL DEFAULT 'serial'",
                    "service_uuid": "TEXT NOT NULL DEFAULT ''",
                    "device_uuid": "TEXT NOT NULL DEFAULT ''",
                    "activation_state": "TEXT NOT NULL DEFAULT 'pending'",
                    "last_seen_at": "TEXT",
                    "last_packet_type": "TEXT",
                },
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS device_bind_logs (
                    id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    old_user_id TEXT,
                    new_user_id TEXT,
                    action_type TEXT NOT NULL,
                    operator_id TEXT,
                    reason TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def _load_from_storage(self) -> None:
        with self._lock, self._connection() as connection:
            device_rows = connection.execute(
                """
                SELECT
                    id,
                    mac_address,
                    device_name,
                    model_code,
                    ingest_mode,
                    service_uuid,
                    device_uuid,
                    user_id,
                    status,
                    activation_state,
                    bind_status,
                    last_seen_at,
                    last_packet_type,
                    created_at
                FROM devices
                ORDER BY created_at ASC
                """
            ).fetchall()
            self._devices = OrderedDict(
                (
                    row["mac_address"],
                    DeviceRecord(
                        id=row["id"],
                        mac_address=row["mac_address"],
                        device_name=row["device_name"],
                        model_code=row["model_code"] or "t10_v3",
                        ingest_mode=row["ingest_mode"] or "serial",
                        service_uuid=row["service_uuid"] or "",
                        device_uuid=row["device_uuid"] or "",
                        user_id=row["user_id"],
                        status=DeviceStatus(row["status"]),
                        activation_state=DeviceActivationState(row["activation_state"] or "pending"),
                        bind_status=DeviceBindStatus(row["bind_status"]),
                        last_seen_at=row["last_seen_at"],
                        last_packet_type=row["last_packet_type"],
                        created_at=row["created_at"],
                    ),
                )
                for row in device_rows
            )

            bind_rows = connection.execute(
                """
                SELECT id, device_id, old_user_id, new_user_id, action_type, operator_id, reason, created_at
                FROM device_bind_logs
                ORDER BY created_at ASC
                """
            ).fetchall()
            self._bind_logs = [
                DeviceBindLogRecord(
                    id=row["id"],
                    device_id=row["device_id"],
                    old_user_id=row["old_user_id"],
                    new_user_id=row["new_user_id"],
                    action_type=row["action_type"],
                    operator_id=row["operator_id"],
                    reason=row["reason"],
                    created_at=row["created_at"],
                )
                for row in bind_rows
            ]
            self._refresh_active_serial_target_locked()

    def _set_active_serial_target_locked(self, mac_address: str | None) -> DeviceRecord | None:
        if not mac_address:
            self._active_serial_target_mac = None
            return None
        normalized_mac = self._normalize_mac(mac_address)
        device = self._devices.get(normalized_mac)
        if (
            device is None
            or device.ingest_mode != DeviceIngestMode.SERIAL
            or device.bind_status != DeviceBindStatus.BOUND
            or not device.user_id
            or device.bind_status == DeviceBindStatus.DISABLED
        ):
            self._active_serial_target_mac = None
            return None
        self._active_serial_target_mac = device.mac_address
        return device

    def _refresh_active_serial_target_locked(self) -> DeviceRecord | None:
        candidates = sorted(
            (
                device
                for device in self._devices.values()
                if device.ingest_mode == DeviceIngestMode.SERIAL
                and device.bind_status == DeviceBindStatus.BOUND
                and device.user_id
                and device.bind_status != DeviceBindStatus.DISABLED
            ),
            key=lambda item: (item.created_at, item.mac_address),
        )
        if not candidates:
            self._active_serial_target_mac = None
            return None
        target = candidates[-1]
        self._active_serial_target_mac = target.mac_address
        return target

    def _upsert_device(self, device: DeviceRecord) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO devices (
                    id,
                    mac_address,
                    device_name,
                    model_code,
                    ingest_mode,
                    service_uuid,
                    device_uuid,
                    user_id,
                    status,
                    activation_state,
                    bind_status,
                    last_seen_at,
                    last_packet_type,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mac_address) DO UPDATE SET
                    id = excluded.id,
                    device_name = excluded.device_name,
                    model_code = excluded.model_code,
                    ingest_mode = excluded.ingest_mode,
                    service_uuid = excluded.service_uuid,
                    device_uuid = excluded.device_uuid,
                    user_id = excluded.user_id,
                    status = excluded.status,
                    activation_state = excluded.activation_state,
                    bind_status = excluded.bind_status,
                    last_seen_at = excluded.last_seen_at,
                    last_packet_type = excluded.last_packet_type,
                    created_at = excluded.created_at
                """,
                (
                    device.id,
                    device.mac_address,
                    device.device_name,
                    device.model_code,
                    device.ingest_mode.value,
                    device.service_uuid,
                    device.device_uuid,
                    device.user_id,
                    device.status.value,
                    device.activation_state.value,
                    device.bind_status.value,
                    device.last_seen_at.isoformat() if device.last_seen_at else None,
                    device.last_packet_type,
                    device.created_at.isoformat(),
                ),
            )
            connection.commit()

    def _insert_bind_log(self, log: DeviceBindLogRecord) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO device_bind_logs
                (id, device_id, old_user_id, new_user_id, action_type, operator_id, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log.id,
                    log.device_id,
                    log.old_user_id,
                    log.new_user_id,
                    log.action_type,
                    log.operator_id,
                    log.reason,
                    log.created_at.isoformat(),
                ),
            )
            connection.commit()

    def _delete_device(self, device_id: str) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM devices WHERE id = ?", (device_id,))
            connection.commit()

    def _delete_bind_logs(self, device_id: str) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM device_bind_logs WHERE device_id = ?", (device_id,))
            connection.commit()

    @staticmethod
    def _ensure_table_columns(connection: sqlite3.Connection, table_name: str, columns: dict[str, str]) -> None:
        existing_columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        for column_name, definition in columns.items():
            if column_name in existing_columns:
                continue
            connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
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

    @staticmethod
    def _resolve_sqlite_path(database_url: str | None) -> Path:
        if not database_url:
            return Path("data") / "app.db"
        prefix = "sqlite+aiosqlite:///"
        if database_url.startswith(prefix):
            return Path(database_url[len(prefix):])
        return Path("data") / "app.db"
