from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.models.alarm_model import AlarmPriority
from backend.models.robot_model import RobotObservation, RobotTask, RobotTaskOutcome, RobotTaskStatus
from backend.services.alarm_service import AlarmService
from backend.services.health_data_repository import HealthDataRepository


class RobotRiskFusionService:
    """Deterministic fusion from robot confirmation result back into fall alarms."""

    def __init__(
        self,
        *,
        alarm_service: AlarmService,
        health_data_repository: HealthDataRepository,
    ) -> None:
        self._alarm_service = alarm_service
        self._health_data_repository = health_data_repository

    def apply_task_result(
        self,
        *,
        task: RobotTask,
        observation: RobotObservation | None = None,
    ) -> dict[str, Any]:
        if not task.alarm_event_id:
            return {"applied": False, "reason": "missing_alarm_event_id"}

        alarm = self._alarm_service.get_alarm(task.alarm_event_id)
        if alarm is None:
            return {"applied": False, "reason": "alarm_not_found", "alarm_id": task.alarm_event_id}

        metadata = dict(alarm.metadata or {})
        fusion = self._fusion_payload(task=task, observation=observation)
        metadata["robot_task"] = self._robot_summary(task)
        metadata["robot_fusion"] = fusion
        if observation is not None:
            metadata["robot_observation"] = observation.model_dump(mode="json")
            if observation.transcript:
                metadata["robot_transcript"] = observation.transcript

        next_level = alarm.alarm_level
        next_message = alarm.message
        if task.outcome in {RobotTaskOutcome.NEED_HELP, RobotTaskOutcome.NO_RESPONSE}:
            next_level = AlarmPriority.CRITICAL
            next_message = self._append_once(next_message, fusion["label"])
        elif task.outcome in {RobotTaskOutcome.SAFE, RobotTaskOutcome.UNKNOWN}:
            next_message = self._append_once(next_message, fusion["label"])
        elif task.status in {RobotTaskStatus.FAILED, RobotTaskStatus.BLOCKED}:
            next_message = self._append_once(next_message, fusion["label"])

        updated_alarm = alarm.model_copy(
            update={
                "alarm_level": next_level,
                "message": next_message,
                "metadata": metadata,
            }
        )
        updated_alarm = self._alarm_service.update_alarm_record(updated_alarm)
        self._health_data_repository.persist_alerts([updated_alarm])
        return {
            "applied": True,
            "alarm_id": updated_alarm.id,
            "alarm_level": updated_alarm.alarm_level.value,
            "fusion": fusion,
        }

    @staticmethod
    def _fusion_payload(
        *,
        task: RobotTask,
        observation: RobotObservation | None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        transcript = observation.transcript if observation else None
        if task.outcome == RobotTaskOutcome.NEED_HELP:
            label = "机器人现场确认需要帮助"
            action = "保持或升级为CRITICAL，并继续家属与社区通知"
        elif task.outcome == RobotTaskOutcome.NO_RESPONSE:
            label = "机器人询问无回应"
            action = "升级为CRITICAL，建议立即人工核实"
        elif task.outcome == RobotTaskOutcome.SAFE:
            label = "老人有回应，等待人工复核或持续观察"
            action = "保留跌倒事件，不自动解除告警"
        elif task.outcome == RobotTaskOutcome.UNKNOWN:
            label = "现场确认结果未知"
            action = "保持原告警，继续人工复核"
        elif task.status in {RobotTaskStatus.FAILED, RobotTaskStatus.BLOCKED}:
            label = "机器人未完成确认"
            action = "不解除告警，传统告警链路继续执行"
        else:
            label = "机器人任务状态已更新"
            action = "等待最终结果"
        return {
            "label": label,
            "action": action,
            "outcome": task.outcome.value if task.outcome else None,
            "status": task.status.value,
            "step": task.current_step.value,
            "transcript": transcript,
            "updated_at": now,
        }

    @staticmethod
    def _robot_summary(task: RobotTask) -> dict[str, Any]:
        return {
            "task_id": task.task_id,
            "gateway_task_id": task.gateway_task_id,
            "source_event_id": task.source_event_id,
            "trace_id": task.trace_id,
            "status": task.status.value,
            "step": task.current_step.value,
            "outcome": task.outcome.value if task.outcome else None,
            "error_code": task.error_code,
            "error_message": task.error_message,
            "updated_at": task.updated_at.astimezone(timezone.utc).isoformat(),
        }

    @staticmethod
    def _append_once(message: str, suffix: str) -> str:
        if suffix in message:
            return message
        return f"{message} | {suffix}"
