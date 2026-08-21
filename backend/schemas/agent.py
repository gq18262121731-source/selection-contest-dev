from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.schemas.health import HealthScoreResponse


class HealthExplainRequest(BaseModel):
    """Structured explanation request."""

    role: Literal["elderly", "children", "community"] = "children"
    health_result: HealthScoreResponse


class HealthExplainResponse(BaseModel):
    """Structured explanation response."""

    role: Literal["elderly", "children", "community"]
    summary: str
    advice: list[str] = Field(default_factory=list)
    severity_explanation: str


class HealthExplainApiResponse(BaseModel):
    """Standard envelope for explanation API."""

    code: str = "OK"
    message: str = "success"
    data: HealthExplainResponse
