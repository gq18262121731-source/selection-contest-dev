from __future__ import annotations

import asyncio
from pathlib import Path

from backend.config import get_settings
import backend.dependencies as dependencies
from backend.dependencies import get_video_bridge_service
from backend.models.alarm_model import AlarmType
from backend.models.video_bridge_model import VideoBridgeFallEventRequest
from backend.services.video_bridge_service import VideoBridgeService


def test_video_bridge_push_creates_alarm() -> None:
    service = get_video_bridge_service()
    settings = get_settings()
    runtime_config_path = Path(settings.data_dir) / "video_bridge_runtime_config.json"
    original_runtime_payload = runtime_config_path.read_text(encoding="utf-8") if runtime_config_path.exists() else None
    original_robot_gateway = dependencies._robot_gateway_service

    class _FakeRobotGateway:
        base_url = settings.robot_gateway_base_url.rstrip("/")
        enabled = True
        timeout_seconds = settings.robot_gateway_timeout_seconds

        async def submit_fall_confirmation_async(self, *, event, alarm):
            return {
                "ok": True,
                "status": "ok",
                "base_url": "http://unitree-go.test",
                "endpoint": "/api/robot/events/fall",
                "status_code": 200,
                "data": {"success": True, "data": {"taskId": "task_robot_001"}},
                "error": None,
            }

    try:
        dependencies._robot_gateway_service = _FakeRobotGateway()
        runtime_config = service.update_runtime_config(
            {
                "base_url": "http://127.0.0.1:8000",
                "camera_id": "camera_01",
                "poll_enabled": False,
                "push_token": "unit-test-token",
                "target_device_mac": "AA:BB:CC:DD:EE:11",
                "target_elder_id": "elder_demo_01",
                "target_family_ids": ["family01"],
            }
        )

        assert runtime_config.push_token_set is True

        payload = VideoBridgeFallEventRequest(
            camera_id="camera_01",
            stream_name="primary",
            state="confirmed_fall",
            status="confirmed_fall",
            risk="high",
            fall_detected=True,
            fall_prob=0.93,
            incident_id="unit-test-incident-001",
            track_id="track-001",
            snapshot_url="http://127.0.0.1:8000/fall-events/snapshots/test.jpg",
            metadata={"source_test": "video_bridge_push"},
        )

        result = asyncio.run(
            service.receive_fall_event_async(
                payload,
                source_ip="10.0.0.8",
                push_token="unit-test-token",
            )
        )

        assert result["promoted"] is True
        alarm = result["alarm"]
        assert alarm is not None
        assert alarm.alarm_type == AlarmType.FALL_INJURY_RISK
        assert alarm.device_mac == "AA:BB:CC:DD:EE:11"
        assert alarm.metadata["elder_id"] == "elder_demo_01"
        assert alarm.metadata["family_ids"] == ["family01"]
        assert alarm.metadata["incident_id"] == "unit-test-incident-001"
        assert alarm.metadata["camera_id"] == "camera_01"
        assert alarm.metadata["trigger"] == "video_bridge_fall_events"
        assert isinstance(alarm.metadata.get("event"), dict)
        assert alarm.metadata["event"]["incident_id"] == "unit-test-incident-001"
        assert alarm.metadata["event"]["state"] == "confirmed_fall"
        assert alarm.metadata["event"]["camera_id"] == "camera_01"
        assert alarm.metadata["event"]["fall_score"] == 0.93
        assert alarm.metadata["event"]["fall_prob"] == 0.93
        assert alarm.metadata["robot_task"]["ok"] is True
        assert alarm.metadata["robot_task"]["data"]["data"]["taskId"] == "task_robot_001"
        assert settings.fall_detection_target_elder_id == "elder_demo_01"
    finally:
        dependencies._robot_gateway_service = original_robot_gateway
        if original_runtime_payload is None:
            runtime_config_path.unlink(missing_ok=True)
        else:
            runtime_config_path.write_text(original_runtime_payload, encoding="utf-8")


def test_poll_promotion_skips_normal_state_when_threshold_is_zero(tmp_path: Path) -> None:
    settings = get_settings().model_copy(
        update={
            "data_dir": tmp_path,
            "vision_service_base_url": "http://127.0.0.1:8090",
            "fall_detection_min_alert_score": 0.0,
        }
    )
    service = VideoBridgeService(settings=settings, runtime_config_path=tmp_path / "video_bridge_runtime_config.json")

    event, reason = service._promotion_event_from_latest(
        {
            "camera_id": "camera_01",
            "fall_state": "normal",
            "fall_prob": 0.0,
            "alarm_confirmed": False,
            "timestamp": "2026-06-16T17:35:46.023+00:00",
        },
        payload={
            "service_state": "running",
            "timestamp": "2026-06-16T17:35:46.023+00:00",
        },
        camera_id="camera_01",
        source={},
    )

    assert event is None
    assert reason == "not_candidate"


def test_poll_promotion_accepts_confirmed_fall_signal(tmp_path: Path) -> None:
    settings = get_settings().model_copy(
        update={
            "data_dir": tmp_path,
            "vision_service_base_url": "http://127.0.0.1:8090",
            "fall_detection_min_alert_score": 0.0,
        }
    )
    service = VideoBridgeService(settings=settings, runtime_config_path=tmp_path / "video_bridge_runtime_config.json")

    event, reason = service._promotion_event_from_latest(
        {
            "camera_id": "camera_01",
            "fall_state": "confirmed_fall",
            "alarm_confirmed": True,
            "fall_prob": 0.93,
            "incident_id": "confirmed-incident-001",
            "track_id": "track-001",
            "timestamp": "2026-06-16T17:35:46.023+00:00",
        },
        payload={
            "service_state": "running",
            "timestamp": "2026-06-16T17:35:46.023+00:00",
        },
        camera_id="camera_01",
        source={},
    )

    assert reason is None
    assert event is not None
    assert event["incident_id"] == "confirmed-incident-001"
    assert event["fall_detected"] is True
    assert event["state"] == "confirmed_fall"
