# Go2 Event-Driven Integration

This document records the competition demo chain after introducing the Go2 gateway relay in the main system.

## System Roles

- `camera-service`: owns fixed-camera capture, fall detection, evidence, and event push.
- `D:\health_new`: owns elder-care alarms, event center, frontend, agent context, and robot task dispatch.
- `unitree_go`: owns Go2 connection, status, safe motion, camera snapshot, and task execution.

## Runtime Chain

```text
camera-service
  POST /api/v1/video-bridge/fall-events
    -> D:\health_new creates/broadcasts fall alarm
    -> D:\health_new POSTs /api/robot/events/fall to unitree_go
    -> unitree_go executes confirm_fall task
    -> D:\health_new exposes robot status/tasks under /api/v1/robot/*
```

## Camera-Service To Main System

Use the existing main-system endpoint:

```http
POST http://<main-system-host>:8000/api/v1/video-bridge/fall-events
Content-Type: application/json
X-Vision-Service-Token: <optional token>
```

Minimum payload:

```json
{
  "camera_id": "camera_01",
  "stream_name": "primary",
  "source": "vision_service",
  "event_type": "fall_confirmed",
  "state": "confirmed_fall",
  "status": "fallen_confirmed",
  "risk": "critical",
  "risk_level": "critical",
  "fall_detected": true,
  "fall_prob": 0.93,
  "fall_score": 0.93,
  "track_id": "20",
  "incident_id": "vision-fall-camera_01_track_20-20260707093015532100",
  "snapshot_url": "http://<camera-service-host>:8000/fall-events/snapshots/example.jpg",
  "timestamp": "2026-07-20T10:31:00+08:00",
  "metadata": {
    "elder_id": "elder-001",
    "location": "bedroom"
  }
}
```

## Main System To Go2 Gateway

Configure:

```text
ROBOT_GATEWAY_ENABLED=true
ROBOT_GATEWAY_BASE_URL=http://127.0.0.1:8090
ROBOT_GATEWAY_TIMEOUT_SECONDS=1.5
```

When a fall alarm is promoted, `D:\health_new` sends:

```http
POST http://127.0.0.1:8090/api/robot/events/fall
Content-Type: application/json
```

Payload:

```json
{
  "event": "fall_detected",
  "elder_id": "elder-001",
  "location": "bedroom",
  "confidence": 0.93,
  "source_event_id": "vision-fall-camera_01_track_20-20260707093015532100",
  "camera_id": "camera_01",
  "metadata": {
    "alarm_id": "<main-system-alarm-id>",
    "alarm_type": "fall_injury_risk",
    "camera_id": "camera_01",
    "incident_id": "vision-fall-camera_01_track_20-20260707093015532100",
    "snapshot_url": "http://<camera-service-host>:8000/fall-events/snapshots/example.jpg",
    "source": "vision_service"
  }
}
```

Robot dispatch is non-blocking for alarm creation. If the Go2 gateway is offline, the fall alarm is still created and its metadata contains `robot_task.status = "unavailable"`.

## Main-System Robot API

Frontend and agents should call the main system, not the Go2 gateway directly:

```http
GET  /api/v1/robot/health
GET  /api/v1/robot/status
GET  /api/v1/robot/tasks
GET  /api/v1/robot/tasks/{task_id}
POST /api/v1/robot/events/fall
POST /api/v1/robot/tasks/target-move
```

This keeps the Go2 repository as the embodied execution endpoint while the elder-care system remains the orchestration authority.
