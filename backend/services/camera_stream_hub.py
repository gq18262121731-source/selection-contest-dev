from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, AsyncGenerator, Awaitable, Callable

from fastapi import WebSocket

from backend.config import Settings
from backend.services.camera_service import CameraService


logger = logging.getLogger(__name__)


class CameraFrameHub:
    """Single backend camera reader that fans frames out to many clients."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._clients: set[WebSocket] = set()
        self._mjpeg_clients = 0
        self._lock = asyncio.Lock()
        self._frame_event = asyncio.Event()
        self._capture_task: asyncio.Task[None] | None = None
        self._latest_frame: bytes | None = None
        self._latest_frame_at: float | None = None
        self._latest_frame_size = 0
        self._last_error: str | None = None
        self._frames_total = 0
        self._broadcast_total = 0
        self._fps_window_started_at = time.monotonic()
        self._fps_window_frames = 0
        self._source_fps = 0.0
        self._broadcast_fps = 0.0
        self._broadcast_window_started_at = time.monotonic()
        self._broadcast_window_frames = 0
        self._active_url: str | None = None
        self._keep_warm = False
        self._last_broadcasted_at = 0.0
        self._external_frames_active_until = 0.0
        # 优化2: 帧缓存机制 - 避免重复请求，提高响应速度
        self._frame_cache: dict[str, tuple[bytes, float]] = {}  # key: cache_key, value: (frame, timestamp)
        self._frame_cache_ttl = 0.15  # 缓存150ms，适合6fps
        self._cache_hits = 0
        self._cache_misses = 0
        self._max_client_frame_bytes = 0

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        stale_clients: list[WebSocket] = []
        async with self._lock:
            stale_clients = [client for client in self._clients if client is not websocket]
            self._clients = {websocket}
            if not self._external_frames_active():
                self._ensure_capture_task()

        for stale in stale_clients:
            with suppress(Exception):
                await stale.close(code=4000, reason="superseded_by_new_camera_viewer")

        if self._latest_frame and self._latest_frame_is_fresh():
            await self._send_frame(websocket, self._latest_frame)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(websocket)
            self._stop_capture_task_if_idle()

    async def start_keep_warm(self) -> None:
        async with self._lock:
            self._keep_warm = True
            self._ensure_capture_task()

    async def stop_keep_warm(self) -> None:
        async with self._lock:
            self._keep_warm = False
            self._stop_capture_task_if_idle()

    async def mjpeg_frames(self) -> AsyncGenerator[bytes, None]:
        async with self._lock:
            self._mjpeg_clients += 1
            self._ensure_capture_task()

        last_frame_at: float | None = None
        max_cached_frame_age = self._max_cached_frame_age_seconds()
        try:
            while True:
                self._frame_event.clear()
                frame = self._latest_frame
                frame_at = self._latest_frame_at
                frame_is_fresh = frame_at is not None and time.time() - frame_at <= max_cached_frame_age
                if frame and frame_at != last_frame_at and frame_is_fresh:
                    last_frame_at = frame_at
                    yield self._format_mjpeg_part(frame)
                    continue

                try:
                    await asyncio.wait_for(self._frame_event.wait(), timeout=4.0)
                except asyncio.TimeoutError:
                    if self._latest_frame:
                        yield self._format_mjpeg_part(self._latest_frame)
        finally:
            async with self._lock:
                self._mjpeg_clients = max(0, self._mjpeg_clients - 1)
                self._stop_capture_task_if_idle()

    def status(self) -> dict[str, object]:
        cache_hit_rate = 0.0
        total_requests = self._cache_hits + self._cache_misses
        if total_requests > 0:
            cache_hit_rate = (self._cache_hits / total_requests) * 100
        
        return {
            "clients": len(self._clients) + self._mjpeg_clients,
            "websocket_clients": len(self._clients),
            "mjpeg_clients": self._mjpeg_clients,
            "running": bool(self._capture_task and not self._capture_task.done()),
            "keep_warm": self._keep_warm,
            "latest_frame_at": self._latest_frame_at,
            "latest_frame_size": self._latest_frame_size,
            "last_error": self._last_error,
            "frames_total": self._frames_total,
            "broadcast_total": self._broadcast_total,
            "target_fps": round(max(1.0, min(self._settings.camera_stream_fps, 30.0)), 2),
            "source_fps": round(self._source_fps, 2),
            "broadcast_fps": round(self._broadcast_fps, 2),
            "measured_fps": round(self._source_fps, 2),
            "active_url": self._mask_url(self._active_url),
            "profile": self._settings.camera_stream_profile,
            "jpeg_quality": max(2, min(self._settings.camera_stream_jpeg_quality, 12)),
            "stream_width": max(0, self._settings.camera_stream_width),
            # 优化监控指标
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_hit_rate": round(cache_hit_rate, 2),
            "cache_size": len(self._frame_cache),
            "max_client_frame_bytes": self._max_client_frame_bytes,
        }

    def latest_frame(self) -> bytes | None:
        return self._latest_frame

    async def publish_external_frame(
        self,
        frame: bytes,
        *,
        source_label: str = "external-frame",
        decorate: bool = True,
    ) -> None:
        if not frame or not frame.startswith(b"\xff\xd8"):
            return
        if decorate:
            frame = await self._decorate_frame_async(frame)
        self._external_frames_active_until = time.monotonic() + self._max_cached_frame_age_seconds()
        if self._capture_task and not self._capture_task.done():
            self._capture_task.cancel()
            self._capture_task = None
        self._latest_frame = frame
        self._latest_frame_at = time.time()
        self._latest_frame_size = len(frame)
        self._active_url = source_label
        self._last_error = None
        self._frame_event.set()
        self._record_frame()
        await self._broadcast_frame(frame)

    def _decorate_frame(self, frame: bytes) -> bytes:
        return frame

    async def _decorate_frame_async(self, frame: bytes) -> bytes:
        """Decorate a frame without blocking the FastAPI event loop.

        Base hubs do no work, but processed hubs perform OpenCV decode/draw/
        encode work. Running that synchronously inside the async capture loop can
        starve unrelated APIs such as /healthz and mobile server settings tests.
        """
        return frame

    def _ensure_capture_task(self) -> None:
        if self._capture_task is None or self._capture_task.done():
            self._capture_task = asyncio.create_task(self._capture_loop())

    def _stop_capture_task_if_idle(self) -> None:
        if self._keep_warm or self._clients or self._mjpeg_clients > 0 or not self._capture_task or self._capture_task.done():
            return
        self._capture_task.cancel()
        self._capture_task = None

    def _has_consumers(self) -> bool:
        return bool(self._keep_warm or self._clients or self._mjpeg_clients > 0)

    def _max_cached_frame_age_seconds(self) -> float:
        return max(1.0, min(3.0, 2.0 / max(1.0, self._settings.camera_stream_fps)))

    def _latest_frame_is_fresh(self) -> bool:
        return (
            self._latest_frame_at is not None
            and time.time() - self._latest_frame_at <= self._max_cached_frame_age_seconds()
        )

    def _external_frames_active(self) -> bool:
        return time.monotonic() <= self._external_frames_active_until

    async def _capture_loop(self) -> None:
        service = CameraService(self._settings)

        try:
            while True:
                async with self._lock:
                    if not self._has_consumers():
                        return

                preferred_mode = service.resolved_source_mode()
                try:
                    if preferred_mode == "local":
                        await self._run_local_snapshot_stream(service)
                    elif service.uses_runtime_managed_source():
                        await self._run_runtime_snapshot_stream(service)
                    else:
                        await self._run_ffmpeg_stream(service)
                except Exception as exc:
                    self._last_error = f"{exc.__class__.__name__}: {exc}"
                    logger.warning("Camera stream failed, retrying: %s", self._last_error)
                    if preferred_mode != "local":
                        try:
                            await self._run_snapshot_stream(service)
                        except Exception as snapshot_exc:
                            self._last_error = f"{snapshot_exc.__class__.__name__}: {snapshot_exc}"
                            logger.warning("RTSP snapshot fallback failed, retrying: %s", self._last_error)
                            if service.can_use_local_camera_fallback() and not service.should_fail_closed_on_rtsp_errors():
                                try:
                                    await self._run_local_snapshot_stream(service)
                                except Exception as fallback_exc:
                                    self._last_error = f"{fallback_exc.__class__.__name__}: {fallback_exc}"
                                    logger.warning("Local camera fallback failed, retrying: %s", self._last_error)
                                    await self._run_snapshot_stream(service)
                            else:
                                await self._run_snapshot_stream(service)
                    else:
                        await self._run_snapshot_stream(service)
                    await asyncio.sleep(0.6)
        except asyncio.CancelledError:
            raise

    async def _run_runtime_mjpeg_stream(self, service: CameraService) -> None:
        """Relay the external runtime MJPEG stream directly.

        The runtime already owns the fragile RTSP connection. Relaying its
        MJPEG stream avoids repeatedly polling snapshots from this backend and
        gives mobile/community pages many more frame changes per second.

        If the runtime stream stalls on cold start, fail fast so the capture
        loop can fall back to high-frequency runtime snapshots. A slightly
        lower but steady snapshot cadence is much better for the mobile app
        than waiting 10+ seconds for a blocked MJPEG read.
        """
        import requests

        url = service.runtime_mjpeg_url
        self._active_url = "runtime-mjpeg-relay"
        connect_timeout = max(0.8, min(self._settings.camera_probe_timeout_seconds, 2.0))
        read_timeout = max(0.8, min(self._settings.camera_snapshot_timeout_seconds, 1.5))
        first_frame_timeout = max(1.5, min(self._settings.camera_snapshot_timeout_seconds, 2.5))
        idle_timeout = max(1.2, min(self._settings.camera_snapshot_timeout_seconds, 2.0))

        def open_response():
            return requests.get(url, stream=True, timeout=(connect_timeout, read_timeout))

        def next_chunk(iterator):
            try:
                return next(iterator)
            except StopIteration:
                return None

        response = await asyncio.to_thread(open_response)
        try:
            response.raise_for_status()
            iterator = response.iter_content(chunk_size=65536)
            buffer = b""
            started_at = time.monotonic()
            last_frame_at = time.monotonic()
            frame_count = 0

            while True:
                async with self._lock:
                    if not self._has_consumers():
                        return

                try:
                    chunk = await asyncio.to_thread(next_chunk, iterator)
                except requests.RequestException as exc:
                    raise RuntimeError(f"RUNTIME_MJPEG_READ_FAILED: {exc}") from exc

                if chunk is None:
                    return

                if not chunk:
                    now = time.monotonic()
                    if frame_count == 0 and now - started_at > first_frame_timeout:
                        raise RuntimeError("RUNTIME_MJPEG_FIRST_FRAME_TIMEOUT")
                    if frame_count > 0 and now - last_frame_at > idle_timeout:
                        raise RuntimeError("RUNTIME_MJPEG_IDLE_TIMEOUT")
                    continue

                buffer += chunk
                now = time.monotonic()
                if frame_count == 0 and now - started_at > first_frame_timeout:
                    raise RuntimeError("RUNTIME_MJPEG_FIRST_FRAME_TIMEOUT")
                if frame_count > 0 and now - last_frame_at > idle_timeout:
                    raise RuntimeError("RUNTIME_MJPEG_IDLE_TIMEOUT")
                while True:
                    start = buffer.find(b"\xff\xd8")
                    end = buffer.find(b"\xff\xd9", start + 2) if start >= 0 else -1
                    if start < 0:
                        buffer = buffer[-2:]
                        break
                    if end < 0:
                        buffer = buffer[start:]
                        break

                    frame = buffer[start : end + 2]
                    buffer = buffer[end + 2 :]
                    frame = await self._decorate_frame_async(frame)
                    frame_count += 1
                    last_frame_at = time.monotonic()
                    self._latest_frame = frame
                    self._latest_frame_at = time.time()
                    self._latest_frame_size = len(frame)
                    self._last_error = None
                    self._frame_event.set()
                    self._record_frame()
                    await self._broadcast_frame(frame)
        finally:
            response.close()

    async def _run_runtime_snapshot_stream(self, service: CameraService) -> None:
        """Serve runtime frames through fast snapshot polling.

        The external runtime already keeps an RTSP reader hot and exposes its
        latest decoded frame as a cheap HTTP snapshot. Polling that cached
        frame gives mobile devices a steadier cadence than relaying the
        runtime MJPEG endpoint when the latter stalls on idle clients.
        """
        fps = max(1.0, min(self._settings.camera_stream_fps, 10.0))
        delay = 1.0 / fps
        self._active_url = "runtime-snapshot-relay"
        consecutive_failures = 0

        while True:
            async with self._lock:
                if not self._has_consumers():
                    return

            started = time.monotonic()
            try:
                frame, _headers = await asyncio.to_thread(
                    service.capture_runtime_jpeg_fast,
                    timeout_seconds=0.8,
                )
                consecutive_failures = 0
            except Exception as exc:
                consecutive_failures += 1
                self._last_error = f"{exc.__class__.__name__}: {exc}"
                if consecutive_failures >= 3:
                    raise RuntimeError(f"RUNTIME_SNAPSHOT_RELAY_FAILED: {self._last_error}") from exc
                await asyncio.sleep(min(delay, 0.25))
                continue

            frame = await self._decorate_frame_async(frame)
            self._latest_frame = frame
            self._latest_frame_at = time.time()
            self._latest_frame_size = len(frame)
            self._last_error = None
            self._frame_event.set()
            self._record_frame()
            await self._broadcast_frame(frame)

            elapsed = time.monotonic() - started
            await asyncio.sleep(max(0.0, delay - elapsed))

    async def _run_ffmpeg_stream(self, service: CameraService) -> None:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        fps = max(1.0, min(self._settings.camera_stream_fps, 30.0))
        jpeg_quality = max(2, min(self._settings.camera_stream_jpeg_quality, 12))
        stream_width = max(0, self._settings.camera_stream_width)
        filters = [f"fps={fps:.2f}"]
        if stream_width > 0:
            filters.append(f"scale={stream_width}:-2:flags=bicubic")
        last_error = ""

        for url in service.stream_rtsp_urls:
            async with self._lock:
                if not self._has_consumers():
                    return

            transport = "udp" if "/udp/" in url.lower() else "tcp"
            cmd = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-fflags",
                "discardcorrupt",
                "-probesize",
                "5000000",
                "-analyzeduration",
                "1000000",
                "-rtsp_transport",
                transport,
                "-timeout",
                str(int(self._settings.camera_snapshot_timeout_seconds * 1_000_000)),
                "-i",
                url,
                "-an",
                "-vf",
                ",".join(filters),
                "-q:v",
                str(jpeg_quality),
                "-flush_packets",
                "1",
                "-f",
                "mjpeg",
                "-",
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            buffer = b""
            frame_count = 0
            last_frame_at = time.monotonic()
            self._active_url = url

            try:
                if process.stdout is None:
                    continue

                while True:
                    async with self._lock:
                        if not self._has_consumers():
                            return

                    try:
                        chunk = await asyncio.wait_for(process.stdout.read(65536), timeout=4.0)
                    except asyncio.TimeoutError:
                        if frame_count == 0 or time.monotonic() - last_frame_at > 4.0:
                            raise RuntimeError("CAMERA_STREAM_READ_TIMEOUT")
                        continue

                    if not chunk:
                        break

                    buffer += chunk
                    while True:
                        start = buffer.find(b"\xff\xd8")
                        end = buffer.find(b"\xff\xd9", start + 2) if start >= 0 else -1
                        if start < 0:
                            buffer = buffer[-2:]
                            break
                        if end < 0:
                            buffer = buffer[start:]
                            break

                        frame = buffer[start : end + 2]
                        buffer = buffer[end + 2 :]
                        frame = await self._decorate_frame_async(frame)
                        frame_count += 1
                        last_frame_at = time.monotonic()
                        self._latest_frame = frame
                        self._latest_frame_at = time.time()
                        self._latest_frame_size = len(frame)
                        self._last_error = None
                        self._frame_event.set()
                        self._record_frame()
                        await self._broadcast_frame(frame)
            finally:
                with suppress(ProcessLookupError):
                    process.kill()
                with suppress(ProcessLookupError, asyncio.TimeoutError):
                    await asyncio.wait_for(process.wait(), timeout=2.0)

            stderr = b""
            if process.stderr:
                with suppress(Exception):
                    stderr = await asyncio.wait_for(process.stderr.read(), timeout=0.2)
            last_error = stderr.decode("utf-8", errors="replace").strip()
            if frame_count > 0:
                return

        raise RuntimeError(last_error or "CAMERA_STREAM_NO_FRAMES")

    async def _capture_snapshot_fallback(self, service: CameraService) -> None:
        try:
            frame, _headers = await asyncio.to_thread(service.capture_jpeg)
        except Exception:
            return
        frame = await self._decorate_frame_async(frame)
        self._latest_frame = frame
        self._latest_frame_at = time.time()
        self._latest_frame_size = len(frame)
        self._frame_event.set()
        self._record_frame()
        await self._broadcast_frame(frame)

    async def _run_snapshot_stream(self, service: CameraService) -> None:
        runtime_managed = service.uses_runtime_managed_source()
        fps_cap = 10.0 if runtime_managed else 6.0
        fps = max(1.0, min(self._settings.camera_stream_fps, fps_cap))
        delay = 1.0 / fps
        delivered = 0
        self._active_url = (
            "runtime-snapshot-relay"
            if runtime_managed
            else "rtsp-snapshot-fallback"
        )
        max_delivered = None if runtime_managed else max(3, int(fps * 4))
        while max_delivered is None or delivered < max_delivered:
            async with self._lock:
                if not self._has_consumers():
                    return
            
            # 优化2: 检查帧缓存
            cache_key = f"snapshot_{int(time.time() * fps)}"
            cached_frame = self._get_cached_frame(cache_key)
            
            if cached_frame is not None:
                frame = cached_frame
                self._cache_hits += 1
            else:
                try:
                    # 优化4: 使用asyncio.to_thread避免阻塞
                    capture = service.capture_runtime_jpeg_fast if runtime_managed else service.capture_jpeg
                    if runtime_managed:
                        frame, _headers = await asyncio.to_thread(capture, timeout_seconds=0.8)
                    else:
                        frame, _headers = await asyncio.to_thread(capture)
                    # 缓存帧
                    self._cache_frame(cache_key, frame)
                    self._cache_misses += 1
                except Exception:
                    return
            
            frame = await self._decorate_frame_async(frame)
            self._latest_frame = frame
            self._latest_frame_at = time.time()
            self._latest_frame_size = len(frame)
            self._last_error = None
            self._frame_event.set()
            self._record_frame()
            await self._broadcast_frame(frame)
            delivered += 1
            await asyncio.sleep(delay)

    async def _run_local_snapshot_stream(self, service: CameraService) -> None:
        fps = max(1.0, min(self._settings.camera_stream_fps, 8.0))
        delay = 1.0 / fps
        await self._run_local_video_capture_stream(service, fps=fps, delay=delay)
        return
        self._active_url = service.local_source_label()
        while True:
            async with self._lock:
                if not self._has_consumers():
                    return
            
            # 优化2: 检查帧缓存
            cache_key = f"local_{int(time.time() * fps)}"
            cached_frame = self._get_cached_frame(cache_key)
            
            if cached_frame is not None:
                frame = cached_frame
                self._cache_hits += 1
            else:
                # 优化4: 使用asyncio.to_thread避免阻塞
                frame, _headers = await asyncio.to_thread(service.capture_local_jpeg)
                # 缓存帧
                self._cache_frame(cache_key, frame)
                self._cache_misses += 1
            
            frame = await self._decorate_frame_async(frame)
            self._latest_frame = frame
            self._latest_frame_at = time.time()
            self._latest_frame_size = len(frame)
            self._last_error = None
            self._frame_event.set()
            self._record_frame()
            await self._broadcast_frame(frame)
            await asyncio.sleep(delay)

    async def _run_local_video_capture_stream(
        self,
        service: CameraService,
        *,
        fps: float,
        delay: float,
    ) -> None:
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("OPENCV_NOT_INSTALLED") from exc

        last_error = ""
        for backend_name, backend in service._local_camera_backends(cv2):  # noqa: SLF001
            try:
                cap = await asyncio.to_thread(
                    cv2.VideoCapture,
                    self._settings.camera_local_index,
                    backend,
                )
            except Exception as exc:
                last_error = f"{backend_name}: {exc.__class__.__name__}: {exc}"
                continue
            try:
                opened = await asyncio.to_thread(cap.isOpened)
                if not opened:
                    last_error = f"{backend_name}: Camera not opened"
                    continue
                with suppress(Exception):
                    await asyncio.to_thread(cap.set, cv2.CAP_PROP_BUFFERSIZE, 1)
                with suppress(Exception):
                    await asyncio.to_thread(cap.set, cv2.CAP_PROP_FRAME_WIDTH, 640)
                with suppress(Exception):
                    await asyncio.to_thread(cap.set, cv2.CAP_PROP_FRAME_HEIGHT, 480)
                with suppress(Exception):
                    await asyncio.to_thread(cap.set, cv2.CAP_PROP_FPS, max(4.0, min(fps, 8.0)))

                while True:
                    async with self._lock:
                        if not self._has_consumers():
                            return

                    ok, frame_data = await asyncio.to_thread(cap.read)
                    if not ok or frame_data is None:
                        raise RuntimeError("LOCAL_CAMERA_FRAME_READ_FAILED")
                    if not service.is_usable_local_frame(frame_data):
                        await asyncio.sleep(min(delay, 0.08))
                        continue

                    frame, _headers = await asyncio.to_thread(
                        service._encode_frame_to_jpeg,  # noqa: SLF001
                        frame_data,
                    )
                    frame = await self._decorate_frame_async(frame)
                    self._latest_frame = frame
                    self._latest_frame_at = time.time()
                    self._latest_frame_size = len(frame)
                    self._last_error = None
                    self._frame_event.set()
                    self._record_frame()
                    await self._broadcast_frame(frame)
                    await asyncio.sleep(delay)
            except Exception as exc:
                last_error = f"{backend_name}: {exc.__class__.__name__}: {exc}"
            finally:
                with suppress(Exception):
                    await asyncio.to_thread(cap.release)

        raise RuntimeError(
            f"LOCAL_CAMERA_STREAM_FAILED: {last_error or 'no backend opened'}"
        )

    def _record_frame(self) -> None:
        self._frames_total += 1
        self._fps_window_frames += 1
        now = time.monotonic()
        elapsed = now - self._fps_window_started_at
        if elapsed >= 2.0:
            self._source_fps = self._fps_window_frames / elapsed
            self._fps_window_frames = 0
            self._fps_window_started_at = now

    def _record_broadcast(self, count: int) -> None:
        if count <= 0:
            return

        self._broadcast_total += count
        self._broadcast_window_frames += count
        now = time.monotonic()
        elapsed = now - self._broadcast_window_started_at
        if elapsed >= 2.0:
            self._broadcast_fps = self._broadcast_window_frames / elapsed
            self._broadcast_window_frames = 0
            self._broadcast_window_started_at = now

    async def _broadcast_frame(self, frame: bytes) -> None:
        async with self._lock:
            clients = list(self._clients)

        if not clients:
            return

        target_fps = max(1.0, min(self._settings.camera_stream_fps, 30.0))
        min_interval = 1.0 / target_fps
        now = time.monotonic()
        if now - self._last_broadcasted_at < min_interval:
            return

        send_frame = await self._prepare_client_frame(frame)

        async def send(websocket: WebSocket) -> tuple[WebSocket, bool]:
            try:
                await asyncio.wait_for(
                    self._send_frame(websocket, send_frame),
                    timeout=max(0.05, self._settings.camera_stream_send_timeout_seconds),
                )
                return websocket, True
            except (asyncio.TimeoutError, Exception):
                return websocket, False

        results = await asyncio.gather(*(send(websocket) for websocket in clients), return_exceptions=False)
        stale = [websocket for websocket, ok in results if not ok]
        sent = sum(1 for _websocket, ok in results if ok)
        if sent > 0:
            self._last_broadcasted_at = now

        self._record_broadcast(sent)

        if stale:
            async with self._lock:
                for websocket in stale:
                    self._clients.discard(websocket)

    @staticmethod
    def _format_mjpeg_part(image: bytes) -> bytes:
        return (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n"
            + f"Content-Length: {len(image)}\r\n\r\n".encode("ascii")
            + image
            + b"\r\n"
        )

    @staticmethod
    async def _send_frame(websocket: WebSocket, frame: bytes) -> None:
        await websocket.send_bytes(frame)

    async def _prepare_client_frame(self, frame: bytes) -> bytes:
        max_bytes = self._max_client_frame_bytes
        if max_bytes <= 0 or len(frame) <= max_bytes:
            return frame
        return await asyncio.to_thread(self._compress_for_client, frame, max_bytes)

    @staticmethod
    def _compress_for_client(frame: bytes, max_bytes: int) -> bytes:
        try:
            import cv2
            import numpy as np
        except Exception:
            return frame

        image = cv2.imdecode(np.frombuffer(frame, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return frame

        height, width = image.shape[:2]
        attempts = [
            (min(width, 960), 82),
            (min(width, 860), 78),
            (min(width, 768), 74),
            (min(width, 640), 70),
            (min(width, 576), 66),
        ]
        candidate = frame
        for target_width, quality in attempts:
            working = image
            if 0 < target_width < width:
                target_height = max(2, int(round(height * (target_width / width))))
                working = cv2.resize(working, (target_width, target_height), interpolation=cv2.INTER_AREA)
            ok, encoded = cv2.imencode(
                ".jpg",
                working,
                [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)],
            )
            if not ok:
                continue
            payload = encoded.tobytes()
            candidate = payload
            if len(payload) <= max_bytes:
                return payload
        return candidate

    def _mask_url(self, url: str | None) -> str | None:
        if not url:
            return None
        password = self._settings.camera_password
        return url.replace(password, "***") if password else url

    def _get_cached_frame(self, cache_key: str) -> bytes | None:
        """获取缓存的帧，如果过期则返回None"""
        if cache_key not in self._frame_cache:
            return None
        
        frame, timestamp = self._frame_cache[cache_key]
        if time.time() - timestamp > self._frame_cache_ttl:
            # 缓存过期，删除
            del self._frame_cache[cache_key]
            return None
        
        return frame

    def _cache_frame(self, cache_key: str, frame: bytes) -> None:
        """缓存帧，并清理过期缓存"""
        self._frame_cache[cache_key] = (frame, time.time())
        
        # 清理过期缓存（保持缓存大小合理）
        if len(self._frame_cache) > 10:
            current_time = time.time()
            expired_keys = [
                key for key, (_, timestamp) in self._frame_cache.items()
                if current_time - timestamp > self._frame_cache_ttl
            ]
            for key in expired_keys:
                del self._frame_cache[key]


class CameraDetectionFrameHub(CameraFrameHub):
    """Camera hub that paints the latest fall-detection bbox onto frames."""

    def __init__(
        self,
        settings: Settings,
        *,
        event_provider: Callable[[], dict[str, Any] | None],
        max_event_age_seconds: float = 8.0,
        fallback_analyzer: Callable[[bytes], dict[str, Any] | None] | None = None,
        fallback_min_interval_seconds: float = 1.0,
    ) -> None:
        super().__init__(settings)
        self._event_provider = event_provider
        self._max_event_age_seconds = max_event_age_seconds
        self._fallback_analyzer = fallback_analyzer
        self._fallback_min_interval_seconds = fallback_min_interval_seconds
        self._fallback_payload: dict[str, Any] | None = None
        self._fallback_payload_at: float | None = None
        self._last_fallback_attempt_at = 0.0
        self._fallback_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="camera-fall-overlay")
        self._fallback_future: Future[dict[str, Any] | None] | None = None

    def _decorate_frame(self, frame: bytes) -> bytes:
        self._poll_fallback_future()
        event = self._resolve_event(frame)
        if not isinstance(event, dict):
            return frame

        bbox = event.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return frame

        frame_width = self._coerce_positive(event.get("frame_width"))
        frame_height = self._coerce_positive(event.get("frame_height"))
        if frame_width <= 0 or frame_height <= 0:
            return frame

        event_timestamp = self._coerce_positive(event.get("_observed_at"))
        if event_timestamp > 0 and time.time() - event_timestamp > self._max_event_age_seconds:
            return frame

        try:
            coords = [float(value) for value in bbox]
        except (TypeError, ValueError):
            return frame

        try:
            import cv2
            import numpy as np
        except Exception:
            return frame

        image = cv2.imdecode(np.frombuffer(frame, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return frame

        height, width = image.shape[:2]
        x1, y1, x2, y2 = coords
        x1 = max(0, min(width - 1, int(round((x1 / frame_width) * width))))
        x2 = max(0, min(width - 1, int(round((x2 / frame_width) * width))))
        y1 = max(0, min(height - 1, int(round((y1 / frame_height) * height))))
        y2 = max(0, min(height - 1, int(round((y2 / frame_height) * height))))
        if x2 <= x1 or y2 <= y1:
            return frame

        state = str(event.get("state") or event.get("event_type") or "tracked").strip() or "tracked"
        fall_score = self._coerce_positive(event.get("fall_score"))
        posture_label = str(event.get("posture_label") or "").strip()
        label = f"{state} {fall_score:.2f}".strip()
        if posture_label:
            label = f"{label} {posture_label}".strip()

        alert_like = state in {
            "suspected_fall",
            "confirmed_fall",
            "post_fall_monitoring",
            "injury_watch",
            "abnormal_recovery",
            "needs_assistance",
            "emergency",
        }
        color = (38, 78, 255) if not alert_like else (32, 90, 235)
        if alert_like:
            color = (0, 80, 255)

        thickness = 3 if alert_like else 2
        cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)

        text_size, baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.62, 2)
        text_w, text_h = text_size
        text_x = x1
        text_y = max(text_h + 10, y1 - 8)
        cv2.rectangle(
            image,
            (text_x - 4, text_y - text_h - 8),
            (text_x + text_w + 6, text_y + baseline + 4),
            color,
            -1,
        )
        cv2.putText(
            image,
            label,
            (text_x, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        return encoded.tobytes() if ok else frame

    async def _decorate_frame_async(self, frame: bytes) -> bytes:
        return await asyncio.to_thread(self._decorate_frame, frame)

    def _resolve_event(self, frame: bytes) -> dict[str, Any] | None:
        event = self._event_provider()
        if self._is_fresh_detection_payload(event):
            return event
        now = time.time()
        if self._is_fresh_detection_payload(self._fallback_payload):
            if self._fallback_payload_at is None or now - self._fallback_payload_at <= self._max_event_age_seconds:
                return self._fallback_payload
        if self._fallback_analyzer is None:
            return None
        if now - self._last_fallback_attempt_at < self._fallback_min_interval_seconds:
            return self._fallback_payload if self._is_fresh_detection_payload(self._fallback_payload) else None
        self._last_fallback_attempt_at = now
        if self._fallback_future is None or self._fallback_future.done():
            self._fallback_future = self._fallback_executor.submit(self._fallback_analyzer, frame)
        return self._fallback_payload if self._is_fresh_detection_payload(self._fallback_payload) else None

    def _poll_fallback_future(self) -> None:
        if self._fallback_future is None or not self._fallback_future.done():
            return
        try:
            payload = self._fallback_future.result()
        except Exception:
            payload = None
        if self._is_fresh_detection_payload(payload):
            self._fallback_payload = payload
            self._fallback_payload_at = time.time()
        self._fallback_future = None

    def overlay_status(self) -> dict[str, object]:
        self._poll_fallback_future()
        event = self._event_provider()
        event_valid = self._is_fresh_detection_payload(event)
        fallback_age = None if self._fallback_payload_at is None else max(0.0, time.time() - self._fallback_payload_at)
        fallback_valid = (
            self._is_fresh_detection_payload(self._fallback_payload)
            and fallback_age is not None
            and fallback_age <= self._max_event_age_seconds
        )
        return {
            "type": "fall",
            "event_valid": event_valid,
            "fallback_valid": fallback_valid,
            "fallback_age_seconds": fallback_age,
            "has_renderable_overlay": bool(event_valid or fallback_valid),
            "fallback_running": bool(self._fallback_future and not self._fallback_future.done()),
            "last_fallback_attempt_at": self._last_fallback_attempt_at or None,
        }

    def current_overlay_payload(self) -> dict[str, Any] | None:
        """Return the freshest renderable fall payload cached by this hub."""
        event = self._event_provider()
        if self._is_fresh_detection_payload(event):
            return event
        now = time.time()
        if self._is_fresh_detection_payload(self._fallback_payload):
            if self._fallback_payload_at is not None and now - self._fallback_payload_at <= self._max_event_age_seconds:
                return self._fallback_payload
        return None

    @staticmethod
    def _is_valid_detection_payload(payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        bbox = payload.get("bbox")
        return isinstance(bbox, (list, tuple)) and len(bbox) == 4

    def _is_fresh_detection_payload(self, payload: Any) -> bool:
        if not self._is_valid_detection_payload(payload):
            return False
        observed_at = self._coerce_positive(payload.get("_observed_at")) if isinstance(payload, dict) else 0.0
        return observed_at <= 0 or time.time() - observed_at <= self._max_event_age_seconds

    @staticmethod
    def _coerce_positive(value: object) -> float:
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 0.0


class CameraPoseFrameHub(CameraFrameHub):
    """Camera hub that paints the latest pose tracks onto frames."""

    _COCO_BONES = (
        (5, 6),
        (5, 7),
        (7, 9),
        (6, 8),
        (8, 10),
        (5, 11),
        (6, 12),
        (11, 12),
        (11, 13),
        (13, 15),
        (12, 14),
        (14, 16),
        (0, 5),
        (0, 6),
    )

    def __init__(
        self,
        settings: Settings,
        *,
        payload_provider: Callable[[], dict[str, Any] | None],
        max_payload_age_seconds: float = 5.0,
        fallback_analyzer: Callable[[bytes], dict[str, Any] | None] | None = None,
        fallback_min_interval_seconds: float = 1.0,
    ) -> None:
        super().__init__(settings)
        self._payload_provider = payload_provider
        self._max_payload_age_seconds = max_payload_age_seconds
        self._fallback_analyzer = fallback_analyzer
        self._fallback_min_interval_seconds = fallback_min_interval_seconds
        self._fallback_payload: dict[str, Any] | None = None
        self._fallback_payload_at: float | None = None
        self._last_fallback_attempt_at = 0.0
        self._fallback_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="camera-pose-overlay")
        self._fallback_future: Future[dict[str, Any] | None] | None = None

    def _decorate_frame(self, frame: bytes) -> bytes:
        self._poll_fallback_future()
        payload = self._resolve_payload(frame)
        if not isinstance(payload, dict):
            return frame

        tracks = payload.get("tracks")
        if not isinstance(tracks, list) or not tracks:
            return frame

        frame_width = self._coerce_positive(payload.get("frame_width"))
        frame_height = self._coerce_positive(payload.get("frame_height"))
        if frame_width <= 0 or frame_height <= 0:
            return frame

        observed_at = self._coerce_positive(payload.get("_observed_at"))
        if observed_at > 0 and time.time() - observed_at > self._max_payload_age_seconds:
            return frame

        try:
            import cv2
            import numpy as np
        except Exception:
            return frame

        image = cv2.imdecode(np.frombuffer(frame, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return frame

        height, width = image.shape[:2]
        for item in tracks:
            if not isinstance(item, dict):
                continue
            bbox = item.get("bbox")
            if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                continue
            try:
                x1, y1, x2, y2 = [float(value) for value in bbox]
            except (TypeError, ValueError):
                continue
            x1 = max(0, min(width - 1, int(round((x1 / frame_width) * width))))
            x2 = max(0, min(width - 1, int(round((x2 / frame_width) * width))))
            y1 = max(0, min(height - 1, int(round((y1 / frame_height) * height))))
            y2 = max(0, min(height - 1, int(round((y2 / frame_height) * height))))
            if x2 <= x1 or y2 <= y1:
                continue

            label = str(item.get("posture_label") or "unknown").strip() or "unknown"
            score = self._coerce_positive(item.get("posture_score"))
            track_id = str(item.get("track_id") or "?")
            risk_like = label in {
                "lying_floor",
                "floor_risk",
                "fall_like",
                "suspected_fall",
                "confirmed_fall",
            }
            color = (0, 0, 255) if risk_like else (0, 80, 255)

            cv2.rectangle(image, (x1, y1), (x2, y2), color, 3)
            text = f"id={track_id} {label} {score:.2f}"
            text_size, baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.58, 2)
            text_w, text_h = text_size
            text_x = x1
            text_y = max(text_h + 10, y1 - 8)
            cv2.rectangle(
                image,
                (text_x - 4, text_y - text_h - 8),
                (text_x + text_w + 6, text_y + baseline + 4),
                color,
                -1,
            )
            cv2.putText(
                image,
                text,
                (text_x, text_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.58,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            keypoints = item.get("keypoints")
            if isinstance(keypoints, list):
                scaled_points: list[tuple[int, int, float] | None] = []
                for point in keypoints:
                    if not isinstance(point, (list, tuple)) or len(point) < 2:
                        scaled_points.append(None)
                        continue
                    try:
                        px = float(point[0])
                        py = float(point[1])
                        pconf = float(point[2]) if len(point) >= 3 else 1.0
                    except (TypeError, ValueError):
                        scaled_points.append(None)
                        continue
                    tx = max(0, min(width - 1, int(round((px / frame_width) * width))))
                    ty = max(0, min(height - 1, int(round((py / frame_height) * height))))
                    scaled_points.append((tx, ty, pconf))

                for bone_a, bone_b in self._COCO_BONES:
                    if bone_a >= len(scaled_points) or bone_b >= len(scaled_points):
                        continue
                    point_a = scaled_points[bone_a]
                    point_b = scaled_points[bone_b]
                    if point_a is None or point_b is None:
                        continue
                    if point_a[2] < 0.18 or point_b[2] < 0.18:
                        continue
                    cv2.line(
                        image,
                        (point_a[0], point_a[1]),
                        (point_b[0], point_b[1]),
                        color,
                        3,
                        cv2.LINE_AA,
                    )

                for point in scaled_points:
                    if point is None or point[2] < 0.15:
                        continue
                    tx, ty, _confidence = point
                    cv2.circle(image, (tx, ty), 5, (255, 255, 255), -1)
                    cv2.circle(image, (tx, ty), 2, color, -1)

        ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        return encoded.tobytes() if ok else frame

    async def _decorate_frame_async(self, frame: bytes) -> bytes:
        return await asyncio.to_thread(self._decorate_frame, frame)

    def _resolve_payload(self, frame: bytes) -> dict[str, Any] | None:
        payload = self._payload_provider()
        if self._is_fresh_pose_payload(payload):
            return payload
        now = time.time()
        if self._is_fresh_pose_payload(self._fallback_payload):
            if self._fallback_payload_at is None or now - self._fallback_payload_at <= self._max_payload_age_seconds:
                return self._fallback_payload
        if self._fallback_analyzer is None:
            return payload if self._is_fresh_pose_payload(payload) else None
        if now - self._last_fallback_attempt_at < self._fallback_min_interval_seconds:
            if self._is_fresh_pose_payload(self._fallback_payload):
                return self._fallback_payload
            return payload if self._is_fresh_pose_payload(payload) else None
        self._last_fallback_attempt_at = now
        if self._fallback_future is None or self._fallback_future.done():
            self._fallback_future = self._fallback_executor.submit(self._fallback_analyzer, frame)
        return self._fallback_payload if self._is_fresh_pose_payload(self._fallback_payload) else None

    def _poll_fallback_future(self) -> None:
        if self._fallback_future is None or not self._fallback_future.done():
            return
        try:
            analyzed = self._fallback_future.result()
        except Exception:
            analyzed = None
        if self._is_fresh_pose_payload(analyzed):
            self._fallback_payload = analyzed
            self._fallback_payload_at = time.time()
        self._fallback_future = None

    def overlay_status(self) -> dict[str, object]:
        self._poll_fallback_future()
        payload = self._payload_provider()
        payload_valid = self._is_fresh_pose_payload(payload)
        fallback_age = None if self._fallback_payload_at is None else max(0.0, time.time() - self._fallback_payload_at)
        fallback_valid = (
            self._is_fresh_pose_payload(self._fallback_payload)
            and fallback_age is not None
            and fallback_age <= self._max_payload_age_seconds
        )
        track_count = 0
        source_payload = payload if payload_valid else (self._fallback_payload if fallback_valid else None)
        if isinstance(source_payload, dict) and isinstance(source_payload.get("tracks"), list):
            track_count = len(source_payload["tracks"])
        return {
            "type": "pose",
            "payload_valid": payload_valid,
            "fallback_valid": fallback_valid,
            "fallback_age_seconds": fallback_age,
            "track_count": track_count,
            "has_renderable_overlay": bool(payload_valid or fallback_valid),
            "fallback_running": bool(self._fallback_future and not self._fallback_future.done()),
            "last_fallback_attempt_at": self._last_fallback_attempt_at or None,
        }

    def current_overlay_payload(self) -> dict[str, Any] | None:
        """Return the freshest renderable pose payload cached by this hub."""
        payload = self._payload_provider()
        if self._is_fresh_pose_payload(payload):
            return payload
        now = time.time()
        if self._is_fresh_pose_payload(self._fallback_payload):
            if self._fallback_payload_at is not None and now - self._fallback_payload_at <= self._max_payload_age_seconds:
                return self._fallback_payload
        return payload if self._is_fresh_pose_payload(payload) else None

    @staticmethod
    def _is_valid_pose_payload(payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        tracks = payload.get("tracks")
        return isinstance(tracks, list) and len(tracks) > 0

    def _is_fresh_pose_payload(self, payload: Any) -> bool:
        if not self._is_valid_pose_payload(payload):
            return False
        observed_at = self._coerce_positive(payload.get("_observed_at")) if isinstance(payload, dict) else 0.0
        return observed_at <= 0 or time.time() - observed_at <= self._max_payload_age_seconds

    @staticmethod
    def _coerce_positive(value: object) -> float:
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 0.0


class CombinedProcessedFrameHub(CameraFrameHub):
    """Combined processed stream: target/pose/fall overlays on the same frame."""

    def __init__(
        self,
        settings: Settings,
        *,
        pose_payload_provider: Callable[[], dict[str, Any] | None],
        fall_payload_provider: Callable[[], dict[str, Any] | None],
        fall_alarm_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        max_payload_age_seconds: float = 5.0,
        pose_fallback_analyzer: Callable[[bytes], dict[str, Any] | None] | None = None,
        fall_fallback_analyzer: Callable[[bytes], dict[str, Any] | None] | None = None,
        fallback_min_interval_seconds: float = 1.0,
    ) -> None:
        super().__init__(settings)
        self._pose_payload_provider = pose_payload_provider
        self._fall_payload_provider = fall_payload_provider
        self._max_payload_age_seconds = max_payload_age_seconds
        self._pose_fallback_analyzer = pose_fallback_analyzer
        self._fall_fallback_analyzer = fall_fallback_analyzer
        self._fall_alarm_callback = fall_alarm_callback
        self._fallback_min_interval_seconds = fallback_min_interval_seconds
        self._pose_fallback_payload: dict[str, Any] | None = None
        self._fall_fallback_payload: dict[str, Any] | None = None
        self._pose_fallback_at: float | None = None
        self._fall_fallback_at: float | None = None
        self._last_pose_fallback_attempt_at = 0.0
        self._last_fall_fallback_attempt_at = 0.0
        self._diagnostic_overlay_at: float | None = None
        self._diagnostic_overlay_reason: str | None = None
        self._fallback_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="camera-overlay")
        self._pose_fallback_future: Future[dict[str, Any] | None] | None = None
        self._fall_fallback_future: Future[dict[str, Any] | None] | None = None
        self._last_promoted_fall_key = ""
        self._last_promoted_fall_at = 0.0
        self._max_client_frame_bytes = 220_000

    def _decorate_frame(self, frame: bytes) -> bytes:
        try:
            import cv2
            import numpy as np
        except Exception:
            return frame

        image = cv2.imdecode(np.frombuffer(frame, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return frame

        self._poll_fallback_futures()
        pose_payload = self._resolve_pose_payload(frame)
        fall_payload = self._resolve_fall_payload(frame)

        rendered_pose = False
        rendered_fall = False
        if isinstance(fall_payload, dict):
            image, rendered_fall = self._draw_fall_overlay(image, fall_payload)
        if isinstance(pose_payload, dict):
            image, rendered_pose = self._draw_pose_overlay(image, pose_payload)
        if not rendered_pose and not rendered_fall:
            image = self._draw_no_target_scan_overlay(image)
            self._diagnostic_overlay_at = time.time()
            self._diagnostic_overlay_reason = "no_renderable_model_payload"
        image = self._draw_status_badge(
            image,
            pose_payload=pose_payload,
            fall_payload=fall_payload,
            rendered_pose=rendered_pose,
            rendered_fall=rendered_fall,
        )

        ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        return encoded.tobytes() if ok else frame

    async def _decorate_frame_async(self, frame: bytes) -> bytes:
        return await asyncio.to_thread(self._decorate_frame, frame)

    def _draw_no_target_scan_overlay(self, image):
        """Visible fallback so processed video never looks identical to raw.

        If the current camera angle or scene prevents person/pose detection, the
        processed stream still needs to prove that the server-side processing
        path is alive and explain why no red box/skeleton is present.
        """
        try:
            import cv2
        except Exception:
            return image
        h, w = image.shape[:2]
        color = (0, 175, 255)
        margin_x = max(14, int(w * 0.035))
        margin_y = max(12, int(h * 0.04))
        x1, y1 = margin_x, margin_y
        x2, y2 = w - margin_x, h - margin_y
        if x2 <= x1 or y2 <= y1:
            return image
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        for i in range(1, 4):
            yy = int(y1 + (y2 - y1) * i / 4)
            cv2.line(image, (x1, yy), (x2, yy), color, 1, cv2.LINE_AA)
        text = "Processed online - no person/pose detected"
        text_size, baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        text_w, text_h = text_size
        text_x = x1 + 10
        text_y = min(y2 - 10, y1 + text_h + 14)
        cv2.rectangle(
            image,
            (text_x - 6, text_y - text_h - 8),
            (min(x2 - 4, text_x + text_w + 8), text_y + baseline + 5),
            (15, 22, 36),
            -1,
        )
        cv2.putText(image, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
        return image

    def _resolve_pose_payload(self, frame: bytes) -> dict[str, Any] | None:
        payload = self._pose_payload_provider()
        if self._is_fresh_pose_payload(payload):
            return payload
        now = time.time()
        if self._is_fresh_pose_payload(self._pose_fallback_payload):
            if self._pose_fallback_at is None or now - self._pose_fallback_at <= self._max_payload_age_seconds:
                return self._pose_fallback_payload
        if self._pose_fallback_analyzer is None:
            return payload if self._is_fresh_pose_payload(payload) else None
        if now - self._last_pose_fallback_attempt_at < self._fallback_min_interval_seconds:
            if self._is_fresh_pose_payload(self._pose_fallback_payload):
                return self._pose_fallback_payload
            return payload if self._is_fresh_pose_payload(payload) else None
        self._last_pose_fallback_attempt_at = now
        if self._pose_fallback_future is None or self._pose_fallback_future.done():
            self._pose_fallback_future = self._fallback_executor.submit(self._pose_fallback_analyzer, frame)
        if self._is_fresh_pose_payload(self._pose_fallback_payload):
            return self._pose_fallback_payload
        return payload if self._is_fresh_pose_payload(payload) else None

    def _resolve_fall_payload(self, frame: bytes) -> dict[str, Any] | None:
        payload = self._fall_payload_provider()
        if self._is_fresh_fall_payload(payload):
            return payload
        now = time.time()
        if self._is_fresh_fall_payload(self._fall_fallback_payload):
            if self._fall_fallback_at is None or now - self._fall_fallback_at <= self._max_payload_age_seconds:
                return self._fall_fallback_payload
        if self._fall_fallback_analyzer is None:
            return payload if self._is_fresh_fall_payload(payload) else None
        if now - self._last_fall_fallback_attempt_at < self._fallback_min_interval_seconds:
            if self._is_fresh_fall_payload(self._fall_fallback_payload):
                return self._fall_fallback_payload
            return payload if self._is_fresh_fall_payload(payload) else None
        self._last_fall_fallback_attempt_at = now
        if self._fall_fallback_future is None or self._fall_fallback_future.done():
            self._fall_fallback_future = self._fallback_executor.submit(self._fall_fallback_analyzer, frame)
        if self._is_fresh_fall_payload(self._fall_fallback_payload):
            return self._fall_fallback_payload
        return payload if self._is_fresh_fall_payload(payload) else None

    def _poll_fallback_futures(self) -> None:
        if self._pose_fallback_future is not None and self._pose_fallback_future.done():
            try:
                payload = self._pose_fallback_future.result()
            except Exception:
                payload = None
            if self._is_fresh_pose_payload(payload):
                self._pose_fallback_payload = payload
                self._pose_fallback_at = time.time()
            self._pose_fallback_future = None

        if self._fall_fallback_future is not None and self._fall_fallback_future.done():
            try:
                payload = self._fall_fallback_future.result()
            except Exception:
                payload = None
            if self._is_fresh_fall_payload(payload):
                self._fall_fallback_payload = payload
                self._fall_fallback_at = time.time()
                self._schedule_fall_alarm_promotion(payload)
            self._fall_fallback_future = None

    def prime_overlay(
        self,
        *,
        pose_payload: dict[str, Any] | None = None,
        fall_payload: dict[str, Any] | None = None,
    ) -> None:
        """Seed overlay payloads from an explicit single-frame analysis result."""
        now = time.time()
        if self._is_fresh_pose_payload(pose_payload):
            self._pose_fallback_payload = pose_payload
            self._pose_fallback_at = now
            self._pose_fallback_future = None
        if self._is_fresh_fall_payload(fall_payload):
            self._fall_fallback_payload = fall_payload
            self._fall_fallback_at = now
            self._fall_fallback_future = None
            self._schedule_fall_alarm_promotion(fall_payload)

    def _schedule_fall_alarm_promotion(self, payload: dict[str, Any] | None) -> None:
        if self._fall_alarm_callback is None or not self._is_fresh_fall_payload(payload):
            return
        assert payload is not None
        state = str(payload.get("state") or payload.get("status") or "").strip().lower()
        try:
            score = float(payload.get("fall_score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        bbox = payload.get("bbox")
        bbox_key = ""
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            try:
                bbox_key = ",".join(str(int(float(value) // 24)) for value in bbox[:4])
            except (TypeError, ValueError):
                bbox_key = ""
        dedupe_key = f"{state}:{round(score, 2)}:{bbox_key}"
        now = time.monotonic()
        if dedupe_key == self._last_promoted_fall_key and now - self._last_promoted_fall_at < 2.0:
            return
        self._last_promoted_fall_key = dedupe_key
        self._last_promoted_fall_at = now

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._fall_alarm_callback(dict(payload)))

    def _draw_fall_overlay(self, image, payload: dict[str, Any]):
        try:
            import cv2
        except Exception:
            return image, False
        if not payload:
            return image, False
        observed_at = self._coerce_positive(payload.get("_observed_at"))
        if observed_at > 0 and time.time() - observed_at > self._max_payload_age_seconds:
            return image, False

        h, w = image.shape[:2]
        frame_width = self._coerce_positive(payload.get("frame_width")) or float(w)
        frame_height = self._coerce_positive(payload.get("frame_height")) or float(h)
        bbox = payload.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return image, False
        try:
            x1, y1, x2, y2 = [float(v) for v in bbox]
        except (TypeError, ValueError):
            return image, False
        x1 = max(0, min(w - 1, int(round((x1 / frame_width) * w))))
        x2 = max(0, min(w - 1, int(round((x2 / frame_width) * w))))
        y1 = max(0, min(h - 1, int(round((y1 / frame_height) * h))))
        y2 = max(0, min(h - 1, int(round((y2 / frame_height) * h))))
        if x2 <= x1 or y2 <= y1:
            return image, False

        state = str(payload.get("state") or payload.get("event_type") or "tracked").strip() or "tracked"
        score = self._coerce_positive(payload.get("fall_score"))
        color = (0, 64, 255)
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 3)
        label = f"{state} {score:.2f}".strip()
        text_size, baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.62, 2)
        text_w, text_h = text_size
        text_y = max(text_h + 10, y1 - 8)
        cv2.rectangle(
            image,
            (x1 - 4, text_y - text_h - 8),
            (x1 + text_w + 6, text_y + baseline + 4),
            color,
            -1,
        )
        cv2.putText(
            image,
            label,
            (x1, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        return image, True

    def _draw_pose_overlay(self, image, payload: dict[str, Any]):
        try:
            import cv2
        except Exception:
            return image, False
        tracks = payload.get("tracks")
        if not isinstance(tracks, list) or not tracks:
            return image, False
        observed_at = self._coerce_positive(payload.get("_observed_at"))
        if observed_at > 0 and time.time() - observed_at > self._max_payload_age_seconds:
            return image, False

        h, w = image.shape[:2]
        frame_width = self._coerce_positive(payload.get("frame_width")) or float(w)
        frame_height = self._coerce_positive(payload.get("frame_height")) or float(h)
        bones = (
            (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
            (5, 11), (6, 12), (11, 12), (11, 13), (13, 15),
            (12, 14), (14, 16), (0, 5), (0, 6),
        )

        for item in tracks:
            if not isinstance(item, dict):
                continue
            bbox = item.get("bbox")
            color = (0, 80, 255)
            if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                try:
                    x1, y1, x2, y2 = [float(v) for v in bbox]
                    x1 = max(0, min(w - 1, int(round((x1 / frame_width) * w))))
                    x2 = max(0, min(w - 1, int(round((x2 / frame_width) * w))))
                    y1 = max(0, min(h - 1, int(round((y1 / frame_height) * h))))
                    y2 = max(0, min(h - 1, int(round((y2 / frame_height) * h))))
                    if x2 > x1 and y2 > y1:
                        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
                except (TypeError, ValueError):
                    pass

            label = str(item.get("posture_label") or item.get("state_label") or "unknown")
            score = self._coerce_positive(item.get("posture_score") or item.get("state_score"))
            text = f"{label} {score:.2f}".strip()
            keypoints = item.get("keypoints")
            if not isinstance(keypoints, list):
                continue
            scaled_points: list[tuple[int, int, float] | None] = []
            for point in keypoints:
                if not isinstance(point, (list, tuple)) or len(point) < 2:
                    scaled_points.append(None)
                    continue
                try:
                    px = float(point[0])
                    py = float(point[1])
                    pconf = float(point[2]) if len(point) >= 3 else 1.0
                except (TypeError, ValueError):
                    scaled_points.append(None)
                    continue
                tx = max(0, min(w - 1, int(round((px / frame_width) * w))))
                ty = max(0, min(h - 1, int(round((py / frame_height) * h))))
                scaled_points.append((tx, ty, pconf))

            text_anchor = next((point for point in scaled_points if point is not None and point[2] >= 0.15), None)
            if text_anchor is not None:
                text_size, baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.56, 2)
                text_w, text_h = text_size
                text_x = max(0, text_anchor[0] - 4)
                text_y = max(text_h + 10, text_anchor[1] - 12)
                cv2.rectangle(
                    image,
                    (text_x - 4, text_y - text_h - 8),
                    (text_x + text_w + 6, text_y + baseline + 4),
                    color,
                    -1,
                )
                cv2.putText(
                    image,
                    text,
                    (text_x, text_y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.56,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA,
                )

            for bone_a, bone_b in bones:
                if bone_a >= len(scaled_points) or bone_b >= len(scaled_points):
                    continue
                point_a = scaled_points[bone_a]
                point_b = scaled_points[bone_b]
                if point_a is None or point_b is None:
                    continue
                if point_a[2] < 0.18 or point_b[2] < 0.18:
                    continue
                cv2.line(
                    image,
                    (point_a[0], point_a[1]),
                    (point_b[0], point_b[1]),
                    color,
                    3,
                    cv2.LINE_AA,
                )

            for point in scaled_points:
                if point is None or point[2] < 0.15:
                    continue
                cv2.circle(image, (point[0], point[1]), 5, (255, 255, 255), -1)
                cv2.circle(image, (point[0], point[1]), 2, color, -1)
        return image, True

    def _draw_status_badge(
        self,
        image,
        *,
        pose_payload: dict[str, Any] | None,
        fall_payload: dict[str, Any] | None,
        rendered_pose: bool,
        rendered_fall: bool,
    ):
        try:
            import cv2
        except Exception:
            return image
        h, w = image.shape[:2]
        if rendered_pose or rendered_fall:
            status = "Processed: overlay active"
            detail = "pose" if rendered_pose else ""
            if rendered_fall:
                detail = f"{detail} fall-box".strip()
            color = (24, 145, 70)
        else:
            status = "Processed: no renderable person/pose"
            pose_status = str((pose_payload or {}).get("status") or "empty")
            fall_status = str((fall_payload or {}).get("status") or "empty")
            detail = f"pose={pose_status} fall={fall_status}"
            color = (0, 136, 255)

        lines = [status, detail]
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.62
        thickness = 2
        sizes = [cv2.getTextSize(line, font, scale, thickness)[0] for line in lines if line]
        box_w = min(w - 24, max((size[0] for size in sizes), default=260) + 28)
        box_h = 28 + 28 * len([line for line in lines if line])
        x1, y1 = 12, 12
        overlay = image.copy()
        cv2.rectangle(overlay, (x1, y1), (x1 + box_w, y1 + box_h), (15, 22, 36), -1)
        image = cv2.addWeighted(overlay, 0.72, image, 0.28, 0)
        cv2.rectangle(image, (x1, y1), (x1 + box_w, y1 + box_h), color, 2)
        y = y1 + 28
        for line in lines:
            if not line:
                continue
            cv2.putText(image, line, (x1 + 14, y), font, scale, (255, 255, 255), thickness, cv2.LINE_AA)
            y += 28
        return image

    def overlay_status(self) -> dict[str, object]:
        self._poll_fallback_futures()
        pose_payload = self._pose_payload_provider()
        fall_payload = self._fall_payload_provider()
        pose_valid = self._is_fresh_pose_payload(pose_payload)
        fall_valid = self._is_fresh_fall_payload(fall_payload)
        pose_fallback_age = None if self._pose_fallback_at is None else max(0.0, time.time() - self._pose_fallback_at)
        fall_fallback_age = None if self._fall_fallback_at is None else max(0.0, time.time() - self._fall_fallback_at)
        pose_fallback_valid = (
            self._is_fresh_pose_payload(self._pose_fallback_payload)
            and pose_fallback_age is not None
            and pose_fallback_age <= self._max_payload_age_seconds
        )
        fall_fallback_valid = (
            self._is_fresh_fall_payload(self._fall_fallback_payload)
            and fall_fallback_age is not None
            and fall_fallback_age <= self._max_payload_age_seconds
        )
        source_pose = pose_payload if pose_valid else (self._pose_fallback_payload if pose_fallback_valid else None)
        track_count = 0
        if isinstance(source_pose, dict) and isinstance(source_pose.get("tracks"), list):
            track_count = len(source_pose["tracks"])
        model_overlay = bool(pose_valid or pose_fallback_valid or fall_valid or fall_fallback_valid)
        diagnostic_age = (
            None if self._diagnostic_overlay_at is None else max(0.0, time.time() - self._diagnostic_overlay_at)
        )
        diagnostic_valid = diagnostic_age is not None and diagnostic_age <= 8.0
        return {
            "type": "combined",
            "pose_payload_valid": pose_valid,
            "pose_fallback_valid": pose_fallback_valid,
            "pose_fallback_age_seconds": pose_fallback_age,
            "pose_track_count": track_count,
            "fall_payload_valid": fall_valid,
            "fall_fallback_valid": fall_fallback_valid,
            "fall_fallback_age_seconds": fall_fallback_age,
            "has_model_overlay": model_overlay,
            "diagnostic_overlay_valid": diagnostic_valid,
            "diagnostic_overlay_age_seconds": diagnostic_age,
            "diagnostic_overlay_reason": self._diagnostic_overlay_reason,
            "has_renderable_overlay": bool(model_overlay or diagnostic_valid),
            "pose_fallback_running": bool(self._pose_fallback_future and not self._pose_fallback_future.done()),
            "fall_fallback_running": bool(self._fall_fallback_future and not self._fall_fallback_future.done()),
            "last_pose_fallback_attempt_at": self._last_pose_fallback_attempt_at or None,
            "last_fall_fallback_attempt_at": self._last_fall_fallback_attempt_at or None,
        }

    def _is_fresh_pose_payload(self, payload: Any) -> bool:
        if not CameraPoseFrameHub._is_valid_pose_payload(payload):
            return False
        observed_at = self._coerce_positive(payload.get("_observed_at")) if isinstance(payload, dict) else 0.0
        return observed_at <= 0 or time.time() - observed_at <= self._max_payload_age_seconds

    def _is_fresh_fall_payload(self, payload: Any) -> bool:
        if not CameraDetectionFrameHub._is_valid_detection_payload(payload):
            return False
        observed_at = self._coerce_positive(payload.get("_observed_at")) if isinstance(payload, dict) else 0.0
        return observed_at <= 0 or time.time() - observed_at <= self._max_payload_age_seconds

    @staticmethod
    def _coerce_positive(value: object) -> float:
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 0.0
