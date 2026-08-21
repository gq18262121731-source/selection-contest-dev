from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.dependencies import (
    get_camera_audio_hub,
    get_camera_detection_frame_hub,
    get_camera_frame_hub,
    get_camera_pose_frame_hub,
    get_camera_processed_frame_hub,
    get_camera_setup_config_service,
    get_camera_source_registry,
    get_camera_source_settings,
    get_family_camera_stream_service,
)
from backend.services.camera_service import CameraService


router = APIRouter(prefix="/camera", tags=["camera"])

_LAST_GOOD_PROCESSED_FRAME: bytes | None = None
_LAST_GOOD_PROCESSED_FRAME_AT: float | None = None
_LAST_GOOD_PROCESSED_FRAME_SOURCE = "none"
_STALE_FRAME_MAX_AGE_SECONDS = 15.0


class CameraSetupConfigRequest(BaseModel):
    camera_source_mode: str | None = None
    camera_local_index: int | None = None
    camera_local_backend: str | None = None
    camera_ip: str | None = None
    camera_user: str | None = None
    camera_password: str | None = None
    camera_rtsp_port: int | None = None
    camera_rtsp_path: str | None = None
    camera_stream_rtsp_path: str | None = None
    camera_stream_quality_path: str | None = None
    camera_audio_rtsp_path: str | None = None
    camera_onvif_port: int | None = None
    camera_stream_profile: str | None = None


def _frame_response(
    frame: bytes,
    *,
    source: str,
    stale: bool = False,
) -> Response:
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "X-Camera-Source": source,
    }
    if stale:
        headers["X-Frame-Stale"] = "true"
    return Response(content=frame, media_type="image/jpeg", headers=headers)


def _remember_last_good_processed_frame(frame: bytes, *, source: str) -> None:
    global _LAST_GOOD_PROCESSED_FRAME, _LAST_GOOD_PROCESSED_FRAME_AT, _LAST_GOOD_PROCESSED_FRAME_SOURCE

    if not frame:
        return
    _LAST_GOOD_PROCESSED_FRAME = frame
    _LAST_GOOD_PROCESSED_FRAME_AT = time.time()
    _LAST_GOOD_PROCESSED_FRAME_SOURCE = source


def _recent_last_good_processed_frame() -> tuple[bytes, str] | None:
    if _LAST_GOOD_PROCESSED_FRAME is None or _LAST_GOOD_PROCESSED_FRAME_AT is None:
        return None
    if time.time() - _LAST_GOOD_PROCESSED_FRAME_AT > _STALE_FRAME_MAX_AGE_SECONDS:
        return None
    return _LAST_GOOD_PROCESSED_FRAME, _LAST_GOOD_PROCESSED_FRAME_SOURCE


def _latest_cached_frame() -> tuple[bytes, str] | None:
    frame = get_camera_processed_frame_hub().latest_frame()
    if frame is not None:
        return frame, "processed-frame-cache"
    frame = get_camera_frame_hub().latest_frame()
    if frame is not None:
        return frame, "raw-frame-cache"
    return None


def _latest_raw_cached_frame() -> tuple[bytes, str] | None:
    frame = get_camera_frame_hub().latest_frame()
    if frame is not None:
        return frame, "raw-frame-cache"
    return None


async def _warm_frame_hubs() -> None:
    await asyncio.gather(
        get_camera_frame_hub().start_keep_warm(),
        get_camera_processed_frame_hub().start_keep_warm(),
    )


async def _wait_for_cached_frame() -> tuple[bytes, str] | None:
    await _warm_frame_hubs()
    cached = _latest_cached_frame()
    if cached is not None:
        return cached
    for _ in range(4):
        await asyncio.sleep(0.15)
        cached = _latest_cached_frame()
        if cached is not None:
            return cached
    return None


async def _wait_for_raw_cached_frame() -> tuple[bytes, str] | None:
    await get_camera_frame_hub().start_keep_warm()
    cached = _latest_raw_cached_frame()
    if cached is not None:
        return cached
    for _ in range(4):
        await asyncio.sleep(0.15)
        cached = _latest_raw_cached_frame()
        if cached is not None:
            return cached
    return None


