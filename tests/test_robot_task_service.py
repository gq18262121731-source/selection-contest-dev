from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from backend.models.alarm_model import AlarmLayer, AlarmPriority, AlarmRecord, AlarmType
from backend.models.robot_model import (
    RobotTaskOutcome,
    RobotTaskResultCallbackRequest,
    RobotTaskStatus,
    RobotTaskStatusCallbackRequest,
    RobotTaskStep,
)
from backend.repositories.robot_task_repo import RobotTaskRepository
from backend.services.alarm_priority_queue import AlarmPriorityQueue
from backend.services.alarm_service import AlarmService
from backend.services.health_data_repository import HealthDataRepository
from backend.services.notification_service import NotificationService
from backend.services.robot_risk_fusion_service import RobotRiskFusionService
from backend.services.robot_task_service import RobotTaskService


class _FakeGateway:
    def __init__(self, response: dict[str, Any]) -> None:
        self.base_url = "http://go2.test"
        self.timeout_seconds = 0.5
        self.enabled = True
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def submit_fall_confirmation_async(
        self,
        *,
        event: dict[str, object],
        alarm: AlarmRecord,
        external_task_id: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "event": event,
                "alarm_id": alarm.id,
                "external_task_id": external_task_id,
                "trace_id": trace_id,
            }
        )
        return dict(self.response)


class _FakeWebSocketManager:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def broadcast_robot_event(self, payload: dict[str, Any]) -> None:
        self.events.append(payload)


class _NoopDetector:
    def evaluate(self, sample):
        return []


def _alarm() -> AlarmRecord:
    return AlarmRecord(
        device_mac="AA:BB:CC:DD:EE:11",
        alarm_type=AlarmType.FALL_INJURY_RISK,
        alarm_level=AlarmPriority.WARNING,
        alarm_layer=AlarmLayer.INTELLIGENT,
        message="视频跌倒告警",
        anomaly_probability=0.93,
        metadata={"elder_id": "elder-001", "elder_name": "张三"},
    )


def _event(source_event_id: str = "fall-event-001") -> dict[str, object]:
    return {
        "incident_id": source_event_id,
        "camera_id": "camera_01",
        "fall_score": 0.93,
        "risk_level": "critical",
        "metadata": {"elder_id": "elder-001", "elder_name": "张三", "location": "客厅"},
    }


def _service(tmp_path: Path, gateway_response: dict[str, Any]) -> tuple[RobotTaskService, RobotTaskRepository, AlarmService, _FakeGateway, _FakeWebSocketManager]:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'robot.db').as_posix()}"
    repo = RobotTaskRepository(database_url)
    health_repo = HealthDataRepository(database_url=database_url)
    alarm_service = AlarmService(
        detector=_NoopDetector(),
        queue=AlarmPriorityQueue(redis_url="redis://127.0.0.1:0/0"),
        notification_service=NotificationService(),
    )
    websocket = _FakeWebSocketManager()
    gateway = _FakeGateway(gateway_response)
    service = RobotTaskService(
        repository=repo,
        gateway_service=gateway,  # type: ignore[arg-type]
        websocket_manager=websocket,  # type: ignore[arg-type]
        risk_fusion_service=RobotRiskFusionService(
            alarm_service=alarm_service,
            health_data_repository=health_repo,
        ),
    )
    return service, repo, alarm_service, gateway, websocket


def test_dispatch_is_idempotent_by_source_event_id_and_saves_gateway_task_id(tmp_path: Path) -> None:
    service, repo, _alarm_service, gateway, websocket = _service(
        tmp_path,
        {
            "ok": True,
            "status": "ok",
            "base_url": "http://go2.test",
            "endpoint": "/api/robot/events/fall",
            "status_code": 200,
            "data": {"success": True, "data": {"taskId": "go2_task_001"}},
            "error": None,
        },
    )
    alarm = _alarm()

    first = asyncio.run(service.dispatch_fall_confirmation(event=_event(), alarm=alarm))
    second = asyncio.run(service.dispatch_fall_confirmation(event=_event(), alarm=alarm))

    assert first["task_id"] == second["task_id"]
    assert second["duplicate"] is True
    assert len(gateway.calls) == 1
    task = repo.get_task(first["task_id"])
    assert task is not None
    assert task.gateway_task_id == "go2_task_001"
    assert task.status == RobotTaskStatus.RUNNING
    assert gateway.calls[0]["external_task_id"] == first["task_id"]
    assert websocket.events[0]["event_type"] == "robot.task.created"


def test_gateway_unavailable_blocks_task_without_losing_local_record(tmp_path: Path) -> None:
    service, repo, _alarm_service, gateway, _websocket = _service(
        tmp_path,
        {
            "ok": False,
            "status": "unavailable",
            "base_url": "http://go2.test",
            "endpoint": "/api/robot/events/fall",
            "status_code": None,
            "data": None,
            "error": "connection_error: refused",
        },
    )

    result = asyncio.run(service.dispatch_fall_confirmation(event=_event(), alarm=_alarm()))

    task = repo.get_task(result["task_id"])
    assert task is not None
    assert task.status == RobotTaskStatus.BLOCKED
    assert task.error_code == "ROBOT_GATEWAY_UNAVAILABLE"
    assert len(gateway.calls) == 1


