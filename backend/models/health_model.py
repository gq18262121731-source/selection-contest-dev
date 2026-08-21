from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class IngestionSource(str, Enum):
    BLE = "ble"
    MQTT = "mqtt"
    SERIAL = "serial"
    MOCK = "mock"


class HealthSample(BaseModel):
    device_mac: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    heart_rate: int = Field(ge=0, le=240)
    temperature: float = Field(ge=0.0, le=45.0)
    blood_oxygen: int = Field(ge=0, le=100)
    blood_pressure: str | None = None
    battery: int = Field(default=0, ge=0, le=100)
    sos_flag: bool = False
    source: IngestionSource = IngestionSource.MOCK
    device_uuid: str | None = None
    ambient_temperature: float | None = None
    surface_temperature: float | None = None
    steps: int | None = None
    packet_type: str | None = None
    sos_value: int | None = None
    sos_trigger: str | None = None
    raw_packet_a: str | None = None
    raw_packet_b: str | None = None
    anomaly_score: float | None = None
    health_score: int | None = None

    @field_validator("device_mac")
    @classmethod
    def normalize_mac(cls, value: str) -> str:
        return value.upper()

    @property
    def blood_pressure_pair(self) -> tuple[int, int]:
        if not self.blood_pressure:
            return 120, 80
        try:
            systolic, diastolic = self.blood_pressure.split("/", maxsplit=1)
            return int(systolic), int(diastolic)
        except (TypeError, ValueError):
            return 120, 80


class HealthTrendPoint(BaseModel):
    timestamp: datetime
    heart_rate: int
    temperature: float
    blood_oxygen: int
    blood_pressure: str | None = None
    steps: int | None = None
    health_score: int | None = None


class IngestResponse(BaseModel):
    success: bool = True
    message: str = "Sample ingested"
    device_mac: str | None = None
    sample: HealthSample | None = None
    triggered_alarm_ids: list[str] = Field(default_factory=list)
