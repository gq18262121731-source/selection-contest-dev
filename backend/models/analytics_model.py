from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class AnalysisScope(str, Enum):
    ELDER = "elder"
    COMMUNITY = "community"


class WindowKind(str, Enum):
    DAY = "day"
    WEEK = "week"


class HistoryBucket(str, Enum):
    RAW = "raw"
    HOUR = "hour"
    DAY = "day"


class SensorHistoryPoint(BaseModel):
    bucket_start: datetime
    bucket_end: datetime | None = None
    heart_rate: float | None = None
    temperature: float | None = None
    blood_oxygen: float | None = None
    health_score: float | None = None
    battery: float | None = None
    steps: float | None = None
    sos_count: int = 0
    sample_count: int = 0
    risk_level: str | None = None


class DeviceHistoryResponse(BaseModel):
    device_mac: str
    window: WindowKind
    bucket: HistoryBucket
    points: list[SensorHistoryPoint] = Field(default_factory=list)


class CommunityWindowReportRequest(BaseModel):
    window: WindowKind = WindowKind.DAY
    device_macs: list[str] = Field(default_factory=list)


class ChartPayload(BaseModel):
    id: str
    title: str
    type: str
    echarts_option: dict[str, object]
    summary: str


class HighRiskEntity(BaseModel):
    device_mac: str
    elder_name: str | None = None
    risk_level: str
    latest_health_score: float | None = None
    active_alert_count: int = 0
    reasons: list[str] = Field(default_factory=list)


class CommunityWindowAnalysis(BaseModel):
    key_metrics: dict[str, object] = Field(default_factory=dict)
    risk_distribution: dict[str, int] = Field(default_factory=dict)
    alert_breakdown: dict[str, int] = Field(default_factory=dict)
    device_status_distribution: dict[str, int] = Field(default_factory=dict)
    high_risk_entities: list[HighRiskEntity] = Field(default_factory=list)
    trend_findings: list[str] = Field(default_factory=list)
    chart_payloads: list[ChartPayload] = Field(default_factory=list)


class CommunityWindowReportResponse(BaseModel):
    window: WindowKind
    generated_at: datetime
    analysis: CommunityWindowAnalysis


class AgentSourceItem(BaseModel):
    source_type: str
    title: str
    url: str | None = None
    snippet: str


class AgentCitation(BaseModel):
    id: str
    title: str
    source_path: str
    chunk_id: str
    snippet: str
    score: float = 0.0


class AgentElderSubject(BaseModel):
    elder_id: str
    elder_name: str
    apartment: str
    device_macs: list[str] = Field(default_factory=list)
    has_realtime_device: bool = False
    latest_timestamp: datetime | None = None
    risk_level: str = "unknown"
    is_demo_subject: bool = False


class CommunityAgentSummaryRequest(BaseModel):
    window: WindowKind = WindowKind.DAY
    question: str = "总结过去一天社区健康情况并给出建议"
    device_macs: list[str] = Field(default_factory=list)
    include_web_search: bool = True
    include_charts: bool = True


class CommunityAgentMeta(BaseModel):
    llm_model: str = ""
    embedding_model: str = ""
    rerank_model: str = ""
    used_tavily: bool = False
    used_rerank: bool = False
    degraded_notes: list[str] = Field(default_factory=list)


class CommunityAgentSummaryResponse(BaseModel):
    window: WindowKind
    generated_at: datetime
    summary_text: str
    advice: list[str] = Field(default_factory=list)
    analysis: CommunityWindowAnalysis
    charts: list[ChartPayload] = Field(default_factory=list)
    sources: list[AgentSourceItem] = Field(default_factory=list)
    agent_meta: CommunityAgentMeta
