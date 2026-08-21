from __future__ import annotations

import asyncio
import io
import json

from fastapi import UploadFile
from starlette.datastructures import Headers

from backend.api import omni_api


class _FakeStreamingVoiceService:
    def omni_chat_stream(self, audio_bytes: bytes, **kwargs):
        assert len(audio_bytes) >= 100
        assert kwargs["fmt"] == "wav"
        assert kwargs["role"] == "elder"
        yield {"type": "answer.delta", "delta": "您好，"}
        yield {
            "type": "audio.delta",
            "delta": "AAAAAA==",
            "sequence": 0,
            "encoding": "pcm_s16le",
            "sample_rate": 24000,
            "channels": 1,
        }
        yield {
            "type": "answer.completed",
            "ok": True,
            "answer": "您好，今天状态稳定。",
            "provider": "test",
            "model": "test-omni",
            "voice": None,
        }


async def _read_stream_body(response) -> str:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
    return "".join(chunks)


def test_omni_stream_api_returns_ndjson_events(monkeypatch) -> None:
    monkeypatch.setattr(omni_api, "_voice_service", _FakeStreamingVoiceService())
    upload = UploadFile(
        file=io.BytesIO(b"audio-bytes" * 20),
        filename="elder.wav",
        headers=Headers({"content-type": "audio/wav"}),
    )

    response = asyncio.run(
        omni_api.omni_analyze_voice_stream(
            file=upload,
            prompt="请简短回答",
            role="elder",
            device_mac="AA:BB:CC:DD:EE:FF",
        )
    )
    body = asyncio.run(_read_stream_body(response))
    events = [json.loads(line) for line in body.splitlines()]

    assert response.media_type == "application/x-ndjson"
    assert response.headers["cache-control"] == "no-cache"
    assert events[0] == {"type": "answer.delta", "delta": "您好，"}
    assert events[1]["type"] == "audio.delta"
    assert events[1]["encoding"] == "pcm_s16le"
    assert events[2]["type"] == "answer.completed"
    assert events[2]["answer"] == "您好，今天状态稳定。"
