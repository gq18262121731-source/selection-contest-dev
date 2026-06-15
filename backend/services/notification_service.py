from __future__ import annotations

from backend.models.alarm_model import AlarmPriority, AlarmRecord, MobilePushRecord
from backend.repositories.mobile_push_device_repo import MobilePushDeviceRepository


class NotificationService:
    """Simulates mobile push delivery for high-priority alarms."""

    def __init__(self, repository: MobilePushDeviceRepository | None = None) -> None:
        self._repository = repository
        self._push_records: list[MobilePushRecord] = []

    def dispatch_mobile_push(self, alarm: AlarmRecord) -> MobilePushRecord:
        title = self._title_for(alarm.alarm_level)
        record = MobilePushRecord(
            alarm_id=alarm.id,
            device_mac=alarm.device_mac,
            title=title,
            body=alarm.message,
            priority=alarm.alarm_level,
        )
        self._push_records.append(record)
        return record

    def list_mobile_pushes(self, limit: int = 50) -> list[MobilePushRecord]:
        return list(reversed(self._push_records[-limit:]))

    @staticmethod
    def _title_for(priority: AlarmPriority) -> str:
        if priority == AlarmPriority.SOS:
            return "SOS 紧急告警"
        if priority == AlarmPriority.CRITICAL:
            return "生命体征危急"
        if priority == AlarmPriority.WARNING:
            return "健康预警通知"
        return "健康通知"