async def _capture_snapshot_bytes() -> tuple[bytes, dict[str, str]]:
    service = CameraService(get_camera_source_settings("active"))
    if service.uses_runtime_managed_source():
        return await asyncio.to_thread(service.capture_runtime_jpeg_fast)
    return await asyncio.to_thread(service.capture_jpeg)


@router.get("/status")
async def camera_status() -> dict[str, object]:
    active = get_camera_source_registry().active_source()
    status = await asyncio.to_thread(CameraService(get_camera_source_settings("active")).check_status)
    return {
        "camera_id": active.camera_id,
        "camera_name": active.name,
        "configured": status.configured,
        "online": status.online,
        "ip": status.ip,
        "port": status.port,
        "path": status.path,
        "checked_at": status.checked_at.isoformat(),
        "latency_ms": status.latency_ms,
        "error": status.error,
        "source": status.source,
        "detail": status.detail,
    }


@router.get("/stream-status")
async def camera_stream_status() -> dict[str, object]:
    active = get_camera_source_registry().active_source()
    raw = get_camera_frame_hub().status()
    processed = get_camera_processed_frame_hub().status()
    pose = get_camera_pose_frame_hub().status()
    detection = get_camera_detection_frame_hub().status()
    family = get_family_camera_stream_service().status()
    return {
        "camera_id": active.camera_id,
        "raw": raw,
        "processed": processed,
        "pose": pose,
        "detection": detection,
        "family": family,
    }


@router.get("/snapshot")
async def camera_snapshot() -> Response:
    try:
        image_bytes, headers = await _capture_snapshot_bytes()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"CAMERA_SNAPSHOT_FAILED: {exc}") from exc
    return Response(content=image_bytes, media_type="image/jpeg", headers=headers)


@router.get("/processed-snapshot")
async def camera_processed_snapshot() -> Response:
    cached = _latest_cached_frame()
    if cached is None:
        cached = await _wait_for_cached_frame()

    if cached is not None:
        frame, source = cached
        _remember_last_good_processed_frame(frame, source=source)
        return _frame_response(frame, source=source)

    try:
        image_bytes, _headers = await _capture_snapshot_bytes()
    except RuntimeError as exc:
        stale = _recent_last_good_processed_frame()
        if stale is not None:
            frame, stale_source = stale
            return _frame_response(frame, source=f"{stale_source}-stale-fallback", stale=True)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        stale = _recent_last_good_processed_frame()
        if stale is not None:
            frame, stale_source = stale
            return _frame_response(frame, source=f"{stale_source}-stale-fallback", stale=True)
        raise HTTPException(status_code=503, detail=f"CAMERA_SNAPSHOT_FAILED: {exc}") from exc

    _remember_last_good_processed_frame(image_bytes, source="direct-snapshot-fallback")
    return _frame_response(image_bytes, source="direct-snapshot-fallback")


@router.get("/family-snapshot")
async def camera_family_snapshot(quality: str | None = None) -> Response:
    family_service = get_family_camera_stream_service()
    await family_service.prepare_profile(quality)
    frame, family_status = await family_service.snapshot(quality)
    normalized_quality = family_service.resolve_quality(quality)
    if frame is not None:
        source = f"family-{normalized_quality}-cache"
        headers = {
            "X-Family-Quality": normalized_quality,
            "X-Family-Source": str(family_status.get("active_source_type") or "cache"),
            "X-Family-Width": str(family_status.get("family_output_width") or 0),
            "X-Family-Height": str(family_status.get("family_output_height") or 0),
            "X-Family-Jpeg-Bytes": str(family_status.get("latest_jpeg_bytes") or len(frame)),
        }
        fallback_reason = str(family_status.get("fallback_reason") or "").strip()
        response = _frame_response(frame, source=source)
        if fallback_reason:
            headers["X-Fallback-Reason"] = fallback_reason
        response.headers.update(headers)
        return response

    cached = _latest_raw_cached_frame()
    if cached is None:
        cached = await _wait_for_raw_cached_frame()

    if cached is not None:
        frame, source = cached
        response = _frame_response(frame, source=source)
        response.headers["X-Family-Quality"] = normalized_quality
        response.headers["X-Family-Source"] = "raw-fallback"
        response.headers["X-Family-Width"] = str(family_status.get("family_output_width") or 0)
        response.headers["X-Family-Height"] = str(family_status.get("family_output_height") or 0)
        response.headers["X-Family-Jpeg-Bytes"] = str(len(frame))
        fallback_reason = str(family_status.get("fallback_reason") or "FAMILY_CACHE_EMPTY").strip()
        response.headers["X-Fallback-Reason"] = fallback_reason
        return response

    try:
        image_bytes, _headers = await _capture_snapshot_bytes()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"CAMERA_SNAPSHOT_FAILED: {exc}") from exc

    response = _frame_response(image_bytes, source="direct-raw-snapshot-fallback")
    response.headers["X-Family-Quality"] = normalized_quality
    response.headers["X-Family-Source"] = "direct-raw-snapshot-fallback"
    response.headers["X-Family-Width"] = str(family_status.get("family_output_width") or 0)
    response.headers["X-Family-Height"] = str(family_status.get("family_output_height") or 0)
    response.headers["X-Family-Jpeg-Bytes"] = str(len(image_bytes))
    response.headers["X-Fallback-Reason"] = str(family_status.get("fallback_reason") or "FAMILY_CACHE_EMPTY")
    return response


