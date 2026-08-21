from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from backend.models.device_model import normalize_and_validate_mac
from backend.models.device_model import DeviceIngestMode


class DeviceBindRequest(BaseModel):
    mac_address: str
    target_user_id: str
    operator_id: str | None = None
    new_ingest_mode: DeviceIngestMode | None = None

    @field_validator("mac_address")
    @classmethod
    def validate_mac_address(cls, value: str) -> str:
        return normalize_and_validate_mac(value)


class DeviceUnbindRequest(BaseModel):
    mac_address: str
    operator_id: str | None = None
    reason: str | None = None

    @field_validator("mac_address")
    @classmethod
    def validate_mac_address(cls, value: str) -> str:
        return normalize_and_validate_mac(value)


class DeviceRebindRequest(BaseModel):
    mac_address: str
    new_user_id: str
    operator_id: str | None = None
    reason: str | None = None

    @field_validator("mac_address")
    @classmethod
    def validate_mac_address(cls, value: str) -> str:
        return normalize_and_validate_mac(value)


class DeviceSelfBindRequest(BaseModel):
    mac_address: str
    device_name: str | None = None
    model_code: str = "t10_v3"
    ingest_mode: DeviceIngestMode = DeviceIngestMode.SERIAL
    service_uuid: str | None = None
    device_uuid: str | None = None

    @field_validator("mac_address")
    @classmethod
    def validate_mac_address(cls, value: str) -> str:
        return normalize_and_validate_mac(value)


class DeviceBindLogRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    device_id: str
    old_user_id: str | None = None
    new_user_id: str | None = None
    action_type: str
    operator_id: str | None = None
    reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
