from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.config import Settings
from backend.services.camera_source_registry import CameraSourceRegistry


class CameraSetupConfigService:
    """Persists the active camera source setup in the local .env file."""

    _SUPPORTED_KEYS = {
        "CAMERA_SOURCE_MODE",
        "CAMERA_LOCAL_INDEX",
        "CAMERA_LOCAL_BACKEND",
        "CAMERA_IP",
        "CAMERA_USER",
        "CAMERA_PASSWORD",
        "CAMERA_RTSP_PORT",
        "CAMERA_RTSP_PATH",
        "CAMERA_STREAM_RTSP_PATH",
        "CAMERA_AUDIO_RTSP_PATH",
        "CAMERA_ONVIF_PORT",
    }
    _KEY_TO_ATTR = {
        "CAMERA_SOURCE_MODE": "camera_source_mode",
        "CAMERA_LOCAL_INDEX": "camera_local_index",
        "CAMERA_LOCAL_BACKEND": "camera_local_backend",
        "CAMERA_IP": "camera_ip",
        "CAMERA_USER": "camera_user",
        "CAMERA_PASSWORD": "camera_password",
        "CAMERA_RTSP_PORT": "camera_rtsp_port",
        "CAMERA_RTSP_PATH": "camera_rtsp_path",
        "CAMERA_STREAM_RTSP_PATH": "camera_stream_rtsp_path",
        "CAMERA_AUDIO_RTSP_PATH": "camera_audio_rtsp_path",
        "CAMERA_ONVIF_PORT": "camera_onvif_port",
    }

    def __init__(self, settings: Settings, registry: CameraSourceRegistry) -> None:
        self._settings = settings
        self._registry = registry
        self._env_path = Path(__file__).resolve().parents[2] / ".env"

    def current(self) -> dict[str, Any]:
        return {
            "camera_source_mode": self._settings.camera_source_mode,
            "camera_local_index": self._settings.camera_local_index,
            "camera_local_backend": self._settings.camera_local_backend,
            "camera_ip": self._settings.camera_ip,
            "camera_user": self._settings.camera_user,
            "camera_password": self._settings.camera_password,
            "camera_rtsp_port": self._settings.camera_rtsp_port,
            "camera_rtsp_path": self._settings.camera_rtsp_path,
            "camera_stream_rtsp_path": self._settings.camera_stream_rtsp_path,
            "camera_audio_rtsp_path": self._settings.camera_audio_rtsp_path,
            "camera_onvif_port": self._settings.camera_onvif_port,
        }

    def temporary_settings(self, payload: dict[str, Any]) -> Settings:
        updates = self._normalize_updates(payload)
        values = {
            self._KEY_TO_ATTR[key]: self._coerce_runtime_value(key, value)
            for key, value in updates.items()
            if key in self._KEY_TO_ATTR
        }
        return self._settings.model_copy(update=values)

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
        self._env_path.write_text(
            "\n".join(next_lines).rstrip() + "\n",
            encoding="utf-8",
        )
        self._apply_runtime_updates(updates)
        self._sync_runtime_truth(updates)
        if self._settings.camera_source_mode == "local":
            self._registry.select_local()
        elif self._settings.camera_source_mode == "rtsp":
            try:
                self._registry.select_source("camera1")
            except KeyError:
                pass
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
        if key == "CAMERA_SOURCE_MODE":
            mode = str(value or "local").strip().lower()
            return mode if mode in {"local", "rtsp", "auto"} else "local"
        if key == "CAMERA_LOCAL_BACKEND":
            backend = str(value or "any").strip().lower()
            return backend if backend in {"auto", "dshow", "msmf", "any"} else "any"
        if key in {"CAMERA_LOCAL_INDEX", "CAMERA_RTSP_PORT", "CAMERA_ONVIF_PORT"}:
            return str(max(0, int(value or 0)))
        return str(value or "").strip()

    def _coerce_runtime_value(self, key: str, value: str) -> str | int:
        if key in {"CAMERA_LOCAL_INDEX", "CAMERA_RTSP_PORT", "CAMERA_ONVIF_PORT"}:
            return int(value)
        return value

    def _read_lines(self) -> list[str]:
        if not self._env_path.exists():
            return []
        return self._env_path.read_text(encoding="utf-8").splitlines()

    def _apply_runtime_updates(self, updates: dict[str, str]) -> None:
        for key, value in updates.items():
            attr = self._KEY_TO_ATTR.get(key)
            if not attr:
                continue
            setattr(self._settings, attr, self._coerce_runtime_value(key, value))

    def _sync_runtime_truth(self, updates: dict[str, str]) -> None:
        camera_keys = {
            "CAMERA_IP",
            "CAMERA_USER",
            "CAMERA_PASSWORD",
            "CAMERA_RTSP_PORT",
            "CAMERA_RTSP_PATH",
            "CAMERA_STREAM_RTSP_PATH",
            "CAMERA_AUDIO_RTSP_PATH",
            "CAMERA_ONVIF_PORT",
        }
        if not any(key in updates for key in camera_keys):
            return
        try:
            runtime_source = self._registry.get_source("camera2")
        except KeyError:
            return
        # Only update the registry-backed runtime truth when the operator edits
        # the global camera values that camera1/camera2 historically inherit.
        payload = self._registry._load_registry()  # noqa: SLF001
        payload.setdefault("camera_truth_overrides", {})
        payload["camera_truth_overrides"].update(
            {
                "host": self._settings.camera_ip.strip() or runtime_source.ip,
                "username": self._settings.camera_user.strip() or runtime_source.user,
                "password": self._settings.camera_password or runtime_source.password,
                "rtsp_port": self._settings.camera_rtsp_port or runtime_source.rtsp_port,
                "stream": self._settings.camera_stream_rtsp_path.strip().split("/")[-1] if self._settings.camera_stream_rtsp_path.strip() else runtime_source.stream_rtsp_path.strip().split("/")[-1],
                "transport": self._settings.camera_stream_rtsp_path.strip().split("/")[1] if self._settings.camera_stream_rtsp_path.strip().startswith("/") and len(self._settings.camera_stream_rtsp_path.strip().split("/")) >= 3 else "tcp",
            }
        )
        self._registry._save_registry(payload)  # noqa: SLF001
