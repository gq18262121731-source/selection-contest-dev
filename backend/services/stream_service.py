from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from backend.models.health_model import HealthSample, HealthTrendPoint


class StreamService:
    """Stores recent realtime samples and trend-ready history in memory."""

    @staticmethod
    def _normalize_mac(device_mac: str) -> str:
        compact = "".join(ch for ch in device_mac if ch.isalnum()).upper()
        if len(compact) == 12:
            return ":".join(compact[i : i + 2] for i in range(0, 12, 2))
        return device_mac.upper()

    def __init__(self, retention_points: int = 600) -> None:
        self._retention_points = retention_points
        self._streams: dict[str, deque[HealthSample]] = defaultdict(
            lambda: deque(maxlen=self._retention_points)
        )

    def publish(self, sample: HealthSample) -> None:
        normalized = self._normalize_mac(sample.device_mac)
        self._streams[normalized].append(sample)

    def latest(self, device_mac: str) -> HealthSample | None:
        normalized = self._normalize_mac(device_mac)
        stream = self._streams.get(normalized)
        if not stream:
            return None
        return stream[-1]

    def recent(self, device_mac: str, limit: int = 60) -> list[HealthSample]:
        return self.recent_in_window(device_mac, minutes=None, limit=limit)

    def recent_in_window(
        self,
        device_mac: str,
        *,
        minutes: int | None = None,
        limit: int = 60,
    ) -> list[HealthSample]:
        normalized = self._normalize_mac(device_mac)
        values = list(self._streams.get(normalized, deque()))
        if minutes is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
            values = [sample for sample in values if sample.timestamp >= cutoff]
        return values[-limit:]

    def recent_by_devices(
        self,
        device_macs: list[str] | None = None,
        *,
        minutes: int = 1440,
        per_device_limit: int = 288,
    ) -> dict[str, list[HealthSample]]:
        selected_macs = [self._normalize_mac(mac) for mac in device_macs] if device_macs else sorted(self._streams.keys())
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        snapshots: dict[str, list[HealthSample]] = {}
        for mac in selected_macs:
            values = [
                sample
                for sample in self._streams.get(mac, deque())
                if sample.timestamp >= cutoff
            ]
            if values:
                snapshots[mac] = values[-per_device_limit:]
        return snapshots

    def trend(
        self,
        device_mac: str,
        *,
        minutes: int = 60,
        limit: int = 120,
    ) -> list[HealthTrendPoint]:
        values = self.recent_in_window(device_mac, minutes=minutes, limit=limit)
        return [
            HealthTrendPoint(
                timestamp=sample.timestamp,
                heart_rate=sample.heart_rate,
                temperature=sample.temperature,
                blood_oxygen=sample.blood_oxygen,
                blood_pressure=sample.blood_pressure,
                health_score=sample.health_score,
            )
            for sample in values
        ]

    def latest_samples(self, filter_macs: list[str] | set[str] | None = None) -> list[HealthSample]:
        snapshots: list[HealthSample] = []
        if filter_macs is not None:
            valid_set = {self._normalize_mac(mac) for mac in filter_macs}
            for mac, stream in self._streams.items():
                if stream and mac in valid_set:
                    snapshots.append(stream[-1])
        else:
            for stream in self._streams.values():
                if stream:
                    snapshots.append(stream[-1])
        return snapshots
