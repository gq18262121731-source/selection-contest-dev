from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.models.alarm_model import AlarmLayer, AlarmPriority, AlarmRecord, AlarmType
from backend.models.health_model import HealthSample, IngestionSource
from backend.services.alarm_priority_queue import AlarmPriorityQueue
from backend.services.alarm_service import AlarmService


class _NotificationStub:
    def __init__(self) -> None:
        self.records: list[AlarmRecord] = []

    def dispatch_mobile_push(self, alarm: AlarmRecord) -> None:
        self.records.append(alarm)


class _DetectorStub:
    def evaluate(self, sample) -> list[AlarmRecord]:
        return []


def _build_sos_alarm(*, created_at: datetime, acknowledged: bool = False) -> AlarmRecord:
    return AlarmRecord(
        device_mac="54:10:26:01:00:DF",
        alarm_type=AlarmType.SOS,
        alarm_level=AlarmPriority.SOS,
        alarm_layer=AlarmLayer.REALTIME,
        message="SOS",
        created_at=created_at,
        acknowledged=acknowledged,
        metadata={"event": "sos_broadcast", "is_real_device": True},
    )


def test_alarm_service_dedupes_active_sos_alarm() -> None:
    notification = _NotificationStub()
    service = AlarmService(
        detector=_DetectorStub(),
        queue=AlarmPriorityQueue(redis_url="redis://localhost:6379/0"),
        notification_service=notification,
        sos_dedupe_window_seconds=15,
    )
    first = _build_sos_alarm(created_at=datetime(2026, 3, 25, 1, 0, tzinfo=timezone.utc))
    second = _build_sos_alarm(created_at=first.created_at + timedelta(seconds=8))

    emitted_first = service.evaluate_alarm_records([first])
    emitted_second = service.evaluate_alarm_records([second])

    assert len(service.list_alarms(active_only=True)) == 1
    assert len(emitted_first) == 1
    assert emitted_second == []
    assert len(notification.records) == 1


def test_alarm_service_respects_configured_sos_dedupe_window() -> None:
    notification = _NotificationStub()
    service = AlarmService(
        detector=_DetectorStub(),
        queue=AlarmPriorityQueue(redis_url="redis://localhost:6379/0"),
        notification_service=notification,
        sos_dedupe_window_seconds=15,
    )
    old_alarm = _build_sos_alarm(created_at=datetime.now(timezone.utc) - timedelta(seconds=40))
    new_alarm = _build_sos_alarm(created_at=datetime.now(timezone.utc))

    emitted_old = service.evaluate_alarm_records([old_alarm])
    emitted_new = service.evaluate_alarm_records([new_alarm])

    assert len(emitted_old) == 1
    assert len(emitted_new) == 1
    assert emitted_new[0].id != emitted_old[0].id
    assert len(service.list_alarms(active_only=True)) == 1


def test_alarm_service_creates_new_sos_after_acknowledge() -> None:
    notification = _NotificationStub()
    service = AlarmService(
        detector=_DetectorStub(),
        queue=AlarmPriorityQueue(redis_url="redis://localhost:6379/0"),
        notification_service=notification,
        sos_dedupe_window_seconds=15,
    )
    first = _build_sos_alarm(created_at=datetime(2026, 3, 25, 1, 0, tzinfo=timezone.utc))
    created = service.evaluate_alarm_records([first])[0]
    service.acknowledge(created.id)
    # Simulate cooldown expiration so the next SOS can be treated as a fresh event.
    service._sos_ack_cooldowns.clear()

    second = _build_sos_alarm(created_at=first.created_at + timedelta(seconds=20))
    emitted = service.evaluate_alarm_records([second])[0]

    assert emitted.id != created.id
    assert len(service.list_alarms(active_only=True)) == 1


def test_alarm_service_suppresses_immediate_post_ack_sos() -> None:
    notification = _NotificationStub()
    service = AlarmService(
        detector=_DetectorStub(),
        queue=AlarmPriorityQueue(redis_url="redis://localhost:6379/0"),
        notification_service=notification,
        sos_dedupe_window_seconds=15,
    )
    first = _build_sos_alarm(created_at=datetime(2026, 3, 25, 1, 0, tzinfo=timezone.utc))
    created = service.evaluate_alarm_records([first])[0]
    service.acknowledge(created.id)

    immediate = _build_sos_alarm(created_at=first.created_at + timedelta(seconds=5))
    emitted = service.evaluate_alarm_records([immediate])

    assert emitted == []


