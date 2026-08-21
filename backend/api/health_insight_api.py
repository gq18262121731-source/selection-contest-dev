from __future__ import annotations

from fastapi import APIRouter

from backend.dependencies import get_health_llm_insight_service
from backend.schemas.health_insight_schema import HealthScoreInsightRequest, HealthScoreInsightResponse


router = APIRouter(prefix="/agent/health-score", tags=["agent"])


@router.post("/insight", response_model=HealthScoreInsightResponse)
async def generate_health_score_insight(payload: HealthScoreInsightRequest) -> HealthScoreInsightResponse:
    return get_health_llm_insight_service().generate(payload)
