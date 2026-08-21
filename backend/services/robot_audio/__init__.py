"""Robot audio device abstractions for the Go2 companion agent."""

from backend.services.robot_audio.base import (
    AudioCapture,
    AudioCaptureError,
    AudioCaptureTimeoutError,
    AudioPlayback,
    AudioSinkState,
    PlaybackStatus,
)
from backend.services.robot_audio.mock_audio import MockAudioSink, MockAudioSource
from backend.services.robot_audio.sink import AudioSink
from backend.services.robot_audio.source import AudioSource

__all__ = [
    "AudioCapture",
    "AudioCaptureError",
    "AudioCaptureTimeoutError",
    "AudioPlayback",
    "AudioSink",
    "AudioSinkState",
    "AudioSource",
    "MockAudioSink",
    "MockAudioSource",
    "PlaybackStatus",
]
