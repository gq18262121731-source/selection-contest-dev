from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import re
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from backend.config import get_settings
from backend.models.health_model import IngestionSource


MAC_ADDRESS_PATTERN = re.compile(r"^[0-9A-F]{12}$")


def normalize_and_validate_mac(value: str) -> str:
    compact = re.sub(r"[^0-9A-Fa-f]", "", value).upper()
    if not MAC_ADDRESS_PATTERN.fullmatch(compact):
        raise ValueError("INVALID_MAC_ADDRESS")
    return ":".join(compact[index : index + 2] for index in range(0, 12, 2))


class DeviceStatus(str, Enum):
    PENDING = "pending"
    ONLINE = "online"
    OFFLINE = "offline"
    WARNING = "warning"


class DeviceActivationState(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"


class DeviceBindStatus(str, Enum):
    UNBOUND = "unbound"
    BOUND = "bound"
    DISABLED = "disabled"


class DeviceIngestMode(str, Enum):
    SERIAL = "serial"
    MQTT = "mqtt"
    BLE = "ble"
    MOCK = "mock"


INGEST_SOURCE_TO_MODE: dict[IngestionSource, DeviceIngestMode] = {
    IngestionSource.SERIAL: DeviceIngestMode.SERIAL,
    IngestionSource.MQTT: DeviceIngestMode.MQTT,
    IngestionSource.BLE: DeviceIngestMode.BLE,
    IngestionSource.MOCK: DeviceIngestMode.MOCK,
}


def ingest_source_matches_mode(
    ingest_mode: DeviceIngestMode | str | None,
    source: IngestionSource | str | None,
) -> bool:
    if ingest_mode is None or source is None:
        return False
    try:
        normalized_mode = ingest_mode if isinstance(ingest_mode, DeviceIngestMode) else DeviceIngestMode(str(ingest_mode))
        normalized_source = source if isinstance(source, IngestionSource) else IngestionSource(str(source))
    except ValueError:
        return False
    return INGEST_SOURCE_TO_MODE.get(normalized_source) == normalized_mode


class DeviceRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    mac_address: str
    device_name: str = Field(default_factory=lambda: get_settings().default_device_name)
    model_code: str = "t10_v3"
    ingest_mode: DeviceIngestMode = DeviceIngestMode.SERIAL
    service_uuid: str = Field(default_factory=lambda: get_settings().service_uuid.upper())
    device_uuid: str = Field(default_factory=lambda: get_settings().device_uuid.upper())
    user_id: str | None = None
    status: DeviceStatus = DeviceStatus.PENDING
    activation_state: DeviceActivationState = DeviceActivationState.PENDING
    bind_status: DeviceBindStatus = DeviceBindStatus.UNBOUND
    last_seen_at: datetime | None = None
    last_packet_type: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("mac_address")
    @classmethod
    def normalize_mac(cls, value: str) -> str:
        return normalize_and_validate_mac(value)


class DeviceRegisterRequest(BaseModel):
    mac_address: str
    device_name: str = Field(default_factory=lambda: get_settings().default_device_name)
    model_code: str = "t10_v3"
    ingest_mode: DeviceIngestMode = DeviceIngestMode.SERIAL
    service_uuid: str = Field(default_factory=lambda: get_settings().service_uuid.upper())
    device_uuid: str = Field(default_factory=lambda: get_settings().device_uuid.upper())
    user_id: str | None = None

    @field_validator("mac_address")
    @classmethod
    def validate_mac_address(cls, value: str) -> str:
        return normalize_and_validate_mac(value)


class SerialTargetSwitchRequest(BaseModel):
    mac_address: str

    @field_validator("mac_address")
    @classmethod
    def validate_mac_address(cls, value: str) -> str:
        return normalize_and_validate_mac(value)


class SerialTargetSwitchResponse(BaseModel):
    active_target_mac: str | None = None
    active_target_device_name: str | None = None
    previous_target_mac: str | None = None
    switched_at: datetime
