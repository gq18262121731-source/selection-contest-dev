from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from dataclasses import dataclass, field
from typing import AsyncGenerator
from urllib.parse import urlparse

from backend.config import Settings
from backend.services.camera_service import CameraService
from backend.services.camera_stream_hub import CameraFrameHub


_BOUNDARY = "frame"


@dataclass(frozen=True)
class FamilyStreamProfile:
    key: str
    source_profile: str
    source_width: int
    output_width: int
    target_fps: float
    jpeg_quality: int


@dataclass
class _FamilyPipelineState:
    profile: FamilyStreamProfile
    source_hub: CameraFrameHub
    clients: int = 0
    keep_warm_until: float = 0.0
    sticky_keep_warm: bool = False
    encoder_task: asyncio.Task[None] | None = None
    frame_event: asyncio.Event = field(default_factory=asyncio.Event)
    version: int = 0
    latest_jpeg: bytes | None = None
    latest_part: bytes | None = None
    latest_emitted_at: float | None = None
    latest_jpeg_bytes: int = 0
    average_jpeg_bytes: float = 0.0
    raw_frame_width: int = 0
    raw_frame_height: int = 0
    family_output_width: int = 0
    family_output_height: int = 0
    latest_encode_ms: float = 0.0
    average_encode_ms: float = 0.0
    last_error: str | None = None
    active_url: str | None = None
    active_source_type: str = "cache"
    source_fps: float = 0.0
    output_fps: float = 0.0
    frames_encoded_total: int = 0
    fallback_count: int = 0
    fallback_reason: str | None = None
    last_main_frame_at: float | None = None
    last_encoded_frame_at: float | None = None
    is_in_fallback: bool = False
    _fps_window_started_at: float = field(default_factory=time.monotonic)
    _fps_window_frames: int = 0

    def active(self) -> bool:
        return self.sticky_keep_warm or self.clients > 0 or time.monotonic() <= self.keep_warm_until

    def note_output_frame(self) -> None:
        self.frames_encoded_total += 1
        self._fps_window_frames += 1
        now = time.monotonic()
        elapsed = now - self._fps_window_started_at
        if elapsed >= 2.0:
            self.output_fps = self._fps_window_frames / elapsed
            self._fps_window_frames = 0
            self._fps_window_started_at = now


