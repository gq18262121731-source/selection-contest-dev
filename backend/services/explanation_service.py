from __future__ import annotations

from backend.schemas.agent import HealthExplainRequest, HealthExplainResponse


EVENT_LABELS: dict[str, str] = {
    "tachycardia": "心率持续偏高",
    "bradycardia": "心率持续偏低",
    "low_spo2": "血氧持续偏低",
    "hypertension": "血压持续偏高",
    "fever": "体温持续偏高",
    "fall_detected": "检测到跌倒事件",
    "poor_signal_quality": "信号质量持续偏低",
}


class ExplanationService:
    """Generate role-aware structured explanations without external LLM calls."""

    def explain(self, request: HealthExplainRequest) -> HealthExplainResponse:
        result = request.health_result
        event_labels = [EVENT_LABELS.get(event.event_type, event.event_type) for event in result.active_events]
        tag_labels = [EVENT_LABELS.get(tag, tag) for tag in result.abnormal_tags]
        labels = event_labels or tag_labels or ["当前未识别到持续异常事件"]
        label_text = "、".join(labels)

        if request.role == "elderly":
            summary = (
                f"当前健康分为 {result.health_score:.1f} 分，风险等级为 {result.risk_level}。"
                f" 系统重点关注：{label_text}。"
            )
            advice = self._advice_for_elderly(result.recommendation_code)
        elif request.role == "community":
            summary = (
                f"该老人当前健康分为 {result.health_score:.1f} 分，风险等级为 {result.risk_level}。"
                f" 当前需要重点跟踪：{label_text}。"
            )
            advice = self._advice_for_community(result.recommendation_code)
        else:
            summary = (
                f"老人当前健康分为 {result.health_score:.1f} 分，风险等级为 {result.risk_level}。"
                f" 系统当前识别到：{label_text}。"
            )
            advice = self._advice_for_children(result.recommendation_code)

        trigger_text = "；".join(result.trigger_reasons) if result.trigger_reasons else "本次未触发硬阈值直通，结果主要来自稳定化后的持续事件判断。"
        stabilization_text = "系统已启用近期窗口稳定化与事件聚合，轻微单点波动不会直接拉低评分。"
        if result.score_adjustment_reason:
            stabilization_text = f"{stabilization_text} 当前分数调整说明：{result.score_adjustment_reason}"

        severity_explanation = (
            f"{stabilization_text} 结构化触发原因：{trigger_text}"
        )
        return HealthExplainResponse(
            role=request.role,
            summary=summary,
            advice=advice,
            severity_explanation=severity_explanation,
        )

    @staticmethod
    def _advice_for_elderly(code: str) -> list[str]:
        mapping = {
            "HEALTH_OK": ["当前状态比较平稳，保持正常作息并继续佩戴设备即可。"],
            "HEALTH_OBSERVE": ["建议先休息并补充水分，稍后复测关键指标。"],
            "RISK_OBSERVE_AND_NOTIFY": ["建议尽快复测，并联系家属或社区人员协助观察。"],
            "URGENT_COMMUNITY_INTERVENTION": ["建议立刻联系社区工作人员或医护人员进行现场评估。"],
            "EMERGENCY_RESPONSE": ["请立即呼叫急救或寻求现场帮助，不要独自处理。"],
        }
        return mapping.get(code, ["请持续关注身体状态，如有明显不适请尽快求助。"])

    @staticmethod
    def _advice_for_children(code: str) -> list[str]:
        mapping = {
            "HEALTH_OK": ["当前可以维持常规关注，继续查看后续趋势即可。"],
            "HEALTH_OBSERVE": ["建议提醒老人休息、补水，并在短时间内再次测量。"],
            "RISK_OBSERVE_AND_NOTIFY": ["建议尽快联系老人，并同步通知社区端做持续观察。"],
            "URGENT_COMMUNITY_INTERVENTION": ["建议立即联系社区值守或附近照护人员到场核查。"],
            "EMERGENCY_RESPONSE": ["建议立即联系急救和社区现场人员，同时持续尝试联系老人。"],
        }
        return mapping.get(code, ["建议继续观察老人状态，并保留本次监测结果。"])

    @staticmethod
    def _advice_for_community(code: str) -> list[str]:
        mapping = {
            "HEALTH_OK": ["维持常规巡检频率，继续观察后续趋势。"],
            "HEALTH_OBSERVE": ["建议安排短周期复测，并确认异常是否持续。"],
            "RISK_OBSERVE_AND_NOTIFY": ["建议将对象列入重点随访，并同步家属。"],
            "URGENT_COMMUNITY_INTERVENTION": ["建议立即安排现场干预或上门核查。"],
            "EMERGENCY_RESPONSE": ["建议立即启动应急响应流程并联系急救资源。"],
        }
        return mapping.get(code, ["建议纳入社区重点关注名单并持续跟踪。"])
