from __future__ import annotations

import inspect
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from backend.services.robot_audio.sink import AudioSink


class WebRTCAudioErrorCode(str, Enum):
    DEPENDENCY_MISSING = "WEBRTC_DEPENDENCY_MISSING"
    CONNECT_FAILED = "WEBRTC_CONNECT_FAILED"
    FILE_NOT_FOUND = "AUDIO_FILE_NOT_FOUND"
    UNSUPPORTED_FORMAT = "AUDIO_FORMAT_UNSUPPORTED"
    MEDIA_OPEN_FAILED = "WEBRTC_MEDIA_OPEN_FAILED"
    NO_AUDIO_TRACK = "WEBRTC_NO_AUDIO_TRACK"
    PLAYBACK_FAILED = "WEBRTC_PLAYBACK_FAILED"
    DISCONNECT_FAILED = "WEBRTC_DISCONNECT_FAILED"


class Go2WebRTCAudioSinkError(RuntimeError):
    def __init__(self, code: WebRTCAudioErrorCode, detail: str) -> None:
        self.code = code
        self.detail = str(detail or "").strip() or code.value
        super().__init__(f"{code.value}: {self.detail}")


class Go2WebRTCAudioSink(AudioSink):
    """Play one WAV file through the Go2 LocalSTA WebRTC audio channel."""

    def __init__(
        self,
        robot_ip: str,
        *,
        aes_128_key: str | None = None,
        play_timeout_seconds: float = 15.0,
        connection_factory: Callable[[], Any] | None = None,
        media_player_factory: Callable[[str], Any] | None = None,
    ) -> None:
        super().__init__(play_timeout_seconds=play_timeout_seconds)
        normalized_ip = str(robot_ip or "").strip()
        if not normalized_ip:
            raise ValueError("robot_ip is required")
        self._robot_ip = normalized_ip
        self._aes_128_key = str(aes_128_key or "").strip() or None
        self._connection_factory = (
            connection_factory or self._create_default_connection
        )
        self._media_player_factory = (
            media_player_factory or self._create_default_media_player
        )

    @property
    def robot_ip(self) -> str:
        return self._robot_ip

    async def _play_file(self, audio_file: Path) -> None:
        self._validate_audio_file(audio_file)

        connection: Any | None = None
        peer_connection: Any | None = None
        audio_track: Any | None = None
        sender: Any | None = None
        primary_error: BaseException | None = None

        try:
            try:
                connection = self._connection_factory()
                await self._await_if_needed(connection.connect())
            except Go2WebRTCAudioSinkError:
                raise
            except Exception as exc:
                raise Go2WebRTCAudioSinkError(
                    WebRTCAudioErrorCode.CONNECT_FAILED,
                    str(exc) or exc.__class__.__name__,
                ) from exc

            peer_connection = getattr(connection, "pc", None)
            if peer_connection is None:
                raise Go2WebRTCAudioSinkError(
                    WebRTCAudioErrorCode.CONNECT_FAILED,
                    "WebRTC connection has no peer connection",
                )

            try:
                player = self._media_player_factory(str(audio_file))
            except Go2WebRTCAudioSinkError:
                raise
            except Exception as exc:
                raise Go2WebRTCAudioSinkError(
                    WebRTCAudioErrorCode.MEDIA_OPEN_FAILED,
                    str(exc) or exc.__class__.__name__,
                ) from exc

            audio_track = getattr(player, "audio", None)
            if audio_track is None:
                raise Go2WebRTCAudioSinkError(
                    WebRTCAudioErrorCode.NO_AUDIO_TRACK,
                    "WAV file does not contain an audio track",
                )

            track_ended = self._track_ended_event(audio_track)
            try:
                sender = peer_connection.addTrack(audio_track)
                await track_ended.wait()
            except Go2WebRTCAudioSinkError:
                raise
            except Exception as exc:
                raise Go2WebRTCAudioSinkError(
                    WebRTCAudioErrorCode.PLAYBACK_FAILED,
                    str(exc) or exc.__class__.__name__,
                ) from exc
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            cleanup_error = await self._cleanup(
                connection=connection,
                peer_connection=peer_connection,
                sender=sender,
                audio_track=audio_track,
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
            raise Go2WebRTCAudioSinkError(
                WebRTCAudioErrorCode.DEPENDENCY_MISSING,
                "install unitree_webrtc_connect and its aiortc dependencies",
            ) from exc

        return UnitreeWebRTCConnection(
            WebRTCConnectionMethod.LocalSTA,
            ip=self._robot_ip,
            aes_128_key=self._aes_128_key,
        )

    @staticmethod
    def _create_default_media_player(audio_file: str) -> Any:
        try:
            from aiortc.contrib.media import MediaPlayer
        except ImportError as exc:
            raise Go2WebRTCAudioSinkError(
                WebRTCAudioErrorCode.DEPENDENCY_MISSING,
                "install aiortc to create the WebRTC audio track",
            ) from exc
        return MediaPlayer(audio_file)

    @staticmethod
    def _validate_audio_file(audio_file: Path) -> None:
        if not audio_file.is_file():
            raise Go2WebRTCAudioSinkError(
                WebRTCAudioErrorCode.FILE_NOT_FOUND,
                str(audio_file),
            )
        if audio_file.suffix.lower() != ".wav":
            raise Go2WebRTCAudioSinkError(
                WebRTCAudioErrorCode.UNSUPPORTED_FORMAT,
                "Go2 WebRTC sink currently accepts WAV files only",
            )

    @staticmethod
    def _track_ended_event(audio_track: Any):
        import asyncio

        event = asyncio.Event()
        on = getattr(audio_track, "on", None)
        if not callable(on):
            raise Go2WebRTCAudioSinkError(
                WebRTCAudioErrorCode.PLAYBACK_FAILED,
                "audio track does not expose an ended event",
            )

        on("ended", event.set)
        if getattr(audio_track, "readyState", None) == "ended":
            event.set()
        return event

    async def _cleanup(
        self,
        *,
        connection: Any | None,
        peer_connection: Any | None,
        sender: Any | None,
        audio_track: Any | None,
    ) -> Go2WebRTCAudioSinkError | None:
        errors: list[str] = []

        if audio_track is not None:
            stop = getattr(audio_track, "stop", None)
            if callable(stop):
                try:
                    await self._await_if_needed(stop())
                except Exception as exc:
                    errors.append(f"track stop failed: {exc}")

        if peer_connection is not None and sender is not None:
            remove_track = getattr(peer_connection, "removeTrack", None)
            if callable(remove_track):
                try:
                    await self._await_if_needed(remove_track(sender))
                except Exception as exc:
                    errors.append(f"track removal failed: {exc}")

        if connection is not None:
            disconnect = getattr(connection, "disconnect", None)
            if callable(disconnect):
                try:
                    await self._await_if_needed(disconnect())
                except Exception as exc:
                    errors.append(f"disconnect failed: {exc}")

        if not errors:
            return None
        return Go2WebRTCAudioSinkError(
            WebRTCAudioErrorCode.DISCONNECT_FAILED,
            "; ".join(errors),
        )

    @staticmethod
    async def _await_if_needed(value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value
