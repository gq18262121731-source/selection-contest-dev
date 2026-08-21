from __future__ import annotations

import json
import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from backend.dependencies import get_device_service, get_settings
from backend.services.voice_service import VoiceService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/omni", tags=["omni"])

_settings = get_settings()
_voice_service = VoiceService(_settings, device_service=get_device_service())


def _resolve_audio_format(filename: str, content_type: str) -> str:
    lower_name = filename.lower()
    lower_type = content_type.lower()
    if lower_name.endswith(".mp3") or "mpeg" in lower_type:
        return "mp3"
    if lower_name.endswith((".m4a", ".aac", ".mp4")) or lower_type in {"audio/mp4", "audio/aac"}:
        return "aac"
    if lower_name.endswith(".amr") or "amr" in lower_type:
        return "amr"
    if lower_name.endswith((".3gp", ".3gpp")) or "3gp" in lower_type or "3gpp" in lower_type:
        return "3gp"
    return "wav"


@router.post("/analyze")
async def omni_analyze_voice(
    file: UploadFile = File(...),
    prompt: str = Form("请先理解语音内容，再结合健康监测数据给出简短回答。"),
    role: str = Form("elder"),
    device_mac: str | None = Form(None),
) -> dict[str, object]:
    """Accept an audio clip and return configured omni text/audio output."""

    content_type = (file.content_type or "").split(";", maxsplit=1)[0].strip().lower()
    allowed = {
        "audio/wav",
        "audio/wave",
        "audio/mpeg",
        "audio/mp4",
        "audio/aac",
        "audio/amr",
        "audio/3gpp",
        "application/octet-stream",
    }

    filename = file.filename or "input.wav"
    if content_type not in allowed and not filename.lower().endswith(
        (".wav", ".mp3", ".m4a", ".aac", ".mp4", ".amr", ".3gp", ".3gpp")
    ):
        raise HTTPException(status_code=400, detail=f"Unsupported audio format: {content_type or 'unknown'}")

    audio_bytes = await file.read()
    if len(audio_bytes) < 100:
        raise HTTPException(status_code=400, detail="Audio file too small")

    fmt = _resolve_audio_format(filename, content_type)
    result = _voice_service.omni_chat(
        audio_bytes,
        prompt=prompt,
        fmt=fmt,
        device_mac=device_mac,
        role=role,
    )

    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error") or "Omni analysis failed")

    return result


@router.post("/analyze/stream")
async def omni_analyze_voice_stream(
    file: UploadFile = File(...),
    prompt: str = Form("请先理解语音内容，再结合健康监测数据给出简短回答。"),
    role: str = Form("elder"),
    device_mac: str | None = Form(None),
) -> StreamingResponse:
    """Stream Omni text deltas, then return the completed playable audio."""

    content_type = (file.content_type or "").split(";", maxsplit=1)[0].strip().lower()
    allowed = {
        "audio/wav",
        "audio/wave",
        "audio/mpeg",
        "audio/mp4",
        "audio/aac",
        "audio/amr",
        "audio/3gpp",
        "application/octet-stream",
    }

    filename = file.filename or "input.wav"
    if content_type not in allowed and not filename.lower().endswith(
        (".wav", ".mp3", ".m4a", ".aac", ".mp4", ".amr", ".3gp", ".3gpp")
    ):
        raise HTTPException(status_code=400, detail=f"Unsupported audio format: {content_type or 'unknown'}")

    audio_bytes = await file.read()
    if len(audio_bytes) < 100:
        raise HTTPException(status_code=400, detail="Audio file too small")

    fmt = _resolve_audio_format(filename, content_type)

    def event_stream():
        for event in _voice_service.omni_chat_stream(
            audio_bytes,
            prompt=prompt,
            fmt=fmt,
            device_mac=device_mac,
            role=role,
        ):
            yield json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/status")
async def omni_status() -> dict[str, object]:
    return {
        "configured": bool(_settings.dashscope_api_key.strip() and _settings.qwen_omni_model_id),
        "model": _settings.qwen_omni_model_id,
        "provider": "dashscope-compatible",
        "supported_modalities": ["audio", "text"],
        "output_modalities": ["text", "audio"],
    }
