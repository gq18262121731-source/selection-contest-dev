from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.models.robot_model import (
    RobotTask,
    RobotTaskStatus,
    RobotTaskStep,
    RobotTaskTimeline,
)
from backend.models.robot_navigation_model import (
    RobotControlOwner,
    RobotNavigationEvent,
    RobotNavigationExecutionState,
    RobotSafetyChecks,
)
from backend.repositories.robot_navigation_repo import RobotNavigationRepository
from backend.repositories.robot_task_repo import RobotTaskRepository
from backend.services.robot_map_service import RobotMapService
from backend.services.robot_navigation_errors import (
    RobotNavigationErrorCode,
    RobotNavigationServiceError,
)
from backend.services.robot_navigation_gateway_service import RobotNavigationGatewayResult, RobotNavigationGatewayService
from backend.services.robot_safety_interlock_service import RobotSafetyInterlockService


class RobotNavigationStateCoordinator:
    """Single source of truth for fine-grained Mock task transitions."""

    ALLOWED: dict[RobotNavigationExecutionState, set[RobotNavigationExecutionState]] = {
        RobotNavigationExecutionState.CREATED: {RobotNavigationExecutionState.SAFETY_CHECKING, RobotNavigationExecutionState.CANCELLED},
        RobotNavigationExecutionState.SAFETY_CHECKING: {
            RobotNavigationExecutionState.BLOCKED,
            RobotNavigationExecutionState.QUEUED,
            RobotNavigationExecutionState.NAVIGATING,
            RobotNavigationExecutionState.RETURNING_HOME,
            RobotNavigationExecutionState.CANCELLED,
        },
        RobotNavigationExecutionState.BLOCKED: {RobotNavigationExecutionState.SAFETY_CHECKING, RobotNavigationExecutionState.CANCELLED},
        RobotNavigationExecutionState.QUEUED: {
            RobotNavigationExecutionState.NAVIGATING,
            RobotNavigationExecutionState.BLOCKED,
            RobotNavigationExecutionState.CANCELLED,
        },
        RobotNavigationExecutionState.NAVIGATING: {
            RobotNavigationExecutionState.PAUSED_MANUAL,
            RobotNavigationExecutionState.PAUSED_ADMIN,
            RobotNavigationExecutionState.ARRIVED,
            RobotNavigationExecutionState.BLOCKED,
            RobotNavigationExecutionState.FAILED,
            RobotNavigationExecutionState.CANCELLED,
        },
        RobotNavigationExecutionState.PAUSED_MANUAL: {RobotNavigationExecutionState.SAFETY_CHECKING, RobotNavigationExecutionState.CANCELLED},
        RobotNavigationExecutionState.PAUSED_ADMIN: {RobotNavigationExecutionState.SAFETY_CHECKING, RobotNavigationExecutionState.CANCELLED},
        RobotNavigationExecutionState.ARRIVED: {
            RobotNavigationExecutionState.VOICE_PROMPTING,
            RobotNavigationExecutionState.WAITING_RESPONSE,
            RobotNavigationExecutionState.SAFETY_CHECKING,
            RobotNavigationExecutionState.COMPLETED,
            RobotNavigationExecutionState.CANCELLED,
        },
        RobotNavigationExecutionState.VOICE_PROMPTING: {
            RobotNavigationExecutionState.WAITING_RESPONSE,
            RobotNavigationExecutionState.FAILED,
            RobotNavigationExecutionState.CANCELLED,
        },
        RobotNavigationExecutionState.WAITING_RESPONSE: {
            RobotNavigationExecutionState.SAFE_RESPONSE,
            RobotNavigationExecutionState.HELP_REQUESTED,
            RobotNavigationExecutionState.NO_RESPONSE,
            RobotNavigationExecutionState.UNCERTAIN,
            RobotNavigationExecutionState.CANCELLED,
        },
        RobotNavigationExecutionState.SAFE_RESPONSE: {RobotNavigationExecutionState.WAITING_ADMIN_CONFIRMATION},
        RobotNavigationExecutionState.WAITING_ADMIN_CONFIRMATION: {
            RobotNavigationExecutionState.SAFETY_CHECKING,
            RobotNavigationExecutionState.CANCELLED,
        },
        RobotNavigationExecutionState.HELP_REQUESTED: {RobotNavigationExecutionState.COMPLETED, RobotNavigationExecutionState.CANCELLED},
        RobotNavigationExecutionState.NO_RESPONSE: {RobotNavigationExecutionState.COMPLETED, RobotNavigationExecutionState.CANCELLED},
        RobotNavigationExecutionState.UNCERTAIN: {RobotNavigationExecutionState.COMPLETED, RobotNavigationExecutionState.CANCELLED},
        RobotNavigationExecutionState.RETURNING_HOME: {
            RobotNavigationExecutionState.PAUSED_MANUAL,
            RobotNavigationExecutionState.PAUSED_ADMIN,
            RobotNavigationExecutionState.BLOCKED,
            RobotNavigationExecutionState.COMPLETED,
            RobotNavigationExecutionState.FAILED,
            RobotNavigationExecutionState.CANCELLED,
        },
        RobotNavigationExecutionState.COMPLETED: set(),
        RobotNavigationExecutionState.FAILED: set(),
        RobotNavigationExecutionState.CANCELLED: set(),
    }

    def ensure_allowed(
        self,
        current: RobotNavigationExecutionState,
        target: RobotNavigationExecutionState,
    ) -> None:
        if target not in self.ALLOWED.get(current, set()):
            raise RobotNavigationServiceError(
                RobotNavigationErrorCode.INVALID_STATE_TRANSITION,
                "非法机器人任务状态迁移",
                details={"current": current.value, "target": target.value},
            )


