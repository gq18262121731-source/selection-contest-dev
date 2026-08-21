from __future__ import annotations

from datetime import datetime, timezone

from backend.models.robot_navigation_model import RobotSafetyChecks, RobotSafetyInterlock


class RobotSafetyInterlockService:
    """Evaluates deterministic Mock safety inputs without touching robot hardware."""

    NAVIGATION_CHECKS = (
        ("robot_online", "ROBOT_OFFLINE"),
        ("emergency_stop_clear", "EMERGENCY_STOP_ACTIVE"),
        ("localization_valid", "LOCALIZATION_INVALID"),
        ("map_loaded", "MAP_NOT_LOADED"),
        ("path_plannable", "PATH_NOT_PLANNABLE"),
        ("robot_stationary", "ROBOT_NOT_STATIONARY"),
        ("control_available", "CONTROL_NOT_AVAILABLE"),
    )
    MAPPING_CHECKS = (
        ("robot_online", "ROBOT_OFFLINE"),
        ("emergency_stop_clear", "EMERGENCY_STOP_ACTIVE"),
        ("robot_stationary", "ROBOT_NOT_STATIONARY"),
        ("control_available", "CONTROL_NOT_AVAILABLE"),
    )

    def check_navigation(self, checks: RobotSafetyChecks) -> RobotSafetyInterlock:
        return self._evaluate(checks, self.NAVIGATION_CHECKS)

    def check_mapping(self, checks: RobotSafetyChecks) -> RobotSafetyInterlock:
        return self._evaluate(checks, self.MAPPING_CHECKS)

    @staticmethod
    def _evaluate(
        checks: RobotSafetyChecks,
        requirements: tuple[tuple[str, str], ...],
    ) -> RobotSafetyInterlock:
        blocked_by = [code for field, code in requirements if not getattr(checks, field)]
        return RobotSafetyInterlock(
            passed=not blocked_by,
            checks=checks,
            blocked_by=blocked_by,
            checked_at=datetime.now(timezone.utc),
        )
