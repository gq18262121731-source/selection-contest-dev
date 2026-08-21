from __future__ import annotations

from abc import ABC, abstractmethod

from backend.services.robot_audio.base import AudioCapture


class AudioSource(ABC):
    """Hardware-neutral source of one captured speech segment."""

    @abstractmethod
    async def record(self, *, timeout_seconds: float | None = None) -> AudioCapture:
        """Capture one audio segment or raise an AudioCaptureError."""
