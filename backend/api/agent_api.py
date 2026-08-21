from __future__ import annotations

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi import Header, HTTPException
from fastapi.responses import JSONResponse

from backend.dependencies import (
    get_care_service,
    get_community_insight_service,
    get_demo_elder_subjects,
    get_explanation_service,
    require_session_user,
)
from backend.models.analytics_model import AgentElderSubject, CommunityAgentSummaryRequest, CommunityAgentSummaryResponse
from backend.schemas.agent import HealthExplainApiResponse, HealthExplainRequest
from backend.schemas.common import build_error_response, build_success_response
from backend.services.health_score_service import ServiceError
from backend.models.user_model import UserRole


router = APIRouter(prefix="/agent", tags=["agent"])


def _require_community_viewer(authorization: str | None):
    try:
        user = require_session_user(authorization)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if user.role not in {UserRole.COMMUNITY, UserRole.ADMIN}:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return user


@router.post("/community/summary", response_model=CommunityAgentSummaryResponse)
async def summarize_community_window(
    payload: CommunityAgentSummaryRequest,
) -> CommunityAgentSummaryResponse:
    return get_community_insight_service().build_agent_summary(payload)


@router.post("/health/explain", response_model=HealthExplainApiResponse)
async def explain_health_result(payload: HealthExplainRequest):
    try:
        result = get_explanation_service().explain(payload)
        return build_success_response(result)
    except ServiceError as exc:
        error = build_error_response(exc.code, exc.message, exc.details)
        return JSONResponse(status_code=exc.status_code, content=jsonable_encoder(error))


@router.get("/elders", response_model=list[AgentElderSubject])
async def list_agent_elders(authorization: str | None = Header(default=None)) -> list[AgentElderSubject]:
    _require_community_viewer(authorization)
    directory = get_care_service().get_directory()
    subjects = [
        AgentElderSubject(
            elder_id=elder.id,
            elder_name=elder.name,
            apartment=elder.apartment,
            device_macs=list(getattr(elder, "device_macs", [])) or ([elder.device_mac] if elder.device_mac else []),
            has_realtime_device=bool((list(getattr(elder, "device_macs", [])) or ([elder.device_mac] if elder.device_mac else []))),
            risk_level="unknown",
            is_demo_subject=False,
        )
        for elder in directory.elders
    ]
    subjects.extend(get_demo_elder_subjects())
    return subjects
