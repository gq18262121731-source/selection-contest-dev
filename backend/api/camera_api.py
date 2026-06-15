from __future__ import annotations

import asyncio

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
)
from backend.services.camera_service import CameraService


router = APIRouter(prefix="/camera", tags=["camera"])


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
    camera_audio_rtsp_path: str | None = None
    camera_onvif_port: int | None = None


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
    return {
        "camera_id": active.camera_id,
        "raw": raw,
        "processed": processed,
        "pose": pose,
        "detection": detection,
    }


@router.get("/snapshot")
async def camera_snapshot() -> Response:
    service = CameraService(get_camera_source_settings("active"))
    try:
        if service.uses_runtime_managed_source():
            image_bytes, headers = await asyncio.to_thread(service.capture_runtime_jpeg_fast)
        else:
            image_bytes, headers = await asyncio.to_thread(service.capture_jpeg)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"CAMERA_SNAPSHOT_FAILED: {exc}") from exc
    return Response(content=image_bytes, media_type="image/jpeg", headers=headers)


@router.get("/processed-snapshot")
async def camera_processed_snapshot() -> Response:
    hub = get_camera_processed_frame_hub()
    frame = hub.latest_frame()
    if frame is None:
        frame = get_camera_frame_hub().latest_frame()
    if frame is None:
        return await camera_snapshot()
    return Response(
        content=frame,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "X-Camera-Source": "processed-frame-cache",
        },
    )


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
