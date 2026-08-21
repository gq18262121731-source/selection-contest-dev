from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.models.alarm_model import AlarmRecord
from backend.models.robot_model import (
    RobotCallbackAck,
    RobotObservation,
    RobotTask,
    RobotTaskOutcome,
    RobotTaskResultCallbackRequest,
    RobotTaskStatus,
    RobotTaskStatusCallbackRequest,
    RobotTaskStep,
    RobotTaskTimeline,
)
from backend.repositories.robot_task_repo import RobotTaskRepository
from backend.services.robot_gateway_service import RobotGatewayService
from backend.services.robot_risk_fusion_service import RobotRiskFusionService
from backend.services.websocket_manager import WebSocketManager


logger = logging.getLogger(__name__)


class RobotTaskService:
    """Main-system orchestration for persisted robot tasks."""

    def __init__(
        self,
        *,
        repository: RobotTaskRepository,
        gateway_service: RobotGatewayService,
        websocket_manager: WebSocketManager,
        risk_fusion_service: RobotRiskFusionService,
    ) -> None:
        self._repository = repository
        self._gateway_service = gateway_service
        self._websocket_manager = websocket_manager
        self._risk_fusion_service = risk_fusion_service

    @property
    def gateway_service(self) -> RobotGatewayService:
        return self._gateway_service

    async def dispatch_fall_confirmation(
        self,
        *,
        event: dict[str, object],
        alarm: AlarmRecord,
    ) -> dict[str, Any]:
        source_event_id = self._source_event_id(event=event, alarm=alarm)
        existing = self._repository.get_by_source_event_id(source_event_id)
        if existing is not None:
            summary = self._dispatch_summary(existing, gateway_response=None, duplicate=True)
            alarm.metadata["robot_task"] = summary
            return summary

        now = datetime.now(timezone.utc)
        task = RobotTask(
            task_id=f"robot_task_{uuid4().hex[:16]}",
            source_event_id=source_event_id,
            trace_id=str(event.get("trace_id") or uuid4()),
            alarm_event_id=alarm.id,
            elder_id=self._elder_id(event=event, alarm=alarm),
            elder_name=self._elder_name(event=event, alarm=alarm),
            location=self._location(event=event, alarm=alarm),
            risk_level=self._risk_level(event=event, alarm=alarm),
            status=RobotTaskStatus.QUEUED,
            current_step=RobotTaskStep.RECEIVED,
            created_at=now,
            updated_at=now,
        )
        self._repository.create_task(task)
        self._repository.add_timeline(
            RobotTaskTimeline(
                task_id=task.task_id,
                callback_id=f"{task.task_id}:created",
                sequence=0,
                status=RobotTaskStatus.QUEUED,
                step=RobotTaskStep.RECEIVED,
                message="主系统收到跌倒事件并创建机器人任务",
                occurred_at=now,
                payload={"source_event_id": source_event_id, "alarm_id": alarm.id},
            )
        )
        await self._publish_task_event("robot.task.created", task)

        gateway_response = await self._submit_gateway(event=event, alarm=alarm, task=task)
        task = self._apply_gateway_response(task, gateway_response)
        task = self._repository.update_task(task)
        self._repository.add_timeline(
            RobotTaskTimeline(
                task_id=task.task_id,
                callback_id=f"{task.task_id}:gateway-dispatch",
                sequence=1,
                status=task.status,
                step=task.current_step,
                message=self._gateway_timeline_message(task, gateway_response),
                occurred_at=datetime.now(timezone.utc),
                payload={"gateway_response": gateway_response},
            )
        )
        await self._publish_task_event(self._event_type_for_task(task), task)
        summary = self._dispatch_summary(task, gateway_response=gateway_response, duplicate=False)
        alarm.metadata["robot_task"] = summary
        return summary

    async def handle_status_callback(self, payload: RobotTaskStatusCallbackRequest) -> RobotCallbackAck:
        return await self._handle_callback(payload, is_result=False)

    async def handle_result_callback(self, payload: RobotTaskResultCallbackRequest) -> RobotCallbackAck:
        return await self._handle_callback(payload, is_result=True)

    def list_tasks(
        self,
        *,
        status: str | None = None,
        elder_id: str | None = None,
        outcome: str | None = None,
        limit: int = 100,
    ) -> list[RobotTask]:
        return self._repository.list_tasks(status=status, elder_id=elder_id, outcome=outcome, limit=limit)

    def get_task(self, task_id: str) -> RobotTask | None:
        return self._repository.get_task(task_id)

    def list_timeline(self, task_id: str) -> list[RobotTaskTimeline]:
        return self._repository.list_timeline(task_id)

    def get_observation(self, task_id: str) -> RobotObservation | None:
        return self._repository.get_observation(task_id)

    async def cancel_task(self, task_id: str) -> RobotTask | None:
        task = self._repository.get_task(task_id)
        if task is None:
            return None
        if task.status in {RobotTaskStatus.COMPLETED, RobotTaskStatus.CANCELLED}:
            return task
        now = datetime.now(timezone.utc)
        task = task.model_copy(
            update={
                "status": RobotTaskStatus.CANCELLED,
                "completed_at": now,
                "current_step": RobotTaskStep.REPORTING,
            }
        )
        task = self._repository.update_task(task)
        self._repository.add_timeline(
            RobotTaskTimeline(
                task_id=task.task_id,
                callback_id=f"{task.task_id}:cancelled",
                sequence=task.last_sequence + 1,
                status=RobotTaskStatus.CANCELLED,
                step=RobotTaskStep.REPORTING,
                message="主系统取消机器人任务",
                occurred_at=now,
                payload={"source": "health_new"},
            )
        )
        await self._publish_task_event("robot.task.updated", task)
        return task

    async def simulate_response(
        self,
        *,
        task_id: str,
        response_type: RobotTaskOutcome,
        transcript: str | None = None,
        snapshot_url: str | None = None,
    ) -> RobotCallbackAck | None:
        task = self._repository.get_task(task_id)
        if task is None:
            return None
        payload = RobotTaskResultCallbackRequest(
            callback_id=f"sim_{task_id}_{uuid4().hex[:8]}",
            sequence=max(task.last_sequence + 1, 10),
            task_id=task.gateway_task_id,
            external_task_id=task.task_id,
            source_event_id=task.source_event_id,
            trace_id=task.trace_id,
            status=RobotTaskStatus.COMPLETED,
            step=RobotTaskStep.REPORTING,
            outcome=response_type,
            message=f"开发模拟机器人结果：{response_type.value}",
            observation={
                "snapshot_url": snapshot_url,
                "camera_available": bool(snapshot_url),
                "voice_available": True,
                "response_type": response_type.value,
                "transcript": transcript,
            },
            robot={"robot_id": task.robot_id or "go2_mock", "mode": "mock"},
        )
        return await self.handle_result_callback(payload)

    async def _handle_callback(
        self,
        payload: RobotTaskStatusCallbackRequest | RobotTaskResultCallbackRequest,
        *,
        is_result: bool,
    ) -> RobotCallbackAck:
        existing_timeline = self._repository.get_timeline_by_callback_id(payload.callback_id)
        if existing_timeline is not None:
            task = self._repository.get_task(existing_timeline.task_id)
            return RobotCallbackAck(
                duplicate=True,
                task_id=existing_timeline.task_id,
                status=task.status if task else existing_timeline.status,
                step=task.current_step if task else existing_timeline.step,
                message="duplicate callback ignored",
            )

        task = self._repository.find_for_callback(
            external_task_id=payload.external_task_id,
            gateway_task_id=payload.task_id,
            source_event_id=payload.source_event_id,
        )
        if task is None:
            logger.warning("Robot callback did not match a task: callback_id=%s", payload.callback_id)
            return RobotCallbackAck(
                ok=False,
                accepted=False,
                message="robot task not found",
            )

        if payload.sequence <= task.last_sequence:
            logger.info(
                "Ignoring stale robot callback: task_id=%s callback_id=%s sequence=%s last_sequence=%s",
                task.task_id,
                payload.callback_id,
                payload.sequence,
                task.last_sequence,
            )
            return RobotCallbackAck(
                accepted=True,
                stale=True,
                task_id=task.task_id,
                status=task.status,
                step=task.current_step,
                message="stale callback ignored",
            )

        task = self._apply_callback_to_task(task, payload, is_result=is_result)
        task = self._repository.update_task(task)
        timeline = RobotTaskTimeline(
            task_id=task.task_id,
            callback_id=payload.callback_id,
            sequence=payload.sequence,
            status=payload.status,
            step=payload.step,
            message=payload.message,
            occurred_at=payload.occurred_at,
            payload=payload.model_dump(mode="json"),
        )
        self._repository.add_timeline(timeline)
        observation: RobotObservation | None = None
        if is_result:
            observation = self._observation_from_result(task, payload)  # type: ignore[arg-type]
            if observation is not None:
                self._repository.save_observation(observation)
            self._risk_fusion_service.apply_task_result(task=task, observation=observation)

        await self._publish_task_event("robot.task.timeline", task, timeline=timeline)
        await self._publish_task_event(self._event_type_for_task(task), task, observation=observation)
        return RobotCallbackAck(
            task_id=task.task_id,
            status=task.status,
            step=task.current_step,
            message="callback accepted",
        )

    async def _submit_gateway(
        self,
        *,
        event: dict[str, object],
        alarm: AlarmRecord,
        task: RobotTask,
    ) -> dict[str, Any]:
        try:
            return await self._gateway_service.submit_fall_confirmation_async(
                event=event,
                alarm=alarm,
                external_task_id=task.task_id,
                trace_id=task.trace_id,
            )
        except TypeError:
            return await self._gateway_service.submit_fall_confirmation_async(event=event, alarm=alarm)
        except Exception as exc:
            logger.warning("Robot gateway dispatch failed unexpectedly: %s", exc)
            return {
                "ok": False,
                "status": "unavailable",
                "base_url": self._gateway_service.base_url,
                "endpoint": "/api/robot/events/fall",
                "status_code": None,
                "data": None,
                "error": str(exc),
            }

    def _apply_gateway_response(self, task: RobotTask, response: dict[str, Any]) -> RobotTask:
        gateway_task_id = self._extract_gateway_task_id(response)
        robot_id = self._extract_robot_id(response)
        blocked_code = self._gateway_block_error(response)
        now = datetime.now(timezone.utc)
        update: dict[str, Any] = {
            "gateway_task_id": gateway_task_id or task.gateway_task_id,
            "robot_id": robot_id or task.robot_id,
        }
        if blocked_code:
            update.update(
                {
                    "status": RobotTaskStatus.BLOCKED,
                    "current_step": RobotTaskStep.PREFLIGHT,
                    "error_code": blocked_code,
                    "error_message": self._gateway_error_message(response),
                }
            )
        elif bool(response.get("ok")):
            update.update(
                {
                    "status": RobotTaskStatus.RUNNING,
                    "current_step": RobotTaskStep.PREFLIGHT,
                    "started_at": task.started_at or now,
                }
            )
        else:
            update.update(
                {
                    "status": RobotTaskStatus.BLOCKED,
                    "current_step": RobotTaskStep.PREFLIGHT,
                    "error_code": self._gateway_error_code(response),
                    "error_message": self._gateway_error_message(response),
                }
            )
        return task.model_copy(update=update)

    @staticmethod
    def _apply_callback_to_task(
        task: RobotTask,
        payload: RobotTaskStatusCallbackRequest | RobotTaskResultCallbackRequest,
        *,
        is_result: bool,
    ) -> RobotTask:
        now = datetime.now(timezone.utc)
        update: dict[str, Any] = {
            "gateway_task_id": payload.task_id or task.gateway_task_id,
            "trace_id": payload.trace_id or task.trace_id,
            "status": payload.status,
            "current_step": payload.step,
            "last_sequence": payload.sequence,
            "started_at": task.started_at or (now if payload.status == RobotTaskStatus.RUNNING else None),
        }
        if payload.status in {RobotTaskStatus.COMPLETED, RobotTaskStatus.FAILED, RobotTaskStatus.CANCELLED, RobotTaskStatus.BLOCKED}:
            update["completed_at"] = task.completed_at or now
        if is_result and isinstance(payload, RobotTaskResultCallbackRequest):
            update["outcome"] = payload.outcome or task.outcome or RobotTaskOutcome.UNKNOWN
            robot_payload = payload.robot if isinstance(payload.robot, dict) else {}
            if robot_payload.get("robot_id"):
                update["robot_id"] = str(robot_payload["robot_id"])
        return task.model_copy(update=update)

    @staticmethod
    def _observation_from_result(
        task: RobotTask,
        payload: RobotTaskResultCallbackRequest,
    ) -> RobotObservation | None:
        observation_payload = payload.observation if isinstance(payload.observation, dict) else {}
        if not observation_payload and payload.outcome is None:
            return None
        response_type = observation_payload.get("response_type") or payload.outcome
        try:
            normalized_response_type = RobotTaskOutcome(response_type) if response_type else payload.outcome
        except ValueError:
            normalized_response_type = RobotTaskOutcome.UNKNOWN
        return RobotObservation(
            task_id=task.task_id,
            snapshot_url=observation_payload.get("snapshot_url"),
            camera_available=RobotTaskService._coerce_optional_bool(observation_payload.get("camera_available")),
            voice_available=RobotTaskService._coerce_optional_bool(observation_payload.get("voice_available")),
            response_type=normalized_response_type,
            transcript=observation_payload.get("transcript"),
            observed_at=payload.occurred_at,
            raw_payload={
                "observation": observation_payload,
                "robot": payload.robot if isinstance(payload.robot, dict) else {},
            },
        )

    async def _publish_task_event(
        self,
        event_type: str,
        task: RobotTask,
        *,
        timeline: RobotTaskTimeline | None = None,
        observation: RobotObservation | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "event_type": event_type,
            "task_id": task.task_id,
            "gateway_task_id": task.gateway_task_id,
            "source_event_id": task.source_event_id,
            "trace_id": task.trace_id,
            "status": task.status.value,
            "step": task.current_step.value,
            "outcome": task.outcome.value if task.outcome else None,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        if timeline is not None:
            payload["timeline"] = timeline.model_dump(mode="json")
        if observation is not None:
            payload["observation"] = observation.model_dump(mode="json")
        await self._websocket_manager.broadcast_robot_event(payload)

    @staticmethod
    def _event_type_for_task(task: RobotTask) -> str:
        if task.status == RobotTaskStatus.COMPLETED:
            return "robot.task.completed"
        if task.status == RobotTaskStatus.FAILED:
            return "robot.task.failed"
        if task.status == RobotTaskStatus.BLOCKED:
            return "robot.task.blocked"
        return "robot.task.updated"

    @staticmethod
    def _source_event_id(*, event: dict[str, object], alarm: AlarmRecord) -> str:
        metadata = dict(event.get("metadata") or {}) if isinstance(event.get("metadata"), dict) else {}
        alarm_metadata = dict(alarm.metadata or {})
        normalized_event = dict(alarm_metadata.get("event") or {}) if isinstance(alarm_metadata.get("event"), dict) else {}
        return str(
            event.get("source_event_id")
            or event.get("incident_id")
            or metadata.get("source_event_id")
            or metadata.get("incident_id")
            or normalized_event.get("incident_id")
            or alarm.id
        ).strip()

    @staticmethod
    def _elder_id(*, event: dict[str, object], alarm: AlarmRecord) -> str:
        metadata = dict(event.get("metadata") or {}) if isinstance(event.get("metadata"), dict) else {}
        return str(metadata.get("elder_id") or alarm.metadata.get("elder_id") or "").strip()

    @staticmethod
    def _elder_name(*, event: dict[str, object], alarm: AlarmRecord) -> str:
        metadata = dict(event.get("metadata") or {}) if isinstance(event.get("metadata"), dict) else {}
        return str(metadata.get("elder_name") or alarm.metadata.get("elder_name") or "").strip()

    @staticmethod
    def _location(*, event: dict[str, object], alarm: AlarmRecord) -> str:
        metadata = dict(event.get("metadata") or {}) if isinstance(event.get("metadata"), dict) else {}
        return str(event.get("location") or metadata.get("location") or alarm.metadata.get("location") or "unknown").strip() or "unknown"

    @staticmethod
    def _risk_level(*, event: dict[str, object], alarm: AlarmRecord) -> str:
        metadata = dict(event.get("metadata") or {}) if isinstance(event.get("metadata"), dict) else {}
        return str(event.get("risk_level") or event.get("risk") or metadata.get("risk_level") or alarm.metadata.get("risk_level") or "unknown").strip() or "unknown"

    @staticmethod
    def _extract_gateway_task_id(response: dict[str, Any]) -> str | None:
        data = response.get("data")
        candidates: list[Any] = []
        if isinstance(data, dict):
            candidates.extend([data.get("task_id"), data.get("taskId"), data.get("id")])
            nested = data.get("data")
            if isinstance(nested, dict):
                candidates.extend([nested.get("task_id"), nested.get("taskId"), nested.get("id")])
        for value in candidates:
            if value:
                return str(value)
        return None

    @staticmethod
    def _extract_robot_id(response: dict[str, Any]) -> str | None:
        data = response.get("data")
        if isinstance(data, dict):
            robot = data.get("robot")
            if isinstance(robot, dict) and robot.get("robot_id"):
                return str(robot["robot_id"])
            if data.get("robot_id"):
                return str(data["robot_id"])
        return None

    @staticmethod
    def _gateway_block_error(response: dict[str, Any]) -> str | None:
        if not bool(response.get("ok")):
            return None
        data = response.get("data")
        if not isinstance(data, dict):
            return None
        error_code = data.get("error_code")
        nested = data.get("data")
        if isinstance(nested, dict):
            error_code = error_code or nested.get("error_code")
            robot_online = nested.get("robotOnline", nested.get("robot_online"))
            motion_ready = nested.get("motionReady", nested.get("motion_ready"))
        else:
            robot_online = data.get("robotOnline", data.get("robot_online"))
            motion_ready = data.get("motionReady", data.get("motion_ready"))
        if error_code:
            return str(error_code)
        if robot_online is False:
            return "BLOCKED_ROBOT_OFFLINE"
        if motion_ready is False:
            return "DDS_NOT_READY"
        if data.get("success") is False or data.get("ok") is False:
            return str(data.get("code") or "ROBOT_GATEWAY_REJECTED")
        return None

    @staticmethod
    def _gateway_error_code(response: dict[str, Any]) -> str:
        error = str(response.get("error") or "").lower()
        status = str(response.get("status") or "").lower()
        if "timeout" in error:
            return "ROBOT_GATEWAY_TIMEOUT"
        if status in {"unavailable", "disabled"} or "connection" in error:
            return "ROBOT_GATEWAY_UNAVAILABLE"
        return "ROBOT_GATEWAY_ERROR"

    @staticmethod
    def _gateway_error_message(response: dict[str, Any]) -> str:
        data = response.get("data")
        if isinstance(data, dict):
            for key in ("error_message", "message", "detail"):
                if data.get(key):
                    return str(data[key])
            nested = data.get("data")
            if isinstance(nested, dict):
                for key in ("error_message", "message", "detail"):
                    if nested.get(key):
                        return str(nested[key])
        return str(response.get("error") or response.get("status") or "robot gateway unavailable")

    @staticmethod
    def _gateway_timeline_message(task: RobotTask, response: dict[str, Any]) -> str:
        if task.status == RobotTaskStatus.BLOCKED:
            return f"机器人任务阻塞：{task.error_code or 'ROBOT_GATEWAY_ERROR'}"
        if bool(response.get("ok")):
            return "go2-gateway 已接收机器人跌倒确认任务"
        return "go2-gateway 未能接收机器人任务"

    @staticmethod
    def _dispatch_summary(
        task: RobotTask,
        *,
        gateway_response: dict[str, Any] | None,
        duplicate: bool,
    ) -> dict[str, Any]:
        summary = {
            "ok": task.status not in {RobotTaskStatus.BLOCKED, RobotTaskStatus.FAILED},
            "duplicate": duplicate,
            "task_id": task.task_id,
            "external_task_id": task.task_id,
            "gateway_task_id": task.gateway_task_id,
            "source_event_id": task.source_event_id,
            "trace_id": task.trace_id,
            "status": task.status.value,
            "step": task.current_step.value,
            "outcome": task.outcome.value if task.outcome else None,
            "error_code": task.error_code,
            "error_message": task.error_message,
        }
        if gateway_response is not None:
            summary.update(
                {
                    "gateway": gateway_response,
                    "data": gateway_response.get("data"),
                    "base_url": gateway_response.get("base_url"),
                    "endpoint": gateway_response.get("endpoint"),
                    "status_code": gateway_response.get("status_code"),
                    "error": gateway_response.get("error"),
                }
            )
        return summary

    @staticmethod
    def _coerce_optional_bool(value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y"}:
                return True
            if normalized in {"false", "0", "no", "n"}:
                return False
        return None
