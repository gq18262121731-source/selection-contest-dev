from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from backend.models.robot_emergency_model import RobotDialogueIntent, RobotEmergencyCaseStatus
from backend.models.robot_navigation_model import (
    RobotMapPoint,
    RobotMapPointStatus,
    RobotNavigationCapability,
    RobotNavigationExecutionState,
    RobotPatrolRoute,
    RobotPatrolRoutePoint,
    RobotPatrolRouteStatus,
    RobotSafetyChecks,
)
from backend.repositories.robot_emergency_repo import RobotEmergencyRepository
from backend.repositories.robot_map_repo import RobotMapRepository
from backend.repositories.robot_navigation_repo import RobotNavigationRepository
from backend.repositories.robot_task_repo import RobotTaskRepository
from backend.schemas.robot_emergency_api_schema import (
    RobotEmergencyAcknowledgeRequest,
    RobotEmergencyDialogueRequest,
    RobotEmergencyDispatchRequest,
    RobotEmergencyMockDialogueStartRequest,
    RobotEmergencyMockReturnCompleteRequest,
    RobotEmergencyResolveRequest,
)
from backend.schemas.robot_navigation_api_schema import (
    RobotMapPreviewRequest,
    RobotMapSaveRequest,
    RobotMappingStartRequest,
    RobotMappingStopRequest,
    RobotPatrolStartRequest,
    RobotPointCreateRequest,
    RobotPointUpdateRequest,
    RobotRouteCreateRequest,
)
from backend.services.robot_emergency_service import RobotEmergencyService
from backend.services.robot_map_service import RobotMapService
from backend.services.robot_navigation_errors import (
    RobotNavigationErrorCode,
    RobotNavigationServiceError,
)
from backend.services.robot_navigation_event_hub import RobotNavigationEventHub
from backend.services.robot_navigation_gateway_service import RobotNavigationGatewayService
from backend.services.robot_navigation_safety_state_resolver import (
    RobotEffectiveSafetySnapshot,
    RobotNavigationSafetyStateResolver,
)
from backend.services.robot_navigation_service import RobotNavigationService


@dataclass(frozen=True)
class RobotApplicationResult:
    data: Any
    replayed: bool = False


