# Fall Detection Model System Guide

Updated on `2026-04-29`.

This document describes the current fall detection model bundle, its working logic, supported features, model components, system integration interface, and deployment notes.

## 1. System Goal

The model is designed for a care/health monitoring system that connects to a camera or video stream and continuously detects whether a target person has fallen.

When a fall is detected, the system should:

1. Locate the person in the frame.
2. Determine whether the event is a real fall or only a suspicious posture.
3. Continue observing after the person recovers.
4. Grade post-fall injury risk.
5. Output structured advice for an upper-layer system.
6. Optionally call a multimodal LLM to review alert snapshots.

The model is not a medical diagnosis system. Injury grading is operational triage: it helps decide whether to ignore, observe, notify staff, or handle urgently.

## 2. Main Capabilities

### Video Detection

Detect falls from a local video file and optionally write an annotated output video.

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\infer_fall.py --mode video --source D:\path\input.mp4 --save-path D:\path\result.mp4 --no-display
```

### Camera / Stream Detection

OpenCV-compatible sources are supported:

- Local camera: `0`, `1`, etc.
- Local video path.
- RTSP stream, for example `rtsp://user:password@camera-ip:554/stream`.
- HTTP stream if OpenCV can open it.

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\infer_fall.py --mode video --source "rtsp://user:password@camera-ip:554/stream" --event-log .\outputs\camera_events.jsonl --snapshot-dir .\outputs\camera_snapshots --no-display
```

### Image Detection

Run a single-image check and write an annotated image plus JSON.

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\infer_fall.py --mode image --source D:\path\image.jpg --output-image .\outputs\image_result.jpg --output-json .\outputs\image_result.json
```

### Event Output for System Integration

Use `--event-log` to write JSONL events. Each line is one JSON object that can be consumed by another project.

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\infer_fall.py --mode video --source "rtsp://user:password@camera/stream" --event-log .\outputs\camera_events.jsonl --snapshot-dir .\outputs\camera_snapshots --save-path .\outputs\camera_review.mp4 --no-display
```

## 3. Model Components

### YOLO Pose Front End

Default:

```text
yolo11n-pose.pt
```

Purpose:

- Detect people.
- Extract body keypoints.
- Provide person boxes for tracking and temporal models.

### GRU Temporal Fall Model

Default:

```text
weights/gru_pose_fall_v1.pt
```

Purpose:

- Analyze pose sequences over time.
- Recognize fall-like temporal changes.

### Hybrid TCN + Transformer Model

Default private-scene model:

```text
weights/hybrid_tcn_transformer_private_real_v1.pt
```

Fallback:

```text
weights/hybrid_tcn_transformer_v2_matchgru.pt
```

Purpose:

- Capture short-term motion transitions.
- Complement GRU with stronger temporal representation.

### Posture Risk Classifier

Default:

```text
runs/yolo_posture_person_binary_cls_v1/weights/best.pt
```

Purpose:

- Classify person crop as `risk` or `safe`.
- Help recognize lying, crawling, bending, or other risky static postures.

### YOLO Fall Detector

Current trained weight:

```text
weights/yolo_fall_detector_v1.pt
```

Purpose:

- Provide object-detection evidence for fall/fallen/lying-like states.
- Used as an auxiliary branch, not as the only fall decision.

Important note:

This detector was trained from weak labels generated from existing videos and pose boxes. It is useful as an auxiliary signal, but production accuracy should be improved with manually checked bounding-box labels from the final camera scene.

### Semantic Temporal Branch

Default:

```text
weights/semantic_mix_falldb_private_real_v1.pt
```

Purpose:

- Provide cross-domain semantic pose features.
- Currently configured with weight `0.00` in the private-scene profile because the current private validation favored GRU + Hybrid + Posture + Detector.

## 4. Current Fusion Logic

The final fall score is computed from multiple branches:

```text
fall_score =
  gru_score      * gru_weight
