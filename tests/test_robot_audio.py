from __future__ import annotations

import asyncio

import pytest

from backend.services.robot_audio import (
    AudioCaptureTimeoutError,
    AudioSinkState,
    MockAudioSink,
    MockAudioSource,
    PlaybackStatus,
)


def test_mock_audio_source_returns_device_neutral_capture() -> None:
    capture = asyncio.run(
        MockAudioSource(
            b"\x00\x01",
            sample_rate_hz=48_000,
            channels=2,
        ).record()
    )

    assert capture.data == b"\x00\x01"
    assert capture.sample_rate_hz == 48_000
    assert capture.channels == 2
    assert capture.as_dict()["size_bytes"] == 2


def test_mock_audio_source_reports_timeout() -> None:
    source = MockAudioSource(capture_delay_seconds=0.05)

    with pytest.raises(AudioCaptureTimeoutError, match="audio capture exceeded"):
        asyncio.run(source.record(timeout_seconds=0.001))


def test_mock_audio_sink_finishes_and_retains_terminal_playback(tmp_path) -> None:
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"RIFF-test")
    sink = MockAudioSink()

    result = asyncio.run(sink.play(audio_file, audio_id="test001"))

    assert result.status is PlaybackStatus.FINISHED
    assert result.started_at is not None
    assert result.finished_at is not None
    assert result.error is None
    assert sink.state is AudioSinkState.IDLE
    assert sink.get_playback("test001") == result
    assert result.as_dict()["status"] == "finished"
    assert sink.played_files == [str(audio_file)]


def test_mock_audio_sink_records_device_error_and_returns_idle(tmp_path) -> None:
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"RIFF-test")
    sink = MockAudioSink(error="speaker unavailable")

    result = asyncio.run(sink.play(audio_file, audio_id="test-error"))

    assert result.status is PlaybackStatus.ERROR
    assert result.error == "speaker unavailable"
    assert result.finished_at is not None
    assert sink.state is AudioSinkState.IDLE
    assert sink.get_playback("test-error") == result


def test_mock_audio_sink_records_timeout_and_returns_idle(tmp_path) -> None:
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"RIFF-test")
    sink = MockAudioSink(
        playback_delay_seconds=0.05,
        play_timeout_seconds=0.001,
    )

    result = asyncio.run(sink.play(audio_file, audio_id="test-timeout"))

    assert result.status is PlaybackStatus.TIMEOUT
    assert result.error == "playback exceeded 0.001 seconds"
    assert result.finished_at is not None
    assert sink.state is AudioSinkState.IDLE
    assert sink.get_playback("test-timeout") == result


def test_audio_sink_rejects_duplicate_audio_id(tmp_path) -> None:
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"RIFF-test")
    sink = MockAudioSink()

    asyncio.run(sink.play(audio_file, audio_id="duplicate"))

    with pytest.raises(ValueError, match="audio_id already exists"):
        asyncio.run(sink.play(audio_file, audio_id="duplicate"))
