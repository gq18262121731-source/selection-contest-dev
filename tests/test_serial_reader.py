from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import iot.serial_reader as serial_reader_module
from backend.models.health_model import HealthSample, IngestionSource
from iot.serial_reader import SerialGatewayReader


class _ParserStub:
    def __init__(self, sample: HealthSample | None = None) -> None:
        self.calls: list[tuple[str, str, IngestionSource]] = []
        self._sample = sample

    def feed(self, device_mac: str, payload: str, *, source: IngestionSource) -> HealthSample | None:
        self.calls.append((device_mac, payload, source))
        return self._sample


class _FakeConnection:
    def __init__(self, scripted_lines: list[bytes | BaseException]) -> None:
        self._scripted_lines = iter(scripted_lines)
        self.in_waiting = 0
        self.writes: list[str] = []

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def write(self, data: bytes) -> None:
        self.writes.append(data.decode("utf-8").strip())
        return None

    def flush(self) -> None:
        return None

    def readline(self) -> bytes:
        item = next(self._scripted_lines)
        if isinstance(item, BaseException):
            raise item
        return item


def test_single_target_reader_drops_off_target_mac_before_parser(monkeypatch) -> None:
    parser = _ParserStub()
    reader = SerialGatewayReader(parser)

    monkeypatch.setattr(reader, "detect_port", lambda port, keywords: "COM3")
    monkeypatch.setattr(reader, "_extract_payload_and_mac", lambda line: ("161803AABBCC", "54:10:26:01:00:DC"))
    monkeypatch.setattr(serial_reader_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        serial_reader_module,
        "serial",
        SimpleNamespace(Serial=lambda **kwargs: _FakeConnection([b"payload\r\n", KeyboardInterrupt()])),
    )

    with pytest.raises(KeyboardInterrupt):
        reader.run(
            collection_strategy="single_target",
            mac_filter="54:10:26:01:00:DF",
            target_mac_provider=lambda: "54:10:26:01:00:DF",
        )

    assert parser.calls == []


def test_single_target_reader_keeps_target_mac_packets(monkeypatch) -> None:
    sample = HealthSample(
        device_mac="54:10:26:01:00:DF",
        timestamp=datetime.now(timezone.utc),
        heart_rate=72,
        temperature=36.5,
        blood_oxygen=98,
        blood_pressure="120/80",
        battery=90,
        source=IngestionSource.SERIAL,
    )
    parser = _ParserStub(sample=sample)
    reader = SerialGatewayReader(parser)
    published: list[HealthSample] = []

    monkeypatch.setattr(reader, "detect_port", lambda port, keywords: "COM3")
    monkeypatch.setattr(reader, "_extract_payload_and_mac", lambda line: ("161803AABBCC", "54:10:26:01:00:DF"))
    monkeypatch.setattr(serial_reader_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        serial_reader_module,
        "serial",
        SimpleNamespace(Serial=lambda **kwargs: _FakeConnection([b"payload\r\n", KeyboardInterrupt()])),
    )

    with pytest.raises(KeyboardInterrupt):
        reader.run(
            collection_strategy="single_target",
            mac_filter="54:10:26:01:00:DF",
            target_mac_provider=lambda: "54:10:26:01:00:DF",
            on_sample=published.append,
        )

    assert parser.calls == [("54:10:26:01:00:DF", "161803AABBCC", IngestionSource.SERIAL)]
    assert published == [sample]


def test_single_target_reader_rotates_response_and_broadcast_types(monkeypatch) -> None:
    parser = _ParserStub()
    reader = SerialGatewayReader(parser)
    connection = _FakeConnection([b"payload\r\n", b"payload\r\n", KeyboardInterrupt()])

    monotonic_values = iter([0.0, 2.5, 2.5, 3.2, 3.2, 3.2, 3.2, 3.2])

    monkeypatch.setattr(reader, "detect_port", lambda port, keywords: "COM3")
    monkeypatch.setattr(reader, "_extract_payload_and_mac", lambda line: ("0201061AFF4C000215AA", "54:10:26:01:00:DF"))
    monkeypatch.setattr(serial_reader_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(serial_reader_module.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(
        serial_reader_module,
        "serial",
        SimpleNamespace(Serial=lambda **kwargs: connection),
    )

    with pytest.raises(KeyboardInterrupt):
        reader.run(
            collection_strategy="single_target",
            mac_filter="54:10:26:01:00:DF",
            target_mac_provider=lambda: "54:10:26:01:00:DF",
            enable_broadcast_sos_overlay=True,
            response_cycle_seconds=2.0,
            broadcast_cycle_seconds=0.5,
        )

    assert "AT+TYPE=5" in connection.writes
    assert "AT+TYPE=4" in connection.writes


def test_detect_port_falls_back_from_stale_preferred_port(monkeypatch) -> None:
    reader = SerialGatewayReader(_ParserStub())

    monkeypatch.setattr(
        serial_reader_module.list_ports,
        "comports",
        lambda: [
            SimpleNamespace(
                device="COM9",
                description="CP210x USB to UART Bridge",
                manufacturer="Silicon Labs",
                hwid="USB VID:PID=10C4:EA60",
            )
        ],
    )

    detected_port = reader.detect_port("COM7", ["cp210"])

    assert detected_port == "COM9"


def test_reader_reconnects_and_redetects_new_com_port(monkeypatch) -> None:
    sample = HealthSample(
        device_mac="54:10:26:01:00:DF",
        timestamp=datetime.now(timezone.utc),
        heart_rate=72,
        temperature=36.5,
        blood_oxygen=98,
        blood_pressure="120/80",
        battery=90,
        source=IngestionSource.SERIAL,
    )
    parser = _ParserStub(sample=sample)
    reader = SerialGatewayReader(parser)
    published: list[HealthSample] = []
    detected_ports = iter(["COM3", "COM4"])
    opened_ports: list[str] = []

    def fake_serial(**kwargs):
        port = kwargs["port"]
        opened_ports.append(port)
        if port == "COM3":
            return _FakeConnection([OSError("port disconnected")])
        return _FakeConnection([b"payload\r\n", KeyboardInterrupt()])

    monkeypatch.setattr(reader, "detect_port", lambda port, keywords: next(detected_ports))
    monkeypatch.setattr(reader, "_extract_payload_and_mac", lambda line: ("161803AABBCC", "54:10:26:01:00:DF"))
    monkeypatch.setattr(serial_reader_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        serial_reader_module,
        "serial",
        SimpleNamespace(Serial=fake_serial),
    )

    with pytest.raises(KeyboardInterrupt):
        reader.run(
            collection_strategy="single_target",
            mac_filter="54:10:26:01:00:DF",
            target_mac_provider=lambda: "54:10:26:01:00:DF",
            on_sample=published.append,
        )

    assert opened_ports == ["COM3", "COM4"]
    assert parser.calls == [("54:10:26:01:00:DF", "161803AABBCC", IngestionSource.SERIAL)]
    assert published == [sample]


def test_extract_payload_does_not_guess_mac_from_noise_before_marker() -> None:
    line = "RAW,ID=0001,DATA=AA11BB22CC33161803AABBCC"
    payload, mac = SerialGatewayReader._extract_payload_and_mac(line)

    assert payload == "161803AABBCC"
    assert mac is None


def test_extract_payload_with_compact_mac_prefix_keeps_mac() -> None:
    line = "5410260100DF161803AABBCC"
    payload, mac = SerialGatewayReader._extract_payload_and_mac(line)

    assert payload == "161803AABBCC"
    assert mac == "54:10:26:01:00:DF"
