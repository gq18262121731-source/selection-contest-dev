from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.services.robot_audio.base import AudioCaptureTimeoutError
from backend.services.robot_audio.webrtc_source import (
    Go2WebRTCAudioSource,
    Go2WebRTCAudioSourceError,
    WebRTCAudioSourceErrorCode,
)


class _FakeArray:
    def __init__(self, payload: bytes, *, itemsize: int = 2) -> None:
        self._payload = payload
        self.dtype = SimpleNamespace(itemsize=itemsize)

    def tobytes(self) -> bytes:
        return self._payload


class _FakeFrame:
    def __init__(
        self,
        payload: bytes,
        *,
        sample_rate: int = 48_000,
        samples: int = 480,
        channels: int = 2,
        format_name: str = "s16",
        conversion_error: str | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.samples = samples
        self.layout = SimpleNamespace(channels=tuple(range(channels)))
        self.format = SimpleNamespace(name=format_name)
        self._array = _FakeArray(payload)
        self._conversion_error = conversion_error

    def to_ndarray(self) -> _FakeArray:
        if self._conversion_error:
            raise RuntimeError(self._conversion_error)
        return self._array


class _FakeAudioChannel:
    def __init__(self, frames: list[_FakeFrame]) -> None:
        self.frames = frames
        self.callbacks = []
        self.switch_calls: list[bool] = []
        self._emit_task = None

    def add_track_callback(self, callback) -> None:
        self.callbacks.append(callback)

    def switchAudioChannel(self, enabled: bool) -> None:
        self.switch_calls.append(enabled)
        if enabled and self.frames:
            self._emit_task = asyncio.get_running_loop().create_task(
                self._emit_frames()
            )

    async def _emit_frames(self) -> None:
        for frame in self.frames:
            for callback in self.callbacks:
                await callback(frame)


class _FakeConnection:
    def __init__(
        self,
        frames: list[_FakeFrame],
        *,
        connect_error: str | None = None,
    ) -> None:
        self.audio = _FakeAudioChannel(frames)
        self.connect_error = connect_error
        self.connected = False
        self.disconnected = False

    async def connect(self) -> None:
        if self.connect_error:
            raise RuntimeError(self.connect_error)
        self.connected = True

    async def disconnect(self) -> None:
        self.disconnected = True


def test_go2_webrtc_source_captures_raw_pcm_and_cleans_up() -> None:
    frame_payload = b"\x00\x01" * 960
    connection = _FakeConnection(
        [_FakeFrame(frame_payload), _FakeFrame(frame_payload)]
    )
    source = Go2WebRTCAudioSource(
        "192.168.123.161",
        capture_duration_seconds=0.02,
        connection_factory=lambda: connection,
    )

    capture = asyncio.run(source.record())

    assert capture.data == frame_payload * 2
    assert capture.format == "pcm_s16le"
    assert capture.sample_rate_hz == 48_000
    assert capture.channels == 2
    assert capture.sample_width_bytes == 2
    assert connection.connected is True
    assert connection.disconnected is True
    assert connection.audio.switch_calls == [True, False]


def test_go2_webrtc_source_maps_connection_failure_and_disconnects() -> None:
    connection = _FakeConnection([], connect_error="robot offline")
    source = Go2WebRTCAudioSource(
        "192.168.123.161",
        connection_factory=lambda: connection,
    )

    with pytest.raises(Go2WebRTCAudioSourceError) as exc_info:
        asyncio.run(source.record())

    assert exc_info.value.code is WebRTCAudioSourceErrorCode.CONNECT_FAILED
    assert str(exc_info.value) == "WEBRTC_CONNECT_FAILED: robot offline"
    assert connection.disconnected is True


def test_go2_webrtc_source_times_out_and_disables_audio_channel() -> None:
    connection = _FakeConnection([])
    source = Go2WebRTCAudioSource(
        "192.168.123.161",
        connection_factory=lambda: connection,
    )

    with pytest.raises(AudioCaptureTimeoutError, match="audio capture exceeded"):
        asyncio.run(source.record(timeout_seconds=0.001))

    assert connection.audio.switch_calls == [True, False]
    assert connection.disconnected is True


def test_go2_webrtc_source_reports_frame_conversion_failure() -> None:
    connection = _FakeConnection(
        [_FakeFrame(b"", conversion_error="invalid audio frame")]
    )
    source = Go2WebRTCAudioSource(
        "192.168.123.161",
        connection_factory=lambda: connection,
    )

    with pytest.raises(Go2WebRTCAudioSourceError) as exc_info:
        asyncio.run(source.record())

    assert exc_info.value.code is WebRTCAudioSourceErrorCode.CAPTURE_FAILED
    assert "invalid audio frame" in str(exc_info.value)
    assert connection.audio.switch_calls == [True, False]
    assert connection.disconnected is True
