from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.go2_companion.agent import Go2CompanionAgent, Go2CompanionChatResult
from backend.api.go2_companion_api import router
from backend.dependencies import get_go2_companion_dialogue_service
from backend.models.health_model import HealthSample, IngestionSource
from backend.schemas.go2_companion_schema import Go2CompanionTextTurnRequest
from backend.schemas.robot_companion_schema import (
    RobotCompanionContext,
    RobotCompanionEnvironmentContext,
    RobotCompanionHealthContext,
    RobotCompanionLocationContext,
    RobotCompanionRobotContext,
)
from backend.services.go2_companion_dialogue_service import Go2CompanionDialogueService


class _Settings:
    dashscope_api_key = "test-key"
    qwen_api_base = "https://example.invalid/v1"
    llm_timeout_seconds = 3
    tongyi_chat_configured = True
    tongyi_chat_model = "qwen-test"


class _FakeCompletions:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="您当前监测状态平稳。南京今天晴、35℃，外出请缩短时间并注意补水。"
                    )
                )
            ]
        )


class _FakeClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions())


class _CapturingAgent:
    configured = True
    model = "qwen-test"

    def __init__(self) -> None:
        self.grounding_context = None

    def chat(self, text: str, *, session_id: str, grounding_context=None):
        self.grounding_context = grounding_context
        return Go2CompanionChatResult(
            reply="您当前监测状态平稳。南京今天晴、35℃，外出请缩短时间并注意补水。",
            provider="mock/qwen",
            model=self.model,
        )


class _ContextManager:
    def build(self, **kwargs) -> RobotCompanionContext:
        assert kwargs["elder_id"] == "elder01_02"
        assert kwargs["device_mac"] == "53:57:08:00:00:01"
        return RobotCompanionContext(
            elder_id="elder01_02",
            elder_name="李四",
            generated_at=datetime.now(timezone.utc),
            health=RobotCompanionHealthContext(
                risk_level="low",
                health_score=86,
                today_steps=2841,
                data_freshness="fresh",
                device_mac="53:57:08:00:00:01",
            ),
            environment=RobotCompanionEnvironmentContext(
                weather="hot",
                temperature=35,
                humidity=49,
                wind_level=3,
                description="晴",
                suggestion="气温较高，建议缩短户外活动时间并注意补水。",
                provider="qweather",
                source="qweather",
            ),
            location=RobotCompanionLocationContext(
                city="南京",
                area="演示区域",
                address="南京",
                provider="mock",
            ),
            robot=RobotCompanionRobotContext(
                online=False,
                motion_enabled=False,
                provider="mock",
            ),
        )


class _StreamService:
    def latest(self, device_mac: str):
        assert device_mac == "53:57:08:00:00:01"
        return HealthSample(
            device_mac=device_mac,
            timestamp=datetime.now(timezone.utc),
            heart_rate=80,
            blood_oxygen=96,
            temperature=36.3,
            blood_pressure="111/69",
            steps=2841,
            health_score=86,
            source=IngestionSource.MOCK,
        )


def _dialogue_service() -> Go2CompanionDialogueService:
    return Go2CompanionDialogueService(
        agent=_CapturingAgent(),  # type: ignore[arg-type]
        context_manager=_ContextManager(),  # type: ignore[arg-type]
        stream_service=_StreamService(),  # type: ignore[arg-type]
    )


def _request() -> Go2CompanionTextTurnRequest:
    return Go2CompanionTextTurnRequest(
        elder_id="elder01_02",
        device_mac="53:57:08:00:00:01",
        session_id="demo-context",
        text="我想出去散步。",
    )


def test_agent_sends_runtime_context_as_separate_system_message() -> None:
    client = _FakeClient()
    agent = Go2CompanionAgent(_Settings(), client=client)  # type: ignore[arg-type]

    result = agent.chat(
        "我想出去散步。",
        session_id="demo-context",
        grounding_context={
            "health": {"heart_rate": 80, "risk_level": "low"},
            "weather": {"description": "晴", "temperature": 35, "provider": "qweather"},
        },
    )

    messages = client.chat.completions.calls[0]["messages"]
    assert [message["role"] for message in messages] == ["system", "system", "user"]
    grounding = messages[1]["content"]
    assert '"heart_rate":80' in grounding
    assert '"provider":"qweather"' in grounding
    assert client.chat.completions.calls[0]["extra_body"] == {
        "enable_thinking": False
    }
    assert client.chat.completions.calls[0]["max_tokens"] == 120
    assert result.reply.startswith("您当前监测状态平稳")


def test_current_grounding_is_placed_after_dialogue_history() -> None:
    client = _FakeClient()
    agent = Go2CompanionAgent(_Settings(), client=client)  # type: ignore[arg-type]
    agent.chat("今天天气怎么样？", session_id="demo-context")

    agent.chat(
        "我现在可以出去散步吗？",
        session_id="demo-context",
        grounding_context={
            "health": {"risk_level": "low"},
            "weather": {"temperature": 35, "provider": "qweather"},
        },
    )

    messages = client.chat.completions.calls[1]["messages"]
    assert [message["role"] for message in messages] == [
        "system",
        "user",
        "assistant",
        "system",
        "user",
    ]
    assert "本轮必须回答的最新问题" in messages[-2]["content"]


def test_dialogue_service_links_health_weather_and_qwen() -> None:
    service = _dialogue_service()

    response = service.process_turn(_request())

    assert response.health_metrics.available is True
    assert response.health_metrics.heart_rate == 80
    assert response.health_metrics.blood_oxygen == 96
    assert response.context.environment.provider == "qweather"
    assert response.context.environment.temperature == 35
    assert response.reply.startswith("您当前监测状态平稳")
    assert service._agent.grounding_context["health"]["risk_level"] == "low"
    assert service._agent.grounding_context["weather"]["provider"] == "qweather"


def test_text_turn_api_returns_grounded_context_contract() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_go2_companion_dialogue_service] = _dialogue_service
    client = TestClient(app)

    response = client.post(
        "/api/v1/go2-companion/text-turn",
        json=_request().model_dump(mode="json"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "1.1"
    assert payload["health_metrics"]["heart_rate"] == 80
    assert payload["context"]["environment"]["provider"] == "qweather"
    assert payload["context"]["robot"]["motion_enabled"] is False
