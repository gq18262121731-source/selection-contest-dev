from __future__ import annotations

import os
from http import HTTPStatus
from types import SimpleNamespace

from backend.services.qwen_file_asr_service import QwenFileAsrService


class _Settings:
    dashscope_api_key = "test-key"
    qwen_asr_model = "qwen3-asr-flash-realtime-2026-02-10"


def test_qwen_file_asr_uses_offline_model_and_parses_text() -> None:
    calls = []

    def caller(**kwargs):
        calls.append(kwargs)
        audio_path = kwargs["messages"][0]["content"][0]["audio"]
        assert os.path.isabs(audio_path)
        assert os.path.exists(audio_path)
        return SimpleNamespace(
            status_code=HTTPStatus.OK,
            output={
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"text": "我现在想出去散步，可以吗？"},
                            ]
                        }
                    }
                ]
            },
        )

    service = QwenFileAsrService(_Settings(), caller=caller)  # type: ignore[arg-type]

    result = service.transcribe(b"RIFF-test-audio", fmt="wav")

    assert service.model == "qwen3-asr-flash"
    assert result == {
        "ok": True,
        "text": "我现在想出去散步，可以吗？",
        "provider": "dashscope/qwen3-asr-flash",
    }
    assert calls[0]["asr_options"]["language"] == "zh"


def test_qwen_file_asr_reports_empty_result() -> None:
    def caller(**kwargs):
        return SimpleNamespace(
            status_code=HTTPStatus.OK,
            output={"choices": [{"message": {"content": []}}]},
        )

    service = QwenFileAsrService(_Settings(), caller=caller)  # type: ignore[arg-type]

    result = service.transcribe(b"RIFF-test-audio", fmt="wav")

    assert result["ok"] is False
    assert result["text"] == ""
    assert "empty text" in str(result["error"])
