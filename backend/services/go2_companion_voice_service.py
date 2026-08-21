from __future__ import annotations

from typing import Any

from agent.go2_companion.agent import (
    Go2CompanionAgent,
    Go2CompanionAgentError,
)
from agent.robot_companion.context_manager import RobotCompanionContextError
from backend.schemas.go2_companion_schema import Go2CompanionTextTurnRequest
from backend.services.go2_companion_dialogue_service import Go2CompanionDialogueService
from backend.services.qwen_file_asr_service import QwenFileAsrService
from backend.services.voice_service import VoiceService


class Go2CompanionVoiceError(RuntimeError):
    def __init__(self, *, stage: str, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.status_code = status_code


class Go2CompanionVoiceService:
    """ASR -> text LLM -> TTS orchestration for one Go2 companion turn."""

    def __init__(
        self,
        *,
        voice_service: VoiceService,
        agent: Go2CompanionAgent,
        dialogue_service: Go2CompanionDialogueService | None = None,
        file_asr_service: QwenFileAsrService | None = None,
    ) -> None:
        self._voice = voice_service
        self._agent = agent
        self._dialogue = dialogue_service
        self._file_asr = file_asr_service

    def process_turn(
        self,
        audio_bytes: bytes,
        *,
        audio_format: str,
        session_id: str,
        voice: str,
        elder_id: str | None = None,
        device_mac: str | None = None,
        location_hint: str | None = None,
    ) -> dict[str, Any]:
        asr = self._transcribe(audio_bytes, audio_format=audio_format)
        if not asr.get("ok"):
            self._raise_stage_error("asr", asr)
        transcript = str(asr.get("text") or "").strip()
        if not transcript:
            raise Go2CompanionVoiceError(
                stage="asr",
                message="未识别到有效语音内容",
                status_code=422,
            )

        context_payload = None
        health_metrics_payload = None
        grounded = False
        try:
            if elder_id:
                if self._dialogue is None:
                    raise Go2CompanionVoiceError(
                        stage="context",
                        message="健康与天气上下文服务未配置",
                        status_code=503,
                    )
                dialogue = self._dialogue.process_turn(
                    Go2CompanionTextTurnRequest(
                        elder_id=elder_id,
                        device_mac=device_mac,
                        location_hint=location_hint,
                        session_id=session_id,
                        text=transcript,
                    )
                )
                reply = dialogue.reply
                llm_provider = dialogue.llm_provider
                llm_model = dialogue.llm_model
                context_payload = dialogue.context.model_dump(mode="json")
                health_metrics_payload = dialogue.health_metrics.model_dump(mode="json")
                grounded = True
            else:
                chat = self._agent.chat(transcript, session_id=session_id)
                reply = chat.reply
                llm_provider = chat.provider
                llm_model = chat.model
        except RobotCompanionContextError as exc:
            raise Go2CompanionVoiceError(
                stage="context",
                message=exc.message,
                status_code=exc.status_code,
            ) from exc
        except Go2CompanionAgentError as exc:
            status_code = 503 if "未配置" in str(exc) else 502
            raise Go2CompanionVoiceError(
                stage="llm",
                message=str(exc),
                status_code=status_code,
            ) from exc

        tts = self._voice.synthesize(
            reply,
            voice=voice,
            fmt="wav",
        )
        if not tts.get("ok"):
            self._raise_stage_error("tts", tts)

        audio_b64 = str(tts.get("audio_b64") or "")
        audio_url = str(tts.get("audio_url") or "")
        if not audio_b64 and not audio_url:
            raise Go2CompanionVoiceError(
                stage="tts",
                message="TTS 未返回可播放音频",
            )

        return {
            "agent": "go2_companion",
            "version": "1.0",
            "session_id": session_id,
            "transcript": transcript,
            "reply": reply,
            "audio_b64": audio_b64,
            "audio_url": audio_url or (
                f"data:audio/wav;base64,{audio_b64}" if audio_b64 else ""
            ),
            "audio_format": str(tts.get("fmt") or "wav"),
            "asr_provider": str(asr.get("provider") or "unknown"),
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "tts_provider": str(tts.get("provider") or "unknown"),
            "tts_voice": str(tts.get("voice") or voice),
            "grounded": grounded,
            "context": context_payload,
            "health_metrics": health_metrics_payload,
            "playback": {
                "mode": "response_only",
                "go2_status": "not_configured",
                "ready_for_client_playback": True,
                "message": (
                    "已返回可播放音频；当前仓库尚未配置真实 Go2 扬声器协议，"
                    "不会声称音频已在机器人上播放。"
                ),
            },
        }

    def status(self) -> dict[str, Any]:
        settings = self._voice.settings
        return {
            "pipeline": ["asr", "llm", "tts"],
            "asr_configured": bool(settings.dashscope_api_key.strip()),
            "llm_configured": self._agent.configured,
            "tts_configured": bool(settings.dashscope_api_key.strip()),
            "asr_model": (
                self._file_asr.model
                if self._file_asr is not None
                else settings.qwen_asr_model_id
            ),
            "llm_model": self._agent.model,
            "tts_model": settings.qwen_tts_model_id,
            "playback_mode": "response_only",
            "go2_microphone": "not_configured",
            "go2_speaker": "not_configured",
            "context_grounding_supported": self._dialogue is not None,
        }

    def _transcribe(
        self,
        audio_bytes: bytes,
        *,
        audio_format: str,
    ) -> dict[str, object]:
        configured_model = str(
            self._voice.settings.qwen_asr_model_id or ""
        ).strip().lower()
        if self._file_asr is not None and configured_model.startswith("qwen3-asr"):
            return self._file_asr.transcribe(audio_bytes, fmt=audio_format)
        return self._voice.transcribe(audio_bytes, fmt=audio_format)

    @staticmethod
    def _raise_stage_error(stage: str, result: dict[str, object]) -> None:
        message = str(result.get("error") or f"{stage.upper()} 处理失败")
        status_code = 503 if "not configured" in message.lower() else 502
        raise Go2CompanionVoiceError(
            stage=stage,
            message=message,
            status_code=status_code,
        )
