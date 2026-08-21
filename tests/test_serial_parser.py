from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.models.health_model import IngestionSource
from iot.parser import T10PacketParser


def _response_a_payload() -> bytes:
    return bytes.fromhex(
        "161803"
        "09E6"
        "5A"
        "0E4A"
        "0048"
        "0062"
        "535708020001"
        "04D2"
    )


def _response_b_payload() -> bytes:
    return bytes.fromhex(
        "160318"
        "78"
        "4E"
        "0E4F"
    )


def _broadcast_payload(sos_value: int = 0x01) -> bytes:
    return bytes.fromhex(
        "0201061AFF4C000215"
        "526164696F6C616E642D541000000000"
        "54"
        "63"
        "0E42"
        f"{sos_value:02X}"
    )


def _broadcast_payload_with_temp(temp_raw: int, sos_value: int = 0x00) -> bytes:
    return bytes.fromhex(
        "0201061AFF4C000215"
        "526164696F6C616E642D541000000000"
        "54"
        "63"
        f"{temp_raw:04X}"
        f"{sos_value:02X}"
    )


def test_response_a_emits_immediately_and_b_merges() -> None:
    """Response A is emitted immediately; when B follows within the merge window,
    a merged AB sample is also emitted."""
    parser = T10PacketParser()

    first = parser.feed("53:57:08:02:00:01", _response_a_payload(), source=IngestionSource.SERIAL)
    second = parser.feed("53:57:08:02:00:01", _response_b_payload(), source=IngestionSource.SERIAL)

    # A is emitted immediately (not None)
    assert first is not None
    assert first.device_mac == "53:57:08:02:00:01"
    assert first.heart_rate == 72
    assert first.blood_oxygen == 98
    assert first.battery == 90
    assert first.steps == 1234
    assert first.packet_type == "response_a"
    assert first.blood_pressure is None  # A doesn't carry BP

    # B merges with the pending A partial
    assert second is not None
    assert second.heart_rate == 72
    assert second.blood_oxygen == 98
    assert second.temperature == 36.63
    assert second.blood_pressure == "120/78"
    assert second.battery == 90
    assert second.steps == 1234
    assert second.packet_type == "response_ab"
    assert second.raw_packet_a == _response_a_payload().hex().upper()
    assert second.raw_packet_b == _response_b_payload().hex().upper()


def test_response_b_arriving_first_emits_partial_then_a_merges() -> None:
    """When B arrives before A, B is emitted as a partial sample with BP data.
    When A arrives next, it merges with the pending B."""
    parser = T10PacketParser()

    first = parser.feed("53:57:08:02:00:01", _response_b_payload(), source=IngestionSource.SERIAL)
    second = parser.feed("53:57:08:02:00:01", _response_a_payload(), source=IngestionSource.SERIAL)

    # B arrives without pending A → emitted as standalone partial
    assert first is not None
    assert first.packet_type == "response_b"
    assert first.blood_pressure == "120/78"
    assert first.heart_rate == 0  # B doesn't carry HR

    # A arrives and finds no pending B → emitted as response_a
    assert second is not None
    assert second.heart_rate == 72
    assert second.blood_oxygen == 98


def test_stale_partial_is_cleaned_and_b_emits_standalone() -> None:
    """After timeout, stale partials are cleaned. Late B is emitted as standalone."""
    parser = T10PacketParser(merge_timeout_seconds=0.1)
    base_time = datetime.now(timezone.utc)

    first = parser.feed(
        "53:57:08:02:00:01",
        _response_a_payload(),
        source=IngestionSource.SERIAL,
        timestamp=base_time,
    )
    second = parser.feed(
        "53:57:08:02:00:01",
        _response_b_payload(),
        source=IngestionSource.SERIAL,
        timestamp=base_time + timedelta(seconds=1),
    )

    # A emitted immediately
    assert first is not None
    assert first.packet_type == "response_a"
    assert first.heart_rate == 72
    assert first.blood_oxygen == 98
    assert first.steps == 1234

    # B arrives after timeout → stale A is cleaned, B emits standalone
    assert second is not None
    assert second.packet_type == "response_b"
    assert second.blood_pressure == "120/78"
    assert second.heart_rate == 0  # B doesn't carry HR


def test_broadcast_packet_extracts_sos_fields() -> None:
    parser = T10PacketParser()

    sample = parser.feed("54:10:26:01:00:DF", _broadcast_payload(0x01), source=IngestionSource.SERIAL)

    assert sample is not None
    assert sample.packet_type == "broadcast"
    assert sample.heart_rate == 84
    assert sample.blood_oxygen == 99
    assert sample.temperature == 36.5
    assert sample.sos_flag is True
    assert sample.sos_value == 1
    assert sample.sos_trigger == "double_click"


def test_broadcast_packet_maps_long_press_sos() -> None:
    parser = T10PacketParser()

    sample = parser.feed("54:10:26:01:00:DF", _broadcast_payload(0x02), source=IngestionSource.SERIAL)

    assert sample is not None
    assert sample.sos_flag is True
    assert sample.sos_value == 2
    assert sample.sos_trigger == "long_press"


def test_broadcast_packet_maps_bitmask_sos_values() -> None:
    parser = T10PacketParser()

    sample_double = parser.feed("54:10:26:01:00:DF", _broadcast_payload(0x81), source=IngestionSource.SERIAL)
    sample_long = parser.feed("54:10:26:01:00:DF", _broadcast_payload(0x82), source=IngestionSource.SERIAL)

    assert sample_double is not None
    assert sample_double.sos_flag is True
    assert sample_double.sos_trigger == "double_click"
    assert sample_double.sos_value == 0x81

    assert sample_long is not None
    assert sample_long.sos_flag is True
    assert sample_long.sos_trigger == "long_press"
    assert sample_long.sos_value == 0x82


def test_broadcast_low_temperature_is_treated_as_surface_temperature() -> None:
    parser = T10PacketParser()
    sample = parser.feed(
        "54:10:26:01:00:DF",
        _broadcast_payload_with_temp(0x0999, 0x00),  # 24.57
        source=IngestionSource.SERIAL,
    )

    assert sample is not None
    assert sample.packet_type == "broadcast"
    assert sample.surface_temperature == 24.57
    assert sample.temperature == 0.0


def test_broadcast_unknown_nonzero_sos_value_still_flags_sos() -> None:
    parser = T10PacketParser()
    sample = parser.feed(
        "54:10:26:01:00:DF",
        _broadcast_payload_with_temp(0x0E3F, 0x80),
        source=IngestionSource.SERIAL,
    )

    assert sample is not None
    assert sample.sos_flag is True
    assert sample.sos_value == 0x80
    assert sample.sos_trigger is None