class RobotNavigationService:
    """Coordinates Mock gateway calls, safety checks, state and persistence."""

    def __init__(
        self,
        task_repository: RobotTaskRepository,
        navigation_repository: RobotNavigationRepository,
        map_service: RobotMapService,
        gateway_service: RobotNavigationGatewayService,
        safety_service: RobotSafetyInterlockService | None = None,
        state_coordinator: RobotNavigationStateCoordinator | None = None,
    ) -> None:
        self.tasks = task_repository
        self.events = navigation_repository
        self.maps = map_service
        self.gateway = gateway_service
        self.safety = safety_service or RobotSafetyInterlockService()
        self.states = state_coordinator or RobotNavigationStateCoordinator()

    def start_mapping(
        self,
        *,
        session_name: str,
        request_id: str,
        checks: RobotSafetyChecks,
    ) -> tuple[Any, RobotNavigationGatewayResult]:
        interlock = self.safety.check_mapping(checks)
        self._require_interlock(interlock)
        result = self.gateway.start_mapping({"session_name": session_name, "request_id": request_id})
        session_id = str(result.data.get("session_id") or f"mapping_{uuid4().hex}")
        map_id = str(result.data.get("map_id") or f"map_{uuid4().hex}")
        robot_map = self.maps.repository.get_map(map_id)
        if robot_map is None:
            robot_map = self.maps.create_draft_map(
                session_name,
                map_id=map_id,
                metadata={"mapping_session_id": session_id, "source": "mock", "operation_id": request_id},
            )
        elif robot_map.metadata.get("operation_id") != request_id or robot_map.name != session_name:
            raise RobotNavigationServiceError(
                RobotNavigationErrorCode.IDEMPOTENCY_CONFLICT,
                "建图 request_id 已用于不同请求",
                details={"request_id": request_id, "map_id": map_id},
            )
        return robot_map, result

    def stop_mapping(self, *, map_id: str, session_id: str, request_id: str, checks: RobotSafetyChecks):
        interlock = self.safety.check_mapping(checks)
        self._require_interlock(interlock)
        result = self.gateway.stop_mapping({"session_id": session_id, "request_id": request_id})
        robot_map = self.maps.mark_preview_ready(map_id, metadata={"preview": result.data, "source": "mock"})
        return robot_map, result

    def save_map(
        self,
        *,
        map_id: str,
        session_id: str,
        name: str,
        request_id: str,
        replacement_confirmed: bool,
    ):
        current = self.maps.require_map(map_id)
        if current.status.value != "preview":
            raise RobotNavigationServiceError(RobotNavigationErrorCode.MAP_STATE_CONFLICT, "地图尚未达到 preview_ready")
        result = self.gateway.save_map(
            {
                "session_id": session_id,
                "name": name,
                "replace_map_id": (self.maps.repository.get_active_map() or current).map_id if self.maps.repository.get_active_map() else None,
                "confirmed": replacement_confirmed,
                "request_id": request_id,
            }
        )
        return self.maps.activate_preview(map_id, replacement_confirmed=replacement_confirmed), result

    def create_task(
        self,
        *,
        source_event_id: str,
        trace_id: str,
        task_type: str,
        location: str,
        risk_level: str = "unknown",
        task_id: str | None = None,
    ) -> RobotTask:
        existing = self.tasks.get_by_source_event_id(source_event_id)
        if existing:
            return existing
        task = RobotTask(
            task_id=task_id or f"robot_task_{uuid4().hex}",
            source_event_id=source_event_id,
            trace_id=trace_id,
            task_type=task_type,
            location=location,
            risk_level=risk_level,
            status=RobotTaskStatus.QUEUED,
            current_step=RobotTaskStep.RECEIVED,
            execution_state=RobotNavigationExecutionState.CREATED,
            control_owner=RobotControlOwner.NONE,
            provider="mock",
            real_motion_enabled=False,
        )
        return self.tasks.create_task(task)

    def start_patrol(self, *, task_id: str, route_id: str, request_id: str, checks: RobotSafetyChecks) -> RobotTask:
        task = self._run_safety(task_id, request_id, checks)
        route, route_points = self.maps.require_valid_route(route_id)
        home = self.maps.require_home_point(route.map_id)
        gateway_result = self._call_gateway_or_block(
            task_id=task.task_id,
            operation_id=request_id,
            call=lambda: self.gateway.start_patrol({
                "external_task_id": task.task_id,
                "route_id": route.route_id,
                "map_id": route.map_id,
                "point_ids": [item.point_id for item in route_points],
                "return_home_point_id": home.point_id,
                "request_id": request_id,
            }),
        )
        task = self._bind_gateway_task_id(task.task_id, gateway_result)
        task = self.transition(task.task_id, RobotNavigationExecutionState.QUEUED, f"{request_id}:queued", "patrol_queued")
        task = self.transition(
            task.task_id,
            RobotNavigationExecutionState.NAVIGATING,
            request_id,
            "patrol_started",
            control_owner=RobotControlOwner.NAVIGATION,
        )
        return self._apply_gateway_navigation_outcome(task, gateway_result, request_id)

    def dispatch_emergency(
        self,
        *,
        task_id: str,
        incident_id: str,
        map_id: str,
        target_point_id: str,
        request_id: str,
        checks: RobotSafetyChecks,
    ) -> RobotTask:
        task = self._run_safety(task_id, request_id, checks, incident_id=incident_id)
        self.maps.require_valid_point(target_point_id, map_id=map_id)
        gateway_result = self._call_gateway_or_block(
            task_id=task.task_id,
            operation_id=request_id,
            incident_id=incident_id,
            call=lambda: self.gateway.emergency_dispatch({
                "incident_id": incident_id,
                "external_task_id": task.task_id,
                "map_id": map_id,
                "target_point_id": target_point_id,
                "request_id": request_id,
            }),
        )
        task = self._bind_gateway_task_id(task.task_id, gateway_result)
        task = self.transition(
            task.task_id,
            RobotNavigationExecutionState.NAVIGATING,
            request_id,
            "emergency_dispatched",
            control_owner=RobotControlOwner.NAVIGATION,
            incident_id=incident_id,
        )
        return self._apply_gateway_navigation_outcome(task, gateway_result, request_id, incident_id=incident_id)

    def pause_task(self, *, task_id: str, request_id: str, manual: bool = False) -> RobotTask:
        task = self._require_task(task_id)
        self.gateway.pause_task(task.gateway_task_id or task_id, {"request_id": request_id})
        target = RobotNavigationExecutionState.PAUSED_MANUAL if manual else RobotNavigationExecutionState.PAUSED_ADMIN
        owner = RobotControlOwner.MANUAL if manual else RobotControlOwner.NONE
        return self.transition(task_id, target, request_id, "task_paused", control_owner=owner)

    def resume_task(self, *, task_id: str, request_id: str, checks: RobotSafetyChecks) -> RobotTask:
        task = self._run_safety(task_id, request_id, checks)
        gateway_result = self._call_gateway_or_block(
            task_id=task.task_id,
            operation_id=request_id,
            call=lambda: self.gateway.resume_task(
                task.gateway_task_id or task_id,
                {"request_id": request_id},
            ),
        )
        task = self.transition(
            task.task_id,
            RobotNavigationExecutionState.NAVIGATING,
            request_id,
            "task_resumed",
            control_owner=RobotControlOwner.NAVIGATION,
        )
        return self._apply_gateway_navigation_outcome(task, gateway_result, request_id)

    def stop_task(self, *, task_id: str, request_id: str) -> RobotTask:
        task = self._require_task(task_id)
        self.gateway.stop_task(task.gateway_task_id or task_id, {"request_id": request_id})
        return self.transition(task_id, RobotNavigationExecutionState.CANCELLED, request_id, "task_stopped")

    def manual_takeover(self, *, task_id: str, request_id: str) -> RobotTask:
        self._require_task(task_id)
        self.gateway.manual_takeover({"request_id": request_id})
        return self.transition(
            task_id,
            RobotNavigationExecutionState.PAUSED_MANUAL,
            request_id,
            "manual_takeover",
            control_owner=RobotControlOwner.MANUAL,
        )

    def release_control(self, *, task_id: str, request_id: str) -> RobotTask:
        self._require_task(task_id)
        self.gateway.release_control({"request_id": request_id})
        return self.update_control_owner(task_id, RobotControlOwner.NONE, request_id, "manual_control_released")

    def return_home(
        self,
        *,
        task_id: str,
        request_id: str,
        checks: RobotSafetyChecks,
        reason: str,
        incident_id: str | None = None,
    ) -> RobotTask:
        task = self._run_safety(task_id, request_id, checks, incident_id=incident_id)
        active_map = self.maps.require_active_map()
        home = self.maps.require_home_point(active_map.map_id)
        self._call_gateway_or_block(
            task_id=task.task_id,
            operation_id=request_id,
            incident_id=incident_id,
            call=lambda: self.gateway.return_home({
                "external_task_id": task.task_id,
                "home_point_id": home.point_id,
                "reason": reason,
                "request_id": request_id,
            }),
        )
        return self.transition(
            task.task_id,
            RobotNavigationExecutionState.RETURNING_HOME,
            request_id,
            "return_home_started",
            control_owner=RobotControlOwner.NAVIGATION,
            incident_id=incident_id,
        )

    def transition(
        self,
        task_id: str,
        target: RobotNavigationExecutionState,
        operation_id: str,
        event_type: str,
        *,
        control_owner: RobotControlOwner | None = None,
        incident_id: str | None = None,
        message: str = "",
        error_code: str | None = None,
    ) -> RobotTask:
        existing_event = self.events.get_event(operation_id)
        if existing_event:
            existing_task = self.tasks.get_task(task_id)
            if existing_task is None:
                raise RobotNavigationServiceError(RobotNavigationErrorCode.TASK_NOT_FOUND, "机器人任务不存在")
            return existing_task
        with self.tasks.transaction() as connection:
            return self.transition_in_transaction(
                connection=connection,
                task_id=task_id,
                target=target,
                operation_id=operation_id,
                event_type=event_type,
                control_owner=control_owner,
                incident_id=incident_id,
                message=message,
                error_code=error_code,
            )

    def transition_in_transaction(
        self,
        *,
        connection,
        task_id: str,
        target: RobotNavigationExecutionState,
        operation_id: str,
        event_type: str,
        control_owner: RobotControlOwner | None = None,
        incident_id: str | None = None,
        message: str = "",
        error_code: str | None = None,
    ) -> RobotTask:
        existing_event = self.events.get_event(operation_id, connection=connection)
        if existing_event:
            task = self.tasks.get_task(task_id, connection=connection)
            if task is None:
                raise RobotNavigationServiceError(RobotNavigationErrorCode.TASK_NOT_FOUND, "机器人任务不存在")
            return task
        task = self.tasks.get_task(task_id, connection=connection)
        if task is None:
            raise RobotNavigationServiceError(
                RobotNavigationErrorCode.TASK_NOT_FOUND,
                "机器人任务不存在",
                details={"task_id": task_id},
            )
        if task.real_motion_enabled is not False or task.provider != "mock":
            raise RobotNavigationServiceError(RobotNavigationErrorCode.REAL_MOTION_DISABLED, "任务不满足 Mock 安全不变量")
        current = task.execution_state or RobotNavigationExecutionState.CREATED
        self.states.ensure_allowed(current, target)
        sequence = task.last_sequence + 1
        now = datetime.now(timezone.utc)
        status, step = self._formal_state(target)
        owner = control_owner if control_owner is not None else task.control_owner
        if target in {RobotNavigationExecutionState.BLOCKED, RobotNavigationExecutionState.CANCELLED, RobotNavigationExecutionState.COMPLETED, RobotNavigationExecutionState.FAILED}:
            owner = RobotControlOwner.NONE
        updated = task.model_copy(
            update={
                "status": status,
                "current_step": step,
                "execution_state": target,
                "control_owner": owner,
                "last_sequence": sequence,
                "error_code": error_code,
                "error_message": message if error_code else None,
                "started_at": task.started_at or (now if status == RobotTaskStatus.RUNNING else None),
                "completed_at": now if status in {RobotTaskStatus.COMPLETED, RobotTaskStatus.FAILED, RobotTaskStatus.CANCELLED} else None,
            }
        )
        updated = self.tasks.update_task(updated, connection=connection)
        self.tasks.add_timeline(
            RobotTaskTimeline(
                task_id=task_id,
                callback_id=operation_id,
                sequence=sequence,
                status=status,
                step=step,
                message=message or event_type,
                occurred_at=now,
                payload={
                    "execution_state": target.value,
                    "control_owner": owner.value,
                    "provider": "mock",
                    "real_motion_enabled": False,
                    "error_code": error_code,
                },
            ),
            connection=connection,
        )
        self.events.add_event(
            RobotNavigationEvent(
                event_id=operation_id,
                task_id=task_id,
                incident_id=incident_id,
                event_type=event_type,
                execution_state=target,
                navigation_state=target,
                control_owner=owner,
                error_code=error_code,
                sequence=sequence,
                message=message,
            ),
            connection=connection,
        )
        return updated

    def update_control_owner(
        self,
        task_id: str,
        owner: RobotControlOwner,
        operation_id: str,
        event_type: str,
    ) -> RobotTask:
        if self.events.get_event(operation_id):
            task = self.tasks.get_task(task_id)
            if task:
                return task
        with self.tasks.transaction() as connection:
            task = self.tasks.get_task(task_id, connection=connection)
            if task is None:
                raise RobotNavigationServiceError(RobotNavigationErrorCode.TASK_NOT_FOUND, "机器人任务不存在")
            if task.control_owner != RobotControlOwner.MANUAL or owner != RobotControlOwner.NONE:
                raise RobotNavigationServiceError(RobotNavigationErrorCode.CONTROL_OWNER_CONFLICT, "控制权释放状态不合法")
            sequence = task.last_sequence + 1
            updated = self.tasks.update_task(task.model_copy(update={"control_owner": owner, "last_sequence": sequence}), connection=connection)
            self.tasks.add_timeline(
                RobotTaskTimeline(
                    task_id=task_id,
                    callback_id=operation_id,
                    sequence=sequence,
                    status=updated.status,
                    step=updated.current_step,
                    message=event_type,
                    payload={"execution_state": updated.execution_state.value, "control_owner": owner.value, "provider": "mock", "real_motion_enabled": False},
                ),
                connection=connection,
            )
            self.events.add_event(
                RobotNavigationEvent(
                    event_id=operation_id,
                    task_id=task_id,
                    event_type=event_type,
                    execution_state=updated.execution_state,
                    navigation_state=updated.execution_state,
                    control_owner=owner,
                    sequence=sequence,
                ),
                connection=connection,
            )
            return updated

    def _run_safety(
        self,
        task_id: str,
        operation_id: str,
        checks: RobotSafetyChecks,
        *,
        incident_id: str | None = None,
    ) -> RobotTask:
        final = self.events.get_event(operation_id)
        if final:
            task = self.tasks.get_task(task_id)
            if task:
                if task.execution_state == RobotNavigationExecutionState.BLOCKED:
                    raise RobotNavigationServiceError(
                        task.error_code or RobotNavigationErrorCode.SAFETY_INTERLOCK_BLOCKED,
                        task.error_message or "任务已被阻塞",
                    )
                return task
        task = self.transition(
            task_id,
            RobotNavigationExecutionState.SAFETY_CHECKING,
            f"{operation_id}:safety",
            "safety_checking",
            control_owner=RobotControlOwner.NONE,
            incident_id=incident_id,
        )
        interlock = self.safety.check_navigation(checks)
        if not interlock.passed:
            self.transition(
                task_id,
                RobotNavigationExecutionState.BLOCKED,
                operation_id,
                "safety_blocked",
                incident_id=incident_id,
                message="安全联锁未通过",
                error_code=RobotNavigationErrorCode.SAFETY_INTERLOCK_BLOCKED.value,
            )
            raise RobotNavigationServiceError(
                RobotNavigationErrorCode.SAFETY_INTERLOCK_BLOCKED,
                "安全联锁未通过，Mock 任务未启动",
                details={"blocked_by": interlock.blocked_by},
            )
        return task

    def _call_gateway_or_block(
        self,
        *,
        task_id: str,
        operation_id: str,
        call,
        incident_id: str | None = None,
    ) -> RobotNavigationGatewayResult:
        try:
            return call()
        except RobotNavigationServiceError as exc:
            task = self.tasks.get_task(task_id)
            if task and task.execution_state == RobotNavigationExecutionState.SAFETY_CHECKING:
                self.transition(
                    task_id,
                    RobotNavigationExecutionState.BLOCKED,
                    operation_id,
                    "gateway_blocked",
                    incident_id=incident_id,
                    message=exc.message,
                    error_code=exc.code,
                )
            raise

    def _bind_gateway_task_id(
        self,
        task_id: str,
        gateway_result: RobotNavigationGatewayResult,
    ) -> RobotTask:
        task = self._require_task(task_id)
        gateway_task_id = gateway_result.data.get("task_id")
        if not isinstance(gateway_task_id, str) or not gateway_task_id.strip():
            return task
        normalized = gateway_task_id.strip()
        if task.gateway_task_id == normalized:
            return task
        return self.tasks.update_task(task.model_copy(update={"gateway_task_id": normalized}))

    def _apply_gateway_navigation_outcome(
        self,
        task: RobotTask,
        gateway_result: RobotNavigationGatewayResult,
        operation_id: str,
        *,
        incident_id: str | None = None,
    ) -> RobotTask:
        """Persist terminal Mock outcomes returned synchronously by go2-gateway."""

        gateway_state = gateway_result.data.get("execution_state")
        if gateway_state == RobotNavigationExecutionState.FAILED.value:
            return self.transition(
                task.task_id,
                RobotNavigationExecutionState.FAILED,
                f"{operation_id}:gateway-failed",
                "gateway_navigation_failed",
                incident_id=incident_id,
                message=str(gateway_result.data.get("error_message") or "Mock navigation failed"),
                error_code=str(gateway_result.data.get("error_code") or "MOCK_NAVIGATION_FAILED"),
            )
        if gateway_state != RobotNavigationExecutionState.COMPLETED.value:
            return task

        current = task
        if current.execution_state == RobotNavigationExecutionState.NAVIGATING:
            current = self.transition(
                current.task_id,
                RobotNavigationExecutionState.ARRIVED,
                f"{operation_id}:gateway-arrived",
                "gateway_task_arrived",
                incident_id=incident_id,
            )
        if current.execution_state == RobotNavigationExecutionState.ARRIVED:
            current = self.transition(
                current.task_id,
                RobotNavigationExecutionState.SAFETY_CHECKING,
                f"{operation_id}:gateway-return-safety",
                "gateway_return_safety_confirmed",
                incident_id=incident_id,
            )
        if current.execution_state == RobotNavigationExecutionState.SAFETY_CHECKING:
            current = self.transition(
                current.task_id,
                RobotNavigationExecutionState.RETURNING_HOME,
                f"{operation_id}:gateway-returning",
                "gateway_return_home_started",
                incident_id=incident_id,
            )
        if current.execution_state == RobotNavigationExecutionState.RETURNING_HOME:
            current = self.transition(
                current.task_id,
                RobotNavigationExecutionState.COMPLETED,
                f"{operation_id}:gateway-completed",
                "gateway_navigation_completed",
                incident_id=incident_id,
            )
        return current

    def _require_task(self, task_id: str) -> RobotTask:
        task = self.tasks.get_task(task_id)
        if task is None:
            raise RobotNavigationServiceError(
                RobotNavigationErrorCode.TASK_NOT_FOUND,
                "机器人任务不存在",
                details={"task_id": task_id},
            )
        return task

    @staticmethod
    def _require_interlock(interlock) -> None:
        if not interlock.passed:
            raise RobotNavigationServiceError(
                RobotNavigationErrorCode.SAFETY_INTERLOCK_BLOCKED,
                "安全联锁未通过，Mock 操作未启动",
                details={"blocked_by": interlock.blocked_by},
            )

    @staticmethod
    def _formal_state(target: RobotNavigationExecutionState) -> tuple[RobotTaskStatus, RobotTaskStep]:
        if target == RobotNavigationExecutionState.BLOCKED:
            return RobotTaskStatus.BLOCKED, RobotTaskStep.PREFLIGHT
        if target == RobotNavigationExecutionState.COMPLETED:
            return RobotTaskStatus.COMPLETED, RobotTaskStep.REPORTING
        if target == RobotNavigationExecutionState.FAILED:
            return RobotTaskStatus.FAILED, RobotTaskStep.REPORTING
        if target == RobotNavigationExecutionState.CANCELLED:
            return RobotTaskStatus.CANCELLED, RobotTaskStep.REPORTING
        if target in {RobotNavigationExecutionState.CREATED, RobotNavigationExecutionState.SAFETY_CHECKING, RobotNavigationExecutionState.QUEUED}:
            return RobotTaskStatus.QUEUED, RobotTaskStep.PREFLIGHT
        if target == RobotNavigationExecutionState.ARRIVED:
            return RobotTaskStatus.RUNNING, RobotTaskStep.ARRIVED
        if target == RobotNavigationExecutionState.VOICE_PROMPTING:
            return RobotTaskStatus.RUNNING, RobotTaskStep.VOICE_PROMPT
        if target in {
            RobotNavigationExecutionState.WAITING_RESPONSE,
            RobotNavigationExecutionState.SAFE_RESPONSE,
            RobotNavigationExecutionState.HELP_REQUESTED,
            RobotNavigationExecutionState.NO_RESPONSE,
            RobotNavigationExecutionState.UNCERTAIN,
            RobotNavigationExecutionState.WAITING_ADMIN_CONFIRMATION,
        }:
            return RobotTaskStatus.RUNNING, RobotTaskStep.WAITING_RESPONSE
        return RobotTaskStatus.RUNNING, RobotTaskStep.MOVING
