from __future__ import annotations

import logging
import socket
import subprocess
import threading
import time
from dataclasses import dataclass

import cv2

from .config import CameraConfig


logger = logging.getLogger(__name__)


@dataclass
class FrameSnapshot:
    latest_jpeg: bytes | None
    latest_frame_at: float | None
    frame_count: int
    last_error: str | None
    last_opened_at: float | None
    running: bool
    reconnect_count: int
    consecutive_failures: int
    current_stream: str


class FrameStore:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.latest_jpeg: bytes | None = None
        self.latest_frame_at: float | None = None
        self.frame_count = 0
        self.last_error: str | None = None
        self.running = False
        self.last_opened_at: float | None = None
        self.current_stream = "unknown"
        self.reconnect_count = 0
        self.consecutive_failures = 0

    def update(self, jpeg: bytes) -> None:
        with self.lock:
            self.latest_jpeg = jpeg
            self.latest_frame_at = time.time()
            self.frame_count += 1
            self.last_error = None
            self.consecutive_failures = 0

    def set_error(self, message: str) -> None:
        with self.lock:
            self.last_error = message
            self.consecutive_failures += 1
        logger.warning(message)

    def mark_opened(self, stream: str) -> None:
        with self.lock:
            self.last_opened_at = time.time()
            self.current_stream = stream
            self.reconnect_count += 1

    def snapshot(self) -> FrameSnapshot:
        with self.lock:
            return FrameSnapshot(
                latest_jpeg=self.latest_jpeg,
                latest_frame_at=self.latest_frame_at,
                frame_count=self.frame_count,
                last_error=self.last_error,
                last_opened_at=self.last_opened_at,
                running=self.running,
                reconnect_count=self.reconnect_count,
                consecutive_failures=self.consecutive_failures,
                current_stream=self.current_stream,
            )


class CameraRuntime:
    def __init__(
        self,
        camera_config: CameraConfig,
        jpeg_quality: int,
        frame_interval_seconds: float,
        viewer_auth_enabled: bool = False,
        viewer_auth_username: str = "camera",
        viewer_auth_password: str = "camera",
    ) -> None:
        self.camera_config = camera_config
        self.jpeg_quality = max(40, min(jpeg_quality, 95))
        self.frame_interval_seconds = max(0.02, frame_interval_seconds)
        self.viewer_auth_enabled = viewer_auth_enabled
        self.viewer_auth_username = viewer_auth_username
        self.viewer_auth_password = viewer_auth_password
        self.frame_store = FrameStore()
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._current_cap: cv2.VideoCapture | None = None
        self._cap_lock = threading.Lock()
        self._last_frame_monotonic = 0.0
        self._stall_timeout_seconds = max(8.0, self.frame_interval_seconds * 80.0)

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(target=self._capture_loop, daemon=True, name="camera-runtime")
        self._worker.start()
        logger.info("Camera runtime started for %s", self.camera_config.masked_rtsp_url)

    def stop(self) -> None:
        self._stop_event.set()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=2.0)
        logger.info("Camera runtime stopped")

    def switch_stream(self, stream: str) -> None:
        self.camera_config.stream = stream
        self._stop_event.set()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=2.0)
        self._stop_event = threading.Event()
        self.start()
        logger.info("Switched stream to %s", stream)

    def _capture_loop(self) -> None:
        self.frame_store.running = True
        while not self._stop_event.is_set():
            # Keep OpenCV as the primary path because this device/stream combo
            # is stable enough to recover, while direct FFmpeg MJPEG piping
            # ends immediately in current tests.
            self._capture_with_opencv()
            time.sleep(1.0)
        self.frame_store.running = False

    def _capture_with_opencv(self) -> None:
        logger.info("Using OpenCV capture path")
        reachable, reachability_error = self._rtsp_endpoint_reachable()
        if not reachable:
            self.frame_store.set_error(reachability_error or "RTSP endpoint is not reachable")
            time.sleep(2.0)
            return
        cap = cv2.VideoCapture(self.camera_config.rtsp_url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        with self._cap_lock:
            self._current_cap = cap
        if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
            try:
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 4000)
            except Exception:
                pass
        if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
            try:
                cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, int(self._stall_timeout_seconds * 1000))
            except Exception:
                pass
        if not cap.isOpened():
            with self._cap_lock:
                if self._current_cap is cap:
                    self._current_cap = None
            self.frame_store.set_error("Unable to open RTSP stream")
            time.sleep(2.0)
            return
        self.frame_store.mark_opened(self.camera_config.stream)
        self._last_frame_monotonic = time.monotonic()
        logger.info("Opened RTSP stream via OpenCV: %s", self.camera_config.masked_rtsp_url)
        try:
            empty_reads = 0
            while not self._stop_event.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    empty_reads += 1
                    if time.monotonic() - self._last_frame_monotonic > self._stall_timeout_seconds:
                        logger.info("RTSP stream frame watchdog timed out; reconnecting")
                        break
                    if empty_reads < 20:
                        time.sleep(0.1)
                        continue
                    if self.frame_store.snapshot().latest_jpeg is not None:
                        logger.info("RTSP stream read stalled; reconnecting")
                    else:
                        self.frame_store.set_error("Failed to read frame; reconnecting")
                    break
                empty_reads = 0
                encoded_ok, encoded = cv2.imencode(
                    ".jpg",
                    frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
                )
                if encoded_ok:
                    self.frame_store.update(encoded.tobytes())
                    self._last_frame_monotonic = time.monotonic()
                time.sleep(self.frame_interval_seconds)
        finally:
            with self._cap_lock:
                if self._current_cap is cap:
                    self._current_cap = None
            cap.release()

    def _rtsp_endpoint_reachable(self) -> tuple[bool, str | None]:
        endpoint = (self.camera_config.host, int(self.camera_config.rtsp_port))
        try:
            with socket.create_connection(endpoint, timeout=3.0):
                return True, None
        except OSError as exc:
            return (
                False,
                f"Configured RTSP endpoint {endpoint[0]}:{endpoint[1]} is not reachable from this computer: "
                f"{exc.__class__.__name__}: {exc}",
            )
