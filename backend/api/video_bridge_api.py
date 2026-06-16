from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request
import requests

from backend.config import get_settings
from backend.dependencies import (
    get_video_bridge_service,
)
from backend.models.alarm_model import AlarmRecord
from backend.models.video_bridge_model import (
    VideoBridgeFallAlarmSimulationRequest,
    VideoBridgeFallAlarmSimulationResponse,
    VideoBridgeFallEventRequest,
    VideoBridgeFallEventResponse,
    VideoBridgeRuntimeConfigResponse,
    VideoBridgeRuntimeConfigUpdateRequest,
    VideoAnalysisIngestResponse,
    VideoAnalysisPushRequest,
    VideoBridgeStatusResponse,
    VisionStreamProbeRequest,
    VisionStreamSwitchHostRequest,
)


router = APIRouter(prefix="/video-bridge", tags=["video-bridge"])


def _clamp_probability(value: float | None, *, default: float = 0.91) -> float:
    if value is None:
        value = default
    return max(0.0, min(1.0, float(value)))


def _fall_alarm_elder_id(alarm: AlarmRecord) -> str:
    return str(alarm.metadata.get("elder_id") or get_settings().fall_detection_target_elder_id or "")


def _fall_alarm_elder_name(alarm: AlarmRecord) -> str:
    return str(alarm.metadata.get("elder_name") or "")


@router.post("/analysis", response_model=VideoAnalysisIngestResponse)
async def receive_video_analysis(payload: VideoAnalysisPushRequest) -> VideoAnalysisIngestResponse:
    """Receive telemetry pushed by a future standalone video analysis service."""

    return get_video_bridge_service().ingest(payload)


@router.get("/status", response_model=VideoBridgeStatusResponse)
async def get_video_bridge_status() -> VideoBridgeStatusResponse:
    """Return bridge status for frontend placeholder and future service checks."""

    return get_video_bridge_service().status()


@router.get("/runtime-config", response_model=VideoBridgeRuntimeConfigResponse)
async def get_video_bridge_runtime_config() -> VideoBridgeRuntimeConfigResponse:
    """Return the shared Vision runtime override used by both video-bridge and /api/v1/vision/*."""
    return get_video_bridge_service().runtime_config()


@router.patch("/runtime-config", response_model=VideoBridgeRuntimeConfigResponse)
async def update_video_bridge_runtime_config(
    payload: VideoBridgeRuntimeConfigUpdateRequest,
) -> VideoBridgeRuntimeConfigResponse:
    """Update the shared Vision runtime override. This is not a separate upstream authority."""
    return get_video_bridge_service().update_runtime_config(payload)


@router.post("/vision/poll-once")
async def poll_vision_service_once() -> dict[str, object]:
    """Pull one health/source/latest cycle from the standalone vision service."""

    return await get_video_bridge_service().poll_once_async()


@router.get("/vision/health")
async def get_vision_service_health() -> object:
    try:
        return get_video_bridge_service().get_vision_health()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"VISION_SERVICE_UNAVAILABLE: {exc}") from exc


@router.get("/vision/source")
async def get_vision_service_source(camera_id: str | None = None) -> object:
    try:
        return get_video_bridge_service().get_vision_source(camera_id)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"VISION_SERVICE_SOURCE_UNAVAILABLE: {exc}") from exc


@router.get("/vision/latest")
async def get_vision_service_latest(camera_id: str | None = None) -> object:
    try:
        return get_video_bridge_service().get_vision_latest(camera_id)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"VISION_SERVICE_RESULTS_UNAVAILABLE: {exc}") from exc


@router.post("/vision/probe")
async def probe_vision_stream(payload: VisionStreamProbeRequest) -> object:
    try:
        return get_video_bridge_service().probe_vision_stream(payload.model_dump(mode="json"))
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"VISION_SERVICE_PROBE_FAILED: {exc}") from exc


@router.post("/vision/switch-host")
async def switch_vision_host(payload: VisionStreamSwitchHostRequest) -> object:
    try:
        return get_video_bridge_service().switch_vision_host(payload.model_dump(mode="json"))
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"VISION_SERVICE_SWITCH_FAILED: {exc}") from exc


@router.post("/fall-events", response_model=VideoBridgeFallEventResponse)
async def receive_video_bridge_fall_event(
    payload: VideoBridgeFallEventRequest,
    request: Request,
    x_vision_service_token: str | None = Header(default=None),
) -> VideoBridgeFallEventResponse:
    """Receive confirmed fall events from the standalone video demo/service."""
    source_ip = request.client.host if request.client else None
    try:
        result = await get_video_bridge_service().receive_fall_event_async(
            payload,
            source_ip=source_ip,
            push_token=x_vision_service_token,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    alarm = result.get("alarm")
    if not result.get("promoted") or not isinstance(alarm, AlarmRecord):
        raise HTTPException(status_code=409, detail="VIDEO_BRIDGE_FALL_EVENT_NOT_CREATED")

    return VideoBridgeFallEventResponse(
        alarm_id=alarm.id,
        alarm_type=alarm.alarm_type.value,
        alarm=alarm,
        camera_id=payload.camera_id.strip(),
        stream_name=payload.stream_name.strip() or "primary",
        risk=payload.risk,
        fall_prob=_clamp_probability(payload.fall_score if payload.fall_score is not None else payload.fall_prob),
        triggered_at=datetime.now(timezone.utc),
        elder_id=_fall_alarm_elder_id(alarm),
        elder_name=_fall_alarm_elder_name(alarm),
    )


@router.post("/simulate-fall-alarm", response_model=VideoBridgeFallAlarmSimulationResponse)
async def simulate_video_bridge_fall_alarm(
    payload: VideoBridgeFallAlarmSimulationRequest | None = None,
) -> VideoBridgeFallAlarmSimulationResponse:
    raise HTTPException(
        status_code=501,
        detail="VIDEO_BRIDGE_FALL_ALARM_SIMULATION_NOT_ENABLED_IN_THIS_WORKSPACE",
    )
