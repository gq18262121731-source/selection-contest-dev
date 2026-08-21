from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agent.analysis_service import HealthDataAnalysisService
from agent.robot_companion.tool_registry import LocationProvider, RobotStateProvider, WeatherProvider
from backend.models.alarm_model import AlarmType
from backend.schemas.robot_companion_schema import (
    RobotCompanionContext,
    RobotCompanionHealthContext,
)
from backend.services.alarm_service import AlarmService
from backend.services.care_service import CareService
from backend.services.stream_service import StreamService


FALL_ALARM_TYPES = {
    AlarmType.FALL_DETECTED,
    AlarmType.FALL_INJURY_RISK,
    AlarmType.VIDEO_FALL,
}


class RobotCompanionContextError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class RobotCompanionContextManager:
    """Builds a read-only context from existing health runtime services."""

    def __init__(
        self,
        *,
        care_service: CareService,
        stream_service: StreamService,
        alarm_service: AlarmService,
        analysis_service: HealthDataAnalysisService,
        weather_provider: WeatherProvider,
        location_provider: LocationProvider,
        robot_state_provider: RobotStateProvider,
    ) -> None:
        self._care = care_service
        self._stream = stream_service
        self._alarms = alarm_service
        self._analysis = analysis_service
        self._weather = weather_provider
        self._location = location_provider
        self._robot_state = robot_state_provider

    def build(
        self,
        *,
        elder_id: str,
        device_mac: str | None,
        location_hint: str | None,
        weather_scenario: str,
    ) -> RobotCompanionContext:
        directory = self._care.get_directory()
        elder = next((item for item in directory.elders if item.id == elder_id), None)
        if elder is None:
            raise RobotCompanionContextError(
                "ELDER_NOT_FOUND",
                "未找到指定老人，无法构建康伴智能体上下文。",
                status_code=404,
            )

        bound_macs = [
            self._normalize_mac(mac)
            for mac in ([elder.device_mac] + list(elder.device_macs or []))
            if mac
        ]
        requested_mac = self._normalize_mac(device_mac) if device_mac else None
        if requested_mac and requested_mac not in set(bound_macs):
            raise RobotCompanionContextError(
                "DEVICE_NOT_BOUND_TO_ELDER",
                "指定设备未绑定给当前老人。",
                status_code=409,
            )
        selected_mac = requested_mac or (bound_macs[0] if bound_macs else None)

        health = self._build_health_context(selected_mac)
        location = self._location.get_location(
            elder_id=elder.id,
            location_hint=location_hint,
            elder_apartment=elder.apartment,
        )
        environment = self._weather.get_weather(
            location=location,
            scenario=weather_scenario,
        )
        return RobotCompanionContext(
            elder_id=elder.id,
            elder_name=elder.name,
            generated_at=datetime.now(timezone.utc),
            health=health,
            environment=environment,
            location=location,
            robot=self._robot_state.get_state(),
        )

    def _build_health_context(self, device_mac: str | None) -> RobotCompanionHealthContext:
        if not device_mac:
            return RobotCompanionHealthContext()

        latest = self._stream.latest(device_mac)
        all_recent_alarms = self._alarms.list_alarms(device_mac=device_mac, active_only=False)
        active_alarms = [alarm for alarm in all_recent_alarms if not alarm.acknowledged]
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_fall = any(
            alarm.alarm_type in FALL_ALARM_TYPES
            and alarm.created_at.astimezone(timezone.utc) >= cutoff
            for alarm in all_recent_alarms
        )
        sos = bool(
            (latest and latest.sos_flag)
            or any(alarm.alarm_type == AlarmType.SOS for alarm in active_alarms)
        )

        if latest is None:
            risk_level = "high" if recent_fall or sos else "unknown"
            freshness = "missing"
            health_score = None
            today_steps = None
        else:
            age = datetime.now(timezone.utc) - latest.timestamp.astimezone(timezone.utc)
            freshness = "fresh" if age <= timedelta(minutes=2) else "stale"
            risk_level = self._analysis.sample_risk_level(latest)
            if recent_fall or sos:
                risk_level = "high"
            health_score = latest.health_score
            today_steps = latest.steps

        return RobotCompanionHealthContext(
            risk_level=risk_level,
            health_score=health_score,
            recent_fall=recent_fall,
            sos=sos,
            today_steps=today_steps,
            data_freshness=freshness,
            device_mac=device_mac,
        )

    @staticmethod
    def _normalize_mac(value: str | None) -> str | None:
        if not value:
            return None
        compact = "".join(character for character in value if character.isalnum()).upper()
        if len(compact) == 12:
            return ":".join(compact[index : index + 2] for index in range(0, 12, 2))
        return value.strip().upper() or None