+ hybrid_score   * hybrid_weight
+ semantic_score * semantic_weight
+ posture_score  * posture_weight
+ detector_score * detector_weight
```

Default private-scene profile:

```text
GRU      0.15
Hybrid   0.45
Semantic 0.00
Posture  0.30
Detector 0.10
Threshold 0.65
```

Configuration file:

```text
configs/model_registry.yaml
```

## 5. Fall State Machine

The real-time monitor maintains a state per tracked person.

Main states:

```text
normal
suspected_fall
confirmed_fall
post_fall_monitoring
recovery_watch
recovered
injury_watch
abnormal_recovery
needs_assistance
emergency
```

Basic flow:

```text
normal
→ suspected_fall
→ confirmed_fall
→ post_fall_monitoring
→ recovery_watch
→ recovered
→ injury_watch / abnormal_recovery / needs_assistance / emergency
→ normal
```

`recovered` does not mean the event is over. The system continues observing after recovery to detect delayed injury signs such as limping, unstable walking, or unusually slow movement.

## 6. Injury Risk Grading

Configuration:

```text
configs/injury_rules.yaml
```

Levels:

```text
I0 normal / no active fall event
I1 minor fall, recovered and still being observed
I2 minor injury risk, delayed or slightly abnormal recovery
I3 moderate injury risk, limping/unstable/abnormal recovery
I4 severe injury risk, unable to recover or needs assistance
I5 emergency risk, long down time or long immobility
```

Tracked signals:

- Down duration.
- Immobile duration.
- Recovery delay.
- Normalized walking speed.
- Body sway.
- Left/right ankle motion asymmetry.
- Limp score.
- Mobility score.
- Stability score.
- Combined injury score.

Example advice:

```text
I1: 已恢复但仍处于观察期，暂不需要紧急处理。
I2: 继续观察，建议提醒管理员关注是否疼痛、崴脚或行动变慢。
I3: 疑似跛行或恢复异常，建议尽快人工查看。
I4: 立即安排人员到场协助，避免让目标人物自行移动。
I5: 立即呼叫现场人员或紧急联系人。
```

## 7. Event JSONL Format

Example event:

```json
{
  "event_type": "fall_confirmed",
  "source": "rtsp://camera/stream",
  "timestamp_s": 12.3,
  "frame_idx": 369,
  "track_id": 1,
  "bbox": [120.0, 90.0, 360.0, 480.0],
  "state": "confirmed_fall",
  "severity": "L2",
  "fall_score": 0.82,
  "scores": {
    "gru": 0.80,
    "hybrid": 0.75,
    "semantic": 0.10,
    "posture": 0.88,
    "detector": 0.52
  },
  "posture_label": "risk",
  "injury": {
    "level": "I2",
    "state": "post_fall_monitoring",
    "score": 0.42,
    "reason": "fall_confirmed_observing",
    "advice": "轻伤风险：继续观察，建议提醒管理员关注是否疼痛、崴脚或行动变慢。",
    "limp_score": 0.0,
    "mobility_score": 0.91,
    "stability_score": 0.08,
    "down_seconds": 1.2,
    "recovery_delay_seconds": null,
    "observe_until_s": 0.0
  },
  "snapshot_path": "outputs/camera_snapshots/track1_fall_confirmed_0000012300.jpg"
}
```

Recommended upper-layer behavior:

- Read the JSONL file continuously.
- If `event_type == "fall_confirmed"`, show an immediate warning.
- If `injury.level` is `I3`, `I4`, or `I5`, escalate notification priority.
- Use `snapshot_path` for UI preview or LLM review.
- Store event records in your own database if the product needs history.

## 8. Multimodal LLM Review

Configuration:

```text
configs/llm_review.yaml
```

Primary model:

```text
Qwen/Qwen3-VL-8B-Instruct
```

Free fallback model:

```text
THUDM/GLM-4.1V-9B-Thinking
```

Run review:

```powershell
$env:SILICONFLOW_API_KEY="your_key"
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\llm_fall_review.py --image .\outputs\camera_snapshots\alert.jpg --detection-json .\outputs\image_result.json
```

The LLM is intended for alert snapshots, not every frame. It should be used to reduce false positives and provide richer human-readable advice.

## 9. Important Deployment Notes

The current model is ready for integration testing, but final deployment should be calibrated with the target camera.

Collect short clips from the final camera:

- Normal walking.
- Sitting and standing up.
- Bending.
- Lying down intentionally.
- Staged fall.
- Post-fall recovery.
- Limping or slow abnormal walking.

Then tune:

```text
configs/model_registry.yaml
configs/alert_rules.yaml
configs/injury_rules.yaml
```

The current default profile is conservative to reduce false positives in private-camera scenes.

## 10. Recommended Integration Checklist

1. Install the Conda/Python environment used by the project.
2. Place model files under `weights/` and `runs/` as configured.
3. Confirm the RTSP URL can be opened by OpenCV.
4. Run a local video smoke test.
5. Run the real camera stream with `--event-log`.
6. Let the upper-layer system tail the JSONL event file.
7. Use snapshots for UI display and optional LLM review.
8. Validate with real target-camera fall and non-fall clips.
9. Tune thresholds before final use.