def test_alarm_service_allows_new_sos_after_short_ack_cooldown_expires() -> None:
    notification = _NotificationStub()
    service = AlarmService(
        detector=_DetectorStub(),
        queue=AlarmPriorityQueue(redis_url="redis://localhost:6379/0"),
        notification_service=notification,
        sos_dedupe_window_seconds=15,
    )
    first = _build_sos_alarm(created_at=datetime(2026, 3, 25, 1, 0, tzinfo=timezone.utc))
    created = service.evaluate_alarm_records([first])[0]
    service.acknowledge(created.id)
    service._sos_ack_cooldowns["54:10:26:01:00:DF"] = datetime.now(timezone.utc) - timedelta(seconds=31)

    later = _build_sos_alarm(created_at=first.created_at + timedelta(seconds=40))
    emitted = service.evaluate_alarm_records([later])

    assert len(emitted) == 1
    assert emitted[0].id != created.id


def test_acknowledging_one_sos_clears_active_sos_siblings() -> None:
    notification = _NotificationStub()
    service = AlarmService(
        detector=_DetectorStub(),
        queue=AlarmPriorityQueue(redis_url="redis://localhost:6379/0"),
        notification_service=notification,
        sos_dedupe_window_seconds=15,
    )
    first = _build_sos_alarm(created_at=datetime(2026, 3, 25, 1, 0, tzinfo=timezone.utc))
    second = _build_sos_alarm(created_at=datetime(2026, 3, 25, 1, 0, 5, tzinfo=timezone.utc))
    service._alarms = [first, second]  # simulate residual duplicate active alarms in memory

    acknowledged, collapsed_ids = service.acknowledge(first.id)

    assert acknowledged is not None
    assert second.id in collapsed_ids
    active = service.list_alarms(active_only=True)
    assert active == []


def test_clear_device_sos_state_resets_cooldown_and_active_sos() -> None:
    notification = _NotificationStub()
    service = AlarmService(
        detector=_DetectorStub(),
        queue=AlarmPriorityQueue(redis_url="redis://localhost:6379/0"),
        notification_service=notification,
        sos_dedupe_window_seconds=15,
    )

    created = service.evaluate_alarm_records(
        [_build_sos_alarm(created_at=datetime(2026, 3, 25, 1, 0, tzinfo=timezone.utc))]
    )[0]
    service.acknowledge(created.id)
    assert service._sos_ack_cooldowns

    # Re-open one active SOS to simulate residual in-memory state during rebind.
    service._alarms[0] = service._alarms[0].model_copy(update={"acknowledged": False})
    service._queue.enqueue(service._alarms[0])

    cleared_alarm_ids = service.clear_device_sos_state("54:10:26:01:00:DF")

    assert len(cleared_alarm_ids) == 1
    assert service._sos_ack_cooldowns == {}
    assert service.list_alarms(active_only=True) == []


def test_non_sos_sample_marks_sos_cycle_end_without_auto_ack_and_allows_second_alarm() -> None:
    notification = _NotificationStub()
    service = AlarmService(
        detector=_DetectorStub(),
        queue=AlarmPriorityQueue(redis_url="redis://localhost:6379/0"),
        notification_service=notification,
        sos_dedupe_window_seconds=15,
    )
    first_created_at = datetime(2026, 3, 25, 1, 0, tzinfo=timezone.utc)
    first = _build_sos_alarm(created_at=first_created_at)
    emitted_first = service.evaluate_alarm_records([first])

    service.observe_sample(
        HealthSample(
            device_mac="54:10:26:01:00:DF",
            timestamp=first_created_at + timedelta(seconds=3),
            heart_rate=82,
            temperature=36.5,
            blood_oxygen=97,
            sos_flag=False,
            source=IngestionSource.SERIAL,
            packet_type="response_a",
        )
    )

    second = _build_sos_alarm(created_at=first_created_at + timedelta(seconds=5))
    emitted_second = service.evaluate_alarm_records([second])

    assert len(emitted_first) == 1
    active_before_second = service.list_alarms(active_only=True)
    assert any(item.id == emitted_first[0].id for item in active_before_second)
    assert len(emitted_second) == 1
    assert emitted_second[0].id != emitted_first[0].id