@router.get("/stream.mjpg")
async def camera_stream() -> StreamingResponse:
    return StreamingResponse(
        get_camera_frame_hub().mjpeg_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@router.get("/family-stream.mjpg")
async def camera_family_stream(quality: str = "balanced") -> StreamingResponse:
    family_service = get_family_camera_stream_service()
    normalized_quality = await family_service.activate_quality(quality)
    return StreamingResponse(
        family_service.mjpeg_frames(normalized_quality),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Camera-Stream": "family-stream",
            "X-Family-Quality": normalized_quality,
        },
    )


@router.get("/processed-stream.mjpg")
async def camera_processed_stream() -> StreamingResponse:
    return StreamingResponse(
        get_camera_processed_frame_hub().mjpeg_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@router.get("/audio/status")
async def camera_audio_status() -> dict[str, object]:
    active = get_camera_source_registry().active_source()
    status = await asyncio.to_thread(CameraService(get_camera_source_settings("active")).check_audio_status)
    return {
        "camera_id": active.camera_id,
        "configured": status.configured,
        "listen_supported": status.listen_supported,
        "talk_supported": status.talk_supported,
        "checked_url": status.checked_url,
        "audio_codec": status.audio_codec,
        "sample_rate": status.sample_rate,
        "channels": status.channels,
        "source": status.source,
        "error": status.error,
    }


@router.get("/audio/stream-status")
async def camera_audio_stream_status() -> dict[str, object]:
    active = get_camera_source_registry().active_source()
    return {
        "camera_id": active.camera_id,
        **get_camera_audio_hub().status(),
    }


@router.get("/health")
async def camera_health() -> dict[str, object]:
    service = CameraService(get_camera_source_settings("active"))
    runtime_health = service.runtime_health()
    status = await asyncio.to_thread(service.check_status)
    return {
        "configured": status.configured,
        "online": status.online,
        "source": status.source,
        "detail": status.detail,
        "error": status.error,
        "runtime_health": runtime_health,
    }


@router.get("/setup")
async def camera_setup_current() -> dict[str, object]:
    return get_camera_setup_config_service().current()


@router.post("/setup")
async def camera_setup_update(payload: CameraSetupConfigRequest) -> dict[str, object]:
    updated = get_camera_setup_config_service().update(payload.model_dump(exclude_none=True))
    await get_family_camera_stream_service().reload_after_settings_update()
    return {"ok": True, "config": updated}


@router.get("/detection-models/status")
async def camera_detection_models_status() -> dict[str, object]:
    return {
        "ok": True,
        "fall_detection_enabled": False,
        "pose_detection_enabled": False,
        "fall_model_root": str(get_camera_source_settings("active").fall_detection_model_root),
        "pose_model_root": str(get_camera_source_settings("active").pose_detection_model_root),
        "note": "Deep fall/pose runtime workers are not auto-enabled in this workspace. Use target-user and video-bridge APIs for validated paths.",
    }
