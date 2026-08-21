from __future__ import annotations

import os
import tempfile
from http import HTTPStatus
from typing import Any, Callable

from backend.config import Settings


class QwenFileAsrService:
    """Transcribe short uploaded audio with the Qwen3 file ASR API."""

    def __init__(
        self,
        settings: Settings,
        *,
        caller: Callable[..., Any] | None = None,
    ) -> None:
        self._settings = settings
        self._caller = caller

    @property
    def model(self) -> str:
        configured = str(self._settings.qwen_asr_model or "").strip().lower()
        if (
            configured.startswith("qwen3-asr-flash")
            and "realtime" not in configured
            and "filetrans" not in configured
        ):
            return configured
        return "qwen3-asr-flash"

    def transcribe(self, audio_bytes: bytes, *, fmt: str) -> dict[str, object]:
        if not self._settings.dashscope_api_key.strip():
            return {
                "ok": False,
                "text": "",
                "error": "DASHSCOPE_API_KEY not configured",
            }

        temporary = tempfile.NamedTemporaryFile(delete=False, suffix=f".{fmt}")
        try:
            temporary.write(audio_bytes)
            temporary.close()
            response = self._get_caller()(
                api_key=self._settings.dashscope_api_key,
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [{"audio": os.path.abspath(temporary.name)}],
                    }
                ],
                result_format="message",
                asr_options={
                    "language": "zh",
                    "enable_itn": True,
                },
            )
            status_code = getattr(response, "status_code", None)
            if status_code != HTTPStatus.OK:
                return {
                    "ok": False,
                    "text": "",
                    "error": str(
                        getattr(response, "message", None)
                        or f"Qwen file ASR failed with status {status_code}"
                    ),
                }
            text = self._extract_text(getattr(response, "output", None))
            if not text:
                return {
                    "ok": False,
                    "text": "",
                    "error": "Qwen file ASR returned empty text",
                }
            return {
                "ok": True,
                "text": text,
                "provider": f"dashscope/{self.model}",
            }
        except Exception as exc:
            return {
                "ok": False,
                "text": "",
                "error": str(exc),
            }
        finally:
            if os.path.exists(temporary.name):
                os.unlink(temporary.name)

    def _get_caller(self) -> Callable[..., Any]:
        if self._caller is None:
            import dashscope

            self._caller = dashscope.MultiModalConversation.call
        return self._caller

    @staticmethod
    def _extract_text(output: Any) -> str:
        if not isinstance(output, dict):
            try:
                output = dict(output or {})
            except (TypeError, ValueError):
                return ""
        choices = output.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0]
        if not isinstance(first, dict):
            return ""
        message = first.get("message")
        if not isinstance(message, dict):
            return ""
        content = message.get("content")
        if not isinstance(content, list):
            return ""
        return "".join(
            str(item.get("text") or "")
            for item in content
            if isinstance(item, dict)
        ).strip()
