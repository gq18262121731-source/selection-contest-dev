# Optimized Fall Detection System Plan

Updated on `2026-04-29`.

## Goal

The project is being upgraded from a model-only fall detector into a complete fall detection and warning workflow:

1. Accurate fall target localization.
2. Image, video, and real-time camera inference.
3. YOLO detection model integration.
4. AI warning analysis and severity levels.
5. Role-based access hooks for future UI/API work.
6. Dataset, model, inference, warning, and feedback loop.
7. Optional multimodal/LLM second-pass analysis.
8. YOLO metric evaluation and GT/prediction comparison artifacts.
9. Real-time warning state management.

## Implemented in this optimization pass

### Model registry

Model paths and deployment profiles are now centralized in:

`configs/model_registry.yaml`

The default deployment profile is `private_scene_fusion_v2`, which keeps the current private-scene tuned fusion:

- GRU: `0.15`
- Hybrid TCN+Transformer: `0.50`
- Semantic temporal: `0.00`
- Posture risk: `0.35`
- YOLO fall detector: `0.00`
- threshold: `0.65`

The YOLO fall detector branch is present but disabled until a dedicated `weights/yolo_fall_detector_v1.pt` is trained.

### Alert rules

State-machine and severity thresholds are now configurable in:

`configs/alert_rules.yaml`

This makes the real-time warning behavior tunable without editing Python code.

### Five-branch real-time fusion

`scripts/realtime_fall_monitor.py` now supports an optional YOLO fall detection branch:

```text
fall_score =
  gru_score * gru_weight
+ hybrid_score * hybrid_weight
+ semantic_score * semantic_weight
+ posture_score * posture_weight
+ detector_score * detector_weight
```

The detector branch is matched back to tracked people by box IoU. It is intentionally optional so an untrained detector cannot destabilize the current working pipeline.

### Unified inference entrypoint

Use:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\infer_fall.py --mode image --source D:\path\image.jpg
```

Video:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\infer_fall.py --mode video --source D:\path\video.mp4 --save-path D:\path\result.mp4 --no-display
```

Camera:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\infer_fall.py --mode camera --source 0
```

Image mode writes:

- `outputs/image_result.jpg`
- `outputs/image_result.json`

### YOLO fall detector training

Dataset template:

`configs/fall_detect_dataset.yaml`

Train:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\train_yolo_fall_detector.py --data .\configs\fall_detect_dataset.yaml --model yolo11s.pt --epochs 150 --imgsz 640 --batch 32
```

After training, copy or sync the best weight to:

`weights/yolo_fall_detector_v1.pt`

Then enable the branch in `configs/model_registry.yaml`:

```yaml
fall_detector:
  enabled: true
```

Start with a conservative detector fusion weight:

```yaml
detector: 0.10
```

Then re-search final weights after validation.

### YOLO detection evaluation

Evaluate a trained detector:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\evaluate_yolo_detect.py --weights .\runs\yolo_fall_detector_v1\weights\best.pt --data .\configs\fall_detect_dataset.yaml --split test
```

The script writes a compact JSON report to:

`reports/yolo_fall_detector_eval.json`

Ultralytics also generates plots and visual evaluation artifacts in the selected run directory.

### Multimodal LLM second-pass review

The recommended low-cost visual review model is:

`Qwen/Qwen3-VL-8B-Instruct`

Configuration:

`configs/llm_review.yaml`

Run a review on an alert snapshot:

```powershell
$env:SILICONFLOW_API_KEY="your_key"
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\llm_fall_review.py --image .\outputs\smoke_detector_result.jpg --detection-json .\outputs\smoke_detector_result.json
```

This module is intended for alert snapshots, not every video frame.

### Post-fall injury risk grading

Real-time monitoring now keeps observing a person after recovery instead of immediately returning to normal. The goal is not medical diagnosis; it is operational injury-risk triage.

Configuration:

`configs/injury_rules.yaml`

Risk levels:

- `I0`: normal / no active fall event
- `I1`: minor fall, recovered and still being observed
- `I2`: minor injury risk, delayed or slightly abnormal recovery
- `I3`: moderate injury risk, limping/unstable/abnormal recovery
- `I4`: severe injury risk, unable to recover or needs assistance
- `I5`: emergency risk, long down time or long immobility

Additional states:

- `injury_watch`
- `abnormal_recovery`
- `needs_assistance`
- `emergency`

Tracked recovery signals:

- down duration
- immobile duration
- recovery delay
- normalized walking speed
- body sway
- left/right ankle motion asymmetry
- combined injury score

This lets the system catch cases where a person stands up after a fall but later appears unstable or limps.

### System integration interface

OpenCV sources are accepted directly:

- Local camera index: `0`
- Local video path: `D:\path\video.mp4`
- RTSP stream: `rtsp://user:password@host:554/stream`
- HTTP video stream if OpenCV can open it

Recommended command for system integration:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\infer_fall.py --mode video --source "rtsp://user:password@camera/stream" --event-log .\outputs\camera_events.jsonl --snapshot-dir .\outputs\camera_snapshots --save-path .\outputs\camera_review.mp4 --no-display
```

`--event-log` writes JSONL records. Each line contains:

- `event_type`: `state_changed`, `fall_confirmed`, or `status`
- `track_id`
- `bbox`
- `state`
- `severity`
- `fall_score`
- branch scores
- `injury.level`
- `injury.reason`
- `injury.advice`
- `snapshot_path`

This is the intended interface for an upper-layer project system. The system can tail this JSONL file, read one line at a time, and trigger UI warnings, notifications, or downstream LLM review.

### Current deployment stance

The default profile is tuned conservatively for private-camera use. It should avoid many sitting/bending false positives, but it must still be calibrated on the final camera view. For production use, collect several clips from the target camera:

- normal sitting
- bending
- lying down intentionally
- walking
- real or staged fall
- post-fall recovery
- limping or abnormal walking after a fall

Then re-run validation and adjust `configs/alert_rules.yaml`, `configs/injury_rules.yaml`, and `configs/model_registry.yaml`.

## Next implementation steps

1. Build `data_processed/fall_detect` from existing video frames and private camera footage.
2. Label or review YOLO boxes for `fall`, `fallen`, `lying`, `sitting`, `bending`, and `person`.
3. Train `yolo_fall_detector_v1`.
4. Enable the detector branch with a small weight.
5. Re-run held-out and private-scene validation.
6. Add event-level metrics: detection delay, false alarms per hour, recovery correctness.
7. Add backend/API and UI modules for permissions, model management, alert events, and user feedback.

## Recommended data priorities

The most valuable new private data is hard negatives:

- sit down
- lie down intentionally
- bend to pick up objects
- kneeling
- crawling
- exercising
- sleeping/resting on the floor
- partial body in frame
- camera shake

These clips reduce false alarms more than adding more easy fall videos.
