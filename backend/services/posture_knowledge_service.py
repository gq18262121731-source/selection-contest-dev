from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PostureKnowledgeService:
    def __init__(self, *, resources_root: Path) -> None:
        self._knowledge_path = resources_root / "posture_knowledge.json"
        self._cache: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if not self._knowledge_path.exists():
            self._cache = {}
            return
        self._cache = json.loads(self._knowledge_path.read_text(encoding="utf-8"))

    def get(self, anomaly_type: str) -> dict[str, Any]:
        item = self._cache.get(anomaly_type)
        if item is None:
            item = self._cache.get("normal", {})
        return dict(item)
