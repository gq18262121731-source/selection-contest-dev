from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Protocol

from agent.analysis_service import HealthDataAnalysisService
from ai.anomaly_detector import CommunityHealthClusterer, IntelligentAnomalyScorer
from backend.models.alarm_model import AlarmRecord
from backend.models.health_model import HealthSample
from backend.models.user_model import UserRole


@dataclass(slots=True)
class AgentModelInput:
    scope: str
    role: UserRole
    question: str
    device_mac: str | None = None
    device_macs: list[str] = field(default_factory=list)
    samples: list[HealthSample] = field(default_factory=list)
    community_samples: dict[str, list[HealthSample]] = field(default_factory=dict)
    alarms: list[AlarmRecord] = field(default_factory=list)
    context: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class AgentModelResult:
    model_name: str
    status: str
    source: str
    summary: str
    payload: dict[str, object] = field(default_factory=dict)
    confidence: float | None = None
    degraded_reason: str | None = None


class HealthAssessmentModel(Protocol):
    def run(self, model_input: AgentModelInput) -> AgentModelResult: ...


class RiskScoringModel(Protocol):
    def run(self, model_input: AgentModelInput) -> AgentModelResult: ...


class AnomalyExplainModel(Protocol):
    def run(self, model_input: AgentModelInput) -> AgentModelResult: ...


class CareSuggestionModel(Protocol):
    def run(self, model_input: AgentModelInput) -> AgentModelResult: ...


class AlarmInterpretationModel(Protocol):
    def run(self, model_input: AgentModelInput) -> AgentModelResult: ...


class RuleBasedHealthAssessmentModel:
    def __init__(self, analysis_service: HealthDataAnalysisService) -> None:
        self._analysis = analysis_service

    def run(self, model_input: AgentModelInput) -> AgentModelResult:
        if model_input.scope == "community":
            payload = self._analysis.summarize_community_history(model_input.community_samples)
            summary = (
                f"社区汇总覆盖 {payload.get('device_count', 0)} 台设备，"
                f"高风险 {payload.get('risk_distribution', {}).get('high', 0)} 台。"
            )
        else:
            payload = self._analysis.summarize_device(model_input.samples)
            latest = payload.get("latest", {})
            summary = (
                f"设备 {payload.get('device_mac', model_input.device_mac or '-')}"
                f" 当前风险等级 {payload.get('risk_level', 'unknown')}，"
                f"血氧 {latest.get('blood_oxygen', '--')}%，"
                f"健康分 {latest.get('health_score', '--')}。"
            )
        return AgentModelResult(
            model_name="HealthAssessmentModel",
            status="ok",
            source="analysis_service",
            summary=summary,
            payload=payload if isinstance(payload, dict) else {},
        )


class RuleBasedRiskScoringModel:
    def run(self, model_input: AgentModelInput) -> AgentModelResult:
        if model_input.scope == "community":
            latest_scores = [
                sample.health_score
                for samples in model_input.community_samples.values()
                for sample in samples[-1:]
                if sample.health_score is not None
            ]
            score = round(mean(latest_scores), 2) if latest_scores else None
            payload = {
                "score": score,
                "score_type": "community_average_health_score",
                "device_count": len(model_input.community_samples),
            }
            summary = f"社区平均健康分 {score if score is not None else '--'}。"
        else:
            latest = model_input.samples[-1] if model_input.samples else None
            score = latest.health_score if latest and latest.health_score is not None else None
            payload = {
                "score": score,
                "score_type": "device_health_score",
                "device_mac": getattr(latest, "device_mac", model_input.device_mac),
            }
            summary = f"当前设备健康分 {score if score is not None else '--'}。"
        return AgentModelResult(
            model_name="RiskScoringModel",
            status="ok" if score is not None else "degraded",
            source="health_score_service_compatible",
            summary=summary,
            payload=payload,
            confidence=0.82 if score is not None else None,
            degraded_reason=None if score is not None else "health_score_not_available",
        )


