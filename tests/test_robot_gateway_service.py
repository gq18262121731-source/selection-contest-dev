from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.models.alarm_model import AlarmLayer, AlarmPriority, AlarmRecord, AlarmType
from backend.services.robot_gateway_service import RobotGatewayService


class _FakeResponse:
    ok = True
    status_code = 200
    headers = {"content-type": "application/json"}
    text = '{"success":true}'

    def json(self) -> dict[str, Any]:
        return {"success": True, "data": {"taskId": "task_001"}}


class _FakeSession:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> _FakeResponse:
        self.requests.append({"method": method, "url": url, **kwargs})
        return _FakeResponse()


def test_robot_gateway_builds_unitree_fall_task_payload() -> None:
    session = _FakeSession()
    service = RobotGatewayService(base_url="http://go2.local:8090", session=session)
    alarm = AlarmRecord(
        device_mac="AA:BB:CC:DD:EE:11",
        alarm_type=AlarmType.FALL_INJURY_RISK,
        alarm_level=AlarmPriority.CRITICAL,
        alarm_layer=AlarmLayer.INTELLIGENT,
        message="fall",
        anomaly_probability=0.94,
        metadata={"elder_id": "elder-001"},
    )

    result = service.submit_fall_event(
        service.build_fall_confirmation_payload(
            event={
                "source": "vision_service",
                "camera_id": "bedroom-camera",
                "incident_id": "fall-incident-001",
                "fall_score": 0.94,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": {"elder_id": "elder-001", "location": "bedroom"},
            },
            alarm=alarm,
        )
    )

    assert result["ok"] is True
    assert session.requests[0]["method"] == "POST"
    assert session.requests[0]["url"] == "http://go2.local:8090/api/robot/events/fall"
    assert session.requests[0]["json"]["event"] == "fall_detected"
    assert session.requests[0]["json"]["elder_id"] == "elder-001"
    assert session.requests[0]["json"]["location"] == "bedroom"
    assert session.requests[0]["json"]["confidence"] == 0.94
    assert session.requests[0]["json"]["source_event_id"] == "fall-incident-001"
    assert session.requests[0]["json"]["camera_id"] == "bedroom-camera"


def test_robot_gateway_disabled_does_not_call_network() -> None:
    session = _FakeSession()
    service = RobotGatewayService(base_url="http://go2.local:8090", enabled=False, session=session)

    result = service.status()

    assert result["ok"] is False
    assert result["status"] == "disabled"
    assert session.requests == []