class RobotNavigationApplicationService:
    """Application boundary used by REST and WebSocket snapshot handlers."""

    DEFAULT_MOCK_PROMPT = "您还好吗？需要帮助吗？"
    MOCK_RETURN_RESOLUTION = "Mock 返航完成，事件已结束"

    def __init__(
        self,
        *,
        map_repository: RobotMapRepository,
        navigation_repository: RobotNavigationRepository,
        emergency_repository: RobotEmergencyRepository,
        task_repository: RobotTaskRepository,
        map_service: RobotMapService,
        navigation_service: RobotNavigationService,
        emergency_service: RobotEmergencyService,
        gateway_service: RobotNavigationGatewayService,
        event_hub: RobotNavigationEventHub,
        legacy_gateway_service: Any | None = None,
        safety_state_resolver: RobotNavigationSafetyStateResolver | None = None,
        state_max_age_seconds: float | None = None,
    ) -> None:
        self.maps = map_repository
        self.navigation_events = navigation_repository
        self.emergencies = emergency_repository
        self.tasks = task_repository
        self.map_service = map_service
        self.navigation = navigation_service
        self.emergency = emergency_service
        self.gateway = gateway_service
        self.event_hub = event_hub
        self.legacy_gateway = legacy_gateway_service
        self.safety_state_resolver = safety_state_resolver or RobotNavigationSafetyStateResolver(
            map_repository=map_repository,
            task_repository=task_repository,
            safety_service=navigation_service.safety,
            state_max_age_seconds=(
                state_max_age_seconds
                if state_max_age_seconds is not None
                else max(1.0, gateway_service.timeout_seconds * 2)
            ),
        )

    def capabilities(self) -> dict[str, Any]:
        return self.gateway.capabilities().data

    def navigation_snapshot(self) -> dict[str, Any]:
        effective = self.build_effective_safety_snapshot()
        active_map = effective.active_map
        current_task = effective.current_task
        checks = effective.checks.model_dump()
        return {
            **effective.gateway_state,
            **checks,
            "provider": "mock",
            "real_motion_enabled": False,
            "active_map": active_map.model_dump(mode="json") if active_map else None,
            "current_task": current_task.model_dump(mode="json") if current_task else None,
            "safety_interlock": effective.interlock.model_dump(mode="json"),
            "fetched_at": effective.fetched_at.isoformat(),
            "state_age_ms": effective.state_age_ms,
            "state_fresh": effective.state_fresh,
        }

    def status_snapshot(self) -> dict[str, Any]:
        navigation = self.navigation_snapshot()
        tasks = self.tasks.list_tasks(limit=20)
        gateway_status: dict[str, Any]
        if self.legacy_gateway is None:
            gateway_status = {"status": "unavailable", "reason": "LEGACY_GATEWAY_NOT_CONFIGURED"}
        else:
            gateway_status = self.legacy_gateway.status()
        return {
            "provider": "mock",
            "real_motion_enabled": False,
            "gateway": gateway_status,
            "navigation": navigation,
            "current_task": next(
                (task.model_dump(mode="json") for task in tasks if task.status.value in {"QUEUED", "RUNNING", "BLOCKED"}),
                None,
            ),
            "safety_interlock": navigation.get("safety_interlock"),
            "control_owner": navigation.get("control_owner", "NONE"),
            "map": navigation.get("active_map"),
            "lidar": {
                "status": "not_verified",
                "available": False,
                "mapping_ready": False,
                "reason": "LIDAR_STATUS_NOT_VERIFIED",
            },
        }

    def diagnostics(self) -> dict[str, Any]:
        return self.status_snapshot()

    def start_mapping(self, request: RobotMappingStartRequest) -> dict[str, Any]:
        fingerprint = self._fingerprint(request.model_dump(mode="json", exclude={"request_id"}))
        existing = next(
            (item for item in self.maps.list_maps() if item.metadata.get("operation_id") == request.request_id),
            None,
        )
        if existing is not None:
            stored_fingerprint = existing.metadata.get("request_fingerprint")
            if (stored_fingerprint and stored_fingerprint != fingerprint) or existing.name != request.session_name:
                self._raise_idempotency_conflict(request.request_id)
            gateway = existing.metadata.get("mapping_start_gateway") or {
                "provider": "mock",
                "real_motion_enabled": False,
                "session_id": existing.metadata.get("mapping_session_id"),
                "map_id": existing.map_id,
            }
            return RobotApplicationResult(
                data={"map": existing.model_dump(mode="json"), "gateway": gateway},
                replayed=True,
            )
        robot_map, gateway = self.navigation.start_mapping(
            session_name=request.session_name,
            request_id=request.request_id,
            checks=self._current_checks(),
        )
        robot_map = self.maps.update_map(
            robot_map.model_copy(
                update={
                    "metadata": {
                        **robot_map.metadata,
                        "request_fingerprint": fingerprint,
                        "mapping_start_gateway": gateway.data,
                    }
                }
            )
        )
        data = {"map": robot_map.model_dump(mode="json"), "gateway": gateway.data}
        self._publish("map_draft_created", data)
        return RobotApplicationResult(data=data)

    def stop_mapping(self, request: RobotMappingStopRequest) -> dict[str, Any]:
        fingerprint = self._fingerprint(request.model_dump(mode="json", exclude={"request_id"}))
        existing = self.maps.get_map(request.map_id)
        if existing and existing.metadata.get("mapping_stop_operation_id") == request.request_id:
            self._ensure_idempotent_metadata(
                existing.metadata,
                request.request_id,
                fingerprint,
                operation_key="mapping_stop_operation_id",
                fingerprint_key="mapping_stop_fingerprint",
            )
            return RobotApplicationResult(
                data={
                    "map": existing.model_dump(mode="json"),
                    "gateway": existing.metadata.get("mapping_stop_gateway", {}),
                },
                replayed=True,
            )
        robot_map, gateway = self.navigation.stop_mapping(
            map_id=request.map_id,
            session_id=request.session_id,
            request_id=request.request_id,
            checks=self._current_checks(),
        )
        robot_map = self.maps.update_map(
            robot_map.model_copy(
                update={
                    "metadata": {
                        **robot_map.metadata,
                        "mapping_stop_operation_id": request.request_id,
                        "mapping_stop_fingerprint": fingerprint,
                        "mapping_stop_gateway": gateway.data,
                    }
                }
            )
        )
        data = {"map": robot_map.model_dump(mode="json"), "gateway": gateway.data}
        self._publish("map_preview_ready", data)
        return data

    def preview_map(self, request: RobotMapPreviewRequest) -> dict[str, Any]:
        fingerprint = self._fingerprint(request.model_dump(mode="json", exclude={"request_id"}))
        existing = self.maps.get_map(request.map_id)
        if existing and existing.metadata.get("preview_operation_id") == request.request_id:
            self._ensure_idempotent_metadata(
                existing.metadata,
                request.request_id,
                fingerprint,
                operation_key="preview_operation_id",
                fingerprint_key="preview_fingerprint",
            )
            return RobotApplicationResult(data=existing.model_dump(mode="json"), replayed=True)
        robot_map = self.map_service.mark_preview_ready(
            request.map_id,
            metadata={
                **request.metadata,
                "preview_operation_id": request.request_id,
                "preview_fingerprint": fingerprint,
            },
        )
        data = robot_map.model_dump(mode="json")
        self._publish("map_preview_ready", data)
        return data

    def save_map(self, request: RobotMapSaveRequest) -> dict[str, Any]:
        fingerprint = self._fingerprint(request.model_dump(mode="json", exclude={"request_id"}))
        existing = self.maps.get_map(request.map_id)
        if existing and existing.metadata.get("save_operation_id") == request.request_id:
            self._ensure_idempotent_metadata(
                existing.metadata,
                request.request_id,
                fingerprint,
                operation_key="save_operation_id",
                fingerprint_key="save_fingerprint",
            )
            return RobotApplicationResult(
                data={
                    "map": existing.model_dump(mode="json"),
                    "gateway": existing.metadata.get("save_gateway", {}),
                },
                replayed=True,
            )
        before = self.maps.get_active_map()
        robot_map, gateway = self.navigation.save_map(
            map_id=request.map_id,
            session_id=request.session_id,
            name=request.name,
            request_id=request.request_id,
            replacement_confirmed=request.replace_confirmed,
        )
        robot_map = self.maps.update_map(
            robot_map.model_copy(
                update={
                    "metadata": {
                        **robot_map.metadata,
                        "save_operation_id": request.request_id,
                        "save_fingerprint": fingerprint,
                        "save_gateway": gateway.data,
                    }
                }
            )
        )
        data = {"map": robot_map.model_dump(mode="json"), "gateway": gateway.data}
        self._publish("map_activated", data)
        if before and before.map_id != robot_map.map_id:
            self._publish("map_points_invalidated", {"map_id": before.map_id})
        return data

    def list_maps(self) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self.maps.list_maps()]

    def active_map(self) -> dict[str, Any]:
        return self.map_service.require_active_map().model_dump(mode="json")

    def list_points(self, map_id: str | None = None) -> list[dict[str, Any]]:
        selected_map = map_id or self.map_service.require_active_map().map_id
        return [item.model_dump(mode="json") for item in self.maps.list_points(selected_map)]

    def create_point(self, request: RobotPointCreateRequest) -> dict[str, Any]:
        fingerprint = self._fingerprint(request.model_dump(mode="json", exclude={"request_id"}))
        existing = self.maps.get_point(request.point_id)
        if existing:
            self._ensure_idempotent(existing.metadata, request.request_id, fingerprint)
            return RobotApplicationResult(data=existing.model_dump(mode="json"), replayed=True)
        point = self.map_service.save_point(
            RobotMapPoint(
                point_id=request.point_id,
                map_id=request.map_id,
                name=request.name,
                point_type=request.point_type,
                x=request.x,
                y=request.y,
                yaw=request.yaw,
                metadata={**request.metadata, "operation_id": request.request_id, "request_fingerprint": fingerprint},
            )
        )
        data = point.model_dump(mode="json")
        self._publish("point_created", data)
        return RobotApplicationResult(data=data)

    def update_point(self, point_id: str, request: RobotPointUpdateRequest) -> dict[str, Any]:
        existing = self.maps.get_point(point_id)
        if existing is None:
            raise RobotNavigationServiceError(RobotNavigationErrorCode.MAP_POINT_NOT_FOUND, "点位不存在")
        fingerprint = self._fingerprint(request.model_dump(mode="json", exclude={"request_id"}))
        if existing.metadata.get("operation_id") == request.request_id:
            self._ensure_idempotent(existing.metadata, request.request_id, fingerprint)
            return existing.model_dump(mode="json")
        updates = request.model_dump(exclude_none=True, exclude={"request_id"})
        metadata = updates.pop("metadata", existing.metadata)
        point = self.map_service.save_point(
            existing.model_copy(
                update={
                    **updates,
                    "metadata": {**metadata, "operation_id": request.request_id, "request_fingerprint": fingerprint},
                }
            )
        )
        data = point.model_dump(mode="json")
        self._publish("point_updated", data)
        return data

    def delete_point(self, point_id: str, request_id: str) -> dict[str, Any]:
        existing = self.maps.get_point(point_id)
        if existing is None:
            raise RobotNavigationServiceError(RobotNavigationErrorCode.MAP_POINT_NOT_FOUND, "点位不存在")
        if existing.status == RobotMapPointStatus.INVALID:
            if existing.metadata.get("operation_id") == request_id:
                return existing.model_dump(mode="json")
            raise RobotNavigationServiceError(
                RobotNavigationErrorCode.IDEMPOTENCY_CONFLICT,
                "点位已由其他操作失效",
            )
        point = self.map_service.save_point(
            existing.model_copy(
                update={
                    "status": RobotMapPointStatus.INVALID,
                    "metadata": {**existing.metadata, "operation_id": request_id},
                }
            )
        )
        data = point.model_dump(mode="json")
        self._publish("point_invalidated", data)
        return data

    def list_routes(self, map_id: str | None = None) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self.maps.list_routes(map_id)]

    def create_route(self, request: RobotRouteCreateRequest) -> dict[str, Any]:
        fingerprint = self._fingerprint(request.model_dump(mode="json", exclude={"request_id"}))
        existing = self.maps.get_route(request.route_id)
        if existing:
            self._ensure_idempotent(existing[0].metadata, request.request_id, fingerprint)
            return RobotApplicationResult(data=self.route_detail(request.route_id), replayed=True)
        route = RobotPatrolRoute(
            route_id=request.route_id,
            map_id=request.map_id,
            name=request.name,
            status=RobotPatrolRouteStatus.VALID,
            metadata={**request.metadata, "operation_id": request.request_id, "request_fingerprint": fingerprint},
        )
        points = [
            RobotPatrolRoutePoint(route_id=request.route_id, point_id=point_id, sequence=index)
            for index, point_id in enumerate(request.point_ids)
        ]
        self.map_service.save_route(route, points)
        data = self.route_detail(route.route_id)
        self._publish("route_created", data)
        return RobotApplicationResult(data=data)

    def route_detail(self, route_id: str) -> dict[str, Any]:
        value = self.maps.get_route(route_id)
        if value is None:
            raise RobotNavigationServiceError(RobotNavigationErrorCode.ROUTE_NOT_FOUND, "巡逻路线不存在")
        route, points = value
        return {
            "route": route.model_dump(mode="json"),
            "points": [item.model_dump(mode="json") for item in points],
        }

    def start_patrol(self, route_id: str, request: RobotPatrolStartRequest) -> dict[str, Any]:
        existing_event = self.navigation_events.get_event(request.request_id)
        if existing_event is not None:
            task = self._require_task(existing_event.task_id or "")
            expected_source = request.source_event_id or f"patrol:{route_id}:{request.request_id}"
            if existing_event.event_type != "patrol_started" or task.source_event_id != expected_source:
                self._raise_idempotency_conflict(request.request_id)
            return RobotApplicationResult(data=task.model_dump(mode="json"), replayed=True)
        task = self.navigation.create_task(
            source_event_id=request.source_event_id or f"patrol:{route_id}:{request.request_id}",
            trace_id=request.trace_id or request.request_id,
            task_type="patrol",
            location=route_id,
        )
        task = self.navigation.start_patrol(
            task_id=task.task_id,
            route_id=route_id,
            request_id=request.request_id,
            checks=self._current_checks(),
        )
        data = task.model_dump(mode="json")
        self._publish("patrol_dispatched", data)
        return RobotApplicationResult(data=data)

    def pause_task(self, task_id: str, request_id: str, *, manual: bool = False) -> dict[str, Any]:
        replay = self._task_operation_replay(task_id, request_id, "task_paused")
        if replay:
            return replay
        task = self.navigation.pause_task(task_id=task_id, request_id=request_id, manual=manual)
        data = task.model_dump(mode="json")
        self._publish("task_paused", data)
        return data

    def resume_task(self, task_id: str, request_id: str) -> dict[str, Any]:
        replay = self._task_operation_replay(task_id, request_id, "task_resumed")
        if replay:
            return replay
        task = self.navigation.resume_task(task_id=task_id, request_id=request_id, checks=self._current_checks())
        data = task.model_dump(mode="json")
        self._publish("task_resumed", data)
        return data

    def stop_task(self, task_id: str, request_id: str) -> dict[str, Any]:
        replay = self._task_operation_replay(task_id, request_id, "task_stopped")
        if replay:
            return replay
        task = self.navigation.stop_task(task_id=task_id, request_id=request_id)
        data = task.model_dump(mode="json")
        self._publish("task_cancelled", data)
        return data

    def manual_acquire(self, task_id: str, request_id: str) -> dict[str, Any]:
        replay = self._task_operation_replay(task_id, request_id, "manual_takeover")
        if replay:
            return replay
        task = self.navigation.manual_takeover(task_id=task_id, request_id=request_id)
        data = task.model_dump(mode="json")
        self._publish("manual_control_acquired", data)
        return data

    def manual_release(self, task_id: str, request_id: str) -> dict[str, Any]:
        replay = self._task_operation_replay(task_id, request_id, "manual_control_released")
        if replay:
            return replay
        task = self.navigation.release_control(task_id=task_id, request_id=request_id)
        data = task.model_dump(mode="json")
        self._publish("manual_control_released", data)
        return data

    def emergency_bundle(self, incident_id: str) -> dict[str, Any]:
        return self.emergency.get_bundle(incident_id).model_dump(mode="json")

    def dispatch_emergency(self, incident_id: str, request: RobotEmergencyDispatchRequest) -> dict[str, Any]:
        existing_case = self.emergencies.get_case_by_incident_id(incident_id)
        if existing_case is not None:
            if existing_case.area_id != request.area_id or existing_case.area_name != request.area_name:
                raise RobotNavigationServiceError(
                    RobotNavigationErrorCode.IDEMPOTENCY_CONFLICT,
                    "incident_id 已用于不同区域的应急请求",
                    details={"incident_id": incident_id},
                )
            return RobotApplicationResult(data=existing_case.model_dump(mode="json"), replayed=True)
        already_completed = self.navigation_events.get_event(request.request_id) is not None
        try:
            case = self.emergency.create_and_dispatch(
                incident_id=incident_id,
                area_id=request.area_id,
                area_name=request.area_name,
                request_id=request.request_id,
                checks=self._current_checks(),
                alarm_id=request.alarm_id,
                camera_id=request.camera_id,
                risk_level=request.risk_level,
                fall_probability=request.fall_probability,
            )
        except RobotNavigationServiceError:
            existing = self.emergencies.get_case_by_incident_id(incident_id)
            if existing:
                self._publish(
                    "emergency_case_created",
                    existing.model_dump(mode="json"),
                    incident_id=incident_id,
                )
                self._publish(
                    "emergency_dispatch_blocked",
                    existing.model_dump(mode="json"),
                    incident_id=incident_id,
                )
            raise
        data = case.model_dump(mode="json")
        if not already_completed:
            self._publish("emergency_case_created", data, incident_id=incident_id)
            self._publish("emergency_dispatched", data, incident_id=incident_id)
        return RobotApplicationResult(data=data, replayed=already_completed)

    def acknowledge_emergency(self, incident_id: str, request: RobotEmergencyAcknowledgeRequest) -> dict[str, Any]:
        existing = self.emergency.require_case(incident_id)
        fingerprint = self._fingerprint(request.model_dump(mode="json", exclude={"request_id"}))
        operations = dict(existing.metadata.get("acknowledge_operations", {}))
        if request.request_id in operations:
            if operations[request.request_id] != fingerprint:
                self._raise_idempotency_conflict(request.request_id)
            return RobotApplicationResult(data=existing.model_dump(mode="json"), replayed=True)
        case = self.emergency.acknowledge(incident_id=incident_id, admin_id=request.admin_id)
        case = self.emergencies.save_case(
            case.model_copy(
                update={
                    "metadata": {
                        **case.metadata,
                        "acknowledge_operations": {**operations, request.request_id: fingerprint},
                    }
                }
            )
        )
        data = case.model_dump(mode="json")
        self._publish("emergency_acknowledged", data, incident_id=incident_id)
        return data

    def resume_emergency(self, incident_id: str, request_id: str) -> dict[str, Any]:
        case = self.emergency.require_case(incident_id)
        replay = self._emergency_task_replay(case, request_id, "task_resumed")
        if replay:
            return replay
        task = self.navigation.resume_task(
            task_id=case.robot_task_id or "",
            request_id=request_id,
            checks=self._current_checks(),
        )
        case = self.emergencies.save_case(
            case.model_copy(update={"status": RobotEmergencyCaseStatus.ACTIVE, "execution_state": task.execution_state, "navigation_state": task.execution_state, "control_owner": task.control_owner})
        )
        data = case.model_dump(mode="json")
        self._publish("emergency_dispatched", data, incident_id=incident_id)
        return data

    def record_dialogue(self, incident_id: str, request: RobotEmergencyDialogueRequest) -> dict[str, Any]:
        existing_turn = next(
            (item for item in self.emergencies.list_dialogue_turns(incident_id) if item.turn_id == request.turn_id),
            None,
        )
        if existing_turn is not None:
            if (
                existing_turn.intent != request.intent
                or existing_turn.input_text != request.input_text
                or existing_turn.confidence != request.confidence
            ):
                self._raise_idempotency_conflict(request.turn_id)
            return RobotApplicationResult(
                data=self.emergency.require_case(incident_id).model_dump(mode="json"),
                replayed=True,
            )
        case = self.emergency.record_dialogue_result(
            incident_id=incident_id,
            turn_id=request.turn_id,
            intent=request.intent,
            input_text=request.input_text,
            confidence=request.confidence,
        )
        data = case.model_dump(mode="json")
        self._publish("dialogue_result_recorded", data, incident_id=incident_id)
        if request.intent == RobotDialogueIntent.SAFE_RESPONSE:
            self._publish("waiting_admin_confirmation", data, incident_id=incident_id)
        else:
            self._publish("alarm_escalation_required", data, incident_id=incident_id)
        return data

    def start_mock_emergency_dialogue(
        self,
        incident_id: str,
        request: RobotEmergencyMockDialogueStartRequest,
    ) -> dict[str, Any]:
        case = self.emergency.require_case(incident_id)
        task = self._require_task(case.robot_task_id or "")
        self._require_mock_emergency_contract(case, task)
        prompt_text = request.mock_prompt_text or self.DEFAULT_MOCK_PROMPT
        fingerprint = self._fingerprint({"mock_prompt_text": prompt_text})
        operations = dict(case.metadata.get("mock_dialogue_start_operations", {}))
        existing_fingerprint = operations.get(request.request_id)
        if existing_fingerprint is not None:
            if existing_fingerprint != fingerprint:
                self._raise_idempotency_conflict(request.request_id)
            return RobotApplicationResult(data=self.emergency_bundle(incident_id), replayed=True)
        if task.execution_state == RobotNavigationExecutionState.WAITING_RESPONSE:
            raise RobotNavigationServiceError(
                RobotNavigationErrorCode.DIALOGUE_ALREADY_STARTED,
                "Mock 应急对话已经开始",
                details={"incident_id": incident_id, "execution_state": task.execution_state.value},
            )
        if task.execution_state not in {
            RobotNavigationExecutionState.NAVIGATING,
            RobotNavigationExecutionState.ARRIVED,
        }:
            raise RobotNavigationServiceError(
                RobotNavigationErrorCode.INVALID_STATE_TRANSITION,
                "当前任务状态不允许开始 Mock 应急对话",
                details={"current": task.execution_state.value, "target": RobotNavigationExecutionState.WAITING_RESPONSE.value},
            )

        case = self.emergency.begin_dialogue(
            incident_id=incident_id,
            operation_id=request.request_id,
        )
        case = self.emergencies.save_case(
            case.model_copy(
                update={
                    "metadata": {
                        **case.metadata,
                        "mock_dialogue_start_operations": {
                            **operations,
                            request.request_id: fingerprint,
                        },
                        "mock_prompt": {
                            "text": prompt_text,
                            "asr_status": "pending_mock",
                            "tts_status": "pending_mock",
                            "source": "mock",
                        },
                    }
                }
            )
        )
        bundle = self.emergency_bundle(incident_id)
        for event_type in ("task_arrived", "voice_prompting", "waiting_response"):
            self._publish(event_type, bundle, incident_id=incident_id)
        return bundle

    def complete_mock_emergency_return(
        self,
        incident_id: str,
        request: RobotEmergencyMockReturnCompleteRequest,
    ) -> dict[str, Any]:
        case = self.emergency.require_case(incident_id)
        task = self._require_task(case.robot_task_id or "")
        self._require_mock_emergency_contract(case, task)
        existing_event = self.navigation_events.get_event(request.request_id)
        if existing_event is not None:
            if existing_event.task_id != task.task_id or existing_event.event_type != "return_home_completed":
                self._raise_idempotency_conflict(request.request_id)
            return RobotApplicationResult(data=self.emergency_bundle(incident_id), replayed=True)
        if case.dialogue_intent != RobotDialogueIntent.SAFE_RESPONSE or not case.acknowledged_by:
            raise RobotNavigationServiceError(
                RobotNavigationErrorCode.SAFE_RESPONSE_REQUIRED,
                "只有安全回应且管理员已确认的应急案例可以完成 Mock 返航",
                details={"incident_id": incident_id},
            )
        if (
            task.execution_state != RobotNavigationExecutionState.RETURNING_HOME
            or case.execution_state != RobotNavigationExecutionState.RETURNING_HOME
        ):
            raise RobotNavigationServiceError(
                RobotNavigationErrorCode.RETURN_NOT_IN_PROGRESS,
                "当前应急任务不处于 Mock 返航中",
                details={
                    "task_execution_state": task.execution_state.value,
                    "case_execution_state": case.execution_state.value,
                },
            )

        self.emergency.complete_return(
            incident_id=incident_id,
            operation_id=request.request_id,
            resolution=self.MOCK_RETURN_RESOLUTION,
        )
        bundle = self.emergency_bundle(incident_id)
        self._publish("return_home_completed", bundle, incident_id=incident_id)
        self._publish("emergency_completed", bundle, incident_id=incident_id)
        return bundle

    def resolve_and_return(self, incident_id: str, request: RobotEmergencyResolveRequest) -> dict[str, Any]:
        existing = self.emergency.require_case(incident_id)
        fingerprint = self._fingerprint(request.model_dump(mode="json", exclude={"request_id"}))
        replay = self._emergency_task_replay(existing, request.request_id, "return_home_started")
        if replay:
            stored_fingerprint = existing.metadata.get("resolve_fingerprint")
            if stored_fingerprint != fingerprint:
                self._raise_idempotency_conflict(request.request_id)
            return replay
        case = self.emergency.resolve_and_return(
            incident_id=incident_id,
            request_id=request.request_id,
            checks=self._current_checks(),
        )
        case = self.emergencies.save_case(
            case.model_copy(
                update={
                    "metadata": {
                        **case.metadata,
                        "resolve_operation_id": request.request_id,
                        "resolve_fingerprint": fingerprint,
                    }
                }
            )
        )
        data = case.model_dump(mode="json")
        self._publish("return_home_requested", data, incident_id=incident_id)
        return data

    def dialogue(self, incident_id: str) -> list[dict[str, Any]]:
        self.emergency.require_case(incident_id)
        return [item.model_dump(mode="json") for item in self.emergencies.list_dialogue_turns(incident_id)]

    def timeline(self, task_id: str) -> list[dict[str, Any]]:
        self._require_task(task_id)
        return [item.model_dump(mode="json") for item in self.tasks.list_timeline(task_id)]

    def task_navigation_events(self, task_id: str) -> list[dict[str, Any]]:
        self._require_task(task_id)
        return [item.model_dump(mode="json") for item in self.navigation_events.list_for_task(task_id)]

    def task_dialogue(self, task_id: str) -> list[dict[str, Any]]:
        task = self._require_task(task_id)
        case = next(
            (item for item in self.emergencies.list_cases() if item.robot_task_id == task.task_id),
            None,
        )
        return self.dialogue(case.incident_id) if case else []

    def _task_operation_replay(
        self,
        task_id: str,
        request_id: str,
        event_type: str,
    ) -> RobotApplicationResult | None:
        event = self.navigation_events.get_event(request_id)
        if event is None:
            return None
        if event.task_id != task_id or event.event_type != event_type:
            self._raise_idempotency_conflict(request_id)
        return RobotApplicationResult(data=self._require_task(task_id).model_dump(mode="json"), replayed=True)

    def _emergency_task_replay(
        self,
        case: Any,
        request_id: str,
        event_type: str,
    ) -> RobotApplicationResult | None:
        event = self.navigation_events.get_event(request_id)
        if event is None:
            return None
        if event.task_id != case.robot_task_id or event.event_type != event_type:
            self._raise_idempotency_conflict(request_id)
        return RobotApplicationResult(data=case.model_dump(mode="json"), replayed=True)

    def _current_checks(self) -> RobotSafetyChecks:
        return self.build_effective_safety_snapshot().checks

    def build_effective_safety_snapshot(self) -> RobotEffectiveSafetySnapshot:
        return self.safety_state_resolver.resolve(self.gateway.state())

    def _publish(self, event_type: str, data: dict[str, Any], *, incident_id: str | None = None) -> None:
        channels = ("navigation", "status", "emergency") if incident_id else ("navigation", "status")
        self.event_hub.publish(event_type, data, channels=channels, incident_id=incident_id)

    def _require_task(self, task_id: str):
        task = self.tasks.get_task(task_id)
        if task is None:
            raise RobotNavigationServiceError(RobotNavigationErrorCode.TASK_NOT_FOUND, "机器人任务不存在")
        return task

    @staticmethod
    def _require_mock_emergency_contract(case: Any, task: Any) -> None:
        if case.provider != "mock" or task.provider != "mock":
            raise RobotNavigationServiceError(
                RobotNavigationErrorCode.MOCK_PROVIDER_CONTRACT_VIOLATION,
                "应急状态推进接口仅允许 Mock Provider",
            )
        if case.real_motion_enabled is not False or task.real_motion_enabled is not False:
            raise RobotNavigationServiceError(
                RobotNavigationErrorCode.REAL_MOTION_DISABLED,
                "应急状态推进接口禁止启用真实运动",
            )

    @staticmethod
    def _fingerprint(payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _ensure_idempotent(metadata: dict[str, Any], operation_id: str, fingerprint: str) -> None:
        if metadata.get("operation_id") == operation_id and metadata.get("request_fingerprint") == fingerprint:
            return
        raise RobotNavigationServiceError(
            RobotNavigationErrorCode.IDEMPOTENCY_CONFLICT,
            "operation_id 已用于不同请求",
            details={"operation_id": operation_id},
        )

    @classmethod
    def _ensure_idempotent_metadata(
        cls,
        metadata: dict[str, Any],
        operation_id: str,
        fingerprint: str,
        *,
        operation_key: str,
        fingerprint_key: str,
    ) -> None:
        if metadata.get(operation_key) == operation_id and metadata.get(fingerprint_key) == fingerprint:
            return
        cls._raise_idempotency_conflict(operation_id)

    @staticmethod
    def _raise_idempotency_conflict(operation_id: str) -> None:
        raise RobotNavigationServiceError(
            RobotNavigationErrorCode.IDEMPOTENCY_CONFLICT,
            "operation_id 已用于不同请求",
            details={"operation_id": operation_id},
        )
