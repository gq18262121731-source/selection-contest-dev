from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.ml.inference import HealthInferenceEngine, InferenceError, ModelArtifactMissingError
from backend.ml.preprocess import DataValidationError
from backend.ml.rule_engine import HealthRuleEngine, RISK_ORDER
from backend.repositories.score_repo import ScoreRepository
from backend.repositories.warning_repo import WarningRepository
from backend.repositories.wearable_repo import WearableRepository
from backend.schemas.health import AlertPrediction, AlertSummary, HealthScoreRequest, HealthScoreResponse, VitalSignsPayload
from backend.services.health_stability_service import HealthStabilityService, StabilitySnapshot


@dataclass(slots=True)
class ServiceError(Exception):
    """API-facing service error."""

    code: str
    message: str
    status_code: int
    details: dict[str, object] = field(default_factory=dict)


class HealthScoreService:
    """Facade around preprocessing, inference and persistence."""

    def __init__(
        self,
        *,
        inference_engine: HealthInferenceEngine,
        wearable_repo: WearableRepository,
        score_repo: ScoreRepository,
        warning_repo: WarningRepository,
        stability_service: HealthStabilityService,
    ) -> None:
        self.inference_engine = inference_engine
        self.wearable_repo = wearable_repo
        self.score_repo = score_repo
        self.warning_repo = warning_repo
        self.stability_service = stability_service
        self.rule_engine = HealthRuleEngine()
        self.score_max_drop_per_sample = self.inference_engine.settings.score_max_drop_per_sample

    def score(self, request: HealthScoreRequest) -> HealthScoreResponse:
        """Score a realtime health request and persist the result."""

        return self.evaluate_vitals(
            vitals=request,
            elderly_id=request.elderly_id,
            device_id=request.device_id,
            timestamp=request.timestamp,
            persist=True,
            stateful_stability=True,
        )

    def evaluate_vitals(
        self,
        *,
        vitals: VitalSignsPayload,
        elderly_id: str = "UNKNOWN",
        device_id: str = "UNKNOWN",
        timestamp: datetime | None = None,
        persist: bool = False,
        stateful_stability: bool = False,
    ) -> HealthScoreResponse:
        """Evaluate a single vital-signs point."""

        evaluated_at = timestamp or datetime.now(timezone.utc)
        try:
            snapshot = self.stability_service.process_point(
                device_id=device_id,
                timestamp=evaluated_at,
                vitals=vitals.model_dump(mode="python"),
                stateful=stateful_stability,
            )
            response = self._score_snapshot(
                snapshot=snapshot,
                elderly_id=elderly_id,
                device_id=device_id,
                evaluated_at=evaluated_at,
                stateful_stability=stateful_stability,
            )
        except DataValidationError as exc:
            raise ServiceError(
                code="VALIDATION_ERROR",
                message=str(exc),
                status_code=400,
                details={"payload": vitals.model_dump(mode="json")},
            ) from exc
        except ModelArtifactMissingError as exc:
            raise ServiceError(
                code="MODEL_ARTIFACT_MISSING",
                message=str(exc),
                status_code=503,
            ) from exc
        except InferenceError as exc:
            raise ServiceError(
                code="INFERENCE_ERROR",
                message=str(exc),
                status_code=500,
            ) from exc

        if persist:
            vitals_payload = vitals.model_dump(mode="json")
            self.wearable_repo.save_event(
                elderly_id=elderly_id,
                device_id=device_id,
                timestamp=evaluated_at,
                payload=vitals_payload,
            )
            self.score_repo.save_result(
                elderly_id=elderly_id,
                device_id=device_id,
                timestamp=evaluated_at,
                result=response.model_dump(mode="json"),
            )
            self.warning_repo.save_result(
                evaluated_at=evaluated_at,
                risk_level=response.risk_level,
                recommendation_code=response.recommendation_code,
                trigger_reasons=response.trigger_reasons,
                abnormal_tags=response.abnormal_tags,
                payload=response.model_dump(mode="json"),
            )

        return response

    def evaluate_window(
        self,
        *,
        window_points: list[dict[str, object]],
        elderly_id: str = "WARNING_CHECK",
        device_id: str = "WINDOW_AGGREGATED",
    ) -> HealthScoreResponse:
        """Evaluate a full window with stateless event aggregation."""

        if not window_points:
            raise ServiceError(
                code="VALIDATION_ERROR",
                message="window_data must not be empty",
                status_code=400,
            )
        try:
            snapshot = self.stability_service.process_window(window_points)
            evaluated_at = snapshot.active_events[-1]["last_seen_time"] if snapshot.active_events else datetime.now(timezone.utc)
            latest_timestamp = window_points[-1].get("timestamp")
            if isinstance(latest_timestamp, datetime):
                evaluated_at = latest_timestamp
            elif isinstance(latest_timestamp, str) and latest_timestamp.strip():
                evaluated_at = datetime.fromisoformat(latest_timestamp)
            return self._score_snapshot(
                snapshot=snapshot,
                elderly_id=elderly_id,
                device_id=device_id,
                evaluated_at=evaluated_at,
                stateful_stability=False,
            )
        except DataValidationError as exc:
            raise ServiceError(
                code="VALIDATION_ERROR",
                message=str(exc),
                status_code=400,
                details={"window_size": len(window_points)},
            ) from exc
        except ModelArtifactMissingError as exc:
            raise ServiceError(
                code="MODEL_ARTIFACT_MISSING",
                message=str(exc),
                status_code=503,
            ) from exc
        except InferenceError as exc:
            raise ServiceError(
                code="INFERENCE_ERROR",
                message=str(exc),
                status_code=500,
            ) from exc

    def _score_snapshot(
        self,
        *,
        snapshot: StabilitySnapshot,
        elderly_id: str,
        device_id: str,
        evaluated_at: datetime,
        stateful_stability: bool,
    ) -> HealthScoreResponse:
        result = self.inference_engine.predict(snapshot.stabilized_vitals)
        stable_score = float(result["final_health_score"])
        score_adjustment_reason: str | None = None

        if snapshot.severe_hard_threshold.level is not None:
            adjusted_score = min(stable_score, self._severe_score_cap(snapshot))
            if adjusted_score < stable_score:
                score_adjustment_reason = "Immediate severe thresholds bypassed score damping."
        else:
            previous_score = self.stability_service.get_last_score(device_id) if stateful_stability else None
            adjusted_score = stable_score
            if previous_score is not None and stable_score < previous_score:
                adjusted_score = max(stable_score, previous_score - self.score_max_drop_per_sample)
                if adjusted_score > stable_score:
                    score_adjustment_reason = (
                        f"Score drop capped at {self.score_max_drop_per_sample:.1f} points for jitter suppression."
                    )
            elif snapshot.raw_hard_threshold.level is not None and not snapshot.active_events:
                score_adjustment_reason = "Short-lived raw fluctuations were smoothed by the recent-window stabilizer."

        if stateful_stability:
            self.stability_service.set_last_score(device_id, adjusted_score)

        applied_hard_level = self._highest_severity_optional(
            [
                result["alerts"]["hard_threshold_level"],
                snapshot.severe_hard_threshold.level,
            ]
        )
        event_severity = self._highest_severity_optional([event["severity"] for event in snapshot.active_events])
        base_level = self.rule_engine.determine_risk_level(adjusted_score)
        risk_level = self._highest_severity([base_level, applied_hard_level, event_severity])

        trigger_reasons = self._select_trigger_reasons(snapshot, result)
        abnormal_tags = self._select_abnormal_tags(snapshot, result)
        recommendation_code = self.rule_engine.recommendation_code(
            risk_level,
            hard_threshold_level=applied_hard_level,
            abnormal_tags=abnormal_tags,
        )
        sub_scores = {key: float(value) for key, value in result["sub_scores"].items()}
        sub_scores["stabilized_final_health_score"] = round(float(result["final_health_score"]), 4)
        sub_scores["final_health_score"] = round(float(adjusted_score), 4)

        return HealthScoreResponse(
            elderly_id=elderly_id,
            device_id=device_id,
            timestamp=evaluated_at,
            health_score=round(float(adjusted_score), 4),
            final_health_score=round(float(adjusted_score), 4),
            rule_health_score=float(result["rule_health_score"]),
            model_health_score=float(result["model_health_score"]),
            risk_level=risk_level,
            risk_score_raw=float(result["risk_score_raw"]),
            sub_scores=sub_scores,
            alerts=AlertSummary(
                hr_alert=AlertPrediction(**result["alerts"]["hr_alert"]),
                spo2_alert=AlertPrediction(**result["alerts"]["spo2_alert"]),
                bp_alert=AlertPrediction(**result["alerts"]["bp_alert"]),
                temp_alert=AlertPrediction(**result["alerts"]["temp_alert"]),
                hard_threshold_level=applied_hard_level,
            ),
            abnormal_tags=abnormal_tags,
            trigger_reasons=trigger_reasons,
            recommendation_code=str(recommendation_code),
            stability_mode=snapshot.stability_mode,
            stabilized_vitals=VitalSignsPayload(**snapshot.stabilized_vitals),
            active_events=list(snapshot.active_events),
            score_adjustment_reason=score_adjustment_reason,
        )

    def _select_trigger_reasons(self, snapshot: StabilitySnapshot, result: dict[str, object]) -> list[str]:
        if snapshot.active_events:
            return [str(event["trigger_reason"]) for event in snapshot.active_events]
        if snapshot.severe_hard_threshold.trigger_reasons:
            return list(snapshot.severe_hard_threshold.trigger_reasons)
        return [str(reason) for reason in result["trigger_reasons"]]

    def _select_abnormal_tags(self, snapshot: StabilitySnapshot, result: dict[str, object]) -> list[str]:
        tags: list[str] = []
        tags.extend(str(event["event_type"]) for event in snapshot.active_events)
        if snapshot.severe_hard_threshold.level is not None:
            tags.extend(snapshot.raw_abnormal_tags)
        else:
            tags.extend(str(tag) for tag in result["abnormal_tags"])
        seen: set[str] = set()
        deduped: list[str] = []
        for tag in tags:
            if tag not in seen:
                seen.add(tag)
                deduped.append(tag)
        return deduped

    def _highest_severity(self, levels: list[str | None]) -> str:
        resolved = [level for level in levels if level]
        if not resolved:
            return "normal"
        return max(resolved, key=lambda item: RISK_ORDER[item])

    def _highest_severity_optional(self, levels: list[str | None]) -> str | None:
        resolved = [level for level in levels if level]
        if not resolved:
            return None
        return max(resolved, key=lambda item: RISK_ORDER[item])

    def _severe_score_cap(self, snapshot: StabilitySnapshot) -> float:
        if snapshot.severe_hard_threshold.level == "critical":
            return 45.0
        raw_rule_score = self.rule_engine.assess(snapshot.raw_vitals).rule_health_score
        return min(raw_rule_score, 68.0)
