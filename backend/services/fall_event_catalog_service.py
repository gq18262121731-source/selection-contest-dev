from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any


class FallEventCatalogService:
    def __init__(self, catalog_path: str | Path) -> None:
        self._catalog_path = Path(catalog_path)
        self._entries = self._load_entries()

    def _load_entries(self) -> list[dict[str, Any]]:
        if not self._catalog_path.is_file():
            return []
        raw = json.loads(self._catalog_path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, list) else []

    def match(self, event: dict[str, Any]) -> dict[str, Any] | None:
        state = str(event.get("state") or "").strip().lower()
        severity = str(event.get("severity") or "").strip().upper()
        injury = event.get("injury") if isinstance(event.get("injury"), dict) else {}
        injury_level = str(injury.get("level") or "").strip().upper()
        fall_score = self._coerce_float(event.get("fall_score"))
        down_seconds = self._coerce_float(injury.get("down_seconds") if isinstance(injury, dict) else 0.0)

        for entry in self._entries:
            states = {str(item).strip().lower() for item in entry.get("state_in", []) if item}
            if states and state not in states:
                continue

            severities = {str(item).strip().upper() for item in entry.get("severity_in", []) if item}
            if severities and severity not in severities:
                continue

            injury_levels = {str(item).strip().upper() for item in entry.get("injury_level_in", []) if item}
            if injury_levels and injury_level not in injury_levels:
                continue

            if fall_score < self._coerce_float(entry.get("min_fall_score"), default=-1.0):
                continue
            max_fall_score = self._coerce_float(entry.get("max_fall_score"), default=1.0)
            if fall_score > max_fall_score:
                continue
            if down_seconds < self._coerce_float(entry.get("min_down_seconds"), default=0.0):
                continue

            template_pool = entry.get("ui_template_pool") if isinstance(entry.get("ui_template_pool"), list) else []
            template = random.choice(template_pool) if template_pool else {}
            return {
                "code": str(entry.get("code") or "").strip(),
                "name": str(entry.get("name") or "").strip(),
                "alert_level": str(entry.get("alert_level") or "NOTICE").strip().upper(),
                "show_immediate_popup": bool(entry.get("show_immediate_popup")),
                "requires_multimodal_review": bool(entry.get("requires_multimodal_review")),
                "template": template if isinstance(template, dict) else {},
                "recommended_actions": list(entry.get("recommended_actions") or []),
            }
        return None

    @staticmethod
    def _coerce_float(value: object, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
