from __future__ import annotations

import base64
import io
import logging
import wave
from typing import Any, Iterator, Literal

from openai import OpenAI

from backend.config import Settings

logger = logging.getLogger(__name__)


class VoiceService:
    """DashScope voice service for ASR, Omni, and TTS flows."""

    _OMNI_AUDIO_VOICE_CANDIDATES = ("Chelsie", "Ethan")
    _QWEN_TTS_VOICE_ALIASES = {
        "longxiaochun": "Cherry",
        "longwan": "Serena",
        "longcheng": "Ethan",
        "longhua": "Chelsie",
        "longyingtian": "Serena",
    }
    _QWEN_TTS_BUILTIN_VOICES = {
        "cherry": "Cherry",
        "serena": "Serena",
        "ethan": "Ethan",
        "chelsie": "Chelsie",
    }

    def __init__(self, settings: Settings, device_service: Any | None = None) -> None:
        self._settings = settings
        self._device_service = device_service

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def _api_key(self) -> str:
        return self._settings.dashscope_api_key.strip()

    @property
    def _configured(self) -> bool:
        return bool(self._api_key)

    @property
    def _compatible_base_url(self) -> str:
        return self._settings.qwen_api_base.strip() or "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def _build_compatible_client(self) -> OpenAI:
        return OpenAI(
            api_key=self._api_key,
            base_url=self._compatible_base_url,
        )

    @staticmethod
    def _normalize_audio_format(fmt: str) -> str:
        normalized = (fmt or "wav").strip().lower()
        if normalized in {"wav", "wave"}:
            return "wav"
        if normalized in {"mp3", "mpeg"}:
            return "mp3"
        if normalized in {"m4a", "aac", "mp4"}:
            return "aac"
        if normalized in {"amr", "3gp", "3gpp"}:
            return normalized
        return "wav"

    @staticmethod
    def _extract_text_delta(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if not isinstance(item, dict):
                    continue
                text_value = item.get("text")
                if isinstance(text_value, str):
                    parts.append(text_value)
                    continue
                nested_text = item.get("content")
                if isinstance(nested_text, str):
                    parts.append(nested_text)
            return "".join(parts)
        return str(content)

    @staticmethod
    def _extract_audio_delta(audio: Any) -> str:
        if audio is None:
            return ""
        if isinstance(audio, dict):
            return str(audio.get("data") or "")
        data = getattr(audio, "data", None)
        if isinstance(data, str):
            return data
        if hasattr(audio, "get"):
            try:
                return str(audio.get("data") or "")
            except Exception:
                return ""
        return ""

    @staticmethod
    def _pcm_b64_to_wav_b64(audio_b64: str, *, sample_rate: int = 24000) -> str:
        if not audio_b64:
            return ""

        pcm_bytes = base64.b64decode(audio_b64)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_bytes)
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    def _build_health_context(self, device_mac: str | None) -> str:
        if not device_mac or self._device_service is None:
            return ""

        try:
            from backend.dependencies import get_display_latest_sample

            normalized_mac = device_mac.strip().upper()
            device = None
            if hasattr(self._device_service, "get_device"):
                device = self._device_service.get_device(normalized_mac)
            ingest_mode = getattr(device, "ingest_mode", None)
            sample = get_display_latest_sample(normalized_mac, ingest_mode)
            if sample is None:
                return ""

            blood_pressure = sample.blood_pressure or "--"
            steps = sample.steps if sample.steps is not None else "--"
            score = sample.health_score if sample.health_score is not None else "--"
            return (
                "\n当前可用的健康监测数据："
                f"心率 {sample.heart_rate} 次/分，"
                f"血氧 {sample.blood_oxygen}%，"
                f"体温 {sample.temperature:.1f} 摄氏度，"
                f"血压 {blood_pressure}，"
                f"步数 {steps}，"
                f"健康分 {score}。"
            )
        except Exception as exc:
            logger.debug("Failed to build health context for omni chat: %s", exc)
            return ""

    @classmethod
    def _resolve_qwen_tts_voice(cls, voice: str | None) -> str:
        normalized = (voice or "").strip()
        if not normalized:
            return "Serena"

        lowered = normalized.lower()
        if lowered in cls._QWEN_TTS_VOICE_ALIASES:
            return cls._QWEN_TTS_VOICE_ALIASES[lowered]
        if lowered in cls._QWEN_TTS_BUILTIN_VOICES:
            return cls._QWEN_TTS_BUILTIN_VOICES[lowered]
        return "Serena"

    @staticmethod
    def _build_elder_voice_style_prompt(*, has_health_context: bool) -> str:
        prompt = (
            "你是面向老人的健康说明助手、AI健康守护助手，当前正处于智慧康养项目的演示体验环节。\n"
            "无论用户说什么，必须优先理解用户的语音，然后基于提供的健康监测数据进行自然、口语化的语音反馈。\n"
            "你的任务是用简单、温和、充满关怀的拟人化口语和体验者（代入老人角色）对话，展现系统的智能化与温度。\n\n"
            "Sound warm, gentle, natural, and reassuring. "
            "Never invent measurements, diagnoses, symptoms, or events.\n\n"
            "约束要求：\n"
            "1. 用简单词语和短句，不使用复杂医学术语。一切回答必须使用简体中文。\n"
            "2. 语气温和、安抚、好理解，不制造恐慌。必须控制在2到3个短句以内，适合直接转换为语音念给老人听。\n"
            "3. 优先告诉老人现在身体大概稳不稳、指标的情况。一次只强调最关键的结论，如果指标异常需要复测或求助时，直接给出最简单的下一步动作（如：帮您呼叫家属）。\n"
            "4. 如果用户询问当天状态，使用诸如“整体指标看起来很平稳”、“血压确实有点小波动，别担心”等高视角的口语描述，不要生硬地朗读数值。\n"
            "5. 绝对不要虚构和捏造任何健康数值、诊断、症状或未发生的事情。\n"
        )
        if has_health_context:
            prompt += (
                "6. 请将下方的监测数据自然地融入长者的关怀回复中。\n"
            )
        else:
            prompt += (
                "6. 目前未能获取到有效的最新体征数据，请坦诚告知，并用温和安抚的口吻回应。\n"
            )
        return prompt

    def transcribe(self, audio_bytes: bytes, *, fmt: str = "wav") -> dict[str, object]:
        """Call DashScope Paraformer ASR to transcribe audio bytes."""
        if not self._configured:
            return {"ok": False, "text": "", "error": "DASHSCOPE_API_KEY not configured"}

        model_id = self._settings.qwen_asr_model_id.strip().lower()
        try:
            import dashscope
            import os
            import tempfile

            dashscope.api_key = self._api_key

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f".{fmt}")
            try:
                tmp.write(audio_bytes)
                tmp.close()
                from dashscope.audio.asr import Recognition, RecognitionCallback

                recognizer = Recognition(
                    model=model_id,
                    callback=RecognitionCallback(),
                    format=fmt,
                    sample_rate=16000,
                )
                result = recognizer.call(tmp.name)
                if getattr(result, "status_code", None) == 200:
                    sentences = result.get_sentence()
                    text = " ".join(
                        sentence.get("text", "")
                        for sentence in (sentences or [])
                        if isinstance(sentence, dict)
                    ).strip()
                    return {"ok": True, "text": text, "provider": f"dashscope/{model_id}"}
                return {"ok": False, "text": "", "error": getattr(result, "message", "ASR failed")}
            finally:
                if os.path.exists(tmp.name):
                    os.unlink(tmp.name)
        except Exception as exc:
            logger.warning("ASR failed: %s", exc)
            return {"ok": False, "text": "", "error": str(exc)}

    def omni_chat_stream(
        self,
        audio_bytes: bytes,
        *,
        prompt: str = "请先理解我的语音，再结合已有的健康监测数据，用自然、温和、好懂的话给出简短回答。",
        fmt: str = "wav",
        device_mac: str | None = None,
        role: str = "elder",
    ) -> Iterator[dict[str, object]]:
        """Yield text deltas and the completed audio from the configured Omni model."""
        if not self._configured:
            yield {
                "type": "error",
                "ok": False,
                "error": "DASHSCOPE_API_KEY not configured",
            }
            return

        model_id = self._settings.qwen_omni_model_id
        input_format = self._normalize_audio_format(fmt)
        normalized_role = (role or "elder").strip().lower()
        health_context = self._build_health_context(device_mac)
        prompt_text = (prompt or "").strip() or "请先理解我的语音，再结合已有的健康监测数据，用自然、温和、好懂的话给出简短回答。"
        system_prompt = (
            self._build_elder_voice_style_prompt(has_health_context=bool(health_context))
            if normalized_role == "elder"
            else (
                "You are a health monitoring assistant. "
                "Reply in Simplified Chinese. "
                "Base your answer only on the provided data and context. "
                "Be clear, concise, and easy to understand. "
                "Do not invent unavailable facts."
            )
        )
        if health_context:
            system_prompt += health_context

        if normalized_role == "elder":
            # Force Qwen-Omni to obey the persona by injecting it directly alongside the audio
            prompt_text = f"【系统指令与约束（必须严格遵守）】\n{system_prompt}\n\n【用户附加要求】\n{prompt_text}"

        audio_input_b64 = base64.b64encode(audio_bytes).decode("ascii")
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": f"data:;base64,{audio_input_b64}",
                            "format": input_format,
                        },
                    },
                    {"type": "text", "text": prompt_text},
                ],
            },
        ]

        try:
            client = self._build_compatible_client()
            request_kwargs: dict[str, object] = {
                "model": model_id,
                "messages": messages,
                "modalities": ["text", "audio"] if normalized_role == "elder" else ["text"],
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            selected_voice: str | None = None
            if normalized_role == "elder":
                completion = None
                last_voice_error: Exception | None = None
                for voice_name in self._OMNI_AUDIO_VOICE_CANDIDATES:
                    try:
                        request_kwargs["audio"] = {
                            "voice": voice_name,
                            "format": "wav",
                        }
                        completion = client.chat.completions.create(**request_kwargs)
                        selected_voice = voice_name
                        break
                    except Exception as exc:
                        message = str(exc).lower()
                        if "parameters.audio.voice" not in message:
                            raise
                        last_voice_error = exc
                if completion is None:
                    if last_voice_error is not None:
                        raise last_voice_error
                    raise RuntimeError("Failed to select a supported omni audio voice")
            else:
                completion = client.chat.completions.create(**request_kwargs)

            text_parts: list[str] = []
            audio_pcm_parts: list[str] = []
            audio_sequence = 0

            for chunk in completion:
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue

                delta = getattr(choices[0], "delta", None)
                if delta is None:
                    continue

                text_delta = self._extract_text_delta(getattr(delta, "content", None))
                if text_delta:
                    text_parts.append(text_delta)
                    yield {
                        "type": "answer.delta",
                        "delta": text_delta,
                    }

                audio_delta = self._extract_audio_delta(getattr(delta, "audio", None))
                if audio_delta:
                    audio_pcm_parts.append(audio_delta)
                    yield {
                        "type": "audio.delta",
                        "delta": audio_delta,
                        "sequence": audio_sequence,
                        "encoding": "pcm_s16le",
                        "sample_rate": 24000,
                        "channels": 1,
                    }
                    audio_sequence += 1

            answer_text = "".join(text_parts).strip()
            audio_pcm_b64 = "".join(audio_pcm_parts)
            audio_wav_b64 = self._pcm_b64_to_wav_b64(audio_pcm_b64) if audio_pcm_b64 else ""
            audio_url = ""

            if normalized_role == "elder" and not audio_wav_b64 and answer_text:
                fallback_tts = self.synthesize(
                    answer_text,
                    voice=self._settings.qwen_tts_voice_id,
                    fmt="wav",
                )
                if fallback_tts.get("ok"):
                    audio_wav_b64 = str(fallback_tts.get("audio_b64", "") or "")
                    audio_url = str(fallback_tts.get("audio_url", "") or "")
                    selected_voice = str(fallback_tts.get("voice") or selected_voice or "")

            if audio_wav_b64 or audio_url:
                yield {
                    "type": "audio.completed",
                    "audio_b64": audio_wav_b64,
                    "audio_pcm_b64": audio_pcm_b64,
                    "audio_url": audio_url
                    or (f"data:audio/wav;base64,{audio_wav_b64}" if audio_wav_b64 else ""),
                    "audio_sample_rate": 24000 if audio_wav_b64 else None,
                    "fmt": "wav",
                    "voice": selected_voice,
                }

            yield {
                "type": "answer.completed",
                "ok": True,
                "answer": answer_text,
                "provider": f"dashscope-compatible/{model_id}",
                "model": model_id,
                "voice": selected_voice if audio_wav_b64 or audio_url else None,
            }
        except Exception as exc:
            logger.error("Omni chat failed: %s", exc)
            message = str(exc)
            lower_message = message.lower()
            if "access_denied" in lower_message or "access denied" in lower_message:
                message = f"当前 DashScope 账号尚未开通 {model_id} 调用权限，请先在阿里云百炼控制台开通模型后再试。"
            yield {
                "type": "error",
                "ok": False,
                "error": message,
            }

    def omni_chat(
        self,
        audio_bytes: bytes,
        *,
        prompt: str = "请先理解我的语音，再结合已有的健康监测数据，用自然、温和、好懂的话给出简短回答。",
        fmt: str = "wav",
        device_mac: str | None = None,
        role: str = "elder",
    ) -> dict[str, object]:
        """Return the legacy aggregated Omni response using the streaming implementation."""
        answer_parts: list[str] = []
        completed_answer = ""
        provider: str | None = None
        model: str | None = None
        voice: str | None = None
        audio_b64 = ""
        audio_pcm_b64 = ""
        audio_url = ""
        audio_sample_rate: int | None = None
        audio_format: str | None = None

        for event in self.omni_chat_stream(
            audio_bytes,
            prompt=prompt,
            fmt=fmt,
            device_mac=device_mac,
            role=role,
        ):
            event_type = str(event.get("type") or "")
            if event_type == "answer.delta":
                answer_parts.append(str(event.get("delta") or ""))
                continue
            if event_type == "audio.completed":
                audio_b64 = str(event.get("audio_b64") or "")
                audio_pcm_b64 = str(event.get("audio_pcm_b64") or "")
                audio_url = str(event.get("audio_url") or "")
                audio_sample_rate_value = event.get("audio_sample_rate")
                audio_sample_rate = (
                    int(audio_sample_rate_value)
                    if isinstance(audio_sample_rate_value, int)
                    else None
                )
                audio_format = str(event.get("fmt") or "") or None
                voice = str(event.get("voice") or "") or None
                continue
            if event_type == "answer.completed":
                completed_answer = str(event.get("answer") or "")
                provider = str(event.get("provider") or "") or None
                model = str(event.get("model") or "") or None
                voice = str(event.get("voice") or "") or voice
                continue
            if event_type == "error":
                return {
                    "ok": False,
                    "text": "",
                    "error": str(event.get("error") or "Omni analysis failed"),
                }

        answer_text = completed_answer or "".join(answer_parts).strip()
        return {
            "ok": True,
            "text": answer_text,
            "answer": answer_text,
            "audio_b64": audio_b64,
            "audio_pcm_b64": audio_pcm_b64,
            "audio_url": audio_url,
            "audio_sample_rate": audio_sample_rate,
            "fmt": audio_format,
            "voice": voice,
            "provider": provider,
            "model": model,
        }

    def synthesize(
        self,
        text: str,
        *,
        voice: str = "longxiaochun",
        speed: float = 1.0,
        fmt: Literal["mp3", "wav", "pcm"] = "mp3",
        workspace: str | None = None,
    ) -> dict[str, object]:
        """Call DashScope TTS and return audio data."""
        if not self._configured:
            return {"ok": False, "audio_b64": "", "error": "DASHSCOPE_API_KEY not configured"}

        if not text.strip():
            return {"ok": False, "audio_b64": "", "error": "empty text"}

        model_id = self._settings.qwen_tts_model_id.strip().lower()
        try:
            import dashscope

            dashscope.api_key = self._api_key

            if "qwen-tts" in model_id or "qwen3-tts" in model_id:
                target_voice = self._resolve_qwen_tts_voice(voice)

                response = dashscope.MultiModalConversation.call(
                    model=model_id,
                    text=text,
                    voice=target_voice,
                    language_type="Chinese",
                    parameters={
                        "format": fmt,
                        "sample_rate": 16000,
                    },
                    stream=False,
                )

                if response.status_code == 200:
                    output = getattr(response, "output", None)
                    audio = getattr(output, "audio", None) if output else None
                    audio_b64 = str(getattr(audio, "data", "") or "")
                    audio_url = str(getattr(audio, "url", "") or "")
                    if audio_b64:
                        return {
                            "ok": True,
                            "audio_b64": audio_b64,
                            "audio_url": "",
                            "fmt": fmt,
                            "provider": f"dashscope/{model_id}",
                            "voice": target_voice,
                        }
                    if audio_url:
                        return {
                            "ok": True,
                            "audio_b64": "",
                            "audio_url": audio_url,
                            "fmt": fmt,
                            "provider": f"dashscope/{model_id}",
                            "voice": target_voice,
                        }
                    return {
                        "ok": False,
                        "audio_b64": "",
                        "error": "Invalid response structure from Qwen-TTS",
                    }

                return {"ok": False, "audio_b64": "", "error": response.message}

            if model_id.startswith("cosyvoice"):
                from dashscope.audio.tts_v2 import AudioFormat, ResultCallback, SpeechSynthesizer

                voice_id = (voice or "").strip() or "longwan"
                if voice_id not in ["longwan", "longxiaochun", "longcheng", "longhua", "longyingtian"]:
                    voice_id = "longwan"

                if fmt == "mp3":
                    audio_format = AudioFormat.MP3_24000HZ_MONO_256KBPS
                elif fmt == "wav":
                    audio_format = AudioFormat.WAV_24000HZ_MONO_16BIT
                else:
                    audio_format = AudioFormat.PCM_16000HZ_MONO_16BIT

                class _Callback(ResultCallback):
                    def __init__(self) -> None:
                        self.err = ""

                    def on_error(self, message) -> None:
                        self.err = str(message)

                callback = _Callback()
                synthesizer = SpeechSynthesizer(
                    model=model_id,
                    voice=voice_id,
                    format=audio_format,
                    speech_rate=speed,
                    callback=callback,
                )
                audio_bytes = synthesizer.call(text)
                if not audio_bytes:
                    return {"ok": False, "audio_b64": "", "error": callback.err or "CosyVoice empty audio"}

                audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
                return {
                    "ok": True,
                    "audio_b64": audio_b64,
                    "audio_url": "",
                    "fmt": fmt,
                    "provider": f"dashscope/{model_id}",
                    "voice": voice_id,
                }

            response = dashscope.SpeechSynthesizer.call(
                model=model_id,
                text=text,
                voice=voice,
                format=fmt,
                sample_rate=16000,
            )
            if response.get_audio_data():
                audio_b64 = base64.b64encode(response.get_audio_data()).decode("ascii")
                return {
                    "ok": True,
                    "audio_b64": audio_b64,
                    "audio_url": "",
                    "fmt": fmt,
                    "provider": f"dashscope/{model_id}",
                }

            return {"ok": False, "audio_b64": "", "error": "TTS failed to generate audio"}
        except Exception as exc:
            logger.error("TTS failed: %s", exc)
            return {"ok": False, "audio_b64": "", "error": str(exc)}
