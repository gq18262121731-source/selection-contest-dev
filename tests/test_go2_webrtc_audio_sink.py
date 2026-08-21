from __future__ import annotations

import asyncio

from backend.services.robot_audio.base import AudioSinkState, PlaybackStatus
from backend.services.robot_audio.webrtc_sink import Go2WebRTCAudioSink


class _FakeAudioTrack:
    def __init__(self, *, auto_finish: bool = True) -> None:
        self.readyState = "live"
        self.auto_finish = auto_finish
        self.stopped = False
        self._ended_callback = None

    def on(self, event: str, callback) -> None:
        assert event == "ended"
        self._ended_callback = callback

    def finish(self) -> None:
        if self.readyState == "ended":
            return
        self.readyState = "ended"
        if self._ended_callback is not None:
            self._ended_callback()

    def stop(self) -> None:
        self.stopped = True
        self.finish()


class _FakePeerConnection:
    def __init__(self) -> None:
        self.added_track = None
        self.removed_sender = None

    def addTrack(self, track):
        self.added_track = track
        sender = object()
        if track.auto_finish:
            asyncio.get_running_loop().call_soon(track.finish)
        return sender

    def removeTrack(self, sender) -> None:
        self.removed_sender = sender


class _FakeConnection:
    def __init__(self, *, connect_error: str | None = None) -> None:
        self.pc = _FakePeerConnection()
        self.connect_error = connect_error
        self.connected = False
        self.disconnected = False

    async def connect(self) -> None:
        if self.connect_error:
            raise RuntimeError(self.connect_error)
        self.connected = True

    async def disconnect(self) -> None:
        self.disconnected = True


class _FakeMediaPlayer:
    def __init__(self, track: _FakeAudioTrack) -> None:
        self.audio = track


def test_go2_webrtc_sink_plays_wav_and_cleans_up(tmp_path) -> None:
    audio_file = tmp_path / "hello.wav"
    audio_file.write_bytes(b"RIFF-test")
    connection = _FakeConnection()
    track = _FakeAudioTrack()
    sink = Go2WebRTCAudioSink(
        "192.168.8.181",
        connection_factory=lambda: connection,
        media_player_factory=lambda _: _FakeMediaPlayer(track),
    )

    result = asyncio.run(sink.play(audio_file, audio_id="hello001"))

    assert result.status is PlaybackStatus.FINISHED
    assert result.error is None
    assert sink.state is AudioSinkState.IDLE
    assert connection.connected is True
    assert connection.disconnected is True
    assert connection.pc.added_track is track
    assert connection.pc.removed_sender is not None
    assert track.stopped is True


def test_go2_webrtc_sink_maps_connection_failure(tmp_path) -> None:
    audio_file = tmp_path / "hello.wav"
    audio_file.write_bytes(b"RIFF-test")
    connection = _FakeConnection(connect_error="robot offline")
    sink = Go2WebRTCAudioSink(
        "192.168.8.181",
        connection_factory=lambda: connection,
        media_player_factory=lambda _: None,
    )

    result = asyncio.run(sink.play(audio_file, audio_id="connect-error"))

    assert result.status is PlaybackStatus.ERROR
    assert result.error == "WEBRTC_CONNECT_FAILED: robot offline"
    assert sink.state is AudioSinkState.IDLE
    assert connection.disconnected is True


def test_go2_webrtc_sink_uses_shared_timeout_and_cleans_up(tmp_path) -> None:
    audio_file = tmp_path / "hello.wav"
    audio_file.write_bytes(b"RIFF-test")
    connection = _FakeConnection()
    track = _FakeAudioTrack(auto_finish=False)
    sink = Go2WebRTCAudioSink(
        "192.168.8.181",
        play_timeout_seconds=0.001,
        connection_factory=lambda: connection,
        media_player_factory=lambda _: _FakeMediaPlayer(track),
    )

    result = asyncio.run(sink.play(audio_file, audio_id="timeout"))

    assert result.status is PlaybackStatus.TIMEOUT
    assert result.error == "playback exceeded 0.001 seconds"
    assert sink.state is AudioSinkState.IDLE
    assert connection.disconnected is True
    assert track.stopped is True


def test_go2_webrtc_sink_rejects_non_wav_without_connecting(tmp_path) -> None:
    audio_file = tmp_path / "hello.mp3"
    audio_file.write_bytes(b"not-wav")
    connection = _FakeConnection()
    sink = Go2WebRTCAudioSink(
        "192.168.8.181",
        connection_factory=lambda: connection,
        media_player_factory=lambda _: None,
    )

    result = asyncio.run(sink.play(audio_file, audio_id="wrong-format"))

    assert result.status is PlaybackStatus.ERROR
    assert result.error is not None
    assert result.error.startswith("AUDIO_FORMAT_UNSUPPORTED:")
    assert connection.connected is False
    assert connection.disconnected is False
