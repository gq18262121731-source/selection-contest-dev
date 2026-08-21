from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from backend.models.robot_model import RobotTask
from backend.models.robot_navigation_model import RobotMap, RobotSafetyChecks, RobotSafetyInterlock
from backend.repositories.robot_map_repo import RobotMapRepository
from backend.repositories.robot_task_repo import RobotTaskRepository
from backend.services.robot_navigation_gateway_service import RobotNavigationGatewayResult
from backend.services.robot_safety_interlock_service import RobotSafetyInterlockService


@dataclass(frozen=True)
class RobotEffectiveSafetySnapshot:
    """One immutable view shared by navigation reads and operation preflight."""

    gateway_state: dict[str, Any]
    checks: RobotSafetyChecks
    interlock: RobotSafetyInterlock
    active_map: RobotMap | None
    current_task: RobotTask | None
    fetched_at: datetime
    state_age_ms: int
    state_fresh: bool


class RobotNavigationSafetyStateResolver:
    """Combines fresh gateway runtime state with the main-system active map."""

    def __init__(
        self,
        *,
        map_repository: RobotMapRepository,
        task_repository: RobotTaskRepository,
        safety_service: RobotSafetyInterlockService,
        state_max_age_seconds: float = 3.0,
    ) -> None:
        self.maps = map_repository
        self.tasks = task_repository
        self.safety = safety_service
        self.state_max_age_seconds = max(0.1, float(state_max_age_seconds))

    def resolve(
        self,
        gateway_result: RobotNavigationGatewayResult,
        *,
        now: datetime | None = None,
    ) -> RobotEffectiveSafetySnapshot:
        checked_at = now or datetime.now(timezone.utc)
        fetched_at = self._as_utc(gateway_result.fetched_at)
        state_age_ms = max(0, int((checked_at - fetched_at).total_seconds() * 1000))
        state_fresh = state_age_ms <= int(self.state_max_age_seconds * 1000)
        gateway_state = dict(gateway_result.data)
        active_map = self.maps.get_active_map()
        current_task = next(
            (
                task
                for task in self.tasks.list_tasks(limit=50)
                if task.status.value in {"QUEUED", "RUNNING", "BLOCKED"}
            ),
            None,
        )

        checks = RobotSafetyChecks(
            robot_online=state_fresh and gateway_state.get("robot_online") is True,
            emergency_stop_clear=state_fresh and gateway_state.get("emergency_stop_clear") is True,
            localization_valid=state_fresh and gateway_state.get("localization_valid") is True,
            map_loaded=(
                state_fresh
                and gateway_state.get("map_loaded") is True
                and active_map is not None
            ),
            path_plannable=state_fresh and gateway_state.get("path_plannable") is True,
            robot_stationary=state_fresh and gateway_state.get("robot_stationary") is True,
            control_available=state_fresh and gateway_state.get("control_available") is True,
        )
        interlock = self.safety.check_navigation(checks)
        return RobotEffectiveSafetySnapshot(
            gateway_state=gateway_state,
            checks=checks,
            interlock=interlock,
            active_map=active_map,
            current_task=current_task,
            fetched_at=fetched_at,
            state_age_ms=state_age_ms,
            state_fresh=state_fresh,
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
