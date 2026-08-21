from __future__ import annotations

import asyncio
import base64
import io
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient
from starlette.datastructures import Headers

from agent.go2_companion.agent import Go2CompanionAgent, Go2CompanionChatResult
from agent.go2_companion.prompt import SYSTEM_PROMPT
from backend.api.go2_companion_api import (
    go2_companion_voice_status,
    go2_companion_voice_turn,
    router,
)
from backend.dependencies import get_go2_companion_voice_service
from backend.services.go2_companion_voice_service import (
    Go2CompanionVoiceError,
    Go2CompanionVoiceService,
)


class _Settings:
    dashscope_api_key = "test-key"
    qwen_api_base = "https://example.invalid/v1"
    llm_timeout_seconds = 3
    tongyi_chat_configured = True
    tongyi_chat_model = "qwen-test"
    qwen_asr_model_id = "asr-test"
    qwen_tts_model_id = "tts-test"


class _FakeCompletions:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs["messages"])
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="我是小康，很高兴陪您聊聊天。")
                )
            ]
        )


class _FakeClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions())


class _FakeVoiceService:
    def __init__(self, *, asr_ok: bool = True) -> None:
        self._settings = _Settings()
        self._asr_ok = asr_ok
        self.transcribe_calls: list[tuple[bytes, str]] = []
        self.synthesize_calls: list[tuple[str, str, str]] = []

    @property
    def settings(self):
        return self._settings

    def transcribe(self, audio_bytes: bytes, *, fmt: str):
        self.transcribe_calls.append((audio_bytes, fmt))
        if not self._asr_ok:
            return {"ok": False, "text": "", "error": "ASR unavailable"}
        return {
            "ok": True,
            "text": "小狗，你叫什么名字？",
            "provider": "mock/asr",
        }

    def synthesize(self, text: str, *, voice: str, fmt: str):
        self.synthesize_calls.append((text, voice, fmt))
        return {
            "ok": True,
            "audio_b64": base64.b64encode(b"RIFF-test-wave").decode("ascii"),
            "audio_url": "",
            "fmt": fmt,
            "provider": "mock/tts",
            "voice": voice,
        }


class _FakeAgent:
    configured = True
    model = "qwen-test"

    def chat(self, text: str, *, session_id: str) -> Go2CompanionChatResult:
        assert text == "小狗，你叫什么名字？"
        assert session_id == "elder-001"
        return Go2CompanionChatResult(
            reply="我是小康，很高兴陪您聊聊天。",
            provider="mock/qwen",
            model=self.model,
        )


class _Dumpable:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def model_dump(self, *, mode: str):
        assert mode == "json"
        return self._payload


class _FakeDialogueService:
    def __init__(self) -> None:
        self.requests = []

    def process_turn(self, request):
        self.requests.append(request)
        return SimpleNamespace(
            reply="当前健康风险较低，南京现在35度，暂时不建议外出。",
            llm_provider="mock/qwen-grounded",
            llm_model="qwen-test",
            context=_Dumpable(
                {
                    "elder_id": "elder01_02",
                    "elder_name": "李四",
                    "generated_at": "2026-07-31T09:00:00Z",
                    "health": {
                        "risk_level": "low",
                        "health_score": None,
                        "recent_fall": False,
                        "sos": False,
                        "today_steps": 4100,
                        "data_freshness": "fresh",
                        "device_mac": "53:57:08:00:00:01",
                    },
                    "environment": {
                        "weather": "hot",
                        "temperature": 35,
                        "humidity": 53,
                        "wind_level": 3,
                        "description": "多云",
                        "suggestion": "高温天气请注意补水。",
                        "provider": "qweather",
                        "source": "qweather",
                    },
                    "location": {
                        "city": "南京",
                        "area": "1-102",
                        "address": "1-102",
                        "provider": "mock",
                    },
                    "robot": {
                        "online": True,
                        "motion_enabled": False,
                        "provider": "mock",
                    },
                }
            ),
            health_metrics=_Dumpable(
                {
                    "available": True,
                    "source": "realtime_stream",
                    "observed_at": "2026-07-31T09:00:00Z",
                    "freshness": "fresh",
                    "risk_level": "low",
                    "heart_rate": 77,
                    "blood_oxygen": 98,
                    "temperature": 36.2,
                    "blood_pressure": "122/75",
                    "health_score": None,
                    "steps": 4100,
                    "recent_fall": False,
                    "sos": False,
                }
            ),
        )


def _service(
    *,
    asr_ok: bool = True,
    grounded: bool = False,
) -> Go2CompanionVoiceService:
    return Go2CompanionVoiceService(
        voice_service=_FakeVoiceService(asr_ok=asr_ok),  # type: ignore[arg-type]
        agent=_FakeAgent(),  # type: ignore[arg-type]
        dialogue_service=(
            _FakeDialogueService() if grounded else None  # type: ignore[arg-type]
        ),
    )


def test_persona_is_voice_first_and_does_not_claim_robot_execution() -> None:
    assert "名字叫“小康”" in SYSTEM_PROMPT
    assert "2 到 3 个短句" in SYSTEM_PROMPT
    assert "不得声称已经开始跟随" in SYSTEM_PROMPT
    assert "不猜测老人的性别" in SYSTEM_PROMPT
    assert "心率、血氧和体温的实际数值" in SYSTEM_PROMPT
    assert "第一句直接说明“可以”或“暂时不建议”" in SYSTEM_PROMPT
    assert "不得自行把某个心率" in SYSTEM_PROMPT
    assert "不得相互归因" in SYSTEM_PROMPT
    assert "不得声称健康数据限制外出" in SYSTEM_PROMPT


