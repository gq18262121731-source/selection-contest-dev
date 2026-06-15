from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, UploadFile, File, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.dependencies import get_settings, get_device_service
from backend.services.voice_service import VoiceService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])

_settings = get_settings()
_voice_service = VoiceService(_settings, device_service=get_device_service())


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    voice: str = Field(default="Serena")
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    fmt: Literal["mp3", "wav", "pcm"] = "mp3"
    workspace: str | None = None

class ASRBase64Request(BaseModel):
    audio_base64: str = Field(..., min_length=100)
    fmt: Literal["mp3", "wav", "pcm"] = "wav"

@router.post("/asr")
async def asr_transcribe(
    request: Request,
    file: UploadFile | None = File(None),
) -> dict:
    """Accept audio file (wav/webm/ogg) and return transcribed text via Qwen ASR."""
    if file is None:
        try:
            body = await request.json()
        except Exception:
            body = None
        if isinstance(body, dict):
            audio_base64 = str(body.get("audio_base64") or "").strip()
            if audio_base64:
                import base64

                if "," in audio_base64 and "base64" in audio_base64.split(",", 1)[0].lower():
                    audio_base64 = audio_base64.split(",", 1)[1].strip()
                try:
                    audio_bytes = base64.b64decode(audio_base64)
                except Exception:
                    raise HTTPException(status_code=400, detail="Invalid base64 audio")
                fmt = str(body.get("fmt") or "wav")
                result = _voice_service.transcribe(audio_bytes, fmt=fmt)
                return result

        raise HTTPException(status_code=400, detail="Missing audio file")

    allowed = {"audio/wav", "audio/wave", "audio/webm", "audio/ogg", "audio/mpeg", "audio/mp4", "application/octet-stream"}
    content_type = (file.content_type or "").split(";")[0].strip()
    if content_type not in allowed and not file.filename:
        raise HTTPException(status_code=400, detail="Unsupported audio format")

    audio_bytes = await file.read()
    if len(audio_bytes) < 100:
        raise HTTPException(status_code=400, detail="Audio file too small")

    fmt = "wav"
    name = (file.filename or "").lower()
    if "webm" in name or "webm" in content_type:
        fmt = "wav"
    elif "ogg" in name or "ogg" in content_type:
        fmt = "wav"
    elif "mp3" in name or "mpeg" in content_type:
        fmt = "mp3"

    result = _voice_service.transcribe(audio_bytes, fmt=fmt)
    return result


@router.post("/tts")
async def tts_synthesize(payload: TTSRequest) -> dict:
    """Convert text to speech via Qwen TTS and return base64-encoded audio."""
    raw = _voice_service.synthesize(
        payload.text,
        voice=(payload.voice or "").strip() or _settings.qwen_tts_voice_id,
        speed=payload.speed,
        fmt=payload.fmt,
        workspace=payload.workspace,
    )
    audio_b64 = str(raw.get("audio_b64", "") or "")
    audio_url = str(raw.get("audio_url", "") or "")
    fmt = str(raw.get("fmt", payload.fmt))
    return {
        "ok": bool(raw.get("ok", False)),
        "audio_b64": audio_b64,
        "audio_url": audio_url or (f"data:audio/{fmt};base64,{audio_b64}" if audio_b64 else ""),
        "fmt": fmt,
        "provider": raw.get("provider"),
        "voice": raw.get("voice", payload.voice),
        "error": raw.get("error"),
    }


@router.get("/status")
async def voice_status() -> dict:
    """Check whether voice services are configured."""
    configured = bool(_settings.dashscope_api_key.strip())
    note = "" if configured else "Set DASHSCOPE_API_KEY (or QWEN_API_KEY) in .env to enable voice features"
    tts_voices = ["Cherry", "Serena", "Ethan", "Chelsie"] if configured else []
    if configured and _settings.qwen_tts_model_id.startswith("cosyvoice"):
        note = "CosyVoice 需要通过音色复刻/音色设计创建 voice id，并在 /voice/tts 传入 voice 参数"
        tts_voices = [_settings.qwen_tts_voice_id]
    return {
        "configured": configured,
        "service_provider": "dashscope" if configured else "none",
        "provider": "dashscope" if configured else "none",
        "supported_languages": ["zh", "en"] if configured else [],
        "asr_model": _settings.qwen_asr_model_id if configured else None,
        "tts_model": _settings.qwen_tts_model_id if configured else None,
        "tts_voices": tts_voices,
        "note": note,
    }
