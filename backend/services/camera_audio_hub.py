from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress

from fastapi import WebSocket

from backend.config import Settings
from backend.services.camera_service import CameraService


logger = logging.getLogger(__name__)


class CameraAudioHub:
    """Fan out a single RTSP audio reader to multiple websocket listeners."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._audio_task: asyncio.Task[None] | None = None
        self._last_error: str | None = None
        self._active_url: str | None = None
        self._chunks_total = 0
        self._bytes_total = 0
        self._started_at: float | None = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._clients.add(websocket)
            if self._audio_task is None or self._audio_task.done():
                self._audio_task = asyncio.create_task(self._audio_loop())

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(websocket)
            if not self._clients and self._audio_task and not self._audio_task.done():
                self._audio_task.cancel()
                self._audio_task = None

    async def shutdown(self) -> None:
        async with self._lock:
            clients = list(self._clients)
            self._clients.clear()
            task = self._audio_task
            self._audio_task = None
        for websocket in clients:
            with suppress(Exception):
                await websocket.close()
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    def status(self) -> dict[str, object]:
        elapsed = time.monotonic() - self._started_at if self._started_at else 0.0
        return {
            "clients": len(self._clients),
            "running": bool(self._audio_task and not self._audio_task.done()),
            "last_error": self._last_error,
            "active_url": self._mask_url(self._active_url),
            "sample_rate": self._settings.camera_audio_sample_rate,
            "format": "pcm_s16le",
            "channels": 1,
            "chunks_total": self._chunks_total,
            "bytes_total": self._bytes_total,
            "kbps": round((self._bytes_total * 8 / 1000 / elapsed), 2) if elapsed > 0 else 0.0,
        }

    async def _audio_loop(self) -> None:
        service = CameraService(self._settings)
        self._started_at = time.monotonic()
        try:
            while True:
                try:
                    await self._run_ffmpeg_audio(service)
                except Exception as exc:  # noqa: BLE001
                    self._last_error = f"{exc.__class__.__name__}: {exc}"
                    logger.warning("Camera audio stream failed, retrying: %s", self._last_error)
                    await asyncio.sleep(0.8)
        except asyncio.CancelledError:
            raise

    async def _run_ffmpeg_audio(self, service: CameraService) -> None:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        audio_url = service.build_audio_rtsp_url()
        urls = [audio_url]
        urls.extend(url for url in service.fallback_rtsp_urls if url not in urls)
        sample_rate = max(8000, min(self._settings.camera_audio_sample_rate, 48000))
        last_error = ""

        for url in urls:
            async with self._lock:
                if not self._clients:
                    return

            transport = "udp" if "/udp/" in url.lower() else "tcp"
            cmd = [
                ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-rtsp_transport",
                transport,
                "-timeout",
                str(int(self._settings.camera_snapshot_timeout_seconds * 1_000_000)),
                "-probesize",
                "5000000",
                "-i",
                url,
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                str(sample_rate),
                "-ac",
                "1",
                "-f",
                "s16le",
                "-",
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._active_url = url
            chunks = 0

            try:
                if process.stdout is None:
                    continue
                while True:
                    async with self._lock:
                        if not self._clients:
                            return

                    try:
                        chunk = await asyncio.wait_for(process.stdout.read(3200), timeout=15.0)
                    except asyncio.TimeoutError as exc:
                        raise RuntimeError("CAMERA_AUDIO_READ_TIMEOUT") from exc

                    if not chunk:
                        break

                    chunks += 1
                    self._chunks_total += 1
                    self._bytes_total += len(chunk)
                    self._last_error = None
                    await self._broadcast(chunk)
            finally:
                process.kill()
                with suppress(ProcessLookupError):
                    await asyncio.wait_for(process.wait(), timeout=2.0)

            stderr = b""
            if process.stderr:
                with suppress(Exception):
                    stderr = await asyncio.wait_for(process.stderr.read(), timeout=0.2)
            last_error = stderr.decode("utf-8", errors="replace").strip()
            if chunks > 0:
                return

        raise RuntimeError(last_error or "CAMERA_AUDIO_NO_CHUNKS")

    async def _broadcast(self, chunk: bytes) -> None:
        async with self._lock:
            clients = list(self._clients)

        stale: list[WebSocket] = []
        for websocket in clients:
            try:
                await websocket.send_bytes(chunk)
            except Exception:
                stale.append(websocket)

        if stale:
            async with self._lock:
                for websocket in stale:
                    self._clients.discard(websocket)

    def _mask_url(self, url: str | None) -> str | None:
        if not url:
            return None
        password = self._settings.camera_password
        return url.replace(password, "***") if password else url
