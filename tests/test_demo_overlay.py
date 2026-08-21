from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import backend.dependencies as dependencies
from ai.data_generator import SyntheticHealthDataGenerator
from backend.models.device_model import DeviceIngestMode, DeviceRecord
from backend.models.health_model import HealthSample, IngestionSource


def test_eligible_demo_overlay_devices_include_all_known_demo_personas(monkeypatch) -> None:
    devices = [
        DeviceRecord(mac_address="53:57:08:00:00:01", ingest_mode=DeviceIngestMode.MOCK),
        DeviceRecord(mac_address="53:57:08:00:00:02", ingest_mode=DeviceIngestMode.SERIAL),
        DeviceRecord(mac_address="54:10:26:01:00:DF", ingest_mode=DeviceIngestMode.SERIAL),
    ]
    personas = [
        SimpleNamespace(mac_address="53:57:08:00:00:01"),
        SimpleNamespace(mac_address="53:57:08:00:00:02"),
    ]

    monkeypatch.setattr(dependencies, "_device_service", SimpleNamespace(list_devices=lambda: devices))
    monkeypatch.setattr(dependencies, "_data_generator", SimpleNamespace(personas=personas))

    assert dependencies._eligible_demo_overlay_device_macs() == ["53:57:08:00:00:01", "53:57:08:00:00:02"]


def test_refresh_demo_overlay_samples_updates_all_known_demo_personas(monkeypatch) -> None:
    devices = [
        DeviceRecord(mac_address="53:57:08:00:00:01", ingest_mode=DeviceIngestMode.MOCK),
        DeviceRecord(mac_address="53:57:08:00:00:02", ingest_mode=DeviceIngestMode.SERIAL),
    ]
    personas = [
        SimpleNamespace(mac_address="53:57:08:00:00:01"),
        SimpleNamespace(mac_address="53:57:08:00:00:02"),
    ]
    refreshed: list[tuple[str, str, str]] = []

    monkeypatch.setattr(dependencies, "_device_service", SimpleNamespace(list_devices=lambda: devices))
    monkeypatch.setattr(
        dependencies,
        "_data_generator",
        SimpleNamespace(
            personas=personas,
            sample_for_device=lambda device_mac: HealthSample(
                device_mac=device_mac,
                timestamp=datetime.now(timezone.utc),
                heart_rate=70,
                temperature=36.5,
                blood_oxygen=98,
                blood_pressure="120/80",
                battery=88,
                source=IngestionSource.MOCK,
            ),
        ),
    )
    monkeypatch.setattr(
        dependencies,
        "_persist_demo_overlay_sample",
        lambda sample, *, explanation, source_label: refreshed.append((sample.device_mac, explanation, source_label)),
    )

    summary = dependencies.refresh_demo_overlay_samples()

    assert refreshed == [
        ("53:57:08:00:00:01", "community sample refresh", "demo_overlay_refresh"),
        ("53:57:08:00:00:02", "community sample refresh", "demo_overlay_refresh"),
    ]
    assert summary["device_count"] == 2
    assert summary["device_macs"] == ["53:57:08:00:00:01", "53:57:08:00:00:02"]


def test_virtual_demo_devices_accept_mock_samples_even_if_legacy_mode_is_serial(monkeypatch) -> None:
    devices = [
        DeviceRecord(mac_address="53:57:08:00:00:01", ingest_mode=DeviceIngestMode.SERIAL),
    ]
    personas = [SimpleNamespace(mac_address="53:57:08:00:00:01")]

    monkeypatch.setattr(dependencies, "_device_service", SimpleNamespace(list_devices=lambda: devices))
    monkeypatch.setattr(dependencies, "_data_generator", SimpleNamespace(personas=personas))

    device = devices[0]
    sample = HealthSample(
        device_mac=device.mac_address,
        timestamp=datetime.now(timezone.utc),
        heart_rate=76,
        temperature=36.6,
        blood_oxygen=98,
        blood_pressure="118/78",
        battery=85,
        source=IngestionSource.MOCK,
    )

    assert dependencies._sample_source_allowed(device, sample) is True


def test_mock_generator_steps_are_daily_cumulative_and_non_decreasing() -> None:
    generator = SyntheticHealthDataGenerator(device_count=1, seed=7)
    mac = generator.personas[0].mac_address
    samples = [
        generator.sample_for_device(mac, now=datetime(2026, 3, 25, 8, 0, tzinfo=timezone.utc)),
        generator.sample_for_device(mac, now=datetime(2026, 3, 25, 8, 30, tzinfo=timezone.utc)),
        generator.sample_for_device(mac, now=datetime(2026, 3, 25, 9, 0, tzinfo=timezone.utc)),
    ]

    assert all(sample.steps is not None for sample in samples)
    assert samples[0].steps <= samples[1].steps <= samples[2].steps


def test_mock_generator_history_includes_steps() -> None:
    generator = SyntheticHealthDataGenerator(device_count=2, seed=11)

    history = generator.build_history(hours=3, step_minutes=30)

    assert history
    for samples in history.values():
        assert samples
        assert all(sample.steps is not None for sample in samples)


def test_mock_generator_personas_follow_setup_subject_names() -> None:
    generator = SyntheticHealthDataGenerator(device_count=3, seed=11)

    assert [persona.display_name for persona in generator.personas] == ["李建国", "张桂兰", "陈德福"]
    assert [persona.apartment for persona in generator.personas] == ["1-102", "1-103", "2-101"]


def test_mock_generator_steps_reset_on_next_day() -> None:
    generator = SyntheticHealthDataGenerator(device_count=1, seed=13)
    mac = generator.personas[0].mac_address

    late_sample = generator.sample_for_device(mac, now=datetime(2026, 3, 25, 15, 50, tzinfo=timezone.utc))
    next_day_sample = generator.sample_for_device(mac, now=datetime(2026, 3, 26, 0, 10, tzinfo=timezone.utc))

    assert late_sample.steps is not None and next_day_sample.steps is not None
    assert next_day_sample.steps < late_sample.steps


def test_mock_generator_midday_steps_track_local_time_progress() -> None:
    generator = SyntheticHealthDataGenerator(device_count=4, seed=21)
    midday_utc = datetime(2026, 3, 25, 4, 30, tzinfo=timezone.utc)  # Asia/Shanghai 12:30

    samples = [
        generator.sample_for_device(persona.mac_address, now=midday_utc)
        for persona in generator.personas[:4]
    ]

    assert all(sample.steps is not None for sample in samples)
    assert min(sample.steps or 0 for sample in samples) >= 800


def test_mock_generator_short_window_values_change_smoothly() -> None:
    generator = SyntheticHealthDataGenerator(device_count=1, seed=42)
    mac = generator.personas[0].mac_address
    start = datetime(2026, 3, 25, 4, 30, tzinfo=timezone.utc)

    samples = [
        generator.sample_for_device(mac, now=start + timedelta(seconds=12 * index))
        for index in range(12)
    ]
    heart_rates = [sample.heart_rate for sample in samples]
    blood_oxygen_values = [sample.blood_oxygen for sample in samples]

    assert len(set(heart_rates)) <= 4
    assert len(set(blood_oxygen_values)) <= 4
    assert max(abs(heart_rates[index] - heart_rates[index - 1]) for index in range(1, len(heart_rates))) <= 4
