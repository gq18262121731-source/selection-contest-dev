from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from backend.services.robot_audio.base import (
    AudioPlayback,
    AudioSinkState,
    PlaybackStatus,
    utc_now,
)

DEFAULT_PLAY_TIMEOUT_SECONDS = 15.0


class AudioSink(ABC):
    """Managed audio sink with a shared playback state and timeout contract."""

    def __init__(self, *, play_timeout_seconds: float = DEFAULT_PLAY_TIMEOUT_SECONDS) -> None:
        if play_timeout_seconds <= 0:
            raise ValueError("play_timeout_seconds must be greater than zero")
        self._play_timeout_seconds = float(play_timeout_seconds)
        self._state = AudioSinkState.IDLE
        self._play_lock = asyncio.Lock()
        self._playbacks: dict[str, AudioPlayback] = {}

    @property
    def state(self) -> AudioSinkState:
        return self._state

    @property
    def play_timeout_seconds(self) -> float:
        return self._play_timeout_seconds

    def get_playback(self, audio_id: str) -> AudioPlayback | None:
        return self._playbacks.get(str(audio_id or "").strip())

    async def play(
        self,
        audio_file: str | Path,
        *,
        audio_id: str | None = None,
        timeout_seconds: float | None = None,
    ) -> AudioPlayback:
        path = Path(audio_file).expanduser()
        normalized_audio_id = str(audio_id or "").strip() or uuid4().hex
        if normalized_audio_id in self._playbacks:
            raise ValueError(f"audio_id already exists: {normalized_audio_id}")

        timeout = (
            self._play_timeout_seconds
            if timeout_seconds is None
            else float(timeout_seconds)
        )
        if timeout <= 0:
            raise ValueError("timeout_seconds must be greater than zero")

        playback = AudioPlayback(
            audio_id=normalized_audio_id,
            audio_file=str(path),
            status=PlaybackStatus.QUEUED,
            queued_at=utc_now(),
        )
        self._playbacks[normalized_audio_id] = playback

        async with self._play_lock:
            playback = replace(
                playback,
                status=PlaybackStatus.PLAYING,
                started_at=utc_now(),
            )
            self._playbacks[normalized_audio_id] = playback
            self._state = AudioSinkState.PLAYING
            try:
                await asyncio.wait_for(self._play_file(path), timeout=timeout)
            except TimeoutError:
                playback = replace(
                    playback,
                    status=PlaybackStatus.TIMEOUT,
                    finished_at=utc_now(),
                    error=f"playback exceeded {timeout:g} seconds",
                )
            except Exception as exc:
                playback = replace(
                    playback,
                    status=PlaybackStatus.ERROR,
                    finished_at=utc_now(),
                    error=str(exc) or exc.__class__.__name__,
                )
            else:
                playback = replace(
                    playback,
                    status=PlaybackStatus.FINISHED,
                    finished_at=utc_now(),
                )
            finally:
                self._playbacks[normalized_audio_id] = playback
                self._state = AudioSinkState.IDLE

        return playback

    @abstractmethod
    async def _play_file(self, audio_file: Path) -> None:
        """Send one audio file to the concrete output device."""
