from __future__ import annotations

import asyncio
from pathlib import Path

from backend.config import get_settings
from backend.dependencies import get_video_bridge_service
from backend.models.alarm_model import AlarmType
from backend.models.video_bridge_model import VideoBridgeFallEventRequest


def test_video_bridge_push_creates_alarm() -> None:
    service = get_video_bridge_service()
    settings = get_settings()
    runtime_config_path = Path(settings.data_dir) / "video_bridge_runtime_config.json"
    original_runtime_payload = runtime_config_path.read_text(encoding="utf-8") if runtime_config_path.exists() else None

    try:
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
        assert settings.fall_detection_target_elder_id == "elder_demo_01"
    finally:
        if original_runtime_payload is None:
            runtime_config_path.unlink(missing_ok=True)
        else:
            runtime_config_path.write_text(original_runtime_payload, encoding="utf-8")