def test_callbacks_are_idempotent_and_stale_sequence_does_not_override(tmp_path: Path) -> None:
    service, repo, _alarm_service, _gateway, _websocket = _service(
        tmp_path,
        {
            "ok": True,
            "status": "ok",
            "base_url": "http://go2.test",
            "endpoint": "/api/robot/events/fall",
            "status_code": 200,
            "data": {"success": True, "data": {"taskId": "go2_task_001"}},
            "error": None,
        },
    )
    dispatch = asyncio.run(service.dispatch_fall_confirmation(event=_event(), alarm=_alarm()))
    task_id = dispatch["task_id"]

    callback = RobotTaskStatusCallbackRequest(
        callback_id="cb_move",
        sequence=4,
        task_id="go2_task_001",
        external_task_id=task_id,
        source_event_id="fall-event-001",
        status=RobotTaskStatus.RUNNING,
        step=RobotTaskStep.MOVING,
        message="机器人正在移动",
    )
    ack = asyncio.run(service.handle_status_callback(callback))
    duplicate = asyncio.run(service.handle_status_callback(callback))
    stale = asyncio.run(
        service.handle_status_callback(
            RobotTaskStatusCallbackRequest(
                callback_id="cb_old",
                sequence=3,
                task_id="go2_task_001",
                external_task_id=task_id,
                source_event_id="fall-event-001",
                status=RobotTaskStatus.RUNNING,
                step=RobotTaskStep.PREFLIGHT,
                message="旧回调",
            )
        )
    )

    task = repo.get_task(task_id)
    assert ack.accepted is True
    assert duplicate.duplicate is True
    assert stale.stale is True
    assert task is not None
    assert task.current_step == RobotTaskStep.MOVING
    assert task.last_sequence == 4
    assert len([item for item in repo.list_timeline(task_id) if item.callback_id == "cb_move"]) == 1


def test_need_help_result_saves_observation_and_escalates_alarm(tmp_path: Path) -> None:
    service, repo, alarm_service, _gateway, _websocket = _service(
        tmp_path,
        {
            "ok": True,
            "status": "ok",
            "base_url": "http://go2.test",
            "endpoint": "/api/robot/events/fall",
            "status_code": 200,
            "data": {"success": True, "data": {"taskId": "go2_task_001"}},
            "error": None,
        },
    )
    alarm = _alarm()
    dispatch = asyncio.run(service.dispatch_fall_confirmation(event=_event(), alarm=alarm))
    alarm_service.evaluate_alarm_records([alarm])

    ack = asyncio.run(
        service.handle_result_callback(
            RobotTaskResultCallbackRequest(
                callback_id="cb_result",
                sequence=10,
                task_id="go2_task_001",
                external_task_id=dispatch["task_id"],
                source_event_id="fall-event-001",
                status=RobotTaskStatus.COMPLETED,
                step=RobotTaskStep.REPORTING,
                outcome=RobotTaskOutcome.NEED_HELP,
                message="机器人现场确认需要帮助",
                observation={
                    "snapshot_url": "http://go2.test/arrival.jpg",
                    "camera_available": True,
                    "voice_available": True,
                    "response_type": "NEED_HELP",
                    "transcript": "我摔倒了，起不来",
                },
                robot={"robot_id": "go2_001", "battery": 76},
            )
        )
    )

    task = repo.get_task(dispatch["task_id"])
    observation = repo.get_observation(dispatch["task_id"])
    updated_alarm = alarm_service.get_alarm(alarm.id)
    assert ack.accepted is True
    assert task is not None
    assert task.status == RobotTaskStatus.COMPLETED
    assert task.outcome == RobotTaskOutcome.NEED_HELP
    assert observation is not None
    assert observation.transcript == "我摔倒了，起不来"
    assert updated_alarm is not None
    assert updated_alarm.alarm_level == AlarmPriority.CRITICAL
    assert updated_alarm.acknowledged is False
    assert updated_alarm.metadata["robot_fusion"]["outcome"] == "NEED_HELP"


def test_persisted_task_timeline_and_observation_survive_repository_restart(tmp_path: Path) -> None:
    service, repo, alarm_service, _gateway, _websocket = _service(
        tmp_path,
        {
            "ok": True,
            "status": "ok",
            "base_url": "http://go2.test",
            "endpoint": "/api/robot/events/fall",
            "status_code": 200,
            "data": {"success": True, "data": {"taskId": "go2_task_001"}},
            "error": None,
        },
    )
    alarm = _alarm()
    dispatch = asyncio.run(service.dispatch_fall_confirmation(event=_event(), alarm=alarm))
    alarm_service.evaluate_alarm_records([alarm])
    asyncio.run(
        service.handle_result_callback(
            RobotTaskResultCallbackRequest(
                callback_id="cb_safe",
                sequence=10,
                task_id="go2_task_001",
                external_task_id=dispatch["task_id"],
                source_event_id="fall-event-001",
                status=RobotTaskStatus.COMPLETED,
                step=RobotTaskStep.REPORTING,
                outcome=RobotTaskOutcome.SAFE,
                observation={"response_type": "SAFE", "transcript": "我没事"},
            )
        )
    )

    restarted_repo = RobotTaskRepository(f"sqlite+aiosqlite:///{(tmp_path / 'robot.db').as_posix()}")
    assert restarted_repo.get_task(dispatch["task_id"]) is not None
    assert len(restarted_repo.list_timeline(dispatch["task_id"])) >= 3
    assert restarted_repo.get_observation(dispatch["task_id"]) is not None
    assert repo.get_task(dispatch["task_id"]) is not None
