from __future__ import annotations

from dataclasses import dataclass, field

from backend.models.alarm_model import AlarmRecord
from backend.models.health_model import HealthSample
from backend.services.alarm_service import AlarmService
from backend.services.care_service import CareService
from backend.services.device_service import DeviceService
from backend.services.stream_service import StreamService


@dataclass(slots=True)
class AgentContextBundle:
    scope: str
    summary: dict[str, object] = field(default_factory=dict)
    tool_hints: list[str] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)


class AgentContextAssembler:
    """Builds health-monitoring business context from existing project services."""

    def __init__(
        self,
        stream_service: StreamService,
        alarm_service: AlarmService,
        device_service: DeviceService,
        care_service: CareService,
    ) -> None:
        self._stream = stream_service
        self._alarm = alarm_service
        self._device = device_service
        self._care = care_service

    def build_device_context(
        self,
        *,
        device_mac: str,
        samples: list[HealthSample] | None = None,
    ) -> AgentContextBundle:
        normalized_mac = device_mac.upper()
        directory = self._care.get_directory()
        elder = next((item for item in directory.elders if item.device_mac == normalized_mac), None)
        related_families = []
        if elder:
            related_families = [family for family in directory.families if family.id in elder.family_ids]
        realtime = self._stream.latest(normalized_mac)
        alarms = self._alarm.list_alarms(device_mac=normalized_mac, active_only=True)
        device = self._device.get_device(normalized_mac)
        trend = self._stream.trend(normalized_mac, minutes=180, limit=24)

        degraded: list[str] = []
        if realtime is None:
            degraded.append("no_realtime_sample")
        if device is None:
            degraded.append("device_ledger_missing")

        return AgentContextBundle(
            scope="device",
            summary={
                "device_mac": normalized_mac,
                "device": device.model_dump(mode="json") if device else None,
                "realtime_sample": realtime.model_dump(mode="json") if realtime else None,
                "trend_points": [point.model_dump(mode="json") for point in trend],
                "active_alarms": [alarm.model_dump(mode="json") for alarm in alarms],
                "elder_profile": elder.model_dump(mode="json") if elder else None,
                "family_profiles": [family.model_dump(mode="json") for family in related_families],
                "sample_count": len(samples or []),
            },
            tool_hints=[
                "query_realtime_health",
                "query_health_trend",
                "query_device_status",
                "query_active_alarms",
                "query_elder_profile",
                "query_family_relations",
            ],
            degraded=degraded,
        )

    def build_community_context(
        self,
        *,
        device_macs: list[str] | None = None,
        device_samples: dict[str, list[HealthSample]] | None = None,
    ) -> AgentContextBundle:
        directory = self._care.get_directory()
        latest_samples = self._stream.latest_samples()
        selected = [mac.upper() for mac in device_macs] if device_macs else []
        alarms = self._alarm.list_alarms(active_only=True)
        filtered_alarms = [alarm for alarm in alarms if not selected or alarm.device_mac in selected]
        summary_samples = device_samples or self._stream.recent_by_devices(selected or None, minutes=180, per_device_limit=120)

        return AgentContextBundle(
            scope="community",
            summary={
                "community": directory.community.model_dump(mode="json"),
                "elder_count": len(directory.elders),
                "family_count": len(directory.families),
                "latest_device_count": len(latest_samples),
                "selected_devices": selected,
                "active_alarms": [alarm.model_dump(mode="json") for alarm in filtered_alarms[:20]],
                "device_history_counts": {mac: len(samples) for mac, samples in summary_samples.items()},
            },
            tool_hints=[
                "query_community_summary",
                "query_active_alarms",
                "query_device_status",
                "query_care_directory",
            ],
            degraded=[],
        )

