from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from backend.models.health_model import HealthSample, IngestionSource


class PacketKind(str, Enum):
    BROADCAST = "broadcast"
    RESPONSE_A = "response_a"
    RESPONSE_B = "response_b"
    LEGACY_RESPONSE_A = "legacy_response_a"
    LEGACY_RESPONSE_B = "legacy_response_b"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class PacketLayout:
    legacy_marker_offset: int = 12
    legacy_header_length: int = 14
    legacy_response_a_marker: bytes = bytes.fromhex("1803")
    legacy_response_b_marker: bytes = bytes.fromhex("0318")
    response_a_marker: bytes = bytes.fromhex("161803")
    response_b_marker: bytes = bytes.fromhex("160318")
    response_scan_limit: int = 64
    broadcast_prefix: bytes = bytes.fromhex("0201061AFF4C000215")
    default_uuid: str = "52616469-6F6C-616E-642D-541000000000"


@dataclass(slots=True)
class PartialPacket:
    first_seen: datetime
    packet_a: bytes | None = None
    packet_b: bytes | None = None
    raw_a: str | None = None
    raw_b: str | None = None
    sample: HealthSample | None = None


class T10PacketParser:
    """Parser for T10 bracelet data aligned with the field script in shouhuan.py."""

    def __init__(
        self,
        layout: PacketLayout | None = None,
        merge_timeout_seconds: float = 1.0,
        sos_window_seconds: int = 15,
    ) -> None:
        self._layout = layout or PacketLayout()
        self._merge_timeout = merge_timeout_seconds
        self._partials: dict[str, PartialPacket] = {}
        self._sos_events: dict[str, deque[datetime]] = defaultdict(deque)
        self._sos_window = timedelta(seconds=sos_window_seconds)

    def feed(
        self,
        device_mac: str | None,
        payload: str | bytes,
        *,
        source: IngestionSource = IngestionSource.BLE,
        timestamp: datetime | None = None,
    ) -> HealthSample | None:
        timestamp = timestamp or datetime.now(timezone.utc)
        stale = self._flush_stale_partials(timestamp)
        packet = self._normalize_payload(payload)
        kind = self.identify_packet(packet)

        if kind is PacketKind.UNKNOWN:
            return stale

        if kind is PacketKind.BROADCAST:
            return self._decode_broadcast(device_mac, packet, timestamp, source) or stale

        if kind is PacketKind.RESPONSE_A:
            return self._handle_response_a(device_mac, packet, timestamp, source) or stale

        if kind is PacketKind.RESPONSE_B:
            return self._handle_response_b(device_mac, packet, timestamp, source) or stale

        return self._decode_legacy(device_mac, packet, kind, timestamp, source) or stale

    def identify_packet(self, payload: bytes) -> PacketKind:
        if payload.startswith(self._layout.broadcast_prefix) and len(payload) >= 29:
            return PacketKind.BROADCAST

        response_a_index = self._find_response_marker(payload, self._layout.response_a_marker)
        if response_a_index != -1 and len(payload) >= response_a_index + 20:
            return PacketKind.RESPONSE_A

        response_b_index = self._find_response_marker(payload, self._layout.response_b_marker)
        if response_b_index != -1 and len(payload) >= response_b_index + 5:
            return PacketKind.RESPONSE_B

        if len(payload) <= self._layout.legacy_marker_offset + 1:
            return PacketKind.UNKNOWN

        marker = payload[
            self._layout.legacy_marker_offset : self._layout.legacy_marker_offset + 2
        ]
        if marker == self._layout.legacy_response_a_marker:
            return PacketKind.LEGACY_RESPONSE_A
        if marker == self._layout.legacy_response_b_marker:
            return PacketKind.LEGACY_RESPONSE_B
        return PacketKind.UNKNOWN

    @staticmethod
    def _normalize_payload(payload: str | bytes) -> bytes:
        if isinstance(payload, bytes):
            return payload
        compact = payload.replace(" ", "").replace(":", "").replace("-", "")
        return bytes.fromhex(compact)

    def _decode_broadcast(
        self,
        device_mac: str | None,
        payload: bytes,
        timestamp: datetime,
        source: IngestionSource,
    ) -> HealthSample | None:
        if not device_mac:
            return None

        uuid_bytes = payload[9:25]
        heart_rate = payload[25]
        blood_oxygen = payload[26]
        raw_temperature = round(int.from_bytes(payload[27:29], byteorder="big") / 100.0, 2)
        # Broadcast temperature may come from surface sensor depending on firmware.
        # Only keep it as body temperature when it is physiologically plausible.
        temperature = raw_temperature if 35.0 <= raw_temperature <= 45.0 else 0.0
        sos_value = payload[29] if len(payload) >= 30 else 0
        sos_trigger = self._decode_sos_trigger(sos_value)
        sos_flag = sos_value != 0

        normalized_mac = self._normalize_mac(device_mac)
        return HealthSample(
            device_mac=normalized_mac,
            timestamp=timestamp,
            heart_rate=heart_rate,
            temperature=temperature,
            blood_oxygen=blood_oxygen,
            battery=0,
            sos_flag=sos_flag,
            sos_value=sos_value,
            sos_trigger=sos_trigger,
            source=source,
            device_uuid=self._format_uuid(uuid_bytes),
            surface_temperature=raw_temperature,
            packet_type=PacketKind.BROADCAST.value,
            raw_packet_a=payload.hex().upper(),
        )

    def _decode_response_a(
        self,
        device_mac: str | None,
        payload: bytes,
        timestamp: datetime,
        source: IngestionSource,
    ) -> HealthSample | None:
        marker_index = self._find_response_marker(payload, self._layout.response_a_marker)
        if marker_index == -1 or len(payload) < marker_index + 20:
            return None

        ambient_temperature = round(
            int.from_bytes(payload[marker_index + 3 : marker_index + 5], byteorder="big") / 100.0,
            2,
        )
        battery = payload[marker_index + 5]
        surface_temperature = round(
            int.from_bytes(payload[marker_index + 6 : marker_index + 8], byteorder="big") / 100.0,
            2,
        )
        sample_temperature = surface_temperature if 35.0 <= surface_temperature <= 45.0 else 0.0
        heart_rate = int.from_bytes(payload[marker_index + 8 : marker_index + 10], byteorder="big")
        blood_oxygen = int.from_bytes(payload[marker_index + 10 : marker_index + 12], byteorder="big")
        resolved_mac = self._normalize_mac(device_mac) if device_mac else None
        if not resolved_mac:
            resolved_mac = self._format_mac(payload[marker_index + 12 : marker_index + 18])
        steps = int.from_bytes(payload[marker_index + 18 : marker_index + 20], byteorder="big")

        return HealthSample(
            device_mac=resolved_mac,
            timestamp=timestamp,
            heart_rate=heart_rate,
            temperature=sample_temperature,
            blood_oxygen=blood_oxygen,
            battery=battery,
            sos_flag=False,
            source=source,
            device_uuid=self._layout.default_uuid,
            ambient_temperature=ambient_temperature,
            surface_temperature=surface_temperature,
            steps=steps,
            packet_type=PacketKind.RESPONSE_A.value,
            raw_packet_a=payload.hex().upper(),
        )

    def _flush_stale_partials(self, now: datetime) -> HealthSample | None:
        stale_macs = [
            mac
            for mac, partial in self._partials.items()
            if now - partial.first_seen > timedelta(seconds=self._merge_timeout)
        ]
        for mac in stale_macs:
            self._partials.pop(mac, None)
        return None

    def _handle_response_a(
        self,
        device_mac: str | None,
        payload: bytes,
        timestamp: datetime,
        source: IngestionSource,
    ) -> HealthSample | None:
        sample = self._decode_response_a(device_mac, payload, timestamp, source)
        if sample is None:
            return None

        partial = self._partials.get(sample.device_mac)
        if not partial or timestamp - partial.first_seen > timedelta(seconds=self._merge_timeout):
            partial = PartialPacket(first_seen=timestamp)

        # If there's already a pending B, merge immediately and clear.
        if partial.packet_b:
            merged = self._merge_response_b(sample, partial.packet_b, partial.raw_b, timestamp)
            self._partials.pop(sample.device_mac, None)
            return merged

        # Store partial and emit A immediately — don't wait for B.
        # The backend's _merge_with_latest will carry forward BP and other fields.
        partial.first_seen = timestamp
        partial.packet_a = payload
        partial.raw_a = payload.hex().upper()
        partial.sample = sample
        self._partials[sample.device_mac] = partial
        return sample

    def _handle_response_b(
        self,
        device_mac: str | None,
        payload: bytes,
        timestamp: datetime,
        source: IngestionSource,
    ) -> HealthSample | None:
        if not device_mac:
            return None

        normalized_mac = self._normalize_mac(device_mac)
        partial = self._partials.get(normalized_mac)

        # If there's a pending A sample, merge B into it and return.
        if partial and partial.sample and timestamp - partial.first_seen <= timedelta(seconds=self._merge_timeout):
            merged = self._merge_response_b(partial.sample, payload, partial.raw_b or payload.hex().upper(), timestamp)
            self._partials.pop(normalized_mac, None)
            return merged

        # B arrived without a pending A (or A timed out).
        # Build a partial sample from B fields only — the backend will merge with latest.
        marker_index = self._find_response_marker(payload, self._layout.response_b_marker)
        if marker_index == -1 or len(payload) < marker_index + 5:
            return None

        systolic = payload[marker_index + 3]
        diastolic = payload[marker_index + 4]
        
        body_temperature = 0.0
        if len(payload) >= marker_index + 7:
            body_temperature = round(
                int.from_bytes(payload[marker_index + 5 : marker_index + 7], byteorder="big") / 100.0,
                2,
            )
        self._partials.pop(normalized_mac, None)
        return HealthSample(
            device_mac=normalized_mac,
            timestamp=timestamp,
            heart_rate=0,
            temperature=body_temperature if 35.0 <= body_temperature <= 45.0 else 0.0,
            blood_oxygen=0,
            blood_pressure=f"{systolic}/{diastolic}",
            battery=0,
            sos_flag=False,
            source=source,
            device_uuid=self._layout.default_uuid,
            packet_type=PacketKind.RESPONSE_B.value,
            raw_packet_b=payload.hex().upper(),
        )

    def _merge_response_b(
        self,
        sample: HealthSample,
        payload: bytes,
        raw_packet_b: str | None,
        timestamp: datetime,
    ) -> HealthSample:
        marker_index = self._find_response_marker(payload, self._layout.response_b_marker)
        if marker_index == -1 or len(payload) < marker_index + 5:
            return sample

        systolic = payload[marker_index + 3]
        diastolic = payload[marker_index + 4]
        
        update_fields: dict[str, object] = {
            "timestamp": timestamp,
            "blood_pressure": f"{systolic}/{diastolic}",
            "packet_type": "response_ab",
            "raw_packet_b": raw_packet_b,
        }

        if len(payload) >= marker_index + 7:
            body_temp = round(
                int.from_bytes(payload[marker_index + 5 : marker_index + 7], byteorder="big") / 100.0,
                2,
            )
            update_fields["temperature"] = body_temp

        return sample.model_copy(update=update_fields)

    @staticmethod
    def _decode_sos_trigger(sos_value: int) -> str | None:
        # Some firmware revisions encode SOS in a bit-field where
        # higher bits carry extra status flags (e.g. 0x81 / 0x82).
        # Keep compatibility with strict values while accepting bitwise forms.
        if sos_value & 0x02:
            return "long_press"
        if sos_value & 0x01:
            return "double_click"
        return None

    def _decode_legacy(
        self,
        device_mac: str | None,
        packet: bytes,
        kind: PacketKind,
        timestamp: datetime,
        source: IngestionSource,
    ) -> HealthSample | None:
        if not device_mac:
            return None

        normalized_mac = self._normalize_mac(device_mac)
        partial = self._partials.get(normalized_mac)
        if not partial or timestamp - partial.first_seen > timedelta(seconds=self._merge_timeout):
            partial = PartialPacket(first_seen=timestamp)

        if kind is PacketKind.LEGACY_RESPONSE_A:
            partial.packet_a = packet
            partial.raw_a = packet.hex().upper()
        else:
            partial.packet_b = packet
            partial.raw_b = packet.hex().upper()

        self._partials[normalized_mac] = partial
        if not partial.packet_a or not partial.packet_b:
            return None

        merged = (
            partial.packet_a[self._layout.legacy_header_length :]
            + partial.packet_b[self._layout.legacy_header_length :]
        )
        del self._partials[normalized_mac]
        return self._decode_legacy_payload(
            normalized_mac,
            merged,
            timestamp,
            source,
            raw_a=partial.raw_a,
            raw_b=partial.raw_b,
        )

    def _decode_legacy_payload(
        self,
        device_mac: str,
        merged: bytes,
        timestamp: datetime,
        source: IngestionSource,
        *,
        raw_a: str | None = None,
        raw_b: str | None = None,
    ) -> HealthSample | None:
        if len(merged) < 9:
            return None

        heart_rate = merged[0]
        temperature = round(((merged[1] << 8) | merged[2]) / 100.0, 1)
        blood_oxygen = merged[3]
        battery = merged[6]
        flags = merged[7]
        event_code = merged[8]
        sos_flag = bool(flags & 0x01) or event_code == 0x02 or self._register_sos(
            device_mac,
            timestamp,
            flags,
            event_code,
        )

        return HealthSample(
            device_mac=device_mac,
            timestamp=timestamp,
            heart_rate=heart_rate,
            temperature=temperature,
            blood_oxygen=blood_oxygen,
            blood_pressure=f"{merged[4]}/{merged[5]}",
            battery=battery,
            sos_flag=sos_flag,
            source=source,
            packet_type="legacy_response",
            raw_packet_a=raw_a,
            raw_packet_b=raw_b,
        )

    def _register_sos(self, device_mac: str, timestamp: datetime, flags: int, event_code: int) -> bool:
        if not (flags & 0x01 or event_code == 0x02):
            return False
        events = self._sos_events[device_mac]
        events.append(timestamp)
        while events and timestamp - events[0] > self._sos_window:
            events.popleft()
        return True

    def parse_dict(self, device_mac: str | None, payload: str | bytes, **kwargs: Any) -> dict[str, Any] | None:
        sample = self.feed(device_mac, payload, **kwargs)
        return sample.model_dump(mode="json") if sample else None

    def _find_response_marker(self, payload: bytes, marker: bytes) -> int:
        return payload.find(marker, 0, self._layout.response_scan_limit) if self._layout.response_scan_limit else payload.find(marker)

    @staticmethod
    def _format_mac(raw: bytes) -> str:
        return ":".join(f"{value:02X}" for value in raw)

    @staticmethod
    def _normalize_mac(device_mac: str) -> str:
        compact = device_mac.replace("-", "").replace(":", "").upper()
        if len(compact) != 12:
            return device_mac.upper()
        return ":".join(compact[index : index + 2] for index in range(0, 12, 2))

    @staticmethod
    def _format_uuid(raw: bytes) -> str:
        hex_value = raw.hex().upper()
        return (
            f"{hex_value[0:8]}-"
            f"{hex_value[8:12]}-"
            f"{hex_value[12:16]}-"
            f"{hex_value[16:20]}-"
            f"{hex_value[20:32]}"
        )
