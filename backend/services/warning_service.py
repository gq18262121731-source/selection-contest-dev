from __future__ import annotations

from datetime import datetime, timezone

from backend.schemas.warning import WarningCheckRequest, WarningCheckResponse
from backend.services.health_score_service import HealthScoreService


class WarningService:
    """Health warning facade for single-point and window inputs."""

    def __init__(self, *, health_score_service: HealthScoreService) -> None:
        self.health_score_service = health_score_service

    def check(self, request: WarningCheckRequest) -> WarningCheckResponse:
        """Evaluate the current point or aggregate an entire window."""

        if request.current_data is not None:
            window_mode = "single_point"
            health_result = self.health_score_service.evaluate_vitals(
                vitals=request.current_data,
                elderly_id="WARNING_CHECK",
                device_id="WARNING_SINGLE_POINT",
                timestamp=datetime.now(timezone.utc),
                persist=False,
                stateful_stability=False,
            )
        else:
            window_mode = "event_aggregated_window"
            health_result = self.health_score_service.evaluate_window(
                window_points=[point.model_dump(mode="python") for point in request.window_data],
                elderly_id="WARNING_CHECK",
                device_id="WINDOW_AGGREGATED",
            )
        return WarningCheckResponse(
            evaluated_at=health_result.timestamp,
            window_mode=window_mode,
            health_score=health_result.health_score,
            risk_level=health_result.risk_level,
            alerts=health_result.alerts,
            abnormal_tags=health_result.abnormal_tags,
            trigger_reasons=health_result.trigger_reasons,
            recommendation_code=health_result.recommendation_code,
            stability_mode=health_result.stability_mode,
            stabilized_vitals=health_result.stabilized_vitals,
            active_events=health_result.active_events,
            score_adjustment_reason=health_result.score_adjustment_reason,
        )
