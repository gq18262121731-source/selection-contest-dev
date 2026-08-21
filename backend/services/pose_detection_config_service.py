from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.config import Settings


class PoseDetectionConfigService:
    """Persists pose ROI and runtime tuning values in the local .env file."""

    _SUPPORTED_KEYS = {
        "POSE_DETECTION_ENABLED",
        "POSE_DETECTION_PROFILE",
        "POSE_DETECTION_PROCESS_EVERY_OVERRIDE",
        "POSE_DETECTION_POSE_CONF_THRESHOLD",
        "POSE_DETECTION_ANALYSIS_WIDTH",
        "POSE_DETECTION_FLOOR_ROI_RECT",
        "POSE_DETECTION_BED_ROI_RECT",
    }
    _KEY_TO_ATTR = {
        "POSE_DETECTION_ENABLED": "pose_detection_enabled",
        "POSE_DETECTION_PROFILE": "pose_detection_profile",
        "POSE_DETECTION_PROCESS_EVERY_OVERRIDE": "pose_detection_process_every_override",
        "POSE_DETECTION_POSE_CONF_THRESHOLD": "pose_detection_pose_conf_threshold",
        "POSE_DETECTION_ANALYSIS_WIDTH": "pose_detection_analysis_width",
        "POSE_DETECTION_FLOOR_ROI_RECT": "pose_detection_floor_roi_rect",
        "POSE_DETECTION_BED_ROI_RECT": "pose_detection_bed_roi_rect",
    }

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._env_path = Path(__file__).resolve().parents[2] / ".env"

    def current(self) -> dict[str, Any]:
        return {
            "enabled": self._settings.pose_detection_enabled,
            "profile": self._settings.pose_detection_profile,
            "process_every_override": self._settings.pose_detection_process_every_override,
            "pose_conf_threshold": self._settings.pose_detection_pose_conf_threshold,
            "analysis_width": self._settings.pose_detection_analysis_width,
            "floor_roi_rect": self._settings.pose_detection_floor_roi_rect,
            "bed_roi_rect": self._settings.pose_detection_bed_roi_rect,
        }

    def update(self, payload: dict[str, Any]) -> dict[str, Any]:
        updates = self._normalize_updates(payload)
        if not updates:
            return self.current()
        lines = self._read_lines()
        applied_keys: set[str] = set()
        next_lines: list[str] = []
        for raw_line in lines:
            line = raw_line.rstrip("\n")
            if "=" not in line or line.lstrip().startswith("#"):
                next_lines.append(line)
                continue
            key, _sep, _value = line.partition("=")
            normalized_key = key.strip().upper()
            if normalized_key in updates:
                next_lines.append(f"{normalized_key}={updates[normalized_key]}")
                applied_keys.add(normalized_key)
            else:
                next_lines.append(line)
        for key, value in updates.items():
            if key not in applied_keys:
                next_lines.append(f"{key}={value}")
        self._env_path.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")
        self._apply_runtime_updates(updates)
        return self.current()

    def _normalize_updates(self, payload: dict[str, Any]) -> dict[str, str]:
        updates: dict[str, str] = {}
        for key, value in payload.items():
            normalized = key.strip().upper()
            if normalized not in self._SUPPORTED_KEYS:
                continue
            updates[normalized] = self._stringify(normalized, value)
        return updates

    def _stringify(self, key: str, value: Any) -> str:
        if key == "POSE_DETECTION_ENABLED":
            return "true" if bool(value) else "false"
        if key in {"POSE_DETECTION_PROCESS_EVERY_OVERRIDE", "POSE_DETECTION_ANALYSIS_WIDTH"}:
            return str(max(0, int(value)))
        if key == "POSE_DETECTION_POSE_CONF_THRESHOLD":
            return str(max(0.0, min(1.0, float(value))))
        return str(value or "").strip()

    def _read_lines(self) -> list[str]:
        if not self._env_path.exists():
            return []
        return self._env_path.read_text(encoding="utf-8").splitlines()

    def _apply_runtime_updates(self, updates: dict[str, str]) -> None:
        for key, value in updates.items():
            attr = self._KEY_TO_ATTR.get(key)
            if not attr:
                continue
            if key == "POSE_DETECTION_ENABLED":
                setattr(self._settings, attr, value.lower() == "true")
            elif key in {"POSE_DETECTION_PROCESS_EVERY_OVERRIDE", "POSE_DETECTION_ANALYSIS_WIDTH"}:
                setattr(self._settings, attr, int(value))
            elif key == "POSE_DETECTION_POSE_CONF_THRESHOLD":
                setattr(self._settings, attr, float(value))
            else:
                setattr(self._settings, attr, value)