class FamilyCameraStreamService:
    """Serve clean family-facing MJPEG/JPEG streams from shared raw family hubs."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = asyncio.Lock()
        self._pipelines: dict[str, _FamilyPipelineState] = {}
        self._stale_source_after_seconds = 2.0
        self._idle_sticky_stale_source_after_seconds = 8.0
        self._hold_last_main_frame_seconds = 2.5
        self._active_quality = self.default_quality()

    def normalize_quality(self, quality: str | None) -> str:
        value = str(quality or "").strip().lower()
        if value in {"smooth", "balanced", "hd"}:
            return value
        if value == "quality":
            return "hd"
        return self.default_quality()

    def default_quality(self) -> str:
        configured = str(getattr(self._settings, "camera_stream_profile", "balanced") or "balanced").strip().lower()
        if configured == "smooth":
            return "smooth"
        if configured == "quality":
            return "hd"
        return "balanced"

    def current_quality(self) -> str:
        return self._active_quality or self.default_quality()

    def resolve_quality(self, quality: str | None) -> str:
        if quality is None or not str(quality).strip():
            return self.current_quality()
        return self.normalize_quality(quality)

    async def warm_default_profile(self) -> None:
        default_quality = self.default_quality()
        self._active_quality = default_quality
        await self._set_sticky_quality(default_quality)
        await self.prepare_profile(default_quality)

    async def reload_after_settings_update(self) -> None:
        async with self._lock:
            pipelines = list(self._pipelines.values())
            self._pipelines = {}
            self._active_quality = self.default_quality()

        for pipeline in pipelines:
            await self._dispose_pipeline(pipeline)

        await self.warm_default_profile()

    async def prepare_profile(self, quality: str) -> None:
        pipeline = await self._get_pipeline(self.normalize_quality(quality))
        pipeline.keep_warm_until = time.monotonic() + 3.0
        await pipeline.source_hub.start_keep_warm()
        self._ensure_pipeline_task(pipeline)

    async def activate_quality(self, quality: str) -> str:
        normalized = self.normalize_quality(quality)
        self._active_quality = normalized
        await self._set_sticky_quality(normalized)
        await self.prepare_profile(normalized)
        return normalized

    async def mjpeg_frames(self, quality: str) -> AsyncGenerator[bytes, None]:
        normalized = await self.activate_quality(quality)
        pipeline = await self._get_pipeline(normalized)
        pipeline.clients += 1
        pipeline.keep_warm_until = time.monotonic() + 5.0

        last_version = -1
        try:
            while True:
                pipeline.frame_event.clear()
                if pipeline.latest_part is not None and pipeline.version != last_version:
                    last_version = pipeline.version
                    yield pipeline.latest_part
                    continue

                try:
                    await asyncio.wait_for(pipeline.frame_event.wait(), timeout=4.0)
                except asyncio.TimeoutError:
                    if pipeline.latest_part is not None:
                        yield pipeline.latest_part
        finally:
            pipeline.clients = max(0, pipeline.clients - 1)
            pipeline.keep_warm_until = time.monotonic() + 1.0
            await self._cleanup_pipeline_if_idle(normalized)

    async def snapshot(self, quality: str) -> tuple[bytes | None, dict[str, object]]:
        normalized = self.resolve_quality(quality)
        pipeline = await self._get_pipeline(normalized)
        pipeline.keep_warm_until = time.monotonic() + 3.0
        await pipeline.source_hub.start_keep_warm()
        self._ensure_pipeline_task(pipeline)

        if pipeline.latest_jpeg is not None:
            return pipeline.latest_jpeg, self._pipeline_status(pipeline)

        for _ in range(12):
            await asyncio.sleep(0.15)
            if pipeline.latest_jpeg is not None:
                return pipeline.latest_jpeg, self._pipeline_status(pipeline)

        return None, self._pipeline_status(pipeline)

    def status(self) -> dict[str, object]:
        profiles: dict[str, object] = {}
        configured_stream_path = CameraService._normalize_path(self._settings.camera_stream_rtsp_path)
        configured_quality_path = CameraService._normalize_path(self._settings.camera_stream_quality_path)
        configured_rtsp_path = CameraService._normalize_path(self._settings.camera_rtsp_path)

        for quality in ("smooth", "balanced", "hd"):
            pipeline = self._pipelines.get(quality)
            if pipeline is None:
                profile = self._profile_for_quality(quality)
                profiles[quality] = {
                    "quality": quality,
                    "source_profile": profile.source_profile,
                    "target_fps": round(profile.target_fps, 2),
                    "jpeg_quality": profile.jpeg_quality,
                    "configured_stream_path": configured_stream_path,
                    "configured_quality_path": configured_quality_path,
                    "configured_rtsp_path": configured_rtsp_path,
                    "running": False,
                    "clients": 0,
                }
                continue
            profiles[quality] = self._pipeline_status(pipeline)

        active_profile = profiles.get(self.current_quality())
        return {
            "default_quality": self.default_quality(),
            "active_quality": self.current_quality(),
            "active_stream_path": active_profile.get("active_stream_path") if isinstance(active_profile, dict) else None,
            "active_source_type": active_profile.get("active_source_type") if isinstance(active_profile, dict) else None,
            "profiles": profiles,
        }

    async def _get_pipeline(self, quality: str) -> _FamilyPipelineState:
        async with self._lock:
            pipeline = self._pipelines.get(quality)
            if pipeline is not None:
                return pipeline

            profile = self._profile_for_quality(quality)
            source_settings = self._source_settings_for_profile(profile)
            pipeline = _FamilyPipelineState(
                profile=profile,
                source_hub=CameraFrameHub(source_settings),
            )
            self._pipelines[quality] = pipeline
            return pipeline

    async def _cleanup_pipeline_if_idle(self, quality: str) -> None:
        pipeline = self._pipelines.get(quality)
        if pipeline is None or pipeline.active():
            return
        await self._dispose_pipeline(pipeline)

    def _ensure_pipeline_task(self, pipeline: _FamilyPipelineState) -> None:
        if pipeline.encoder_task is None or pipeline.encoder_task.done():
            pipeline.encoder_task = asyncio.create_task(self._pipeline_loop(pipeline))

    async def _dispose_pipeline(self, pipeline: _FamilyPipelineState) -> None:
        pipeline.sticky_keep_warm = False
        await pipeline.source_hub.stop_keep_warm()
        if pipeline.encoder_task is not None and not pipeline.encoder_task.done():
            pipeline.encoder_task.cancel()
            with suppress(asyncio.CancelledError):
                await pipeline.encoder_task
        pipeline.encoder_task = None

    async def _pipeline_loop(self, pipeline: _FamilyPipelineState) -> None:
        last_source_at: float | None = None
        next_emit_at = 0.0

        try:
            while pipeline.active():
                source_frame, source_frame_at, source_status = await self._resolve_source_frame(
                    pipeline,
                )
                source_fps = float(source_status.get("source_fps") or 0.0)
                active_url = source_status.get("active_url")

                pipeline.source_fps = source_fps
                pipeline.active_url = str(active_url) if active_url else None
                pipeline.active_source_type = str(source_status.get("active_source_type") or "cache")

                if not source_frame or source_frame_at is None:
                    await asyncio.sleep(0.05)
                    continue

                if source_frame_at == last_source_at:
                    await asyncio.sleep(0.01)
                    continue

                now = time.monotonic()
                min_interval = 1.0 / max(1.0, pipeline.profile.target_fps)
                if now < next_emit_at:
                    await asyncio.sleep(min(0.01, next_emit_at - now))
                    continue
                emit_started_at = now

                if self._can_passthrough_source_frame(pipeline, source_status):
                    info = self._inspect_passthrough_frame(source_frame)
                    if info is None:
                        pipeline.last_error = "FAMILY_FRAME_INSPECT_FAILED"
                        await asyncio.sleep(0.02)
                        continue
                    pipeline.last_error = None
                    last_source_at = float(source_frame_at)
                    self._apply_passthrough_frame(pipeline, source_frame, info)
                    next_emit_at = max(next_emit_at + min_interval, emit_started_at + min_interval)
                    continue

                encoded, info = await asyncio.to_thread(
                    self._encode_family_frame,
                    source_frame,
                    width=pipeline.profile.output_width,
                    jpeg_quality=pipeline.profile.jpeg_quality,
                )
                if encoded is None:
                    pipeline.last_error = "FAMILY_JPEG_ENCODE_FAILED"
                    await asyncio.sleep(0.04)
                    continue

                pipeline.last_error = None
                last_source_at = float(source_frame_at)
                self._apply_encoded_frame(pipeline, encoded, info)
                next_emit_at = max(next_emit_at + min_interval, emit_started_at + min_interval)

            await pipeline.source_hub.stop_keep_warm()
        except asyncio.CancelledError:
            await pipeline.source_hub.stop_keep_warm()
            raise
        finally:
            pipeline.encoder_task = None

    async def _resolve_source_frame(
        self,
        pipeline: _FamilyPipelineState,
    ) -> tuple[bytes | None, float | None, dict[str, object]]:
        source_status = pipeline.source_hub.status()
        source_frame = pipeline.source_hub.latest_frame()
        source_frame_at = self._coerce_timestamp(source_status.get("latest_frame_at"))
        source_active_url = str(source_status.get("active_url") or "")
        source_is_snapshot_fallback = self._is_snapshot_fallback_url(source_active_url)
        freshness_threshold = (
            self._idle_sticky_stale_source_after_seconds
            if pipeline.clients == 0 and pipeline.sticky_keep_warm
            else self._stale_source_after_seconds
        )
        if self._is_fresh_frame(source_frame, source_frame_at, freshness_threshold) and not (
            pipeline.profile.key != "smooth" and source_is_snapshot_fallback
        ):
            if pipeline.profile.key != "smooth":
                pipeline.last_main_frame_at = source_frame_at
                pipeline.fallback_reason = None
                pipeline.is_in_fallback = False
            source_status = dict(source_status)
            source_status["active_source_type"] = self._classify_source_type(
                source_active_url,
                fallback=False,
            )
            return source_frame, source_frame_at, source_status

        if (
            pipeline.profile.key != "smooth"
            and pipeline.latest_jpeg is not None
            and pipeline.last_encoded_frame_at is not None
            and time.time() - pipeline.last_encoded_frame_at <= self._hold_last_main_frame_seconds
            and not source_is_snapshot_fallback
        ):
            source_status = dict(source_status)
            source_status["active_source_type"] = self._classify_source_type(
                source_active_url,
                fallback=False,
            )
            return source_frame, source_frame_at, source_status

        if pipeline.profile.key == "smooth":
            source_status = dict(source_status)
            source_status["active_source_type"] = self._classify_source_type(
                source_active_url,
                fallback=False,
            )
            return source_frame, source_frame_at, source_status

        fallback_hub = await self._fallback_hub()
        fallback_status = fallback_hub.status()
        fallback_frame = fallback_hub.latest_frame()
        fallback_frame_at = self._coerce_timestamp(fallback_status.get("latest_frame_at"))
        if self._is_fresh_frame(fallback_frame, fallback_frame_at, self._stale_source_after_seconds):
            fallback_status = dict(fallback_status)
            fallback_reason = self._fallback_reason_for_status(
                source_status,
                source_frame_at=source_frame_at,
            )
            if not pipeline.is_in_fallback or pipeline.fallback_reason != fallback_reason:
                pipeline.fallback_count += 1
            pipeline.fallback_reason = fallback_reason
            pipeline.is_in_fallback = True
            fallback_status["active_url"] = (
                f"{fallback_status.get('active_url') or 'family-smooth'} (fallback)"
            )
            if source_status.get("last_error") or fallback_reason:
                fallback_status["last_error"] = source_status.get("last_error")
            fallback_status["active_source_type"] = "fallback"
            fallback_status["fallback_reason"] = fallback_reason
            return fallback_frame, fallback_frame_at, fallback_status

        source_status = dict(source_status)
        source_status["active_source_type"] = self._classify_source_type(
            source_active_url,
            fallback=False,
        )
        return source_frame, source_frame_at, source_status

    def _can_passthrough_source_frame(
        self,
        pipeline: _FamilyPipelineState,
        source_status: dict[str, object],
    ) -> bool:
        active_source_type = str(source_status.get("active_source_type") or "")
        if active_source_type == "fallback":
            return False
        return pipeline.profile.source_width > 0

    def _apply_passthrough_frame(
        self,
        pipeline: _FamilyPipelineState,
        encoded: bytes,
        info: dict[str, float | int],
    ) -> None:
        passthrough_info = dict(info)
        passthrough_info.setdefault("encode_ms", 0.0)
        self._apply_encoded_frame(pipeline, encoded, passthrough_info)

    @staticmethod
    def _inspect_passthrough_frame(frame: bytes) -> dict[str, float | int] | None:
        size = FamilyCameraStreamService._jpeg_dimensions(frame)
        if size is None:
            return None
        width, height = size
        return {
            "raw_width": width,
            "raw_height": height,
            "output_width": width,
            "output_height": height,
            "encode_ms": 0.0,
        }

    def _apply_encoded_frame(
        self,
        pipeline: _FamilyPipelineState,
        encoded: bytes,
        info: dict[str, float | int],
    ) -> None:
        pipeline.latest_jpeg = encoded
        pipeline.latest_part = self._format_mjpeg_part(encoded)
        pipeline.latest_emitted_at = time.time()
        pipeline.last_encoded_frame_at = pipeline.latest_emitted_at
        pipeline.latest_jpeg_bytes = len(encoded)
        pipeline.raw_frame_width = int(info.get("raw_width") or 0)
        pipeline.raw_frame_height = int(info.get("raw_height") or 0)
        pipeline.family_output_width = int(info.get("output_width") or 0)
        pipeline.family_output_height = int(info.get("output_height") or 0)
        pipeline.latest_encode_ms = float(info.get("encode_ms") or 0.0)

        if pipeline.average_jpeg_bytes <= 0:
            pipeline.average_jpeg_bytes = float(len(encoded))
        else:
            pipeline.average_jpeg_bytes = (pipeline.average_jpeg_bytes * 0.75) + (len(encoded) * 0.25)

        if pipeline.average_encode_ms <= 0:
            pipeline.average_encode_ms = pipeline.latest_encode_ms
        else:
            pipeline.average_encode_ms = (pipeline.average_encode_ms * 0.75) + (pipeline.latest_encode_ms * 0.25)

        pipeline.version += 1
        pipeline.note_output_frame()
        pipeline.frame_event.set()

    def _pipeline_status(self, pipeline: _FamilyPipelineState) -> dict[str, object]:
        source_status = pipeline.source_hub.status()
        return {
            "quality": pipeline.profile.key,
            "source_profile": pipeline.profile.source_profile,
            "active_quality": self.current_quality(),
            "configured_stream_path": CameraService._normalize_path(self._settings.camera_stream_rtsp_path),
            "configured_quality_path": CameraService._normalize_path(self._settings.camera_stream_quality_path),
            "configured_rtsp_path": CameraService._normalize_path(self._settings.camera_rtsp_path),
            "running": bool(pipeline.encoder_task and not pipeline.encoder_task.done()),
            "clients": pipeline.clients,
            "keep_warm": pipeline.active(),
            "sticky_keep_warm": pipeline.sticky_keep_warm,
            "raw_frame_width": pipeline.raw_frame_width,
            "raw_frame_height": pipeline.raw_frame_height,
            "output_width": pipeline.family_output_width,
            "output_height": pipeline.family_output_height,
            "family_output_width": pipeline.family_output_width,
            "family_output_height": pipeline.family_output_height,
            "target_fps": round(pipeline.profile.target_fps, 2),
            "family_target_fps": round(pipeline.profile.target_fps, 2),
            "jpeg_quality": pipeline.profile.jpeg_quality,
            "family_jpeg_quality": pipeline.profile.jpeg_quality,
            "latest_jpeg_bytes": pipeline.latest_jpeg_bytes,
            "average_jpeg_bytes": int(round(pipeline.average_jpeg_bytes)) if pipeline.average_jpeg_bytes > 0 else 0,
            "encode_ms": round(pipeline.latest_encode_ms, 2),
            "average_encode_ms": round(pipeline.average_encode_ms, 2),
            "source_fps": round(pipeline.source_fps, 2),
            "output_fps": round(pipeline.output_fps, 2),
            "frames_encoded_total": pipeline.frames_encoded_total,
            "latest_frame_at": pipeline.latest_emitted_at,
            "last_encoded_frame_at": pipeline.last_encoded_frame_at,
            "last_main_frame_at": pipeline.last_main_frame_at,
            "fallback_count": pipeline.fallback_count,
            "fallback_reason": pipeline.fallback_reason,
            "last_error": pipeline.last_error or source_status.get("last_error"),
            "active_url": pipeline.active_url or source_status.get("active_url"),
            "active_stream_path": self._stream_path_from_url(pipeline.active_url or source_status.get("active_url")),
            "active_source_type": pipeline.active_source_type,
        }

    def _profile_for_quality(self, quality: str) -> FamilyStreamProfile:
        normalized = self.normalize_quality(quality)
        if normalized == "smooth":
            return FamilyStreamProfile(
                key="smooth",
                source_profile="smooth",
                source_width=720,
                output_width=720,
                target_fps=15.0,
                jpeg_quality=75,
            )
        if normalized == "hd":
            return FamilyStreamProfile(
                key="hd",
                source_profile="quality",
                source_width=1280,
                output_width=1280,
                target_fps=10.0,
                jpeg_quality=88,
            )
        return FamilyStreamProfile(
            key="balanced",
            source_profile="quality",
            source_width=960,
            output_width=960,
            target_fps=12.0,
            jpeg_quality=82,
        )

    def _source_settings_for_profile(self, profile: FamilyStreamProfile) -> Settings:
        return self._settings.model_copy(
            update={
                "camera_stream_profile": profile.source_profile,
                "camera_stream_fps": profile.target_fps,
                "camera_stream_width": profile.source_width,
            }
        )

    async def _fallback_hub(self) -> CameraFrameHub:
        smooth_pipeline = await self._get_pipeline("smooth")
        smooth_pipeline.keep_warm_until = max(
            smooth_pipeline.keep_warm_until,
            time.monotonic() + 3.0,
        )
        await smooth_pipeline.source_hub.start_keep_warm()
        self._ensure_pipeline_task(smooth_pipeline)
        return smooth_pipeline.source_hub

    @staticmethod
    def _format_mjpeg_part(image: bytes) -> bytes:
        return (
            f"--{_BOUNDARY}\r\n".encode("ascii")
            + b"Content-Type: image/jpeg\r\n"
            + f"Content-Length: {len(image)}\r\n\r\n".encode("ascii")
            + image
            + b"\r\n"
        )

    @staticmethod
    def _encode_family_frame(
        frame: bytes,
        *,
        width: int,
        jpeg_quality: int,
    ) -> tuple[bytes | None, dict[str, float | int]]:
        try:
            import cv2
            import numpy as np
        except Exception:
            return None, {}

        started = time.perf_counter()
        image = cv2.imdecode(np.frombuffer(frame, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return None, {}

        raw_height, raw_width = image.shape[:2]
        working = image
        if width > 0 and raw_width > width:
            target_height = max(2, int(round(raw_height * (width / raw_width))))
            working = cv2.resize(working, (width, target_height), interpolation=cv2.INTER_AREA)

        output_height, output_width = working.shape[:2]
        ok, encoded = cv2.imencode(
            ".jpg",
            working,
            [int(cv2.IMWRITE_JPEG_QUALITY), int(max(55, min(95, jpeg_quality)))],
        )
        if not ok:
            return None, {}

        encode_ms = (time.perf_counter() - started) * 1000.0
        return encoded.tobytes(), {
            "raw_width": raw_width,
            "raw_height": raw_height,
            "output_width": output_width,
            "output_height": output_height,
            "encode_ms": encode_ms,
        }

    def _is_fresh_frame(
        self,
        frame: bytes | None,
        frame_at: float | None,
        freshness_threshold: float,
    ) -> bool:
        return (
            frame is not None
            and frame_at is not None
            and time.time() - frame_at <= freshness_threshold
        )

    async def _set_sticky_quality(self, quality: str) -> None:
        normalized = self.normalize_quality(quality)
        await self._get_pipeline(normalized)
        async with self._lock:
            pipelines = list(self._pipelines.items())
        for pipeline_quality, pipeline in pipelines:
            sticky = pipeline_quality == normalized
            if pipeline.sticky_keep_warm == sticky:
                continue
            pipeline.sticky_keep_warm = sticky
            if sticky:
                await pipeline.source_hub.start_keep_warm()
                self._ensure_pipeline_task(pipeline)
            elif pipeline.clients == 0:
                await self._cleanup_pipeline_if_idle(pipeline_quality)

    def _fallback_reason_for_status(
        self,
        source_status: dict[str, object],
        *,
        source_frame_at: float | None,
    ) -> str:
        active_url = str(source_status.get("active_url") or "").strip().lower()
        if self._is_snapshot_fallback_url(active_url):
            return "MAIN_STREAM_DEGRADED_TO_SNAPSHOT"
        last_error = str(source_status.get("last_error") or "").strip()
        if last_error:
            return last_error
        if source_frame_at is None:
            return "MAIN_CACHE_EMPTY"
        age_seconds = max(0.0, time.time() - source_frame_at)
        return f"MAIN_FRAME_STALE:{age_seconds:.2f}s"

    @staticmethod
    def _classify_source_type(active_url: str, *, fallback: bool) -> str:
        if fallback:
            return "fallback"
        normalized = str(active_url or "").lower()
        if FamilyCameraStreamService._is_snapshot_fallback_url(normalized):
            return "snapshot"
        if "/av0_0" in normalized:
            return "main"
        if "/av0_1" in normalized:
            return "sub"
        return "cache"

    @staticmethod
    def _stream_path_from_url(active_url: object) -> str | None:
        if active_url is None:
            return None
        text = str(active_url).strip()
        if not text:
            return None
        if "://" not in text:
            return text
        try:
            parsed = urlparse(text)
        except Exception:
            return text
        return parsed.path or text

    @staticmethod
    def _coerce_timestamp(value: object) -> float | None:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        return numeric if numeric > 0 else None

    @staticmethod
    def _is_snapshot_fallback_url(active_url: str) -> bool:
        normalized = str(active_url or "").strip().lower()
        return "snapshot-fallback" in normalized or normalized == "runtime-snapshot-relay"

    @staticmethod
    def _jpeg_dimensions(frame: bytes) -> tuple[int, int] | None:
        if len(frame) < 10 or frame[:2] != b"\xff\xd8":
            return None

        index = 2
        length = len(frame)
        while index + 8 < length:
            if frame[index] != 0xFF:
                index += 1
                continue

            marker = frame[index + 1]
            index += 2
            if marker in {0xD8, 0xD9}:
                continue
            if marker == 0xDA:
                break
            if index + 2 > length:
                return None
            segment_length = int.from_bytes(frame[index : index + 2], "big")
            if segment_length < 2 or index + segment_length > length:
                return None
            if marker in {
                0xC0, 0xC1, 0xC2, 0xC3,
                0xC5, 0xC6, 0xC7,
                0xC9, 0xCA, 0xCB,
                0xCD, 0xCE, 0xCF,
            }:
                if index + 7 > length:
                    return None
                height = int.from_bytes(frame[index + 3 : index + 5], "big")
                width = int.from_bytes(frame[index + 5 : index + 7], "big")
                if width > 0 and height > 0:
                    return width, height
                return None
            index += segment_length
        return None
