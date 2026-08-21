from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from backend.models.health_model import HealthSample
from backend.models.user_model import UserRole


class CommunityProfile(BaseModel):
    id: str
    name: str
    address: str
    manager: str
    hotline: str


class ElderProfile(BaseModel):
    id: str
    name: str
    age: int = Field(ge=50, le=120)
    apartment: str
    community_id: str
    device_mac: str
    device_macs: list[str] = Field(default_factory=list)
    family_ids: list[str] = Field(default_factory=list)


class FamilyProfile(BaseModel):
    id: str
    name: str
    relationship: str
    phone: str
    community_id: str
    elder_ids: list[str] = Field(default_factory=list)
    login_username: str


class CareDirectory(BaseModel):
    community: CommunityProfile
    elders: list[ElderProfile] = Field(default_factory=list)
    families: list[FamilyProfile] = Field(default_factory=list)


class CareFeatureAccess(BaseModel):
    basic_advice: bool = True
    device_metrics: bool = False
    health_evaluation: bool = False
    health_report: bool = False


class CareAccessDeviceMetric(BaseModel):
    device_mac: str
    device_name: str
    device_status: str
    activation_state: str | None = None
    bind_status: str
    elder_id: str | None = None
    elder_name: str | None = None
    latest_sample: HealthSample | None = None


class CareHealthReportSummary(BaseModel):
    device_mac: str
    risk_level: str
    sample_count: int
    latest_health_score: int | None = None
    recommendations: list[str] = Field(default_factory=list)
    notable_events: list[str] = Field(default_factory=list)


class CareHealthEvaluationSummary(BaseModel):
    device_mac: str
    risk_level: str
    risk_flags: list[str] = Field(default_factory=list)
    latest_health_score: int | None = None


class CommunityDashboardMetrics(BaseModel):
    elder_count: int = 0
    family_count: int = 0
    device_total: int = 0
    device_pending: int = 0
    device_online: int = 0
    device_offline: int = 0
    active_alarm_count: int = 0
    unacknowledged_alarm_count: int = 0
    sos_alarm_count: int = 0
    health_alert_count: int = 0
    device_alert_count: int = 0
    high_risk_elder_count: int = 0
    average_health_score: float = 0.0
    average_blood_oxygen: float = 0.0
    today_alarm_count: int = 0
    last_sync_at: datetime | None = None


class CommunityDashboardTrendPoint(BaseModel):
    timestamp: datetime
    average_health_score: float = 0.0
    alert_count: int = 0
    high_risk_count: int = 0


class StructuredHealthInsight(BaseModel):
    evaluated_at: datetime | None = None
    health_score: float | None = None
    rule_health_score: float | None = None
    model_health_score: float | None = None
    risk_level: str | None = None
    abnormal_tags: list[str] = Field(default_factory=list)
    trigger_reasons: list[str] = Field(default_factory=list)
    active_event_count: int = 0
    recommendation_code: str | None = None
    score_adjustment_reason: str | None = None


class CommunityDashboardElderItem(BaseModel):
    elder_id: str
    elder_name: str
    apartment: str
    device_mac: str | None = None
    family_names: list[str] = Field(default_factory=list)
    risk_level: str
    risk_score: int = 0
    risk_reasons: list[str] = Field(default_factory=list)
    device_status: str = "unknown"
    latest_timestamp: datetime | None = None
    latest_health_score: int | None = None
    heart_rate: int | None = None
    blood_oxygen: int | None = None
    blood_pressure: str | None = None
    temperature: float | None = None
    steps: int | None = None
    active_alarm_count: int = 0
    sos_active: bool = False
    active_sos_alarm_id: str | None = None
    active_sos_trigger: str | None = None
    structured_health: StructuredHealthInsight | None = None


class CommunityDashboardDeviceItem(BaseModel):
    device_mac: str
    device_name: str
    model_code: str | None = None
    ingest_mode: str | None = None
    service_uuid: str | None = None
    device_uuid: str | None = None
    elder_id: str | None = None
    elder_name: str | None = None
    apartment: str | None = None
    device_status: str
    activation_state: str | None = None
    bind_status: str
    risk_level: str
    risk_reasons: list[str] = Field(default_factory=list)
    latest_timestamp: datetime | None = None
    last_seen_at: datetime | None = None
    last_packet_type: str | None = None
    latest_health_score: int | None = None
    heart_rate: int | None = None
    blood_oxygen: int | None = None
    blood_pressure: str | None = None
    temperature: float | None = None
    battery: int | None = None
    steps: int | None = None
    active_alarm_count: int = 0
    sos_active: bool = False
    active_sos_alarm_id: str | None = None
    active_sos_trigger: str | None = None
    structured_health: StructuredHealthInsight | None = None


class CommunityDashboardAlertItem(BaseModel):
    alarm_id: str
    device_mac: str
    elder_name: str | None = None
    apartment: str | None = None
    alarm_type: str
    alarm_layer: str
    alarm_level: int
    message: str
    created_at: datetime
    acknowledged: bool = False


class RelationTopologyNode(BaseModel):
    id: str
    kind: Literal["community", "elder", "family", "device"]
    label: str
    subtitle: str | None = None
    status: str | None = None
    risk_level: str | None = None


class RelationTopologyLane(BaseModel):
    elder: RelationTopologyNode
    families: list[RelationTopologyNode] = Field(default_factory=list)
    devices: list[RelationTopologyNode] = Field(default_factory=list)


class CommunityRelationTopology(BaseModel):
    community: RelationTopologyNode
    lanes: list[RelationTopologyLane] = Field(default_factory=list)
    unassigned_devices: list[RelationTopologyNode] = Field(default_factory=list)


class CommunityDashboardSummary(BaseModel):
    community: CommunityProfile
    metrics: CommunityDashboardMetrics
    top_risk_elders: list[CommunityDashboardElderItem] = Field(default_factory=list)
    device_statuses: list[CommunityDashboardDeviceItem] = Field(default_factory=list)
    recent_alerts: list[CommunityDashboardAlertItem] = Field(default_factory=list)
    trend: list[CommunityDashboardTrendPoint] = Field(default_factory=list)
    relation_topology: CommunityRelationTopology | None = None


class AgentReportPeriod(BaseModel):
    start_at: str
    end_at: str
    duration_minutes: int
    sample_count: int


class AgentMetricReportItem(BaseModel):
    latest: int | float | None = None
    average: float | None = None
    min: int | float | None = None
    max: int | float | None = None
    trend: str | None = None


class AgentDeviceHealthReport(BaseModel):
    report_type: str = "device_health_report"
    device_mac: str
    subject_name: str | None = None
    device_name: str | None = None
    generated_at: str
    period: AgentReportPeriod
    summary: str
    risk_level: str
    risk_flags: list[str] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    metrics: dict[str, AgentMetricReportItem] = Field(default_factory=dict)
    references: list[str] = Field(default_factory=list)


class CareAccessProfile(BaseModel):
    user_id: str
    role: UserRole
    community_id: str
    family_id: str | None = None
    binding_state: Literal["bound", "unbound", "not_applicable"]
    bound_device_macs: list[str] = Field(default_factory=list)
    related_elder_ids: list[str] = Field(default_factory=list)
    capabilities: CareFeatureAccess
    basic_advice: str
    device_metrics: list[CareAccessDeviceMetric] = Field(default_factory=list)
    health_evaluations: list[CareHealthEvaluationSummary] = Field(default_factory=list)
    health_reports: list[CareHealthReportSummary] = Field(default_factory=list)
