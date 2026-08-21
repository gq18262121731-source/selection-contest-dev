from __future__ import annotations

import asyncio
import inspect
from enum import Enum
from typing import Any, Callable
from uuid import uuid4

from backend.services.robot_audio.base import (
    AudioCapture,
    AudioCaptureError,
    AudioCaptureTimeoutError,
    utc_now,
)
from backend.services.robot_audio.source import AudioSource


class WebRTCAudioSourceErrorCode(str, Enum):
    DEPENDENCY_MISSING = "WEBRTC_DEPENDENCY_MISSING"
    CONNECT_FAILED = "WEBRTC_CONNECT_FAILED"
    AUDIO_CHANNEL_UNAVAILABLE = "WEBRTC_AUDIO_CHANNEL_UNAVAILABLE"
    CAPTURE_FAILED = "WEBRTC_AUDIO_CAPTURE_FAILED"
    NO_AUDIO_FRAMES = "WEBRTC_NO_AUDIO_FRAMES"
    STREAM_FORMAT_CHANGED = "WEBRTC_AUDIO_FORMAT_CHANGED"
    DISCONNECT_FAILED = "WEBRTC_DISCONNECT_FAILED"


class Go2WebRTCAudioSourceError(AudioCaptureError):
    def __init__(self, code: WebRTCAudioSourceErrorCode, detail: str) -> None:
        self.code = code
        self.detail = str(detail or "").strip() or code.value
        super().__init__(f"{code.value}: {self.detail}")


