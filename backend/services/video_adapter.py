from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.models.video_bridge_model import VideoAnalysisPushRequest, VideoAnalysisRecord


ADAPTER_VERSION = "video_adapter.v1"


class VideoAnalysisAdapter:
    """Normalize standalone video-service telemetry for the main system.

    This adapter is deliberately thin: it translates a future service payload
    into a stable main-system record, but it does not open RTSP, run detection,
    touch websocket video streams, or promote fall events into alarms.
    """

    def normalize(self, payload: VideoAnalysisPushRequest) -> VideoAnalysisRecord:
        stable_fields = set(VideoAnalysisPushRequest.model_fields.keys())
        raw = {
            key: value
            for key, value in payload.model_dump(mode="python").items()
            if key in stable_fields
        }
        metadata = dict(payload.metadata or {})
        extras = self._extract_extra_fields(payload)
        if extras:
            metadata.setdefault("extra", {}).update(extras)

        received_at = datetime.now(timezone.utc)
        timestamp = payload.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        frame_age_ms = payload.frame_age_ms
        stale = bool(payload.capture_stale or payload.camera_lost)
        if frame_age_ms is not None and frame_age_ms >= 5000:
            stale = True

        raw.update(
            {
                "camera_id": payload.camera_id.strip(),
                "stream_name": payload.stream_name.strip() or "primary",
                "timestamp": timestamp,
                "metadata": metadata,
                "received_at": received_at,
                "stale": stale,
                "adapter_version": ADAPTER_VERSION,
            }
        )
        return VideoAnalysisRecord(**raw)

    def mock_record(self) -> VideoAnalysisRecord:
        now = datetime.now(timezone.utc)
        return VideoAnalysisRecord(
            camera_id="camera-placeholder-01",
            stream_name="primary",
            service_state="mock",
            camera_lost=False,
            capture_stale=False,
            frame_age_ms=240,
            video_fps=12.0,
            overlay_fps=6.0,
            ws_fps=0.0,
            stream_type="ws_image",
            stream_url="/ws/camera/processed",
            track_id="mock-track-001",
            bbox=[0.28, 0.18, 0.62, 0.86],
            target={"target_id": "elder-placeholder", "label": "reserved", "matched": False, "confidence": 0.0},
            fall_state="normal",
            risk="low",
            fall_prob=0.04,
            snapshot_url=None,
            timestamp=now,
            received_at=now,
            stale=False,
            adapter_version=ADAPTER_VERSION,
            metadata={"source": "mock_placeholder", "note": "Reserved main-system video bridge sample."},
        )

    @staticmethod
    def _extract_extra_fields(payload: VideoAnalysisPushRequest) -> dict[str, Any]:
        known = set(VideoAnalysisPushRequest.model_fields.keys())
        extra = payload.model_extra or {}
        return {key: value for key, value in extra.items() if key not in known}
