from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from backend.models.alarm_model import AlarmQueueItem, AlarmRecord, MobilePushRecord
from backend.models.health_model import HealthSample


logger = logging.getLogger(__name__)


class AlarmService:
    """Evaluates incoming samples and stores active alarms."""

    def __init__(
        self,
        detector: object,
        queue: object,
        notification_service: object,
        *,
        sos_dedupe_window_seconds: int = 15,
        sos_release_window_seconds: int = 2,
    ) -> None:
        self._detector = detector
        self._queue = queue
        self._notification_service = notification_service
        self._alarms: list[AlarmRecord] = []
        self._sos_dedupe_window = timedelta(seconds=max(1, sos_dedupe_window_seconds))
        self._sos_release_window = timedelta(seconds=max(1, sos_release_window_seconds))
        # Post-acknowledgment cooldown: after a user dismisses an SOS popup,
        # some bracelet firmware may continue broadcasting SOS bits for a while.
        # This dict tracks {device_mac: ack_timestamp} so we can suppress
        # repeated alerts from the same physical event.
        self._sos_ack_cooldowns: dict[str, datetime] = {}
        self._last_non_sos_sample_at: dict[str, datetime] = {}
        # Keep post-ack suppression short; long cooldowns can hide true new SOS events.
        # Use a small multiple of the dedupe window to absorb lingering packets only.
        self._sos_ack_cooldown_duration = timedelta(
            seconds=max(20, int(self._sos_dedupe_window.total_seconds() * 2)),
        )

    def evaluate(self, sample: HealthSample) -> list[AlarmRecord]:
        alarms = self._detector.evaluate(sample)
        return self.evaluate_alarm_records(alarms)

    def evaluate_alarm_records(self, alarms: list[AlarmRecord]) -> list[AlarmRecord]:
        normalized: list[AlarmRecord] = []
        if alarms:
            for alarm in alarms:
                upserted = self._upsert_alarm(alarm)
                if upserted is not None:
                    normalized.append(upserted)
        self._alarms.sort(key=lambda item: (item.alarm_level.value, item.created_at), reverse=False)
        return normalized

    def list_alarms(self, device_mac: str | None = None, active_only: bool = False) -> list[AlarmRecord]:
        alarms = self._alarms
        if device_mac:
            normalized_mac = self._normalize_mac(device_mac)
            alarms = [alarm for alarm in alarms if self._normalize_mac(alarm.device_mac) == normalized_mac]
        if active_only:
            alarms = [alarm for alarm in alarms if not alarm.acknowledged]
        return alarms

    def queue_items(self, active_only: bool = True) -> list[AlarmQueueItem]:
        return self._queue.items(active_only=active_only)

    def queue_snapshot(self) -> dict[str, object]:
        return self._queue.snapshot()

    def list_mobile_pushes(self, limit: int = 50) -> list[MobilePushRecord]:
        return self._notification_service.list_mobile_pushes(limit=limit)

    @staticmethod
    def _normalize_mac(device_mac: str) -> str:
        compact = "".join(ch for ch in device_mac if ch.isalnum()).upper()
        if len(compact) == 12:
            return ":".join(compact[i : i + 2] for i in range(0, 12, 2))
        return device_mac.upper()

    def clear_device_sos_state(self, device_mac: str) -> list[str]:
        """Clear transient SOS suppression state for a specific device.

        This is used when a device is (re)bound so the next SOS from the same
        physical band is treated as a fresh event for the new owner context.
        Returns the IDs of active SOS alarms that were collapsed.
        """
        normalized_mac = self._normalize_mac(device_mac)
        self._sos_ack_cooldowns.pop(normalized_mac, None)
        self._last_non_sos_sample_at.pop(normalized_mac, None)
        cleared_alarm_ids: list[str] = []
        for index, existing in enumerate(self._alarms):
            if existing.alarm_type.value != "sos" or existing.acknowledged:
                continue
            if self._normalize_mac(existing.device_mac) != normalized_mac:
                continue
            self._alarms[index] = existing.model_copy(update={"acknowledged": True})
            self._queue.remove(existing.id)
            cleared_alarm_ids.append(existing.id)
        if cleared_alarm_ids:
            logger.info(
                "Cleared %d residual SOS alarms for %s after device binding context changed.",
                len(cleared_alarm_ids),
                normalized_mac,
            )
        return cleared_alarm_ids

    def observe_sample(self, sample: HealthSample) -> list[str]:
        normalized_mac = self._normalize_mac(sample.device_mac)
        if sample.sos_flag:
            return []

        self._last_non_sos_sample_at[normalized_mac] = sample.timestamp
        return []

    def acknowledge(self, alarm_id: str) -> tuple[AlarmRecord | None, list[str]]:
        for index, alarm in enumerate(self._alarms):
            if alarm.id == alarm_id:
                updated = alarm.model_copy(update={"acknowledged": True})
                self._alarms[index] = updated
                self._queue.remove(alarm_id)
                collapsed_sibling_ids: list[str] = []
                # Record SOS acknowledgment so subsequent broadcasts from
                # the same physical button press are silently suppressed.
                if alarm.alarm_type.value == "sos":
                    mac = self._normalize_mac(alarm.device_mac)
                    self._sos_ack_cooldowns[mac] = datetime.now(timezone.utc)
                    collapsed_sibling_ids = self._acknowledge_active_sos_siblings(
                        device_mac=mac,
                        exclude_alarm_id=alarm_id,
                    )
                    logger.info(
                        "SOS acknowledged for %s (collapsed %d sibling alarms) - cooldown active for %ds.",
                        mac,
                        len(collapsed_sibling_ids),
                        self._sos_ack_cooldown_duration.total_seconds(),
                    )
                return updated, collapsed_sibling_ids
        return None, []

    def _acknowledge_active_sos_siblings(self, *, device_mac: str, exclude_alarm_id: str) -> list[str]:
        acknowledged_ids: list[str] = []
        normalized_mac = self._normalize_mac(device_mac)
        for index, existing in enumerate(self._alarms):
            if existing.id == exclude_alarm_id:
                continue
            if existing.alarm_type.value != "sos":
                continue
            if existing.acknowledged:
                continue
            if self._normalize_mac(existing.device_mac) != normalized_mac:
                continue
            self._alarms[index] = existing.model_copy(update={"acknowledged": True})
            self._queue.remove(existing.id)
            acknowledged_ids.append(existing.id)
        return acknowledged_ids

    def _upsert_alarm(self, alarm: AlarmRecord) -> AlarmRecord | None:
        # Check post-acknowledgment cooldown first: if the user just dismissed
        # an SOS for this device, suppress subsequent SOS packets silently.
        if alarm.alarm_type.value == "sos" and self._is_in_sos_ack_cooldown(alarm.device_mac):
            return None

        existing_index = self._find_active_sos_index(alarm)
        if existing_index is not None:
            self._collapse_active_sos_duplicates(
                device_mac=alarm.device_mac,
                keep_alarm_id=self._alarms[existing_index].id,
            )
            # Repeated SOS packets from the same active event should not emit
            # another queue item or trigger another popup on clients.
            return None

        self._alarms.append(alarm)
        self._queue.enqueue(alarm)
        self._notification_service.dispatch_mobile_push(alarm)
        return alarm

    def _is_in_sos_ack_cooldown(self, device_mac: str) -> bool:
        """Return True if the device is within the post-acknowledgment cooldown."""
        mac = self._normalize_mac(device_mac)
        ack_at = self._sos_ack_cooldowns.get(mac)
        if ack_at is None:
            return False
        elapsed = datetime.now(timezone.utc) - ack_at
        if elapsed > self._sos_ack_cooldown_duration:
            # Cooldown expired - clear it so future SOS events are not affected.
            del self._sos_ack_cooldowns[mac]
            return False
        logger.debug(
            "SOS suppressed for %s - within post-ack cooldown (%ds/%ds elapsed).",
            mac,
            elapsed.total_seconds(),
            self._sos_ack_cooldown_duration.total_seconds(),
        )
        return True

    def _find_active_sos_index(self, alarm: AlarmRecord) -> int | None:
        if alarm.alarm_type.value != "sos":
            return None
        now = datetime.now(timezone.utc)
        incoming_mac = self._normalize_mac(alarm.device_mac)
        last_non_sos_at = self._last_non_sos_sample_at.get(incoming_mac)
        for index in range(len(self._alarms) - 1, -1, -1):
            existing = self._alarms[index]
            if existing.alarm_type.value != "sos":
                continue
            if self._normalize_mac(existing.device_mac) != incoming_mac or existing.acknowledged:
                continue
            if (
                last_non_sos_at is not None
                and last_non_sos_at >= existing.created_at + self._sos_release_window
            ):
                # A new non-SOS sample means the previous SOS packet burst has
                # ended. Treat subsequent SOS as a new event, but do not
                # auto-acknowledge existing alarms; only users should clear them.
                continue
            # A single SOS button press causes multiple broadcast packets.
            # Group unacknowledged packets within the configured dedupe window.
            # If an unacknowledged alarm is older than that window, treat it as
            # stale and clear it so a fresh SOS can trigger a new popup.
            age = now - existing.created_at
            if age > self._sos_dedupe_window:
                self._alarms[index] = existing.model_copy(update={"acknowledged": True})
                self._queue.remove(existing.id)
                continue
            return index
        return None

    def _collapse_active_sos_duplicates(self, *, device_mac: str, keep_alarm_id: str) -> None:
        normalized_mac = self._normalize_mac(device_mac)
        for index, existing in enumerate(self._alarms):
            if existing.id == keep_alarm_id:
                continue
            if existing.alarm_type.value != "sos":
                continue
            if self._normalize_mac(existing.device_mac) != normalized_mac or existing.acknowledged:
                continue
            self._alarms[index] = existing.model_copy(update={"acknowledged": True})
            self._queue.remove(existing.id)
