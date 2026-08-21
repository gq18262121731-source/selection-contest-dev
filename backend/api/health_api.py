from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from backend.dependencies import (
    get_community_clusterer,
    get_community_insight_service,
    get_device_service,
    get_display_latest_sample,
    get_display_trend_samples,
    get_intelligent_scorer,
    get_structured_health_score_service,
    get_stream_service,
    get_warning_evaluation_service,
    ingest_sample,
)
from backend.models.analytics_model import (
    CommunityWindowReportRequest,
    CommunityWindowReportResponse,
    DeviceHistoryResponse,
    HistoryBucket,
    WindowKind,
)
from backend.models.device_model import DeviceStatus
from backend.models.health_model import HealthSample, HealthTrendPoint, IngestResponse
from backend.schemas.common import build_error_response, build_success_response
from backend.schemas.health import HealthScoreApiResponse, HealthScoreRequest
from backend.schemas.warning import WarningCheckApiResponse, WarningCheckRequest
from backend.services.health_score_service import ServiceError


router = APIRouter(prefix="/health", tags=["health"])


@router.post("/ingest", response_model=IngestResponse)
async def ingest_health_sample(payload: HealthSample) -> IngestResponse:
    return await ingest_sample(payload)


@router.get("/realtime/{device_mac}", response_model=HealthSample)
async def get_realtime_sample(device_mac: str) -> HealthSample:
    device = get_device_service().get_device(device_mac)
    if device and device.status == DeviceStatus.OFFLINE:
        raise HTTPException(status_code=404, detail="Device is offline")
    sample = get_display_latest_sample(device_mac, device.ingest_mode if device else None)
    if not sample:
        raise HTTPException(status_code=404, detail="No realtime sample available")
    return sample


@router.get("/trend/{device_mac}", response_model=list[HealthTrendPoint])
async def get_health_trend(
    device_mac: str,
    minutes: int = Query(default=60, ge=5, le=10080),
    limit: int = Query(default=120, ge=10, le=1000),
) -> list[HealthTrendPoint]:
    device = get_device_service().get_device(device_mac)
    if device and device.status == DeviceStatus.OFFLINE:
        return []
    samples = get_display_trend_samples(
        device_mac,
        device.ingest_mode if device else None,
        minutes=minutes,
        limit=limit,
    )
    return [
        HealthTrendPoint(
            timestamp=sample.timestamp,
            heart_rate=sample.heart_rate,
            temperature=sample.temperature,
            blood_oxygen=sample.blood_oxygen,
            blood_pressure=sample.blood_pressure,
            steps=sample.steps,
            health_score=sample.health_score,
        )
        for sample in samples
    ]


@router.get("/devices/{device_mac}/history", response_model=DeviceHistoryResponse)
async def get_device_history(
    device_mac: str,
    window: WindowKind = Query(default=WindowKind.DAY),
    bucket: HistoryBucket | None = Query(default=None),
) -> DeviceHistoryResponse:
    selected_bucket = bucket or (HistoryBucket.HOUR if window == WindowKind.DAY else HistoryBucket.DAY)
    return get_community_insight_service().get_device_history(
        device_mac=device_mac,
        window=window,
        bucket=selected_bucket,
    )


@router.get("/community/overview")
async def get_community_overview() -> dict[str, object]:
    devices = get_device_service().list_devices()
    online_macs = [d.mac_address for d in devices if d.status != DeviceStatus.OFFLINE]
    samples = get_stream_service().latest_samples(filter_macs=online_macs)
    history_by_device = get_stream_service().recent_by_devices(
        device_macs=online_macs,
        minutes=60,
        per_device_limit=60
    )
    summary = get_community_clusterer().summarize(samples, history_by_device)
    score = 0.0
    if samples:
        windows = [
            [
                sample.heart_rate,
                sample.temperature,
                sample.blood_oxygen,
                (sample.blood_pressure_pair or (120, 80))[0],
            ]
            for sample in samples
        ]
        score = get_intelligent_scorer().score_sequence(windows)
    return {
        "clusters": summary.clusters,
        "device_count": len(samples),
        "intelligent_anomaly_score": score,
        "trend": summary.trend,
        "risk_heatmap": summary.risk_heatmap,
    }


@router.post("/community/window-report", response_model=CommunityWindowReportResponse)
async def build_community_window_report(
    payload: CommunityWindowReportRequest,
) -> CommunityWindowReportResponse:
    return get_community_insight_service().build_window_report(
        window=payload.window,
        device_macs=payload.device_macs,
    )


@router.get("/community/window-report/export", response_model=CommunityWindowReportResponse)
async def export_community_window_report(
    window: WindowKind = Query(default=WindowKind.DAY),
    device_macs: list[str] | None = Query(default=None),
) -> CommunityWindowReportResponse:
    return get_community_insight_service().build_window_report(
        window=window,
        device_macs=device_macs or [],
    )


@router.get("/intelligent/{device_mac}")
async def get_intelligent_device_analysis(device_mac: str) -> dict[str, object]:
    history = get_stream_service().recent_in_window(device_mac, minutes=60, limit=360)
    if not history:
        raise HTTPException(status_code=404, detail="No device history available")
    result = get_intelligent_scorer().infer_device(device_mac, history, now=history[-1].timestamp, force=True)
    if result is None:
        return {"device_mac": device_mac.upper(), "ready": False, "message": "Not enough data for intelligent inference"}
    return {
        "device_mac": device_mac.upper(),
        "ready": True,
        "probability": result.probability,
        "score": result.score,
        "drift_score": result.drift_score,
        "reconstruction_score": result.reconstruction_score,
        "reason": result.reason,
    }


@router.post("/score", response_model=HealthScoreApiResponse)
async def score_health_snapshot(payload: HealthScoreRequest):
    try:
        result = get_structured_health_score_service().score(payload)
        return build_success_response(result)
    except ServiceError as exc:
        error = build_error_response(exc.code, exc.message, exc.details)
        return JSONResponse(status_code=exc.status_code, content=jsonable_encoder(error))


@router.post("/warning/check", response_model=WarningCheckApiResponse)
async def check_health_warning(payload: WarningCheckRequest):
    try:
        result = get_warning_evaluation_service().check(payload)
        return build_success_response(result)
    except ServiceError as exc:
        error = build_error_response(exc.code, exc.message, exc.details)
        return JSONResponse(status_code=exc.status_code, content=jsonable_encoder(error))