def test_agent_keeps_bounded_session_history() -> None:
    client = _FakeClient()
    agent = Go2CompanionAgent(
        _Settings(),  # type: ignore[arg-type]
        client=client,
        max_history_turns=1,
    )

    first = agent.chat("你叫什么名字？", session_id="elder-001")
    second = agent.chat("你能陪我聊天吗？", session_id="elder-001")

    assert first.reply == "我是小康，很高兴陪您聊聊天。"
    assert second.model == "qwen-test"
    second_messages = client.chat.completions.calls[1]
    assert [message["role"] for message in second_messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]


def test_agent_can_disable_session_history() -> None:
    client = _FakeClient()
    agent = Go2CompanionAgent(
        _Settings(),  # type: ignore[arg-type]
        client=client,
        max_history_turns=0,
    )

    agent.chat("第一句话", session_id="elder-001")
    agent.chat("第二句话", session_id="elder-001")

    assert [message["role"] for message in client.chat.completions.calls[1]] == [
        "system",
        "user",
    ]


def test_voice_pipeline_runs_asr_llm_tts_and_marks_go2_unconfigured() -> None:
    result = _service().process_turn(
        b"audio-bytes" * 20,
        audio_format="wav",
        session_id="elder-001",
        voice="Serena",
    )

    assert result["transcript"] == "小狗，你叫什么名字？"
    assert result["reply"] == "我是小康，很高兴陪您聊聊天。"
    assert result["audio_format"] == "wav"
    assert result["playback"]["mode"] == "response_only"
    assert result["playback"]["go2_status"] == "not_configured"
    assert result["playback"]["ready_for_client_playback"] is True
    assert result["grounded"] is False
    assert result["context"] is None
    assert result["health_metrics"] is None


def test_voice_pipeline_can_ground_reply_with_health_and_weather() -> None:
    service = _service(grounded=True)

    result = service.process_turn(
        b"audio-bytes" * 20,
        audio_format="wav",
        session_id="elder-001",
        voice="Serena",
        elder_id="elder01_02",
        device_mac="53:57:08:00:00:01",
        location_hint="南京",
    )

    assert result["grounded"] is True
    assert result["reply"].startswith("当前健康风险较低")
    assert result["context"]["environment"]["provider"] == "qweather"
    assert result["health_metrics"]["heart_rate"] == 77
    assert result["playback"]["go2_status"] == "not_configured"


def test_voice_pipeline_reports_failed_stage() -> None:
    with pytest.raises(Go2CompanionVoiceError) as exc_info:
        _service(asr_ok=False).process_turn(
            b"audio-bytes" * 20,
            audio_format="wav",
            session_id="elder-001",
            voice="Serena",
        )

    assert exc_info.value.stage == "asr"
    assert exc_info.value.status_code == 502


def test_voice_turn_api_returns_pipeline_contract() -> None:
    upload = UploadFile(
        file=io.BytesIO(b"audio-bytes" * 20),
        filename="elder.wav",
        headers=Headers({"content-type": "audio/wav"}),
    )

    response = asyncio.run(
        go2_companion_voice_turn(
            file=upload,
            session_id="elder-001",
            voice="Serena",
            service=_service(),
        )
    )

    assert response.agent == "go2_companion"
    assert response.transcript == "小狗，你叫什么名字？"
    assert response.playback.go2_status == "not_configured"


def test_voice_turn_api_rejects_unsupported_file() -> None:
    upload = UploadFile(
        file=io.BytesIO(b"not-audio" * 20),
        filename="payload.txt",
        headers=Headers({"content-type": "text/plain"}),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            go2_companion_voice_turn(
                file=upload,
                session_id="elder-001",
                voice="Serena",
                service=_service(),
            )
        )

    assert getattr(exc_info.value, "status_code", None) == 400


def test_voice_status_exposes_hardware_boundary() -> None:
    response = asyncio.run(go2_companion_voice_status(service=_service()))

    assert response.pipeline == ["asr", "llm", "tts"]
    assert response.go2_microphone == "not_configured"
    assert response.go2_speaker == "not_configured"
    assert response.context_grounding_supported is False


def test_multipart_route_contract() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_go2_companion_voice_service] = _service
    client = TestClient(app)

    response = client.post(
        "/api/v1/go2-companion/voice-turn",
        files={"file": ("elder.wav", b"audio-bytes" * 20, "audio/wav")},
        data={"session_id": "elder-001", "voice": "Serena"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["transcript"] == "小狗，你叫什么名字？"
    assert payload["playback"]["go2_status"] == "not_configured"
    assert payload["grounded"] is False


def test_multipart_route_can_enable_health_weather_grounding() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_go2_companion_voice_service] = lambda: _service(
        grounded=True
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/go2-companion/voice-turn",
        files={"file": ("elder.wav", b"audio-bytes" * 20, "audio/wav")},
        data={
            "session_id": "elder-001",
            "voice": "Serena",
            "elder_id": "elder01_02",
            "device_mac": "53:57:08:00:00:01",
            "location_hint": "南京",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["grounded"] is True
    assert payload["context"]["environment"]["provider"] == "qweather"
    assert payload["health_metrics"]["blood_oxygen"] == 98
