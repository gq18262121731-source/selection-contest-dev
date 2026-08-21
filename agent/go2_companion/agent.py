from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Mapping

from openai import OpenAI

from agent.go2_companion.prompt import SYSTEM_PROMPT, build_grounding_prompt
from backend.config import Settings


class Go2CompanionAgentError(RuntimeError):
    pass


@dataclass(frozen=True)
class Go2CompanionChatResult:
    reply: str
    provider: str
    model: str


class Go2CompanionAgent:
    """Small, voice-first Qwen companion with bounded in-memory dialogue history."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: Any | None = None,
        max_history_turns: int = 3,
        max_sessions: int = 128,
    ) -> None:
        self._settings = settings
        self._client = client
        self._max_history_messages = max(0, int(max_history_turns)) * 2
        self._max_sessions = max(1, int(max_sessions))
        self._history: OrderedDict[str, list[dict[str, str]]] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self._settings.tongyi_chat_configured)

    @property
    def model(self) -> str:
        return self._settings.tongyi_chat_model

    def chat(
        self,
        text: str,
        *,
        session_id: str,
        grounding_context: Mapping[str, Any] | None = None,
    ) -> Go2CompanionChatResult:
        normalized_text = str(text or "").strip()
        if not normalized_text:
            raise Go2CompanionAgentError("老人话语为空")
        if not self.configured:
            raise Go2CompanionAgentError("Qwen 文本对话未配置")

        normalized_session = self._normalize_session_id(session_id)
        with self._lock:
            history = list(self._history.get(normalized_session, []))

        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
            *(
                [
                    {
                        "role": "system",
                        "content": build_grounding_prompt(grounding_context),
                    }
                ]
                if grounding_context is not None
                else []
            ),
            {"role": "user", "content": normalized_text},
        ]

        try:
            completion = self._get_client().chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.4,
                max_tokens=120,
                stream=False,
                extra_body={"enable_thinking": False},
            )
            reply = self._extract_reply(completion)
        except Exception as exc:
            raise Go2CompanionAgentError(f"Qwen 对话失败: {exc}") from exc

        if not reply:
            raise Go2CompanionAgentError("Qwen 未返回有效回复")

        with self._lock:
            updated = [
                *self._history.get(normalized_session, []),
                {"role": "user", "content": normalized_text},
                {"role": "assistant", "content": reply},
            ]
            if self._max_history_messages:
                self._history[normalized_session] = updated[-self._max_history_messages :]
                self._history.move_to_end(normalized_session)
                while len(self._history) > self._max_sessions:
                    self._history.popitem(last=False)
            else:
                self._history.pop(normalized_session, None)

        return Go2CompanionChatResult(
            reply=reply,
            provider="dashscope-compatible",
            model=self.model,
        )

    def reset(self, session_id: str) -> None:
        with self._lock:
            self._history.pop(self._normalize_session_id(session_id), None)

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = OpenAI(
                api_key=self._settings.dashscope_api_key,
                base_url=(
                    self._settings.qwen_api_base.strip()
                    or "https://dashscope.aliyuncs.com/compatible-mode/v1"
                ),
                timeout=max(20.0, float(self._settings.llm_timeout_seconds)),
                max_retries=0,
            )
        return self._client

    @staticmethod
    def _extract_reply(completion: Any) -> str:
        choices = getattr(completion, "choices", None) or []
        if not choices:
            return ""
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", "") if message is not None else ""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            return "".join(parts).strip()
        return str(content or "").strip()

    @staticmethod
    def _normalize_session_id(value: str) -> str:
        normalized = str(value or "").strip()
        return normalized[:100] or "default"