class Go2WebRTCAudioSource(AudioSource):
    """Capture a fixed-duration raw PCM segment from the Go2 WebRTC microphone."""

    def __init__(
        self,
        robot_ip: str,
        *,
        aes_128_key: str | None = None,
        capture_duration_seconds: float = 5.0,
        record_timeout_seconds: float = 15.0,
        connection_factory: Callable[[], Any] | None = None,
    ) -> None:
        normalized_ip = str(robot_ip or "").strip()
        if not normalized_ip:
            raise ValueError("robot_ip is required")
        if capture_duration_seconds <= 0:
            raise ValueError("capture_duration_seconds must be greater than zero")
        if record_timeout_seconds <= 0:
            raise ValueError("record_timeout_seconds must be greater than zero")

        self._robot_ip = normalized_ip
        self._aes_128_key = str(aes_128_key or "").strip() or None
        self._capture_duration_seconds = float(capture_duration_seconds)
        self._record_timeout_seconds = float(record_timeout_seconds)
        self._connection_factory = (
            connection_factory or self._create_default_connection
        )

    @property
    def robot_ip(self) -> str:
        return self._robot_ip

    @property
    def capture_duration_seconds(self) -> float:
        return self._capture_duration_seconds

    async def record(self, *, timeout_seconds: float | None = None) -> AudioCapture:
        timeout = (
            self._record_timeout_seconds
            if timeout_seconds is None
            else float(timeout_seconds)
        )
        if timeout <= 0:
            raise ValueError("timeout_seconds must be greater than zero")

        try:
            return await asyncio.wait_for(self._record_once(), timeout=timeout)
        except TimeoutError as exc:
            raise AudioCaptureTimeoutError(
                f"audio capture exceeded {timeout:g} seconds"
            ) from exc

    async def _record_once(self) -> AudioCapture:
        connection: Any | None = None
        audio_channel: Any | None = None
        channel_enabled = False
        primary_error: BaseException | None = None
        capture_complete = asyncio.Event()
        chunks: list[bytes] = []
        stream_metadata: dict[str, Any] = {}
        captured_seconds = 0.0
        callback_error: Exception | None = None

        async def receive_frame(frame: Any) -> None:
            nonlocal callback_error, captured_seconds
            if capture_complete.is_set():
                return
            try:
                frame_data, metadata, frame_duration = self._frame_payload(frame)
                if not stream_metadata:
                    stream_metadata.update(metadata)
                elif metadata != stream_metadata:
                    raise Go2WebRTCAudioSourceError(
                        WebRTCAudioSourceErrorCode.STREAM_FORMAT_CHANGED,
                        f"expected {stream_metadata}, received {metadata}",
                    )
                chunks.append(frame_data)
                captured_seconds += frame_duration
                if captured_seconds >= self._capture_duration_seconds:
                    capture_complete.set()
            except Exception as exc:
                callback_error = exc
                capture_complete.set()

        try:
            try:
                connection = self._connection_factory()
                await self._await_if_needed(connection.connect())
            except Go2WebRTCAudioSourceError:
                raise
            except Exception as exc:
                raise Go2WebRTCAudioSourceError(
                    WebRTCAudioSourceErrorCode.CONNECT_FAILED,
                    str(exc) or exc.__class__.__name__,
                ) from exc

            audio_channel = getattr(connection, "audio", None)
            if audio_channel is None:
                raise Go2WebRTCAudioSourceError(
                    WebRTCAudioSourceErrorCode.AUDIO_CHANNEL_UNAVAILABLE,
                    "WebRTC connection has no audio channel",
                )

            add_callback = getattr(audio_channel, "add_track_callback", None)
            switch_channel = getattr(audio_channel, "switchAudioChannel", None)
            if not callable(add_callback) or not callable(switch_channel):
                raise Go2WebRTCAudioSourceError(
                    WebRTCAudioSourceErrorCode.AUDIO_CHANNEL_UNAVAILABLE,
                    "audio channel does not expose capture controls",
                )

            try:
                add_callback(receive_frame)
                await self._await_if_needed(switch_channel(True))
                channel_enabled = True
                await capture_complete.wait()
            except Go2WebRTCAudioSourceError:
                raise
            except Exception as exc:
                raise Go2WebRTCAudioSourceError(
                    WebRTCAudioSourceErrorCode.CAPTURE_FAILED,
                    str(exc) or exc.__class__.__name__,
                ) from exc

            if callback_error is not None:
                if isinstance(callback_error, Go2WebRTCAudioSourceError):
                    raise callback_error
                raise Go2WebRTCAudioSourceError(
                    WebRTCAudioSourceErrorCode.CAPTURE_FAILED,
                    str(callback_error) or callback_error.__class__.__name__,
                ) from callback_error
            if not chunks or not stream_metadata:
                raise Go2WebRTCAudioSourceError(
                    WebRTCAudioSourceErrorCode.NO_AUDIO_FRAMES,
                    "capture completed without PCM frames",
                )

            return AudioCapture(
                audio_id=uuid4().hex,
                data=b"".join(chunks),
                format=stream_metadata["format"],
                sample_rate_hz=stream_metadata["sample_rate_hz"],
                channels=stream_metadata["channels"],
                sample_width_bytes=stream_metadata["sample_width_bytes"],
                captured_at=utc_now(),
            )
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            cleanup_error = await self._cleanup(
                connection=connection,
                audio_channel=audio_channel,
                channel_enabled=channel_enabled,
            )
            if cleanup_error is not None and primary_error is None:
                raise cleanup_error

    def _create_default_connection(self) -> Any:
        try:
            from unitree_webrtc_connect.webrtc_driver import (
                UnitreeWebRTCConnection,
                WebRTCConnectionMethod,
            )
        except ImportError as exc:
            raise Go2WebRTCAudioSourceError(
                WebRTCAudioSourceErrorCode.DEPENDENCY_MISSING,
                "install unitree_webrtc_connect and its aiortc dependencies",
            ) from exc

        return UnitreeWebRTCConnection(
            WebRTCConnectionMethod.LocalSTA,
            ip=self._robot_ip,
            aes_128_key=self._aes_128_key,
        )

    @staticmethod
    def _frame_payload(frame: Any) -> tuple[bytes, dict[str, Any], float]:
        array = frame.to_ndarray()
        payload = array.tobytes()
        if not payload:
            raise ValueError("audio frame is empty")

        sample_rate = int(getattr(frame, "sample_rate", 0) or 0)
        samples = int(getattr(frame, "samples", 0) or 0)
        sample_width = int(getattr(getattr(array, "dtype", None), "itemsize", 0) or 0)
        layout = getattr(frame, "layout", None)
        layout_channels = getattr(layout, "channels", None)
        channels = len(layout_channels) if layout_channels is not None else 0
        format_name = str(
            getattr(getattr(frame, "format", None), "name", "") or ""
        ).lower()

        if sample_rate <= 0 or samples <= 0 or sample_width <= 0 or channels <= 0:
            raise ValueError("audio frame metadata is incomplete")

        format_map = {
            "s16": "pcm_s16le",
            "s16p": "pcm_s16le_planar",
            "s32": "pcm_s32le",
            "s32p": "pcm_s32le_planar",
            "flt": "pcm_f32le",
            "fltp": "pcm_f32le_planar",
        }
        audio_format = format_map.get(format_name, f"pcm_{format_name or 'unknown'}")
        metadata = {
            "format": audio_format,
            "sample_rate_hz": sample_rate,
            "channels": channels,
            "sample_width_bytes": sample_width,
        }
        return payload, metadata, samples / sample_rate

    async def _cleanup(
        self,
        *,
        connection: Any | None,
        audio_channel: Any | None,
        channel_enabled: bool,
    ) -> Go2WebRTCAudioSourceError | None:
        errors: list[str] = []

        if audio_channel is not None and channel_enabled:
            switch_channel = getattr(audio_channel, "switchAudioChannel", None)
            if callable(switch_channel):
                try:
                    await self._await_if_needed(switch_channel(False))
                except Exception as exc:
                    errors.append(f"audio channel shutdown failed: {exc}")

        if connection is not None:
            disconnect = getattr(connection, "disconnect", None)
            if callable(disconnect):
                try:
                    await self._await_if_needed(disconnect())
                except Exception as exc:
                    errors.append(f"disconnect failed: {exc}")

        if not errors:
            return None
        return Go2WebRTCAudioSourceError(
            WebRTCAudioSourceErrorCode.DISCONNECT_FAILED,
            "; ".join(errors),
        )

    @staticmethod
    async def _await_if_needed(value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value
