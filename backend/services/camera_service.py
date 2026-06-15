from __future__ import annotations

import os
import socket
import subprocess
import struct
import sys
import time
import xml.etree.ElementTree as ET
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Generator
from urllib.parse import quote

import requests

from backend.config import Settings


@dataclass(frozen=True)
class CameraStatus:
    configured: bool
    online: bool
    ip: str
    port: int
    path: str
    checked_at: datetime
    latency_ms: float | None = None
    error: str | None = None
    source: str = "rtsp"
    detail: str | None = None


@dataclass(frozen=True)
class CameraAudioStatus:
    configured: bool
    listen_supported: bool
    talk_supported: bool
    checked_url: str | None = None
    audio_codec: str | None = None
    sample_rate: int | None = None
    channels: int | None = None
    source: str = "rtsp"
    sdk_available: bool = False
    sdk_arch: str | None = None
    sdk_loadable: bool = False
    sdk_message: str | None = None
    gateway_configured: bool = False
    activex_available: bool = False
    activex_clsid: str | None = None
    activex_inproc_path: str | None = None
    activex_message: str | None = None
    error: str | None = None


class CameraService:
    _PE_MACHINE_TYPES = {
        0x014C: "x86",
        0x8664: "x64",
        0x01C0: "ARM",
        0x01C4: "ARMv7",
        0xAA64: "ARM64",
    }
    _PROFILE_TOKEN_CACHE: dict[tuple[str, int], str] = {}
    _PTZ_DIRECTIONS = {
        "up": (0.0, 1.0, 0.0),
        "down": (0.0, -1.0, 0.0),
        "left": (-1.0, 0.0, 0.0),
        "right": (1.0, 0.0, 0.0),
        "up_left": (-1.0, 1.0, 0.0),
        "up_right": (1.0, 1.0, 0.0),
        "down_left": (-1.0, -1.0, 0.0),
        "down_right": (1.0, -1.0, 0.0),
        "zoom_in": (0.0, 0.0, 1.0),
        "zoom_out": (0.0, 0.0, -1.0),
    }

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # 优化1: HTTP Session连接池 - 复用连接，减少TCP握手开销
        self._http_session = requests.Session()
        # 配置连接池：最大10个连接，每个主机最大5个连接
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=1,
            pool_block=False
        )
        self._http_session.mount('http://', adapter)
        self._http_session.mount('https://', adapter)
        # 设置默认超时
        self._http_session.timeout = max(2.0, settings.camera_probe_timeout_seconds)
        runtime_base_url = (
            os.environ.get("CAMERA_RUNTIME_BASE_URL", "").strip()
            or getattr(settings, "camera_runtime_base_url", "").strip()
            or settings.camera_local_http_url.strip()
            or "http://127.0.0.1:8090"
        ).rstrip("/")
        self._runtime_base_url = runtime_base_url
        self._runtime_health_url = f"{runtime_base_url}/api/v1/camera/health"
        self._runtime_snapshot_url = f"{runtime_base_url}/api/v1/camera/snapshot"
        self._runtime_mjpeg_url = f"{runtime_base_url}/api/v1/camera/stream.mjpg"
        self._runtime_status_url = f"{runtime_base_url}/status"

    @property
    def configured(self) -> bool:
        source_mode = self._settings.camera_source_mode
        if source_mode == "local":
            return True
        if source_mode == "auto":
            return self._rtsp_configured or self._settings.camera_local_index >= 0
        return self._rtsp_configured

    @property
    def _rtsp_configured(self) -> bool:
        return bool(
            self._settings.camera_ip.strip()
            and self._settings.camera_user.strip()
            and self._settings.camera_password
            and self._settings.camera_rtsp_port > 0
        )

    def resolved_source_mode(self) -> str:
        mode = self._settings.camera_source_mode
        if mode != "auto":
            return mode
        if self.uses_runtime_managed_source():
            return "rtsp"
        if self._rtsp_target_is_local_machine():
            return "local"
        if self._rtsp_configured:
            return "rtsp"
        return "local"

    def uses_runtime_managed_source(self) -> bool:
        if getattr(self._settings, "vision_service_poll_enabled", False):
            return False
        host = self._settings.camera_ip.strip()
        return bool(host == "192.168.8.253")

    @property
    def runtime_mjpeg_url(self) -> str:
        return self._runtime_mjpeg_url

    @property
    def runtime_snapshot_url(self) -> str:
        return self._runtime_snapshot_url

    def capture_runtime_jpeg_fast(self, *, timeout_seconds: float = 0.8) -> tuple[bytes, dict[str, str]]:
        """Return the latest frame from the external runtime without RTSP fallback.

        The runtime already owns the RTSP connection and keeps the latest JPEG
        in memory. Public API routes use this as a hard fast path so a mobile
        snapshot request cannot fall through into slow OpenCV/ffmpeg probing.
        """
        if not self.uses_runtime_managed_source():
            raise RuntimeError("RUNTIME_SOURCE_NOT_ACTIVE")

        timeout = max(0.25, min(float(timeout_seconds), 1.5))
        response = requests.get(
            self._runtime_snapshot_url,
            timeout=timeout,
            headers={"Cache-Control": "no-cache"},
        )
        response.raise_for_status()
        content = response.content
        if not content.startswith(b"\xff\xd8") or len(content) <= 1000:
            raise RuntimeError("RUNTIME_SNAPSHOT_INVALID")
        headers = {
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "X-Camera-Source": "runtime-snapshot-fast-proxy",
        }
        frame_age = response.headers.get("X-Frame-Age-Seconds")
        if frame_age:
            headers["X-Frame-Age-Seconds"] = frame_age
        frame_at = response.headers.get("X-Frame-Timestamp")
        if frame_at:
            headers["X-Frame-Timestamp"] = frame_at
        return content, headers

    def runtime_health(self) -> dict[str, Any] | None:
        if not self.uses_runtime_managed_source():
            return None
        try:
            response = self._http_session.get(
                self._runtime_health_url,
                timeout=max(1.0, self._settings.camera_probe_timeout_seconds),
            )
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else None
        except Exception:
            pass

        try:
            response = self._http_session.get(
                self._runtime_status_url,
                timeout=max(1.0, self._settings.camera_probe_timeout_seconds),
            )
            response.raise_for_status()
            payload = response.json()
            return self._normalize_vision_service_status(payload) if isinstance(payload, dict) else None
        except Exception:
            return None

    def _normalize_vision_service_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        stream = payload.get("main_stream")
        if not isinstance(stream, dict):
            stream = payload.get("analysis_stream")
        if not isinstance(stream, dict):
            cameras = payload.get("cameras")
            stream = cameras[0] if isinstance(cameras, list) and cameras and isinstance(cameras[0], dict) else {}

        service_state = str(payload.get("service_state") or payload.get("service_status") or "unknown")
        connected = bool(stream.get("connected"))
        frame_age_ms = stream.get("frame_age_ms")
        has_frame = connected and frame_age_ms is not None
        last_error = str(stream.get("last_error") or "").strip() or None
        if not last_error and not has_frame:
            last_error = service_state

        return {
            "has_frame": has_frame,
            "frame_age_ms": frame_age_ms,
            "capture_fps": stream.get("capture_fps"),
            "last_error": last_error,
            "stream_state": stream.get("stream_state") or service_state,
            "bridge_latency_ms": 0.0,
            "runtime_kind": "vision_service",
            "detail_url": self._runtime_status_url,
        }

    def can_use_local_camera_fallback(self) -> bool:
        return self._settings.camera_source_mode in {"auto", "local"} and self._settings.camera_local_index >= 0

    def should_fail_closed_on_rtsp_errors(self) -> bool:
        return self._rtsp_configured and self.resolved_source_mode() == "rtsp"

    @property
    def rtsp_url(self) -> str:
        return self._build_rtsp_url(self._settings.camera_rtsp_path, self._settings.camera_rtsp_port)

    def build_audio_rtsp_url(self) -> str:
        return self._build_rtsp_url(self._settings.camera_audio_rtsp_path, self._settings.camera_rtsp_port)

    @property
    def fallback_rtsp_urls(self) -> list[str]:
        configured_path = self._normalize_path(self._settings.camera_rtsp_path)
        configured_stream_path = self._normalize_path(self._settings.camera_stream_rtsp_path)
        quality_path = self._normalize_path(self._settings.camera_stream_quality_path)
        smooth_path = self._normalize_path(self._settings.camera_stream_smooth_path)
        candidates = [
            (configured_path, self._settings.camera_rtsp_port),
            (configured_stream_path, self._settings.camera_rtsp_port),
            (quality_path, self._settings.camera_rtsp_port),
            (smooth_path, self._settings.camera_rtsp_port),
            ("/udp/av0_0", self._settings.camera_rtsp_port),
            ("/udp/av0_1", self._settings.camera_rtsp_port),
        ]
        urls: list[str] = []
        for path, port in candidates:
            url = self._build_rtsp_url(path, port)
            if url not in urls:
                urls.append(url)
        return urls

    @property
    def stream_rtsp_urls(self) -> list[str]:
        configured_path = self._normalize_path(self._settings.camera_stream_rtsp_path)
        smooth_path = self._normalize_path(self._settings.camera_stream_smooth_path)
        quality_path = self._normalize_path(self._settings.camera_stream_quality_path)

        if self._settings.camera_stream_profile == "quality":
            preferred_paths = [quality_path, configured_path, smooth_path]
        elif self._settings.camera_stream_profile == "smooth":
            preferred_paths = [smooth_path, configured_path, quality_path]
        else:
            preferred_paths = [configured_path, smooth_path, quality_path]

        candidates = [(path, self._settings.camera_rtsp_port) for path in preferred_paths] + [
            ("/udp/av0_0", 10554),
            ("/udp/av0_1", 10554),
            ("/tcp/av0_1", 10554),
            ("/tcp/av0_0", 10554),
        ]
        urls: list[str] = []
        for path, port in candidates:
            url = self._build_rtsp_url(path, port)
            if url not in urls:
                urls.append(url)
        return urls

    def _build_rtsp_url(self, path: str, port: int) -> str:
        user = quote(self._settings.camera_user.strip(), safe="")
        password = quote(self._settings.camera_password, safe="")
        normalized_path = self._normalize_path(path)
        return f"rtsp://{user}:{password}@{self._settings.camera_ip.strip()}:{port}{normalized_path}"

    def check_status(self) -> CameraStatus:
        checked_at = datetime.now(timezone.utc)
        ip = self._settings.camera_ip.strip()
        port = self._settings.camera_rtsp_port
        path = self._normalize_path(self._settings.camera_rtsp_path)
        source_mode = self.resolved_source_mode()

        if source_mode == "local":
            return self._check_local_camera_status(checked_at)

        if not self._rtsp_configured:
            if self.can_use_local_camera_fallback():
                return self._check_local_camera_status(checked_at)
            return CameraStatus(
                configured=False,
                online=False,
                ip=ip,
                port=port,
                path=path,
                checked_at=checked_at,
                error="CAMERA_NOT_CONFIGURED",
                source="rtsp",
            )

        if self.uses_runtime_managed_source():
            runtime = self.runtime_health()
            if runtime is not None:
                has_frame = bool(runtime.get("has_frame"))
                last_error = str(runtime.get("last_error") or "").strip() or None
                status_error = None if has_frame else (last_error or "RUNTIME_NO_FRAME")
                return CameraStatus(
                    configured=True,
                    online=has_frame,
                    ip=ip,
                    port=port,
                    path=path,
                    checked_at=checked_at,
                    latency_ms=round(float(runtime.get("bridge_latency_ms") or 0.0), 2),
                    error=status_error,
                    source="rtsp",
                    detail=f"runtime-proxy -> {runtime.get('detail_url') or self._runtime_mjpeg_url}",
                )

        started = time.perf_counter()
        try:
            with socket.create_connection((ip, port), timeout=self._settings.camera_probe_timeout_seconds):
                latency_ms = (time.perf_counter() - started) * 1000
            return CameraStatus(
                configured=True,
                online=True,
                ip=ip,
                port=port,
                path=path,
                checked_at=checked_at,
                latency_ms=round(latency_ms, 2),
                source="rtsp",
                detail=f"RTSP {ip}:{port}{path}",
            )
        except OSError as exc:
            if self.can_use_local_camera_fallback() and not self.should_fail_closed_on_rtsp_errors():
                local_status = self._check_local_camera_status(checked_at, rtsp_error=f"{exc.__class__.__name__}: {exc}")
                if local_status.online:
                    return local_status
            return CameraStatus(
                configured=True,
                online=False,
                ip=ip,
                port=port,
                path=path,
                checked_at=checked_at,
                error=f"{exc.__class__.__name__}: {exc}",
                source="rtsp",
            )

    def check_audio_status(self) -> CameraAudioStatus:
        source_mode = self.resolved_source_mode()
        if source_mode == "local":
            return CameraAudioStatus(
                configured=True,
                listen_supported=False,
                talk_supported=False,
                source="local",
                error="LOCAL_CAMERA_AUDIO_UNSUPPORTED",
            )

        if not self._rtsp_configured:
            return CameraAudioStatus(
                configured=False,
                listen_supported=False,
                talk_supported=False,
                source="rtsp",
                error="CAMERA_NOT_CONFIGURED",
            )

        try:
            status = self._probe_rtsp_audio()
        except Exception as exc:  # noqa: BLE001
            status = CameraAudioStatus(
                configured=True,
                listen_supported=False,
                talk_supported=False,
                source="rtsp",
                error=f"{exc.__class__.__name__}: {exc}",
            )
        sdk_fields = self._probe_audio_sdk_fields()
        activex_fields = self._probe_activex_fields()
        fields = {**status.__dict__, **sdk_fields, **activex_fields}
        fields["talk_supported"] = bool(
            fields.get("talk_supported")
            or fields.get("gateway_configured")
            or fields.get("activex_available")
        )
        return CameraAudioStatus(**fields)

    def capture_jpeg(self) -> tuple[bytes, dict[str, str]]:
        source_mode = self.resolved_source_mode()
        if source_mode == "local":
            return self.capture_local_jpeg()

        if not self._rtsp_configured:
            if self.can_use_local_camera_fallback():
                return self.capture_local_jpeg()
            raise RuntimeError("CAMERA_NOT_CONFIGURED")

        if self.uses_runtime_managed_source():
            return self.capture_runtime_jpeg_fast(timeout_seconds=0.8)

        if source_mode == "rtsp":
            try:
                return self._capture_jpeg_with_opencv()
            except RuntimeError as rtsp_error:
                image_bytes = self._capture_jpeg_with_ffmpeg()
                if image_bytes:
                    return image_bytes, {"Cache-Control": "no-store, max-age=0"}
                try:
                    return self._capture_jpeg_via_http()
                except RuntimeError:
                    pass
                raise rtsp_error

        # 优化：先尝试HTTP快照（P2P摄像头的最佳方式）
        try:
            return self._capture_jpeg_via_http()
        except RuntimeError:
            pass  # HTTP失败，继续尝试RTSP

        try:
            return self._capture_jpeg_with_opencv()
        except RuntimeError as rtsp_error:
            image_bytes = self._capture_jpeg_with_ffmpeg()
            if image_bytes:
                return image_bytes, {"Cache-Control": "no-store, max-age=0"}
            if self.can_use_local_camera_fallback() and not self.should_fail_closed_on_rtsp_errors():
                try:
                    return self.capture_local_jpeg()
                except RuntimeError:
                    raise rtsp_error

        raise RuntimeError("CAMERA_FRAME_READ_TIMEOUT")

    def capture_local_jpeg(self) -> tuple[bytes, dict[str, str]]:
        # 优先使用HTTP快照服务（独立进程，避免OpenCV异步问题）
        local_http_url = getattr(self._settings, 'camera_local_http_url', '').strip()
        if local_http_url:
            try:
                response = self._http_session.get(
                    f"{local_http_url}/snapshot",
                    timeout=max(2.0, self._settings.camera_snapshot_timeout_seconds)
                )
                if response.status_code == 200:
                    content = response.content
                    if content.startswith(b"\xff\xd8") and len(content) > 1000:
                        headers = {
                            "Cache-Control": "no-store, max-age=0",
                            "X-Camera-Source": "local-http",
                        }
                        return content, headers
            except Exception:
                pass  # 失败则继续尝试直接访问
        
        # 回退到直接访问摄像头
        return self._capture_local_jpeg_subprocess()

    def _capture_local_jpeg_subprocess(self) -> tuple[bytes, dict[str, str]]:
        script = r"""
import sys
import time
import cv2
import numpy as np

index = int(sys.argv[1])
preferred = (sys.argv[2] if len(sys.argv) > 2 else "any").strip().lower()

backend_map = {
    "dshow": getattr(cv2, "CAP_DSHOW", getattr(cv2, "CAP_ANY", 0)),
    "any": getattr(cv2, "CAP_ANY", 0),
    "msmf": getattr(cv2, "CAP_MSMF", getattr(cv2, "CAP_ANY", 0)),
}
backend_order = []
for name in (preferred, "dshow", "any", "msmf"):
    if name in backend_map and name not in backend_order:
        backend_order.append(name)

frame = None
selected_backend = None
last_error = "Frame read failed"
for backend_name in backend_order:
    cap = cv2.VideoCapture(index, backend_map[backend_name])
    try:
        if not cap.isOpened():
            last_error = f"{backend_name}: Camera not opened"
            continue
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        deadline = time.monotonic() + 2.8
        while time.monotonic() < deadline:
            ok, candidate = cap.read()
            if not ok or candidate is None:
                time.sleep(0.04)
                continue
            gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
            mean = float(np.mean(gray))
            std = float(np.std(gray))
            if mean >= 8.0 and std >= 6.0:
                frame = candidate
                selected_backend = backend_name
                break
            time.sleep(0.04)
        if frame is not None:
            break
        last_error = f"{backend_name}: Frame read failed"
    finally:
        cap.release()

if frame is None:
    raise RuntimeError(last_error)

ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 86])
if not ok:
    raise RuntimeError("JPEG encode failed")
height, width = frame.shape[:2]
print(f"BACKEND={selected_backend or 'unknown'} WIDTH={width} HEIGHT={height}", file=sys.stderr)
sys.stdout.buffer.write(encoded.tobytes())
"""
        timeout = max(3.0, min(float(self._settings.camera_snapshot_timeout_seconds), 12.0))
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                script,
                str(self._settings.camera_local_index),
                str(self._settings.camera_local_backend or "any"),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        image = completed.stdout
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        if completed.returncode != 0 or not image.startswith(b"\xff\xd8") or len(image) < 1000:
            raise RuntimeError(f"LOCAL_CAMERA_CAPTURE_FAILED: {stderr or completed.returncode}")

        headers = {
            "Cache-Control": "no-store, max-age=0",
            "X-Camera-Source": "local-subprocess",
        }
        for part in stderr.split():
            if part.startswith("BACKEND="):
                headers["X-Camera-Backend"] = part.removeprefix("BACKEND=")
            if part.startswith("WIDTH="):
                headers["X-Camera-Width"] = part.removeprefix("WIDTH=")
            elif part.startswith("HEIGHT="):
                headers["X-Camera-Height"] = part.removeprefix("HEIGHT=")
        return image, headers

    def mjpeg_frames(self) -> Generator[bytes, None, None]:
        if not self.configured:
            raise RuntimeError("CAMERA_NOT_CONFIGURED")

        yield from self._mjpeg_frames_from_snapshots()

    def _mjpeg_frames_from_snapshots(self) -> Generator[bytes, None, None]:
        fps = max(0.2, min(self._settings.camera_stream_fps, 6.0))  # 提高上限到6fps
        frame_delay = 1.0 / fps
        while True:
            try:
                image, _headers = self.capture_jpeg()
                yield self._format_mjpeg_part(image)
            except RuntimeError:
                time.sleep(0.8)
                continue
            time.sleep(frame_delay)

    @staticmethod
    def _format_mjpeg_part(image: bytes) -> bytes:
        return (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n"
            + f"Content-Length: {len(image)}\r\n\r\n".encode("ascii")
            + image
            + b"\r\n"
        )

    def ptz_move(self, direction: str, mode: str = "pulse") -> dict[str, object]:
        if not self.configured:
            raise RuntimeError("CAMERA_NOT_CONFIGURED")

        normalized = direction.strip().lower().replace("-", "_")
        normalized_mode = mode.strip().lower()
        if normalized == "stop":
            profile_token = self._get_onvif_profile_token()
            self._onvif_stop(profile_token)
            return {"ok": True, "direction": normalized, "mode": normalized_mode}

        if normalized not in self._PTZ_DIRECTIONS:
            raise ValueError("CAMERA_PTZ_DIRECTION_INVALID")
        if normalized_mode not in {"pulse", "continuous"}:
            raise ValueError("CAMERA_PTZ_MODE_INVALID")

        profile_token = self._get_onvif_profile_token()
        pan, tilt, zoom = self._PTZ_DIRECTIONS[normalized]
        speed = max(0.05, min(abs(self._settings.camera_ptz_speed), 1.0))
        self._onvif_continuous_move(profile_token, pan * speed, tilt * speed, zoom * speed)
        if normalized_mode == "pulse":
            time.sleep(max(0.08, min(self._settings.camera_ptz_move_seconds, 1.5)))
            self._onvif_stop(profile_token)
        return {"ok": True, "direction": normalized, "mode": normalized_mode}

    def _get_onvif_profile_token(self) -> str:
        cache_key = (self._settings.camera_ip.strip(), self._settings.camera_onvif_port)
        cached = self._PROFILE_TOKEN_CACHE.get(cache_key)
        if cached:
            return cached

        body = """
        <trt:GetProfiles xmlns:trt="http://www.onvif.org/ver10/media/wsdl" />
        """
        xml_text = self._post_onvif("/onvif/media_service", body)
        root = ET.fromstring(xml_text)
        namespace = {"trt": "http://www.onvif.org/ver10/media/wsdl"}
        profile = root.find(".//trt:Profiles", namespace)
        token = profile.attrib.get("token") if profile is not None else None
        if not token:
            raise RuntimeError("CAMERA_ONVIF_PROFILE_NOT_FOUND")
        self._PROFILE_TOKEN_CACHE[cache_key] = token
        return token

    def _onvif_continuous_move(self, profile_token: str, pan: float, tilt: float, zoom: float) -> None:
        body = f"""
        <tptz:ContinuousMove xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">
          <tptz:ProfileToken>{profile_token}</tptz:ProfileToken>
          <tptz:Velocity>
            <tt:PanTilt x="{pan:.3f}" y="{tilt:.3f}" />
            <tt:Zoom x="{zoom:.3f}" />
          </tptz:Velocity>
        </tptz:ContinuousMove>
        """
        self._post_onvif("/onvif/ptz_service", body)

    def _onvif_stop(self, profile_token: str) -> None:
        body = f"""
        <tptz:Stop xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl">
          <tptz:ProfileToken>{profile_token}</tptz:ProfileToken>
          <tptz:PanTilt>true</tptz:PanTilt>
          <tptz:Zoom>true</tptz:Zoom>
        </tptz:Stop>
        """
        self._post_onvif("/onvif/ptz_service", body)

    def _post_onvif(self, path: str, body: str) -> str:
        envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
        <s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
          <s:Body>{body}</s:Body>
        </s:Envelope>
        """
        url = f"http://{self._settings.camera_ip.strip()}:{self._settings.camera_onvif_port}{path}"
        # 优化: 使用Session连接池
        response = self._http_session.post(
            url,
            data=envelope.encode("utf-8"),
            headers={"Content-Type": "application/soap+xml; charset=utf-8"},
            timeout=max(2.0, self._settings.camera_probe_timeout_seconds),
        )
        if response.status_code >= 400:
            raise RuntimeError(f"CAMERA_ONVIF_HTTP_{response.status_code}")
        return response.text

    def _capture_jpeg_via_http(self) -> tuple[bytes, dict[str, str]]:
        """
        通过HTTP接口获取快照（适用于P2P摄像头）
        尝试多个常见的HTTP快照路径
        """
        ip = self._settings.camera_ip.strip()
        user = self._settings.camera_user.strip()
        password = self._settings.camera_password
        timeout = max(2.0, self._settings.camera_snapshot_timeout_seconds)
        
        # 常见的HTTP快照路径
        snapshot_urls = [
            # ONVIF标准快照
            f"http://{ip}:{self._settings.camera_onvif_port}/onvif/snapshot",
            f"http://{ip}:{self._settings.camera_onvif_port}/onvif-http/snapshot",
            # 通用CGI路径
            f"http://{ip}/cgi-bin/snapshot.cgi",
            f"http://{ip}/snapshot.jpg",
            f"http://{ip}/image/jpeg.cgi",
            f"http://{ip}/tmpfs/auto.jpg",
            # 带认证的路径
            f"http://{ip}/cgi-bin/api.cgi?cmd=Snap&channel=0&user={user}&password={password}",
            # 其他常见路径
            f"http://{ip}:{self._settings.camera_onvif_port}/snapshot.jpg",
            f"http://{ip}:{self._settings.camera_rtsp_port}/snapshot.jpg",
        ]
        
        last_error = ""
        for url in snapshot_urls:
            try:
                # 使用Session连接池
                response = self._http_session.get(
                    url,
                    auth=(user, password) if user and password else None,
                    timeout=timeout,
                    allow_redirects=True,
                )
                
                if response.status_code == 200:
                    content = response.content
                    # 验证是否为有效的JPEG
                    if content.startswith(b"\xff\xd8") and len(content) > 1000:
                        headers = {
                            "Cache-Control": "no-store, max-age=0",
                            "X-Camera-Source": "http-snapshot",
                        }
                        return content, headers
                        
            except Exception as exc:
                last_error = f"{exc.__class__.__name__}: {exc}"
                continue
        
        raise RuntimeError(f"HTTP_SNAPSHOT_FAILED: {last_error}")

    def _capture_jpeg_with_ffmpeg(self) -> bytes | None:
        try:
            import imageio_ffmpeg
        except ImportError:
            return None

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        for url in self.fallback_rtsp_urls:
            transport = self._rtsp_transport_for_url(url)
            cmd = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-rtsp_transport",
                transport,
                "-timeout",
                str(int(self._settings.camera_snapshot_timeout_seconds * 1_000_000)),
                "-i",
                url,
                "-frames:v",
                "1",
                "-f",
                "image2pipe",
                "-vcodec",
                "mjpeg",
                "-",
            ]
            try:
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=self._settings.camera_snapshot_timeout_seconds + 4,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                continue

            if result.returncode == 0 and result.stdout.startswith(b"\xff\xd8"):
                return result.stdout

        return None

    def _capture_jpeg_with_opencv(self) -> tuple[bytes, dict[str, str]]:
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("OPENCV_NOT_INSTALLED") from exc

        frame = None
        previous_options = os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS")
        # 优化3: OpenCV优化配置 - 减少延迟，提高响应速度
        for url in self.fallback_rtsp_urls:
            transport = self._rtsp_transport_for_url(url)
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                f"rtsp_transport;{transport}|stimeout;5000000|max_delay;0|fflags;nobuffer|flags;low_delay"
            )
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            # 优化: 设置缓冲区大小为1，减少延迟
            with suppress(Exception):
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            # 优化: 设置FPS以提高捕获速度
            with suppress(Exception):
                cap.set(cv2.CAP_PROP_FPS, 30)
            if not cap.isOpened():
                cap.release()
                continue

            deadline = time.monotonic() + self._settings.camera_snapshot_timeout_seconds
            try:
                while time.monotonic() < deadline:
                    ok, candidate = cap.read()
                    if ok and candidate is not None:
                        frame = candidate
                        break
            finally:
                cap.release()

            if frame is not None:
                break
        if previous_options is None:
            os.environ.pop("OPENCV_FFMPEG_CAPTURE_OPTIONS", None)
        else:
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = previous_options

        if frame is None:
            raise RuntimeError("CAMERA_FRAME_READ_TIMEOUT")

        return self._encode_frame_to_jpeg(frame)

    def _probe_rtsp_audio(self) -> CameraAudioStatus:
        try:
            import imageio_ffmpeg
        except ImportError as exc:
            raise RuntimeError("IMAGEIO_FFMPEG_NOT_INSTALLED") from exc

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        last_error = ""
        timeout_seconds = max(2.0, min(self._settings.camera_probe_timeout_seconds, 5.0))
        audio_url = self.build_audio_rtsp_url()
        urls = [audio_url]
        urls.extend(url for url in self.stream_rtsp_urls[:2] if url not in urls)
        for url in urls:
            transport = self._rtsp_transport_for_url(url)
            cmd = [
                ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-rtsp_transport",
                transport,
                "-timeout",
                str(int(timeout_seconds * 1_000_000)),
                "-probesize",
                "5000000",
                "-i",
                url,
                "-t",
                "1",
                "-vn",
                "-f",
                "null",
                "-",
            ]
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds + 3,
                check=False,
            )
            output = self._mask_url(result.stderr.decode("utf-8", errors="replace")) or ""
            audio_line = self._find_ffmpeg_audio_line(output)
            if audio_line:
                codec, sample_rate, channels = self._parse_ffmpeg_audio_line(audio_line)
                return CameraAudioStatus(
                    configured=True,
                    listen_supported=True,
                    talk_supported=False,
                    checked_url=self._mask_url(url),
                    audio_codec=codec,
                    sample_rate=sample_rate,
                    channels=channels,
                    source="rtsp",
                )
            last_error = output.strip()

        return CameraAudioStatus(
            configured=True,
            listen_supported=False,
            talk_supported=False,
            checked_url=self._mask_url(urls[0]) if urls else None,
            source="rtsp",
            error=(last_error[-500:] if last_error else "CAMERA_AUDIO_TRACK_NOT_FOUND"),
        )

    def _probe_audio_sdk_fields(self) -> dict[str, object]:
        from pathlib import Path

        gateway_url = self._settings.camera_audio_gateway_url.strip()
        configured_dir = self._settings.camera_sdk_dll_dir.strip()
        default_dir = (
            Path(__file__).resolve().parents[2]
            / "摄像头说明书"
            / "extracted"
            / "SDK_phone (2)"
            / "SDK_phone"
            / "Lib"
            / "win32"
        )
        sdk_dir = Path(configured_dir) if configured_dir else default_dir
        dll = sdk_dir / "P2PAPI.dll"
        fields: dict[str, object] = {
            "sdk_available": dll.exists(),
            "sdk_arch": None,
            "sdk_loadable": False,
            "sdk_message": None,
            "gateway_configured": bool(gateway_url),
        }
        if not dll.exists():
            fields["sdk_message"] = f"SDK_DLL_NOT_FOUND: {dll}"
            return fields

        arch = self._read_pe_machine(dll)
        python_arch = f"{struct.calcsize('P') * 8}-bit"
        fields["sdk_arch"] = arch
        if arch == "x86" and struct.calcsize("P") == 8:
            fields["sdk_message"] = "SDK_DLL_X86_WITH_64BIT_BACKEND: use 32-bit gateway process or request x64 SDK"
            return fields

        try:
            import ctypes

            ctypes.WinDLL(str(dll))
            fields["sdk_loadable"] = True
            fields["sdk_message"] = f"SDK_LOADABLE_WITH_{python_arch}_PYTHON"
        except OSError as exc:
            fields["sdk_message"] = f"{exc.__class__.__name__}: {exc}"
        return fields

    def _probe_activex_fields(self) -> dict[str, object]:
        clsid = self._settings.camera_activex_clsid.strip().strip("{}")
        fields: dict[str, object] = {
            "activex_available": False,
            "activex_clsid": clsid or None,
            "activex_inproc_path": None,
            "activex_message": None,
        }
        if not clsid:
            fields["activex_message"] = "ACTIVEX_CLSID_NOT_CONFIGURED"
            return fields

        try:
            import winreg
        except ImportError:
            fields["activex_message"] = "ACTIVEX_WINDOWS_ONLY"
            return fields

        registry_path = f"CLSID\\{{{clsid}}}\\InprocServer32"
        registry_views = [
            ("64-bit", getattr(winreg, "KEY_WOW64_64KEY", 0)),
            ("32-bit", getattr(winreg, "KEY_WOW64_32KEY", 0)),
            ("default", 0),
        ]
        checked: list[str] = []
        for view_name, view_flag in registry_views:
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, registry_path, 0, winreg.KEY_READ | view_flag) as key:
                    value, _value_type = winreg.QueryValueEx(key, "")
                    fields["activex_available"] = True
                    fields["activex_inproc_path"] = str(value)
                    fields["activex_message"] = f"ACTIVEX_REGISTERED_{view_name.upper()}"
                    return fields
            except OSError as exc:
                checked.append(f"{view_name}: {exc.winerror if hasattr(exc, 'winerror') else exc}")

        fields["activex_message"] = "ACTIVEX_NOT_REGISTERED: " + "; ".join(checked)
        return fields

    def _capture_local_frame(self) -> Any:
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("OPENCV_NOT_INSTALLED") from exc

        # 尝试多种后端，解决异步环境下的OpenCV问题
        backends = self._local_camera_backends(cv2)
        
        last_error = ""
        for backend_name, backend in backends:
            try:
                cap = cv2.VideoCapture(self._settings.camera_local_index, backend)
                try:
                    if not cap.isOpened():
                        last_error = f"{backend_name}: Camera not opened"
                        continue
                    
                    # 设置较短的超时
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    
                    # 尝试读取帧
                    deadline = time.monotonic() + max(1.5, min(self._settings.camera_snapshot_timeout_seconds, 4.0))
                    while time.monotonic() < deadline:
                        ok, frame = cap.read()
                        if ok and frame is not None and self.is_usable_local_frame(frame):
                            return frame
                        time.sleep(0.04)
                    
                    last_error = f"{backend_name}: Frame read failed"
                finally:
                    cap.release()
            except Exception as exc:
                last_error = f"{backend_name}: {exc.__class__.__name__}: {exc}"
                continue
        
        raise RuntimeError(f"LOCAL_CAMERA_ALL_BACKENDS_FAILED: {last_error}")

    @staticmethod
    def is_usable_local_frame(frame: Any) -> bool:
        try:
            import cv2
            import numpy as np
        except ImportError:
            return True

        if frame is None:
            return False
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            return float(np.mean(gray)) >= 8.0 and float(np.std(gray)) >= 6.0
        except Exception:
            return False

    def _encode_frame_to_jpeg(self, frame: Any) -> tuple[bytes, dict[str, str]]:
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("OPENCV_NOT_INSTALLED") from exc

        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 86])
        if not ok:
            raise RuntimeError("CAMERA_JPEG_ENCODE_FAILED")

        height, width = frame.shape[:2]
        headers = {
            "Cache-Control": "no-store, max-age=0",
            "X-Camera-Width": str(width),
            "X-Camera-Height": str(height),
        }
        return encoded.tobytes(), headers

    def local_source_label(self) -> str:
        backend = self._settings.camera_local_backend.upper()
        return f"local://camera/{self._settings.camera_local_index}?backend={backend}"

    def _check_local_camera_status(self, checked_at: datetime, rtsp_error: str | None = None) -> CameraStatus:
        if self._settings.camera_source_mode == "local" and rtsp_error is None:
            return CameraStatus(
                configured=True,
                online=True,
                ip="local",
                port=0,
                path=f"/camera/{self._settings.camera_local_index}",
                checked_at=checked_at,
                latency_ms=0.0,
                source="local",
                detail=(
                    "Browser local camera preview is active; backend OpenCV "
                    "probing is skipped to avoid device contention"
                ),
            )

        started = time.perf_counter()
        try:
            frame = self._capture_local_frame()
            latency_ms = (time.perf_counter() - started) * 1000
            height, width = frame.shape[:2]
            detail = f"Local camera #{self._settings.camera_local_index} ({width}x{height})"
            if rtsp_error:
                detail = f"{detail}; RTSP unavailable, using local fallback"
            return CameraStatus(
                configured=True,
                online=True,
                ip="local",
                port=0,
                path=f"/camera/{self._settings.camera_local_index}",
                checked_at=checked_at,
                latency_ms=round(latency_ms, 2),
                source="local",
                detail=detail,
            )
        except RuntimeError as exc:
            return CameraStatus(
                configured=True,
                online=False,
                ip="local",
                port=0,
                path=f"/camera/{self._settings.camera_local_index}",
                checked_at=checked_at,
                error=str(exc) if not rtsp_error else f"{rtsp_error}; local fallback failed: {exc}",
                source="local",
                detail=f"Local camera #{self._settings.camera_local_index}",
            )

    def _rtsp_target_is_local_machine(self) -> bool:
        ip = self._settings.camera_ip.strip().lower()
        if not ip:
            return False
        return ip in self._local_host_addresses()

    def _local_host_addresses(self) -> set[str]:
        addresses = {"127.0.0.1", "localhost", "::1"}
        with suppress(OSError):
            hostname = socket.gethostname()
            addresses.add(hostname.lower())
            for ip in socket.gethostbyname_ex(hostname)[2]:
                if ip:
                    addresses.add(ip.lower())
        return addresses

    def _local_camera_backends(self, cv2_module: Any) -> list[tuple[str, int]]:
        preferred = self._settings.camera_local_backend
        candidates: list[tuple[str, int]] = []

        def add(name: str, backend: int) -> None:
            item = (name, backend)
            if item not in candidates:
                candidates.append(item)

        if preferred == "dshow":
            add("dshow", cv2_module.CAP_DSHOW)
        elif preferred == "msmf":
            add("msmf", cv2_module.CAP_MSMF)

        if preferred in {"auto", "any"}:
            add("dshow", cv2_module.CAP_DSHOW)
            add("any", cv2_module.CAP_ANY)
            add("msmf", cv2_module.CAP_MSMF)
        else:
            add("dshow", cv2_module.CAP_DSHOW)
            add("any", cv2_module.CAP_ANY)
            add("msmf", cv2_module.CAP_MSMF)

        return candidates

    def _mask_url(self, url: str | None) -> str | None:
        if not url:
            return None
        password = self._settings.camera_password
        return url.replace(password, "***") if password else url

    @staticmethod
    def _find_ffmpeg_audio_line(output: str) -> str | None:
        for line in output.splitlines():
            if " Audio: " in line:
                return line.strip()
        return None

    @staticmethod
    def _parse_ffmpeg_audio_line(line: str) -> tuple[str | None, int | None, int | None]:
        codec = None
        sample_rate = None
        channels = None
        marker = " Audio: "
        index = line.find(marker)
        if index >= 0:
            after = line[index + len(marker) :]
            codec = after.split(",", 1)[0].strip() or None

        for token in line.split(","):
            normalized = token.strip().lower()
            if normalized.endswith("hz"):
                digits = "".join(ch for ch in normalized if ch.isdigit())
                if digits:
                    sample_rate = int(digits)
            if "mono" in normalized:
                channels = 1
            elif "stereo" in normalized:
                channels = 2
        return codec, sample_rate, channels

    @classmethod
    def _read_pe_machine(cls, path: object) -> str | None:
        try:
            with open(path, "rb") as handle:
                handle.seek(0x3C)
                pe_offset = int.from_bytes(handle.read(4), "little")
                handle.seek(pe_offset + 4)
                machine = int.from_bytes(handle.read(2), "little")
        except OSError:
            return None
        return cls._PE_MACHINE_TYPES.get(machine, f"0x{machine:04X}")

    @staticmethod
    def _normalize_path(path: str) -> str:
        normalized = (path or "/tcp/av0_0").strip()
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        return normalized

    @staticmethod
    def _rtsp_transport_for_url(url: str) -> str:
        return "udp" if "/udp/" in url.lower() else "tcp"