class ServiceBackedAnomalyExplainModel:
    def __init__(
        self,
        scorer: IntelligentAnomalyScorer | None = None,
        clusterer: CommunityHealthClusterer | None = None,
    ) -> None:
        self._scorer = scorer
        self._clusterer = clusterer

    def run(self, model_input: AgentModelInput) -> AgentModelResult:
        if model_input.scope == "community":
            if self._clusterer is None:
                return AgentModelResult(
                    model_name="AnomalyExplainModel",
                    status="degraded",
                    source="placeholder",
                    summary="社区异常解释模型未接入。",
                    degraded_reason="community_clusterer_unavailable",
                )
            latest_samples = [samples[-1] for samples in model_input.community_samples.values() if samples]
            summary = self._clusterer.summarize(latest_samples, model_input.community_samples)
            return AgentModelResult(
                model_name="AnomalyExplainModel",
                status="ok",
                source="community_clusterer",
                summary=f"社区异常聚类已完成，危险设备 {len(summary.clusters.get('danger', []))} 台。",
                payload={
                    "clusters": summary.clusters,
                    "trend": summary.trend,
                    "risk_heatmap": summary.risk_heatmap,
                },
                confidence=0.74,
            )

        if self._scorer is None or len(model_input.samples) < 2:
            return AgentModelResult(
                model_name="AnomalyExplainModel",
                status="degraded",
                source="placeholder",
                summary="设备异常解释模型当前不可用或数据不足。",
                degraded_reason="intelligent_scorer_unavailable_or_insufficient_data",
            )
        device_mac = model_input.device_mac or model_input.samples[-1].device_mac
        result = self._scorer.infer_device(device_mac, model_input.samples, force=True)
        if result is None:
            return AgentModelResult(
                model_name="AnomalyExplainModel",
                status="degraded",
                source="intelligent_scorer",
                summary="当前数据量不足，无法生成智能异常解释。",
                degraded_reason="insufficient_device_history",
            )
        return AgentModelResult(
            model_name="AnomalyExplainModel",
            status="ok",
            source="intelligent_scorer",
            summary=f"智能异常评分 {result.probability:.0%}，原因：{result.reason}",
            payload={
                "probability": result.probability,
                "score": result.score,
                "drift_score": result.drift_score,
                "reconstruction_score": result.reconstruction_score,
                "reason": result.reason,
                "health_score": result.health_score,
                "sustained_minutes": result.sustained_minutes,
                "alarm_ready": result.alarm_ready,
                "attention_weights": result.attention_weights,
                "feature_contributions": result.feature_contributions,
            },
            confidence=result.probability,
        )


class RuleBasedCareSuggestionModel:
    def run(self, model_input: AgentModelInput) -> AgentModelResult:
        recommendations: list[str] = []
        if model_input.scope == "community":
            context_recommendations = model_input.context.get("analysis_recommendations", [])
            if isinstance(context_recommendations, list):
                recommendations = [str(item) for item in context_recommendations[:4]]
            if not recommendations:
                recommendations = ["继续保持社区级巡检，并优先复核高风险设备。"]
        else:
            context_recommendations = model_input.context.get("analysis_recommendations", [])
            if isinstance(context_recommendations, list):
                recommendations = [str(item) for item in context_recommendations[:4]]
            if not recommendations:
                recommendations = ["继续观察生命体征变化，必要时联系家属或医生。"]
        return AgentModelResult(
            model_name="CareSuggestionModel",
            status="ok",
            source="rule_based",
            summary="；".join(recommendations),
            payload={"recommendations": recommendations},
        )


class RuleBasedAlarmInterpretationModel:
    def run(self, model_input: AgentModelInput) -> AgentModelResult:
        alarms = [alarm for alarm in model_input.alarms if not alarm.acknowledged]
        if not alarms:
            return AgentModelResult(
                model_name="AlarmInterpretationModel",
                status="ok",
                source="alarm_service",
                summary="当前没有未确认告警。",
                payload={"active_alarm_count": 0, "active_alarms": []},
            )
        top = alarms[:5]
        summary = "；".join(f"{alarm.alarm_type}:{alarm.message}" for alarm in top)
        return AgentModelResult(
            model_name="AlarmInterpretationModel",
            status="ok",
            source="alarm_service",
            summary=summary,
            payload={
                "active_alarm_count": len(alarms),
                "active_alarms": [
                    {
                        "id": alarm.id,
                        "device_mac": alarm.device_mac,
                        "alarm_type": str(alarm.alarm_type),
                        "alarm_level": int(alarm.alarm_level),
                        "message": alarm.message,
                    }
                    for alarm in top
                ],
            },
        )


class AgentModelSuite:
    def __init__(
        self,
        *,
        health_assessment: HealthAssessmentModel,
        risk_scoring: RiskScoringModel,
        anomaly_explain: AnomalyExplainModel,
        care_suggestion: CareSuggestionModel,
        alarm_interpretation: AlarmInterpretationModel,
    ) -> None:
        self._models = {
            "health_assessment": health_assessment,
            "risk_scoring": risk_scoring,
            "anomaly_explain": anomaly_explain,
            "care_suggestion": care_suggestion,
            "alarm_interpretation": alarm_interpretation,
        }

    def run_all(self, model_input: AgentModelInput) -> dict[str, AgentModelResult]:
        results: dict[str, AgentModelResult] = {}
        for key, model in self._models.items():
            try:
                results[key] = model.run(model_input)
            except Exception as exc:
                results[key] = AgentModelResult(
                    model_name=key,
                    status="degraded",
                    source="placeholder",
                    summary=f"{key} 执行失败，已降级。",
                    degraded_reason=exc.__class__.__name__,
                )
        return results
