from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from agent.analysis_service import HealthDataAnalysisService
from agent.robot_companion.action_planner import RobotCompanionActionPlanner
from agent.robot_companion.context_manager import (
    RobotCompanionContextError,
    RobotCompanionContextManager,
)
from agent.robot_companion.robot_agent import (
    RobotCompanionAgentService,
    RobotCompanionIntentClassifier,
)
from agent.robot_companion.safety_guard import RobotCompanionSafetyGuard
from agent.robot_companion.tool_registry import (
    MockLocationProvider,
    MockRobotStateProvider,
    MockWeatherProvider,
)
from backend.api.robot_companion_api import robot_companion_dialogue
from backend.models.alarm_model import AlarmLayer, AlarmPriority, AlarmRecord, AlarmType
from backend.models.care_model import CareDirectory, CommunityProfile, ElderProfile
from backend.models.health_model import HealthSample
from backend.schemas.robot_companion_schema import (
    RobotCompanionActionType,
    RobotCompanionDialogueRequest,
    RobotCompanionIntent,
)


DEVICE_MAC = "53:57:08:00:00:01"


class _RuleOnlySettings:
    qwen_llm_configured = False


class _CareService:
    def get_directory(self) -> CareDirectory:
        return CareDirectory(
            community=CommunityProfile(
                id="community-001",
                name="测试社区",
                address="南京",
                manager="值守员",
                hotline="000",
            ),
            elders=[
                ElderProfile(
                    id="elder-001",
                    name="李奶奶",
                    age=72,
                    apartment="1栋101",
                    community_id="community-001",
                    device_mac=DEVICE_MAC,
                    device_macs=[DEVICE_MAC],
                )
            ],
        )


class _StreamService:
    def __init__(self, sample: HealthSample | None) -> None:
        self._sample = sample

    def latest(self, device_mac: str) -> HealthSample | None:
        assert device_mac == DEVICE_MAC
        return self._sample


class _AlarmService:
    def __init__(self, alarms: list[AlarmRecord] | None = None) -> None:
        self._alarms = alarms or []

    def list_alarms(self, device_mac: str | None = None, active_only: bool = False) -> list[AlarmRecord]:
        rows = [
            alarm
            for alarm in self._alarms
            if device_mac is None or alarm.device_mac == device_mac
        ]
        if active_only:
            rows = [alarm for alarm in rows if not alarm.acknowledged]
        return rows


def _sample(*, blood_oxygen: int = 98, health_score: int = 86) -> HealthSample:
    return HealthSample(
        device_mac=DEVICE_MAC,
        timestamp=datetime.now(timezone.utc),
        heart_rate=72,
        temperature=36.5,
        blood_oxygen=blood_oxygen,
        blood_pressure="120/80",
        battery=80,
        health_score=health_score,
        steps=2500,
    )


def _service(
    *,
    sample: HealthSample | None = None,
    alarms: list[AlarmRecord] | None = None,
) -> RobotCompanionAgentService:
    context_manager = RobotCompanionContextManager(
        care_service=_CareService(),  # type: ignore[arg-type]
        stream_service=_StreamService(sample),  # type: ignore[arg-type]
        alarm_service=_AlarmService(alarms),  # type: ignore[arg-type]
        analysis_service=HealthDataAnalysisService(),
        weather_provider=MockWeatherProvider(),
        location_provider=MockLocationProvider(),
        robot_state_provider=MockRobotStateProvider(),
    )
    return RobotCompanionAgentService(
        context_manager=context_manager,
        intent_classifier=RobotCompanionIntentClassifier(_RuleOnlySettings()),  # type: ignore[arg-type]
        action_planner=RobotCompanionActionPlanner(),
        safety_guard=RobotCompanionSafetyGuard(),
    )


def test_walk_request_builds_real_health_context_and_blocks_motion() -> None:
    result = _service(sample=_sample()).dialogue(
        RobotCompanionDialogueRequest(
            elder_id="elder-001",
            text="小狗，我们出去走走吧",
            demo_weather="sunny",
            use_llm=False,
        )
    )

    assert result.agent == "care_companion"
    assert result.decision.intent == RobotCompanionIntent.WALK_REQUEST
    assert result.context.health.health_score == 86
    assert result.context.health.risk_level == "low"
    assert result.context.health.today_steps == 2500
    assert result.context.environment.provider == "mock"
    assert result.context.location.provider == "mock"
    assert result.action_plan.type == RobotCompanionActionType.PREPARE_FOLLOW
    assert result.action_plan.enabled is False
    assert result.action_plan.execution == "not_executed"
    assert result.safety.status == "blocked"
    assert result.safety.code == "MOTION_DISABLED"


def test_rain_blocks_outdoor_companion_plan_before_motion_check() -> None:
    result = _service(sample=_sample()).dialogue(
        RobotCompanionDialogueRequest(
            elder_id="elder-001",
            text="今天陪我去公园",
            demo_weather="rain",
            use_llm=False,
        )
    )

    assert result.decision.intent == RobotCompanionIntent.WALK_REQUEST
    assert result.context.environment.weather == "rain"
    assert result.safety.code == "WEATHER_RAIN"
    assert "路面" in result.reply


def test_recent_fall_blocks_walk_and_escalates_health_context() -> None:
    fall_alarm = AlarmRecord(
        device_mac=DEVICE_MAC,
        alarm_type=AlarmType.FALL_DETECTED,
        alarm_level=AlarmPriority.CRITICAL,
        alarm_layer=AlarmLayer.REALTIME,
        message="检测到跌倒",
    )
    result = _service(sample=_sample(), alarms=[fall_alarm]).dialogue(
        RobotCompanionDialogueRequest(
            elder_id="elder-001",
            text="陪我出去散步",
            use_llm=False,
        )
    )

    assert result.context.health.recent_fall is True
    assert result.context.health.risk_level == "high"
    assert result.safety.code == "RECENT_FALL"
    assert "不要走太远" in result.reply


def test_emergency_intent_generates_non_executed_help_plan() -> None:
    result = _service(sample=_sample()).dialogue(
        RobotCompanionDialogueRequest(
            elder_id="elder-001",
            text="我摔倒了，快帮帮我",
            use_llm=False,
        )
    )

    assert result.decision.intent == RobotCompanionIntent.EMERGENCY
    assert result.action_plan.type == RobotCompanionActionType.REQUEST_HELP
    assert result.action_plan.enabled is False
    assert result.safety.code == "HUMAN_CONFIRMATION_REQUIRED"
    assert "不会自动" in result.reply


def test_dialogue_api_returns_companion_contract() -> None:
    payload = RobotCompanionDialogueRequest(
        elder_id="elder-001",
        text="今天的天气怎么样",
        demo_weather="sunny",
        use_llm=False,
    )

    result = asyncio.run(robot_companion_dialogue(payload, _service(sample=_sample())))

    assert result.decision.intent == RobotCompanionIntent.WEATHER_QUERY
    assert result.action_plan.type == RobotCompanionActionType.NONE
    assert result.safety.status == "allowed"
    assert result.safety.code == "ADVISORY_ONLY"


def test_unbound_device_cannot_be_used_for_elder_health_context() -> None:
    request = RobotCompanionDialogueRequest(
        elder_id="elder-001",
        device_mac="AA:BB:CC:DD:EE:FF",
        text="看看我的健康状态",
        use_llm=False,
    )

    with pytest.raises(RobotCompanionContextError) as exc_info:
        _service(sample=_sample()).dialogue(request)

    assert exc_info.value.code == "DEVICE_NOT_BOUND_TO_ELDER"
    assert exc_info.value.status_code == 409
