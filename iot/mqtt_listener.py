from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from backend.models.health_model import HealthSample, IngestionSource
from iot.parser import T10PacketParser

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None


@dataclass(slots=True)
class MQTTGatewayEnvelope:
    device_mac: str | None
    hex_payload: str
    data_type: str | None = None
    rssi: int | None = None
    raw_message: str | None = None


class MQTTGatewayListener:
    """MQTT gateway adapter for ESP32 or dedicated BLE relay hardware."""

    _HEX_CLEANER = re.compile(r"[^0-9A-Fa-f]")

    def __init__(self, parser: T10PacketParser) -> None:
        self._parser = parser

    def parse_message(self, payload: bytes | str | dict[str, Any]) -> MQTTGatewayEnvelope | None:
        if isinstance(payload, dict):
            return self._parse_json_message(payload, raw_message=None)

        raw_message = payload.decode("utf-8", errors="ignore") if isinstance(payload, bytes) else payload
        if not isinstance(raw_message, str):
            return None

        text = raw_message.strip()
        if not text:
            return None

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None

        if isinstance(parsed, dict):
            return self._parse_json_message(parsed, raw_message=text)

        return self._parse_vendor_payload(text)

    def build_sample(self, payload: bytes | str | dict[str, Any]) -> HealthSample | None:
        envelope = self.parse_message(payload)
        if envelope is None:
            return None
        return self._parser.feed(
            envelope.device_mac,
            envelope.hex_payload,
            source=IngestionSource.MQTT,
        )

    def run(
        self,
        broker_host: str,
        broker_port: int,
        topic: str,
        *,
        username: str | None = None,
        password: str | None = None,
        keepalive_seconds: int = 60,
        on_sample: Callable[[HealthSample], None] | None = None,
    ) -> None:
        if mqtt is None:
            raise RuntimeError("paho-mqtt 未安装，无法启用 MQTT 网关模式。")

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if username:
            client.username_pw_set(username=username, password=password or None)

        def handle_message(_client, _userdata, message):
            sample = self.build_sample(message.payload)
            if sample and on_sample:
                on_sample(sample)

        client.on_message = handle_message
        client.connect(broker_host, broker_port, keepalive_seconds)
        client.subscribe(topic)
        client.loop_forever()

    def _parse_json_message(
        self,
        payload: dict[str, Any],
        *,
        raw_message: str | None,
    ) -> MQTTGatewayEnvelope | None:
        if "raw_payload" in payload:
            return self._parse_vendor_payload(str(payload["raw_payload"]))

        hex_payload = payload.get("hex_payload", payload.get("payload"))
        if not isinstance(hex_payload, str):
            return None

        compact_payload = self._normalize_hex(hex_payload)
        if not compact_payload or len(compact_payload) % 2 != 0:
            return None

        device_mac = payload.get("device_mac")
        normalized_mac = self._normalize_mac(device_mac) if isinstance(device_mac, str) and device_mac.strip() else None
        data_type = str(payload["data_type"]).strip().upper() if payload.get("data_type") is not None else None
        rssi = self._coerce_rssi(payload.get("rssi"))
        return MQTTGatewayEnvelope(
            device_mac=normalized_mac,
            hex_payload=compact_payload,
            data_type=data_type or None,
            rssi=rssi,
            raw_message=raw_message,
        )

    def _parse_vendor_payload(self, payload: str) -> MQTTGatewayEnvelope | None:
        compact = self._normalize_hex(payload)
        if len(compact) <= 16:
            return None

        data_type = compact[:2]
        mac = self._normalize_mac(compact[2:14])
        rssi = self._decode_rssi(compact[14:16])
        hex_payload = compact[16:]
        if not hex_payload or len(hex_payload) % 2 != 0:
            return None

        return MQTTGatewayEnvelope(
            device_mac=mac,
            hex_payload=hex_payload,
            data_type=data_type,
            rssi=rssi,
            raw_message=payload,
        )

    @classmethod
    def _normalize_hex(cls, value: str) -> str:
        return cls._HEX_CLEANER.sub("", value).upper()

    @staticmethod
    def _normalize_mac(value: str) -> str:
        compact = value.replace(":", "").replace("-", "").upper()
        if len(compact) != 12:
            return value.strip().upper()
        return ":".join(compact[index : index + 2] for index in range(0, 12, 2))

    @staticmethod
    def _decode_rssi(value: str) -> int:
        decoded = int(value, 16)
        return decoded - 256 if decoded >= 128 else decoded

    @staticmethod
    def _coerce_rssi(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            if re.fullmatch(r"[0-9A-Fa-f]{2}", stripped):
                return MQTTGatewayListener._decode_rssi(stripped)
            try:
                return int(stripped)
            except ValueError:
                return None
        return None
