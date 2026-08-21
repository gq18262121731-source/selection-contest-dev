from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FallResponseKnowledgeService:
    """Loads family-facing fall response guidance from local JSON resources."""

    def __init__(self, *, resources_root: Path) -> None:
        self._knowledge_path = resources_root / "fall_response_knowledge.json"
        self._cache: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if not self._knowledge_path.exists():
            self._cache = {}
            return
        self._cache = json.loads(self._knowledge_path.read_text(encoding="utf-8"))

    def get(
        self,
        *,
        catalog_code: str | None,
        event_state: str | None,
        severity: str | None,
        injury_level: str | None,
        alert_level: str | None,
        recommended_actions: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_catalog = str(catalog_code or "").strip()
        normalized_state = str(event_state or "").strip().lower()
        normalized_severity = str(severity or "").strip().upper()
        normalized_injury = str(injury_level or "").strip().upper()
        normalized_alert = str(alert_level or "").strip().upper()
        fallback_actions = list(recommended_actions or [])

        candidates = [
            normalized_catalog,
            f"{normalized_state}:{normalized_severity}:{normalized_injury}".strip(":"),
            f"{normalized_state}:{normalized_severity}".strip(":"),
            normalized_state,
            normalized_alert,
            "default",
        ]

        chosen: dict[str, Any] | None = None
        knowledge_key = "default"
        for key in candidates:
            if not key:
                continue
            item = self._cache.get(key)
            if isinstance(item, dict):
                chosen = dict(item)
                knowledge_key = key
                break

        if chosen is None:
            chosen = {}

        immediate_actions = chosen.get("immediate_actions")
        if not isinstance(immediate_actions, list) or not immediate_actions:
            immediate_actions = fallback_actions

        contra = chosen.get("contraindications")
        if not isinstance(contra, list):
            contra = []

        severity_label = str(chosen.get("severity_label") or "").strip()
        if not severity_label:
            severity_label = self._default_severity_label(
                alert_level=normalized_alert,
                event_state=normalized_state,
                injury_level=normalized_injury,
            )

        family_message = str(chosen.get("family_message") or "").strip()
        if not family_message:
            family_message = self._default_family_message(
                alert_level=normalized_alert,
                event_state=normalized_state,
            )

        return {
            "knowledge_key": knowledge_key,
            "severity_label": severity_label,
            "title": str(chosen.get("title") or "").strip(),
            "immediate_actions": [str(item).strip() for item in immediate_actions if str(item).strip()],
            "contraindications": [str(item).strip() for item in contra if str(item).strip()],
            "call_emergency": bool(chosen.get("call_emergency")),
            "family_message": family_message,
        }

    @staticmethod
    def _default_severity_label(
        *,
        alert_level: str,
        event_state: str,
        injury_level: str,
    ) -> str:
        if event_state in {"abnormal_recovery", "emergency", "needs_assistance"}:
            return "高危跌倒"
        if injury_level in {"I3", "I4", "I5"} or alert_level == "CRITICAL":
            return "高危跌倒"
        if event_state == "confirmed_fall":
            return "已确认跌倒"
        if event_state in {"suspected_fall", "possible_fall"} or alert_level == "WARNING":
            return "疑似跌倒"
        if event_state in {"post_fall_monitoring", "injury_watch", "recovery_watch"}:
            return "跌倒后持续观察"
        return "跌倒风险提醒"

    @staticmethod
    def _default_family_message(*, alert_level: str, event_state: str) -> str:
        if event_state in {"abnormal_recovery", "emergency", "needs_assistance"} or alert_level == "CRITICAL":
            return "请优先确认老人意识、呼吸和外伤情况，必要时立刻呼叫急救。"
        if event_state == "confirmed_fall":
            return "请尽快查看现场，确认老人是否能自主起身并联系护理人员。"
        if event_state in {"suspected_fall", "possible_fall"}:
            return "系统正在持续复核当前事件，请先查看现场画面并按风险处理。"
        return "请持续关注现场变化，并根据老人的实际状态决定是否寻求帮助。"
