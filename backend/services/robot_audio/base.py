from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AudioSinkState(str, Enum):
    IDLE = "idle"
    PLAYING = "playing"


class PlaybackStatus(str, Enum):
    QUEUED = "queued"
    PLAYING = "playing"
    FINISHED = "finished"
    ERROR = "error"
    TIMEOUT = "timeout"


class AudioCaptureError(RuntimeError):
    """Raised when an audio source cannot complete a recording."""


class AudioCaptureTimeoutError(AudioCaptureError):
    """Raised when an audio source exceeds its recording timeout."""


@dataclass(frozen=True)
class AudioCapture:
    audio_id: str
    data: bytes
    format: str
    sample_rate_hz: int
    channels: int
    sample_width_bytes: int
    captured_at: datetime

    def as_dict(self) -> dict[str, object]:
        return {
            "audio_id": self.audio_id,
            "format": self.format,
            "sample_rate_hz": self.sample_rate_hz,
            "channels": self.channels,
            "sample_width_bytes": self.sample_width_bytes,
            "captured_at": self.captured_at.isoformat(),
            "size_bytes": len(self.data),
        }


@dataclass(frozen=True)
class AudioPlayback:
    audio_id: str
    audio_file: str
    status: PlaybackStatus
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "audio_id": self.audio_id,
            "audio_file": self.audio_file,
            "status": self.status.value,
            "queued_at": self.queued_at.isoformat(),
            "started_at": (
                self.started_at.isoformat() if self.started_at is not None else None
            ),
            "finished_at": (
                self.finished_at.isoformat() if self.finished_at is not None else None
            ),
            "error": self.error,
        }
