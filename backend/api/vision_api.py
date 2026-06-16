from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.dependencies import get_vision_service_client
from backend.services.vision_service_client import VisionServiceClient


router = APIRouter(prefix="/vision", tags=["vision"])


def _wrap_response(
    result: dict,
    *,
    client: VisionServiceClient,
    camera_id: str | None = None,
) -> dict:
    payload = {
        "status": result.get("status"),
        "reason": result.get("reason"),
        "base_url": client.base_url,
        "default_camera_id": client.default_camera_id,
        "vision_service": result,
    }
    if camera_id is not None:
        payload["camera_id"] = camera_id
    return payload


@router.get("/health")
async def vision_health(
    client: VisionServiceClient = Depends(get_vision_service_client),
) -> dict:
    return _wrap_response(client.get_health(), client=client)


@router.get("/status")
async def vision_status(
    camera_id: str | None = None,
    client: VisionServiceClient = Depends(get_vision_service_client),
) -> dict:
    resolved_camera_id = (camera_id or client.default_camera_id).strip() or client.default_camera_id
    return _wrap_response(client.get_status(resolved_camera_id), client=client, camera_id=resolved_camera_id)


@router.get("/source")
async def vision_source(
    camera_id: str | None = None,
    client: VisionServiceClient = Depends(get_vision_service_client),
) -> dict:
    resolved_camera_id = (camera_id or client.default_camera_id).strip() or client.default_camera_id
    return _wrap_response(client.get_stream_source(resolved_camera_id), client=client, camera_id=resolved_camera_id)


@router.get("/results/latest")
async def vision_results_latest(
    camera_id: str | None = None,
    client: VisionServiceClient = Depends(get_vision_service_client),
) -> dict:
    resolved_camera_id = (camera_id or client.default_camera_id).strip() or client.default_camera_id
    return _wrap_response(client.get_latest_result(resolved_camera_id), client=client, camera_id=resolved_camera_id)
