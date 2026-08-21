from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

from backend.services.robot_audio.base import (
    AudioCapture,
    AudioCaptureError,
    AudioCaptureTimeoutError,
    utc_now,
)
from backend.services.robot_audio.sink import AudioSink
from backend.services.robot_audio.source import AudioSource


class MockAudioSource(AudioSource):
    def __init__(
        self,
        data: bytes = b"mock-audio",
        *,
        audio_format: str = "pcm_s16le",
        sample_rate_hz: int = 48_000,
        channels: int = 2,
        sample_width_bytes: int = 2,
        capture_delay_seconds: float = 0.0,
        error: str | None = None,
    ) -> None:
        self._data = bytes(data)
        self._audio_format = audio_format
        self._sample_rate_hz = sample_rate_hz
        self._channels = channels
        self._sample_width_bytes = sample_width_bytes
        self._capture_delay_seconds = max(0.0, float(capture_delay_seconds))
        self._error = error

    async def record(self, *, timeout_seconds: float | None = None) -> AudioCapture:
        async def capture() -> AudioCapture:
            if self._capture_delay_seconds:
                await asyncio.sleep(self._capture_delay_seconds)
            if self._error:
                raise AudioCaptureError(self._error)
            return AudioCapture(
                audio_id=uuid4().hex,
                data=self._data,
                format=self._audio_format,
                sample_rate_hz=self._sample_rate_hz,
                channels=self._channels,
                sample_width_bytes=self._sample_width_bytes,
                captured_at=utc_now(),
            )

        if timeout_seconds is None:
            return await capture()
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        try:
            return await asyncio.wait_for(capture(), timeout=float(timeout_seconds))
        except TimeoutError as exc:
            raise AudioCaptureTimeoutError(
                f"audio capture exceeded {timeout_seconds:g} seconds"
            ) from exc


class MockAudioSink(AudioSink):
    def __init__(
        self,
        *,
        playback_delay_seconds: float = 0.0,
        error: str | None = None,
        play_timeout_seconds: float = 15.0,
    ) -> None:
        super().__init__(play_timeout_seconds=play_timeout_seconds)
        self._playback_delay_seconds = max(0.0, float(playback_delay_seconds))
        self._error = error
        self.played_files: list[str] = []

    async def _play_file(self, audio_file: Path) -> None:
        self.played_files.append(str(audio_file))
        if self._playback_delay_seconds:
            await asyncio.sleep(self._playback_delay_seconds)
        if self._error:
            raise RuntimeError(self._error)
