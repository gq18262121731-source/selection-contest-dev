from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from ai.anomaly_detector import IntelligentAnomalyScorer
from backend.models.care_model import ElderProfile
from backend.models.health_model import HealthSample
from backend.schemas.health import VitalSignsPayload
from backend.schemas.health_insight_schema import HealthScoreInsightRequest, RecentAlarmInsight
from backend.services.alarm_service import AlarmService
from backend.services.care_service import CareService
from backend.services.device_service import DeviceService
from backend.services.health_score_service import HealthScoreService, ServiceError
from backend.services.stream_service import StreamService


SCORE_NOTICE_FALLBACK = "结构化健康评分模型未完整加载，当前使用规则评分与降级模型评分进行辅助分析。"
TECHNICAL_ERROR_PATTERNS = (
    "Missing model artifacts",
    "static_health_model.pt",
    "feature_scaler.joblib",
    "feature_columns.json",
    "Traceback",
    "Exception",
)
PATH_PATTERN = re.compile(r"([A-Za-z]:\\|/(?:home|usr|var|tmp|opt|mnt|data|Users|workspace)/[^\s\]]+)")


class HealthInsightContextService:
    """Builds a read-only health-score insight context from existing runtime services."""

    def __init__(
        self,
        *,
        care_service: CareService,
        device_service: DeviceService,
        stream_service: StreamService,
        score_service: HealthScoreService,
        alarm_service: AlarmService,
        intelligent_scorer: IntelligentAnomalyScorer,
    ) -> None:
        self._care_service = care_service
        self._device_service = device_service
        self._stream_service = stream_service
        self._score_service = score_service
        self._alarm_service = alarm_service
        self._intelligent_scorer = intelligent_scorer

    def build_context(self, request: HealthScoreInsightRequest) -> dict[str, Any]:
        device_mac = self._normalize_mac(request.device_mac)
        elder = self._find_elder(device_mac=device_mac, elder_id=request.elder_id)
        device = self._device_service.get_device(device_mac)
        latest = self._stream_service.latest(device_mac)
        history = self._stream_service.recent_in_window(
            device_mac,
            minutes=request.window_minutes,
            limit=max(12, request.window_minutes * 12),
        )
        if latest and (not history or history[-1].timestamp != latest.timestamp):
            history.append(latest)

        score_result = self._sanitize_score_result(
            self._score_history(history, elder_id=elder.id if elder else request.elder_id, device_mac=device_mac)
        )
        intelligent_result = self._infer_intelligent(device_mac, history)
        alarms = self._recent_alarms(device_mac=device_mac, window_minutes=request.window_minutes)

        return {
            "device_mac": device_mac,
            "elder": {
                "elder_id": elder.id if elder else request.elder_id,
                "elder_name": elder.name if elder else None,
                "room_no": elder.apartment if elder else None,
            },
            "device": {
                "device_name": getattr(device, "device_name", None),
                "device_status": getattr(device, "status", None).value if getattr(device, "status", None) else None,
            },
            "latest_vitals": self._sample_to_latest_vitals(latest),
            "data_freshness": self._freshness(latest),
            "health_score": score_result,
            "stability": self._stability_from_score(score_result),
            "trend": self._trend_summary(history),
            "time_series_model": intelligent_result,
            "recent_alarms": [alarm.model_dump(mode="json") for alarm in alarms],
            "high_priority_reasons": self._high_priority_reasons(latest, score_result, alarms),
            "missing_fields": self._missing_fields(latest),
            "window_minutes": request.window_minutes,
        }

    @staticmethod
    def _normalize_mac(device_mac: str) -> str:
        compact = "".join(ch for ch in device_mac if ch.isalnum()).upper()
        if len(compact) == 12:
            return ":".join(compact[index : index + 2] for index in range(0, 12, 2))
        return device_mac.strip().upper()

    def _find_elder(self, *, device_mac: str, elder_id: str | None) -> ElderProfile | None:
        directory = self._care_service.get_directory()
        if elder_id:
            match = next((elder for elder in directory.elders if elder.id == elder_id), None)
            if match:
                return match
        return next(
            (
                elder
                for elder in directory.elders
                if device_mac in {self._normalize_mac(mac) for mac in ([elder.device_mac] + list(elder.device_macs or [])) if mac}
            ),
            None,
        )

    def _score_history(
        self,
        history: list[HealthSample],
        *,
        elder_id: str | None,
        device_mac: str,
    ) -> dict[str, Any] | None:
        if not history:
            return None
        try:
            if len(history) >= 2:
                return self._score_service.evaluate_window(
                    window_points=[self._sample_to_window_point(sample) for sample in history],
                    elderly_id=elder_id or "UNKNOWN_ELDER",
                    device_id=device_mac,
                ).model_dump(mode="json")
            latest = history[-1]
            return self._score_service.evaluate_vitals(
                vitals=self._sample_to_vitals(latest),
                elderly_id=elder_id or "UNKNOWN_ELDER",
                device_id=device_mac,
                timestamp=latest.timestamp,
                persist=False,
                stateful_stability=False,
            ).model_dump(mode="json")
        except ServiceError as exc:
            return {"error": exc.code, "message": exc.message}

    def _infer_intelligent(self, device_mac: str, history: list[HealthSample]) -> dict[str, Any]:
        if len(history) < 2:
            return {"ready": False, "message": "时间序列样本不足，模型结果暂缺。"}
        try:
            result = self._intelligent_scorer.infer_device(device_mac, history, now=history[-1].timestamp, force=True)
        except Exception as exc:  # pragma: no cover - defensive around optional model runtime
            return {"ready": False, "message": f"时间序列模型暂不可用：{exc}"}
        if result is None:
            return {"ready": False, "message": "时间序列样本不足，模型结果暂缺。"}
        return {
            "ready": True,
            "probability": result.probability,
            "score": result.score,
            "drift_score": result.drift_score,
            "reconstruction_score": result.reconstruction_score,
            "reason": result.reason,
            "health_score": result.health_score,
            "sustained_minutes": result.sustained_minutes,
            "alarm_ready": result.alarm_ready,
        }

    def _recent_alarms(self, *, device_mac: str, window_minutes: int) -> list[RecentAlarmInsight]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max(1, window_minutes))
        rows = []
        for alarm in self._alarm_service.list_alarms(device_mac=device_mac, active_only=False):
            created_at = alarm.created_at.astimezone(timezone.utc)
            if created_at < cutoff and alarm.acknowledged:
                continue
            rows.append(
                RecentAlarmInsight(
                    alarm_id=alarm.id,
                    alarm_type=alarm.alarm_type.value,
                    alarm_level=int(alarm.alarm_level.value),
                    message=alarm.message,
                    created_at=alarm.created_at,
                    acknowledged=alarm.acknowledged,
                )
            )
        return sorted(rows, key=lambda item: item.created_at, reverse=True)[:10]

    @staticmethod
    def _sample_to_vitals(sample: HealthSample) -> VitalSignsPayload:
        sbp, dbp = sample.blood_pressure_pair
        return VitalSignsPayload(
            heart_rate=float(sample.heart_rate),
            spo2=float(sample.blood_oxygen),
            sbp=float(sbp),
            dbp=float(dbp),
            body_temp=float(sample.temperature),
            fall_detection=False,
            data_accuracy=100.0,
        )

    @classmethod
    def _sample_to_window_point(cls, sample: HealthSample) -> dict[str, object]:
        vitals = cls._sample_to_vitals(sample).model_dump(mode="python")
        vitals["timestamp"] = sample.timestamp
        return vitals

    @staticmethod
    def _sample_to_latest_vitals(sample: HealthSample | None) -> dict[str, Any]:
        if sample is None:
            return {
                "heart_rate": None,
                "spo2": None,
                "blood_pressure": None,
                "body_temp": None,
                "steps": None,
                "updated_at": None,
            }
        return {
            "heart_rate": sample.heart_rate,
            "spo2": sample.blood_oxygen,
            "blood_pressure": sample.blood_pressure,
            "body_temp": sample.temperature,
            "steps": sample.steps,
            "updated_at": sample.timestamp.isoformat(),
        }

    @staticmethod
    def _freshness(sample: HealthSample | None) -> str:
        if sample is None:
            return "missing"
        age = datetime.now(timezone.utc) - sample.timestamp.astimezone(timezone.utc)
        return "fresh" if age <= timedelta(minutes=2) else "stale"

    @staticmethod
    def _stability_from_score(score_result: dict[str, Any] | None) -> dict[str, Any]:
        if not score_result:
            return {"active_events": [], "stabilized_vitals": None, "score_adjustment_reason": None}
        return {
            "active_events": score_result.get("active_events", []),
            "stabilized_vitals": score_result.get("stabilized_vitals"),
            "score_adjustment_reason": score_result.get("score_adjustment_reason"),
        }

    def _trend_summary(self, history: list[HealthSample]) -> dict[str, Any]:
        if not history:
            return {"sample_count": 0, "metrics": {}, "summary": "近段时间趋势数据暂缺。"}
        metrics = {
            "heart_rate": [float(sample.heart_rate) for sample in history],
            "spo2": [float(sample.blood_oxygen) for sample in history],
            "body_temp": [float(sample.temperature) for sample in history],
            "sbp": [float(sample.blood_pressure_pair[0]) for sample in history],
            "dbp": [float(sample.blood_pressure_pair[1]) for sample in history],
        }
        return {
            "sample_count": len(history),
            "start_at": history[0].timestamp.isoformat(),
            "end_at": history[-1].timestamp.isoformat(),
            "metrics": {name: self._metric_summary(name, values) for name, values in metrics.items()},
        }

    def _metric_summary(self, name: str, values: list[float]) -> dict[str, Any]:
        first = values[0]
        last = values[-1]
        delta = last - first
        abnormal_count = sum(1 for value in values if self._is_abnormal(name, value))
        return {
            "min": min(values),
            "max": max(values),
            "latest": last,
            "direction": "up" if delta > 1 else "down" if delta < -1 else "stable",
            "sustained_abnormal": abnormal_count >= max(2, len(values) // 2),
            "abnormal_count": abnormal_count,
        }

    @staticmethod
    def _is_abnormal(name: str, value: float) -> bool:
        if name == "heart_rate":
            return value < 50 or value > 110
        if name == "spo2":
            return value < 92
        if name == "body_temp":
            return value < 35.5 or value >= 38.0
        if name == "sbp":
            return value < 90 or value >= 160
        if name == "dbp":
            return value < 60 or value >= 100
        return False

    @staticmethod
    def _missing_fields(sample: HealthSample | None) -> list[str]:
        if sample is None:
            return ["heart_rate", "spo2", "blood_pressure", "body_temp", "steps", "updated_at"]
        missing = []
        if sample.blood_pressure is None:
            missing.append("blood_pressure")
        if sample.steps is None:
            missing.append("steps")
        return missing

    def _high_priority_reasons(
        self,
        latest: HealthSample | None,
        score_result: dict[str, Any] | None,
        alarms: list[RecentAlarmInsight],
    ) -> list[str]:
        reasons: list[str] = []
        for alarm in alarms:
            if alarm.alarm_type in {"sos", "fall_detected", "fall_injury_risk", "video_fall"} and not alarm.acknowledged:
                reasons.append(f"{alarm.alarm_type} 告警未确认，请优先联系现场值守人员核查。")
        if latest:
            sbp, dbp = latest.blood_pressure_pair
            if latest.blood_oxygen < 90:
                reasons.append("血氧明显偏低，请优先复核设备读数并联系医护人员。")
            if latest.heart_rate >= 140 or latest.heart_rate < 40:
                reasons.append("心率达到高优先级阈值，请立即复核并安排现场查看。")
            if sbp >= 180 or dbp >= 110:
                reasons.append("血压达到高优先级阈值，请优先联系医护人员。")
            if latest.temperature >= 39.0:
                reasons.append("体温明显异常，请尽快复测并联系医护人员。")
        if score_result and score_result.get("risk_level") == "critical":
            reasons.append("健康评分规则结果为 critical，请按高优先级流程处置。")
        return list(dict.fromkeys(reasons))

    @staticmethod
    def _contains_technical_error(value: Any) -> bool:
        text = str(value or "")
        return any(pattern in text for pattern in TECHNICAL_ERROR_PATTERNS) or bool(PATH_PATTERN.search(text))

    @classmethod
    def _sanitize_score_result(cls, score_result: dict[str, Any] | None) -> dict[str, Any] | None:
        if not score_result:
            return score_result

        sanitized = dict(score_result)
        raw_error = sanitized.get("error")
        raw_message = sanitized.get("message")
        raw_adjustment = sanitized.get("score_adjustment_reason")
        has_technical_error = any(
            cls._contains_technical_error(value)
            for value in (raw_error, raw_message, raw_adjustment)
        )
        if not has_technical_error:
            return sanitized

        sanitized["model_artifacts_available"] = False
        sanitized["score_mode"] = "fallback"
        sanitized["score_notice"] = SCORE_NOTICE_FALLBACK
        sanitized.pop("message", None)
        sanitized.pop("error", None)
        if cls._contains_technical_error(raw_adjustment):
            sanitized["score_adjustment_reason"] = SCORE_NOTICE_FALLBACK
        return sanitized
