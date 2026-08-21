from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from backend.dependencies import get_agent_service, get_stream_service
from backend.models.analytics_model import AnalysisScope, WindowKind
from backend.models.care_model import AgentDeviceHealthReport
from backend.models.user_model import UserRole


router = APIRouter(prefix="/chat", tags=["chat"])


class DeviceAnalysisRequest(BaseModel):
    device_mac: str
    question: str = Field(default="请结合最近监测数据生成健康分析。", min_length=4)
    role: UserRole = UserRole.FAMILY
    mode: str = Field(default="qwen", pattern="^(auto|qwen|tongyi|ollama)$")
    history_limit: int = Field(default=120, ge=12, le=1000)
    history_minutes: int = Field(default=1440, ge=30, le=43200)


class ChatHistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class CommunityAnalysisRequest(BaseModel):
    question: str = Field(default="请总结当前分析窗口内的健康态势并给出处置建议。", min_length=4)
    role: UserRole = UserRole.COMMUNITY
    mode: str = Field(default="qwen", pattern="^(auto|qwen|tongyi|ollama)$")
    history_minutes: int = Field(default=1440, ge=30, le=43200)
    per_device_limit: int = Field(default=240, ge=12, le=1000)
    device_macs: list[str] = Field(default_factory=list)
    workflow: Literal[
        "overview",
        "risk_ranking",
        "alert_digest",
        "device_focus",
        "elder_focus",
        "community_report",
        "elder_report",
        "report_generation",
        "free_chat",
    ] = "free_chat"
    focus_device_mac: str | None = None
    history: list[ChatHistoryTurn] = Field(default_factory=list)
    scope: AnalysisScope = AnalysisScope.COMMUNITY
    subject_elder_id: str | None = None
    window: WindowKind = WindowKind.DAY
    provider: Literal["qwen", "tongyi", "ollama", "auto"] = "qwen"
    include_report: bool = False


class DeviceHealthReportRequest(BaseModel):
    device_mac: str
    start_at: datetime
    end_at: datetime
    role: UserRole = UserRole.FAMILY
    mode: str = Field(default="qwen", pattern="^(auto|qwen|tongyi|ollama)$")

    @model_validator(mode="after")
    def validate_window(self) -> "DeviceHealthReportRequest":
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be later than start_at")
        return self


@router.post("/analyze")
async def analyze_health(payload: DeviceAnalysisRequest) -> dict[str, object]:
    recent = get_stream_service().recent_in_window(
        payload.device_mac,
        minutes=payload.history_minutes,
        limit=payload.history_limit,
    )
    return get_agent_service().analyze_device(
        role=payload.role,
        question=payload.question,
        samples=recent,
        mode=payload.mode,
    )


@router.post("/analyze/device")
async def analyze_device(payload: DeviceAnalysisRequest) -> dict[str, object]:
    return await analyze_health(payload)


@router.post("/analyze/device/stream")
async def analyze_device_stream(payload: DeviceAnalysisRequest) -> StreamingResponse:
    recent = get_stream_service().recent_in_window(
        payload.device_mac,
        minutes=payload.history_minutes,
        limit=payload.history_limit,
    )

    def event_stream():
        for event in get_agent_service().stream_analyze_device(
            role=payload.role,
            question=payload.question,
            samples=recent,
            mode=payload.mode,
        ):
            yield json.dumps(event, ensure_ascii=False).encode("utf-8") + b"\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@router.post("/analyze/community")
async def analyze_community(payload: CommunityAnalysisRequest) -> dict[str, object]:
    result = get_agent_service().analyze_community(
        role=payload.role,
        question=payload.question,
        device_samples=None,
        mode=payload.mode,
        history_minutes=payload.history_minutes,
        workflow=payload.workflow,
        focus_device_mac=payload.focus_device_mac,
        history=[item.model_dump(mode="python") for item in payload.history],
        scope=payload.scope.value,
        subject_elder_id=payload.subject_elder_id,
        window=payload.window.value,
        provider=payload.provider,
        include_report=payload.include_report,
        per_device_limit=payload.per_device_limit,
        device_macs=payload.device_macs,
    )
    if not isinstance(result.get("citations"), list):
        result["citations"] = list(result.get("citations") or [])
    if not isinstance(result.get("attachments"), list):
        result["attachments"] = []
    return result


@router.post("/analyze/community/stream")
async def analyze_community_stream(payload: CommunityAnalysisRequest) -> StreamingResponse:
    def event_stream():
        for event in get_agent_service().stream_analyze_community(
            role=payload.role,
            question=payload.question,
            device_samples=None,
            mode=payload.mode,
            history_minutes=payload.history_minutes,
            workflow=payload.workflow,
            focus_device_mac=payload.focus_device_mac,
            history=[item.model_dump(mode="python") for item in payload.history],
            scope=payload.scope.value,
            subject_elder_id=payload.subject_elder_id,
            window=payload.window.value,
            provider=payload.provider,
            include_report=payload.include_report,
            per_device_limit=payload.per_device_limit,
            device_macs=payload.device_macs,
        ):
            yield json.dumps(event, ensure_ascii=False).encode("utf-8") + b"\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@router.post("/report/device", response_model=AgentDeviceHealthReport)
async def generate_device_health_report(payload: DeviceHealthReportRequest) -> AgentDeviceHealthReport:
    samples = [
        sample
        for sample in get_stream_service().recent(payload.device_mac, limit=1000)
        if payload.start_at <= sample.timestamp <= payload.end_at
    ]
    report = get_agent_service().generate_device_health_report(
        role=payload.role,
        device_mac=payload.device_mac,
        start_at=payload.start_at.astimezone(timezone.utc),
        end_at=payload.end_at.astimezone(timezone.utc),
        samples=samples,
        mode=payload.mode,
    )
    return AgentDeviceHealthReport.model_validate(report)


@router.get("/capabilities")
async def get_chat_capabilities() -> dict[str, object]:
    return get_agent_service().capability_report()


@router.get("/mcp-tools")
async def get_mcp_tool_specs() -> dict[str, object]:
    report = get_agent_service().capability_report()
    return {
        "mcp_connected": report.get("extensions", {}).get("mcp_connected", False),
        "tools": report.get("tool_specs", []),
    }
