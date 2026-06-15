# Video Bridge Prestage

This stage reserves a main-system integration point for a future standalone
video analysis service. It does not connect to RTSP, change WebRTC/WebSocket
video streams, run YOLO/pose/tracking, mutate `FallStateMachine`, or create
alarm POST events.

## Legacy Video Modules

These existing modules remain in place and are intentionally isolated from the
new bridge:

- `backend/api/camera_api.py`
- `backend/api/camera_source_api.py`
- `backend/services/camera_service.py`
- `backend/services/camera_stream_hub.py`
- `backend/services/camera_source_registry.py`
- `backend/services/camera_setup_config_service.py`
- `backend/services/camera_audio_hub.py`
- `backend/services/fall_detection_service.py`
- `backend/services/pose_detection_service.py`
- `backend/services/target_user_fall_service.py`
- `frontend/vue-dashboard/src/components/CameraMonitorCard.vue`
- `frontend/vue-dashboard/src/components/CameraRegistrationPanel.vue`
- `frontend/vue-dashboard/src/components/PoseDebugPanel.vue`

## New Adapter Layer

- `backend/services/video_adapter.py`
  Normalizes future video-service telemetry into the main-system schema.
- `backend/services/video_bridge_service.py`
  Keeps the latest normalized telemetry in memory for status and placeholder UI.
- `backend/models/video_bridge_model.py`
  Defines the reserved data contract.
- `backend/api/video_bridge_api.py`
  Exposes the main-system bridge endpoints.

## API

`POST /api/v1/video-bridge/analysis`

Accepts a standalone service push payload.

```json
{
  "camera_id": "room-101",
  "stream_name": "main",
  "service_state": "running",
  "camera_lost": false,
  "capture_stale": false,
  "frame_age_ms": 180,
  "video_fps": 12.4,
  "overlay_fps": 5.8,
  "ws_fps": 4.6,
  "track_id": "track-demo-01",
  "bbox": [120, 80, 260, 360],
  "target": {
    "target_id": "elder-01",
    "label": "registered",
    "matched": true,
    "confidence": 0.92
  },
  "fall_state": "normal",
  "risk": "low",
  "fall_prob": 0.06,
  "snapshot_url": "/snapshots/room-101/latest.jpg",
  "timestamp": "2026-05-29T05:30:00+08:00"
}
```

Example response:

```json
{
  "ok": true,
  "accepted": true,
  "camera_id": "room-101",
  "stream_name": "main",
  "received_at": "2026-05-28T21:38:42.608805Z",
  "service_state": "running",
  "stale": false
}
```

`GET /api/v1/video-bridge/status`

Returns current bridge state, latest analysis, and all in-memory camera rows for
the frontend placeholder page.

## Frontend Placeholder

- `frontend/vue-dashboard/src/views/VideoBridgePage.vue`
- Route: `#/video-bridge`
- Navigation label: `视频接入口`

The page displays mock/last-pushed bridge state, FPS metrics, target/fall/risk
fields, and a non-video placeholder frame. It does not open any video stream.
