from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from backend.models.robot_emergency_model import (
    RobotDialogueIntent,
    RobotDialogueRole,
    RobotDialogueTurn,
    RobotEmergencyCase,
    RobotEmergencyCaseStatus,
)
from backend.models.robot_model import RobotTask, RobotTaskStatus, RobotTaskStep, RobotTaskTimeline
from backend.models.robot_navigation_model import (
    RobotControlOwner,
    RobotNavigationEvent,
    RobotNavigationExecutionState,
    RobotSafetyChecks,
)
from backend.repositories.robot_emergency_repo import RobotEmergencyRepository
from backend.services.robot_navigation_errors import (
    RobotNavigationErrorCode,
    RobotNavigationServiceError,
)
from backend.services.robot_navigation_service import RobotNavigationService


class RobotEmergencyService:
    """Incident-level Mock emergency orchestration with idempotent persistence."""

    def __init__(
        self,
        repository: RobotEmergencyRepository,
        navigation_service: RobotNavigationService,
    ) -> None:
        self.repository = repository
        self.navigation = navigation_service

    def create_and_dispatch(
        self,
        *,
        incident_id: str,
        area_id: str,
        area_name: str,
        request_id: str,
        checks: RobotSafetyChecks,
        alarm_id: str | None = None,
        camera_id: str | None = None,
        risk_level: str = "critical",
        fall_probability: float | None = None,
    ) -> RobotEmergencyCase:
        active_map = self.navigation.maps.require_active_map()
        observation = self.navigation.maps.find_observation_point(active_map.map_id, area_id)
        home = self.navigation.maps.require_home_point(active_map.map_id)
        source_event_id = f"robot-emergency:{incident_id}"
        with self.repository.transaction() as connection:
            existing = self.repository.get_case_by_incident_id(incident_id, connection=connection)
            if existing is not None:
                return existing
            task = self.navigation.tasks.get_by_source_event_id(source_event_id, connection=connection)
            if task is None:
                task = RobotTask(
                    task_id=f"robot_task_{uuid4().hex}",
                    source_event_id=source_event_id,
                    trace_id=request_id,
                    alarm_event_id=alarm_id,
                    task_type="emergency_fall_response",
                    location=area_name,
                    risk_level=risk_level,
                    status=RobotTaskStatus.QUEUED,
                    current_step=RobotTaskStep.RECEIVED,
                    execution_state=RobotNavigationExecutionState.CREATED,
                    control_owner=RobotControlOwner.NONE,
                    provider="mock",
                    real_motion_enabled=False,
                    last_sequence=1,
                )
                self.navigation.tasks.create_task(task, connection=connection)
                self.navigation.tasks.add_timeline(
                    RobotTaskTimeline(
                        task_id=task.task_id,
                        callback_id=f"{incident_id}:created",
                        sequence=1,
                        status=task.status,
                        step=task.current_step,
                        message="emergency_case_created",
                        payload={"incident_id": incident_id, "provider": "mock", "real_motion_enabled": False},
                    ),
                    connection=connection,
                )
                self.navigation.events.add_event(
                    RobotNavigationEvent(
                        event_id=f"{incident_id}:created",
                        task_id=task.task_id,
                        incident_id=incident_id,
                        event_type="emergency_case_created",
                        execution_state=RobotNavigationExecutionState.CREATED,
                        navigation_state=RobotNavigationExecutionState.CREATED,
                        sequence=1,
                    ),
                    connection=connection,
                )
            case = self.repository.save_case(
                RobotEmergencyCase(
                    case_id=f"emergency_case_{uuid4().hex}",
                    incident_id=incident_id,
                    robot_task_id=task.task_id,
                    alarm_id=alarm_id,
                    camera_id=camera_id,
                    area_id=area_id,
                    area_name=area_name,
                    observation_point_id=observation.point_id,
                    home_point_id=home.point_id,
                    risk_level=risk_level,
                    fall_probability=fall_probability,
                    metadata={"map_id": active_map.map_id, "source": "mock"},
                ),
                connection=connection,
            )

        try:
            task = self.navigation.dispatch_emergency(
                task_id=case.robot_task_id or "",
                incident_id=incident_id,
                map_id=active_map.map_id,
                target_point_id=observation.point_id,
                request_id=request_id,
                checks=checks,
            )
        except RobotNavigationServiceError as exc:
            latest = self.navigation.tasks.get_task(case.robot_task_id or "")
            blocked = case.model_copy(
                update={
                    "status": RobotEmergencyCaseStatus.BLOCKED,
                    "execution_state": latest.execution_state if latest else RobotNavigationExecutionState.BLOCKED,
                    "navigation_state": latest.execution_state if latest else RobotNavigationExecutionState.BLOCKED,
                    "control_owner": latest.control_owner if latest else RobotControlOwner.NONE,
                    "error_code": exc.code,
                    "error_message": exc.message,
                }
            )
            self.repository.save_case(blocked)
            raise
        return self.repository.save_case(
            case.model_copy(
                update={
                    "status": RobotEmergencyCaseStatus.ACTIVE,
                    "execution_state": task.execution_state,
                    "navigation_state": task.execution_state,
                    "control_owner": task.control_owner,
                    "error_code": None,
                    "error_message": None,
                }
            )
        )

    def begin_dialogue(self, *, incident_id: str, operation_id: str) -> RobotEmergencyCase:
        case = self.require_case(incident_id)
        task_id = case.robot_task_id or ""
        task = self.navigation.tasks.get_task(task_id)
        if task is None:
            self._raise(RobotNavigationErrorCode.TASK_NOT_FOUND, "应急案例关联任务不存在")
        if task.execution_state == RobotNavigationExecutionState.NAVIGATING:
            task = self.navigation.transition(task_id, RobotNavigationExecutionState.ARRIVED, f"{operation_id}:arrived", "arrived", incident_id=incident_id)
        if task.execution_state == RobotNavigationExecutionState.ARRIVED:
            task = self.navigation.transition(task_id, RobotNavigationExecutionState.VOICE_PROMPTING, f"{operation_id}:voice", "voice_prompting", incident_id=incident_id)
        if task.execution_state == RobotNavigationExecutionState.VOICE_PROMPTING:
            task = self.navigation.transition(task_id, RobotNavigationExecutionState.WAITING_RESPONSE, operation_id, "waiting_response", incident_id=incident_id)
        return self.repository.save_case(
            case.model_copy(update={"execution_state": task.execution_state, "navigation_state": task.execution_state, "control_owner": task.control_owner})
        )

    def record_dialogue_result(
        self,
        *,
        incident_id: str,
        turn_id: str,
        intent: RobotDialogueIntent,
        input_text: str | None = None,
        confidence: float | None = None,
    ) -> RobotEmergencyCase:
        case = self.require_case(incident_id)
        if case.robot_task_id is None:
            self._raise(RobotNavigationErrorCode.TASK_NOT_FOUND, "应急案例尚未创建机器人任务")
        target = {
            RobotDialogueIntent.SAFE_RESPONSE: RobotNavigationExecutionState.SAFE_RESPONSE,
            RobotDialogueIntent.NEED_HELP: RobotNavigationExecutionState.HELP_REQUESTED,
            RobotDialogueIntent.NO_RESPONSE: RobotNavigationExecutionState.NO_RESPONSE,
            RobotDialogueIntent.UNCERTAIN: RobotNavigationExecutionState.UNCERTAIN,
        }[intent]
        with self.repository.transaction() as connection:
            duplicate = connection.execute(
                "SELECT 1 FROM robot_dialogue_turns WHERE turn_id = ?",
                (turn_id,),
            ).fetchone()
            if duplicate:
                existing = self.repository.get_case_by_incident_id(incident_id, connection=connection)
                return existing or case
            task = self.navigation.transition_in_transaction(
                connection=connection,
                task_id=case.robot_task_id,
                target=target,
                operation_id=turn_id,
                event_type="dialogue_result",
                incident_id=incident_id,
                message=intent.value,
            )
            if intent == RobotDialogueIntent.SAFE_RESPONSE:
                task = self.navigation.transition_in_transaction(
                    connection=connection,
                    task_id=case.robot_task_id,
                    target=RobotNavigationExecutionState.WAITING_ADMIN_CONFIRMATION,
                    operation_id=f"{turn_id}:admin-confirmation",
                    event_type="waiting_admin_confirmation",
                    incident_id=incident_id,
                )
            turn = RobotDialogueTurn(
                turn_id=turn_id,
                incident_id=incident_id,
                robot_task_id=case.robot_task_id,
                role=RobotDialogueRole.USER,
                text=input_text or "",
                input_text=input_text,
                intent=intent,
                confidence=confidence,
                recommended_action="confirm_return_home" if intent == RobotDialogueIntent.SAFE_RESPONSE else "notify_admin",
                conversation_complete=True,
                asr_status="mock",
                tts_status="mock",
                metadata={"source": "mock"},
            )
            self.repository.add_dialogue_turn(turn, connection=connection)
            status = RobotEmergencyCaseStatus.ACTIVE if intent == RobotDialogueIntent.SAFE_RESPONSE else RobotEmergencyCaseStatus.ESCALATED
            updated_case = self.repository.save_case(
                case.model_copy(
                    update={
                        "status": status,
                        "execution_state": task.execution_state,
                        "navigation_state": task.execution_state,
                        "control_owner": task.control_owner,
                        "dialogue_intent": intent,
                    }
                ),
                connection=connection,
            )
            return updated_case

    def acknowledge(self, *, incident_id: str, admin_id: str) -> RobotEmergencyCase:
        case = self.require_case(incident_id)
        return self.repository.save_case(
            case.model_copy(update={"acknowledged_by": admin_id, "acknowledged_at": datetime.now(timezone.utc)})
        )

    def resolve_and_return(
        self,
        *,
        incident_id: str,
        request_id: str,
        checks: RobotSafetyChecks,
    ) -> RobotEmergencyCase:
        case = self.require_case(incident_id)
        if case.dialogue_intent != RobotDialogueIntent.SAFE_RESPONSE or not case.acknowledged_by:
            self._raise(
                RobotNavigationErrorCode.INCIDENT_STATE_CONFLICT,
                "只有安全回应且管理员已确认的案例可以返航",
            )
        task = self.navigation.return_home(
            task_id=case.robot_task_id or "",
            request_id=request_id,
            checks=checks,
            reason="safe_response_confirmed_by_admin",
            incident_id=incident_id,
        )
        return self.repository.save_case(
            case.model_copy(update={"execution_state": task.execution_state, "navigation_state": task.execution_state, "control_owner": task.control_owner})
        )

    def complete_return(self, *, incident_id: str, operation_id: str, resolution: str) -> RobotEmergencyCase:
        case = self.require_case(incident_id)
        with self.repository.transaction() as connection:
            task = self.navigation.transition_in_transaction(
                connection=connection,
                task_id=case.robot_task_id or "",
                target=RobotNavigationExecutionState.COMPLETED,
                operation_id=operation_id,
                event_type="return_home_completed",
                incident_id=incident_id,
            )
            return self.repository.save_case(
                case.model_copy(
                    update={
                        "status": RobotEmergencyCaseStatus.RESOLVED,
                        "execution_state": task.execution_state,
                        "navigation_state": task.execution_state,
                        "control_owner": task.control_owner,
                        "resolution": resolution,
                        "resolved_at": datetime.now(timezone.utc),
                    }
                ),
                connection=connection,
            )

    def require_case(self, incident_id: str) -> RobotEmergencyCase:
        case = self.repository.get_case_by_incident_id(incident_id)
        if case is None:
            self._raise(
                RobotNavigationErrorCode.INCIDENT_NOT_FOUND,
                "应急案例不存在",
                details={"incident_id": incident_id},
            )
        return case

    def get_bundle(self, incident_id: str):
        bundle = self.repository.get_incident_bundle(incident_id)
        if bundle is None:
            self._raise(RobotNavigationErrorCode.INCIDENT_NOT_FOUND, "应急案例不存在")
        return bundle

    @staticmethod
    def _raise(code: RobotNavigationErrorCode, message: str, *, details: dict | None = None) -> None:
        raise RobotNavigationServiceError(code, message, details=details)
