from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CameraConfig:
    host: str
    username: str
    password: str
    rtsp_port: int
    transport: str
    stream: str

    @property
    def rtsp_url(self) -> str:
        return (
            f"rtsp://{self.username}:{self.password}"
            f"@{self.host}:{self.rtsp_port}/{self.transport}/{self.stream}"
        )

    @property
    def masked_rtsp_url(self) -> str:
        return self.rtsp_url.replace(self.password, "***") if self.password else self.rtsp_url


@dataclass
class ViewerConfig:
    listen_host: str
    listen_port: int
    jpeg_quality: int
    frame_interval_seconds: float
    log_dir: str
    auth_enabled: bool
    auth_username: str
    auth_password: str


@dataclass
class RuntimeConfig:
    camera: CameraConfig
    viewer: ViewerConfig


def load_runtime_config(path: Path) -> RuntimeConfig:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    camera = raw.get("camera", {})
    viewer = raw.get("viewer", {})
    return RuntimeConfig(
        camera=CameraConfig(
            host=str(camera.get("host", "192.168.8.248")),
            username=str(camera.get("username", "admin")),
            password=str(camera.get("password", "admin")),
            rtsp_port=int(camera.get("rtsp_port", 554)),
            transport=str(camera.get("transport", "tcp")),
            stream=str(camera.get("stream", "av0_1")),
        ),
        viewer=ViewerConfig(
            listen_host=str(viewer.get("listen_host", "127.0.0.1")),
            listen_port=int(viewer.get("listen_port", 8090)),
            jpeg_quality=int(viewer.get("jpeg_quality", 80)),
            frame_interval_seconds=float(viewer.get("frame_interval_seconds", 0.08)),
            log_dir=str(viewer.get("log_dir", "runtime_logs")),
            auth_enabled=bool(viewer.get("auth_enabled", False)),
            auth_username=str(viewer.get("auth_username", "camera")),
            auth_password=str(viewer.get("auth_password", "camera")),
        ),
    )

