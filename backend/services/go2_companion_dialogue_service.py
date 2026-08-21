from __future__ import annotations

from typing import Any

from agent.go2_companion.agent import Go2CompanionAgent
from agent.robot_companion.context_manager import RobotCompanionContextManager
from backend.schemas.go2_companion_schema import (
    Go2CompanionHealthMetrics,
    Go2CompanionTextTurnRequest,
    Go2CompanionTextTurnResponse,
)
from backend.services.stream_service import StreamService


class Go2CompanionDialogueService:
    """Ground Qwen companion replies with current health and weather facts."""

    def __init__(
        self,
        *,
        agent: Go2CompanionAgent,
        context_manager: RobotCompanionContextManager,
        stream_service: StreamService,
    ) -> None:
        self._agent = agent
        self._context = context_manager
        self._stream = stream_service

    def process_turn(
        self,
        request: Go2CompanionTextTurnRequest,
    ) -> Go2CompanionTextTurnResponse:
        context = self._context.build(
            elder_id=request.elder_id,
            device_mac=request.device_mac,
            location_hint=request.location_hint,
            weather_scenario="sunny",
        )
        health_metrics = self._build_health_metrics(
            device_mac=context.health.device_mac,
            freshness=context.health.data_freshness,
            risk_level=context.health.risk_level,
            recent_fall=context.health.recent_fall,
            sos=context.health.sos,
        )
        session_id = request.session_id or request.elder_id
        chat = self._agent.chat(
            request.text,
            session_id=session_id,
            grounding_context=self._build_grounding_context(
                context=context,
                health_metrics=health_metrics,
            ),
        )
        return Go2CompanionTextTurnResponse(
            session_id=session_id,
            reply=chat.reply,
            llm_provider=chat.provider,
            llm_model=chat.model,
            context=context,
            health_metrics=health_metrics,
        )

    def _build_health_metrics(
        self,
        *,
        device_mac: str | None,
        freshness: str,
        risk_level: str,
        recent_fall: bool,
        sos: bool,
    ) -> Go2CompanionHealthMetrics:
        sample = self._stream.latest(device_mac) if device_mac else None
        return Go2CompanionHealthMetrics(
            available=sample is not None,
            source="realtime_stream",
            observed_at=sample.timestamp if sample else None,
            freshness=freshness,
            risk_level=risk_level,
            heart_rate=sample.heart_rate if sample else None,
            blood_oxygen=sample.blood_oxygen if sample else None,
            temperature=sample.temperature if sample else None,
            blood_pressure=sample.blood_pressure if sample else None,
            health_score=sample.health_score if sample else None,
            steps=sample.steps if sample else None,
            recent_fall=recent_fall,
            sos=sos,
        )

    @staticmethod
    def _build_grounding_context(
        *,
        context,
        health_metrics: Go2CompanionHealthMetrics,
    ) -> dict[str, Any]:
        return {
            "elder": {
                "id": context.elder_id,
                "name": context.elder_name,
            },
            "health": health_metrics.model_dump(mode="json"),
            "weather": context.environment.model_dump(mode="json"),
            "location": context.location.model_dump(mode="json"),
            "capability_boundary": {
                "robot_motion_enabled": context.robot.motion_enabled,
                "robot_online": context.robot.online,
            },
        }
