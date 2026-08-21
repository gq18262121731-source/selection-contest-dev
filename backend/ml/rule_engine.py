from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from backend.config import get_settings
from backend.ml.scoring import clamp_score


RISK_ORDER: dict[str, int] = {
    "normal": 0,
    "attention": 1,
    "warning": 2,
    "critical": 3,
}


@dataclass(slots=True)
class HardThresholdResult:
    level: str | None
    trigger_reasons: list[str]


@dataclass(slots=True)
class RuleAssessment:
    rule_health_score: float
    base_score: float
    fall_penalty: float
    quality_factor: float
    sub_scores: dict[str, float]
    abnormal_tags: list[str]
    hard_threshold: HardThresholdResult


class HealthRuleEngine:
    """Explainable rule engine for health scoring and warning detection."""

    def __init__(self) -> None:
        settings = get_settings()
        self.weights = settings.rule_score_weights
        self.quality_floor = settings.rule_quality_floor
        self.signal_quality_threshold = settings.poor_signal_quality_threshold

    def hr_score(self, heart_rate: float) -> float:
        if 60 <= heart_rate <= 100:
            return 100.0
        if 50 <= heart_rate < 60:
            return 85.0
        if 100 < heart_rate <= 110:
            return 80.0
        if 40 <= heart_rate < 50:
            return 65.0
        if 110 < heart_rate <= 130:
            return 60.0
        return 35.0

    def spo2_score(self, spo2: float) -> float:
        if spo2 >= 95:
            return 100.0
        if 93 <= spo2 < 95:
            return 85.0
        if 90 <= spo2 < 93:
            return 65.0
        if 88 <= spo2 < 90:
            return 45.0
        return 20.0

    def bp_score(self, sbp: float, dbp: float) -> float:
        if sbp < 120 and dbp < 80:
            return 100.0
        if 120 <= sbp < 130 and dbp < 80:
            return 88.0
        if 130 <= sbp < 140 or 80 <= dbp < 90:
            return 72.0
        if 140 <= sbp < 160 or 90 <= dbp < 100:
            return 50.0
        if 160 <= sbp < 180 or 100 <= dbp < 110:
            return 30.0
        return 15.0

    def temp_score(self, body_temp: float) -> float:
        if 36.3 <= body_temp <= 37.2:
            return 100.0
        if 37.2 < body_temp <= 37.5:
            return 82.0
        if 37.5 < body_temp <= 38.0:
            return 60.0
        if 36.0 <= body_temp < 36.3:
            return 82.0
        return 40.0

    def assess(self, payload: Mapping[str, float | int]) -> RuleAssessment:
        heart_rate = float(payload["heart_rate"])
        spo2 = float(payload["spo2"])
        sbp = float(payload["sbp"])
        dbp = float(payload["dbp"])
        body_temp = float(payload["body_temp"])
        fall_detection = int(payload.get("fall_detection", 0))
        data_accuracy = float(payload.get("data_accuracy", 100.0))

        score_hr = self.hr_score(heart_rate)
        score_spo2 = self.spo2_score(spo2)
        score_bp = self.bp_score(sbp, dbp)
        score_temp = self.temp_score(body_temp)
        base_score = (
            self.weights["heart_rate"] * score_hr
            + self.weights["spo2"] * score_spo2
            + self.weights["blood_pressure"] * score_bp
            + self.weights["body_temp"] * score_temp
        )
        fall_penalty = 20.0 if fall_detection == 1 else 0.0
        quality_factor = min(max(data_accuracy / 100.0, self.quality_floor), 1.0)
        rule_health_score = clamp_score((base_score - fall_penalty) * quality_factor)
        abnormal_tags = self.generate_abnormal_tags(payload)
        hard_threshold = self.evaluate_hard_thresholds(payload)
        return RuleAssessment(
            rule_health_score=rule_health_score,
            base_score=base_score,
            fall_penalty=fall_penalty,
            quality_factor=quality_factor,
            sub_scores={
                "score_hr": score_hr,
                "score_spo2": score_spo2,
                "score_bp": score_bp,
                "score_temp": score_temp,
                "base_score": base_score,
                "fall_penalty": fall_penalty,
                "quality_factor": quality_factor,
            },
            abnormal_tags=abnormal_tags,
            hard_threshold=hard_threshold,
        )

    def determine_risk_level(self, final_health_score: float) -> str:
        if final_health_score >= 85:
            return "normal"
        if final_health_score >= 70:
            return "attention"
        if final_health_score >= 50:
            return "warning"
        return "critical"

    def upgrade_risk_level(self, base_level: str, hard_level: str | None) -> str:
        if hard_level is None:
            return base_level
        return hard_level if RISK_ORDER[hard_level] > RISK_ORDER[base_level] else base_level

    def evaluate_hard_thresholds(self, payload: Mapping[str, float | int]) -> HardThresholdResult:
        heart_rate = float(payload["heart_rate"])
        spo2 = float(payload["spo2"])
        sbp = float(payload["sbp"])
        dbp = float(payload["dbp"])
        body_temp = float(payload["body_temp"])
        fall_detection = int(payload.get("fall_detection", 0))

        warning_reasons: list[str] = []
        critical_reasons: list[str] = []

        if spo2 < 90:
            warning_reasons.append("SpO2 below 90%")
        if heart_rate > 130:
            warning_reasons.append("Heart rate above 130 bpm")
        if heart_rate < 45:
            warning_reasons.append("Heart rate below 45 bpm")
        if sbp >= 160:
            warning_reasons.append("Systolic blood pressure above or equal to 160 mmHg")
        if dbp >= 100:
            warning_reasons.append("Diastolic blood pressure above or equal to 100 mmHg")
        if body_temp >= 38.0:
            warning_reasons.append("Body temperature above or equal to 38.0 C")
        if fall_detection == 1:
            warning_reasons.append("Fall detection triggered")

        if spo2 < 88:
            critical_reasons.append("SpO2 below 88%")
        if heart_rate > 140:
            critical_reasons.append("Heart rate above 140 bpm")
        if heart_rate < 40:
            critical_reasons.append("Heart rate below 40 bpm")
        if sbp >= 180:
            critical_reasons.append("Systolic blood pressure above or equal to 180 mmHg")
        if dbp >= 110:
            critical_reasons.append("Diastolic blood pressure above or equal to 110 mmHg")
        if body_temp >= 39.0:
            critical_reasons.append("Body temperature above or equal to 39.0 C")
        if fall_detection == 1 and (spo2 < 90 or heart_rate > 130):
            critical_reasons.append("Fall with concurrent hypoxia or severe tachycardia")

        if critical_reasons:
            return HardThresholdResult(level="critical", trigger_reasons=critical_reasons)
        if warning_reasons:
            return HardThresholdResult(level="warning", trigger_reasons=warning_reasons)
        return HardThresholdResult(level=None, trigger_reasons=[])

    def generate_abnormal_tags(self, payload: Mapping[str, float | int]) -> list[str]:
        heart_rate = float(payload["heart_rate"])
        spo2 = float(payload["spo2"])
        sbp = float(payload["sbp"])
        dbp = float(payload["dbp"])
        body_temp = float(payload["body_temp"])
        fall_detection = int(payload.get("fall_detection", 0))
        data_accuracy = float(payload.get("data_accuracy", 100.0))

        tags: list[str] = []
        if heart_rate > 100:
            tags.append("tachycardia")
        if heart_rate < 60:
            tags.append("bradycardia")
        if spo2 < 90:
            tags.append("low_spo2")
        if sbp >= 140 or dbp >= 90:
            tags.append("hypertension")
        if body_temp >= 37.3:
            tags.append("fever")
        if fall_detection == 1:
            tags.append("fall_detected")
        if data_accuracy < self.signal_quality_threshold:
            tags.append("poor_signal_quality")
        return sorted(set(tags))

    def recommendation_code(
        self,
        risk_level: str,
        *,
        hard_threshold_level: str | None,
        abnormal_tags: list[str],
    ) -> str:
        if risk_level == "critical":
            emergency_tags = {"fall_detected", "low_spo2"}
            if hard_threshold_level == "critical" and (emergency_tags & set(abnormal_tags)):
                return "EMERGENCY_RESPONSE"
            if hard_threshold_level == "critical":
                return "URGENT_COMMUNITY_INTERVENTION"
            return "URGENT_COMMUNITY_INTERVENTION"
        if risk_level == "warning":
            return "RISK_OBSERVE_AND_NOTIFY"
        if risk_level == "attention":
            return "HEALTH_OBSERVE"
        return "HEALTH_OK"
