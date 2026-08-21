# Elder Fall Detection Execution Plan

Generated: 2026-05-06

## 2026-05-06 Implementation Update

Completed in this execution round:

- Added optional Ultralytics pose tracking via `--pose-tracker none|botsort|bytetrack`.
- Installed the `lap` dependency required by Ultralytics BoT-SORT / ByteTrack in `C:\Users\YANG\.conda\envs\AI`.
- Built v2 recall dataset:
  - `D:\Program\model\fall_detection\data_processed\fall_detect_v2_recall`
  - train images: 3,406
  - val images: 1,014
  - test images: 3,512
  - total labels:
    - person: 3,985
    - fall: 816
    - fallen: 803
    - sitting: 1,322
    - lying: 390
    - bending: 40
- Added v2 dataset config:
  - `D:\Program\model\fall_detection\configs\fall_detect_v2_recall_dataset.yaml`
- Trained a first detector v2 probe:
  - `D:\Program\model\fall_detection\runs\yolo_fall_detector_v2_recall_probe\weights\best.pt`

Runtime replay comparison on `C:\Users\YANG\Videos\Captures\跌倒.mp4`:

| Runtime | Verdict | Events | Confirmed | Detector max |
| --- | --- | ---: | ---: | ---: |
| patched default tracker + v1 detector | PASS | 15 | 1 | 0.279 |
| BoT-SORT + v1 detector | PASS | 11 | 2 | 0.316 |
| BoT-SORT + v2 detector probe | PASS | 9 | 2 | 0.000 |

Current interpretation:

- BoT-SORT improves this clip by producing 2 confirmed events and fewer total event fragments.
- v2 detector improves offline metrics but does not help this specific local clip's detector branch yet.
- This means the next high-value work is hard-negative evaluation and detector threshold/label tuning, not blindly promoting v2.

Detector v1 val baseline:

- precision: 0.397
- recall: 0.662
- mAP50: 0.487
- mAP50-95: 0.332

Detector v2 probe val on v2 dataset:

- precision: 0.480
- recall: 0.684
- mAP50: 0.532
- mAP50-95: 0.422

Known risks:

- `bending` labels are still scarce and currently not represented in train/val strongly enough.
- v2 improves `lying`, which is useful, but it increases the need for normal lie-down/sleep negative replay.
- No detector should be promoted until it passes hard-negative videos.

## Immediate Findings

- The current fall pipeline is usable but underuses the detector branch.
- `yolo_fall_detector_v1.pt` sees `fallen` frames in the local fall clip, but its boxes often do not overlap pose-track boxes.
- The runtime fusion has been patched to use expanded-box affinity and detector-only tracks.
- Verification on `C:\Users\YANG\Videos\Captures\跌倒.mp4` remains `PASS`.
- Detector branch now appears in event summaries with `detector` max score `0.279`, instead of `0.0`.

## Current Data Assets

From `scripts/audit_fall_data_assets.py`:

- Public videos: 220
- Public images: 77,236
- Pose-cache videos: 220
- YOLO fall-detect images: 2,840
- YOLO fall-detect labels:
  - person: 1,318
  - fall: 299
  - fallen: 348
  - sitting: 590
  - lying: 190
  - bending: 27

This is enough for a v2 detector training run, but not enough for product-grade elderly deployment.

## Baseline Detector Metrics

Command:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe scripts\evaluate_yolo_detect.py `
  --weights D:\Program\model\fall_detection\weights\yolo_fall_detector_v1.pt `
  --split val `
  --name yolo_fall_detector_v1_val_eval_after_fusion_plan `
  --output reports\yolo_fall_detector_v1_val_eval.json
```

Result:

- Overall precision: 0.397
- Overall recall: 0.662
- mAP50: 0.487
- mAP50-95: 0.332
- `fall` precision: 0.177
- `fall` recall: 0.694
- `fallen` precision: 0.491
- `fallen` recall: 0.559
- `lying` recall: 0.208

Interpretation: recall is only moderate and precision is weak, so detector retraining is necessary.

## Phase 1 Runtime Fixes

Completed:

- Added expanded-box detector/track affinity.
- Added horizontal-overlap and near-feet matching.
- Added detector-only tracks when pose tracking misses the fallen body.
- Added detector-only scoring floor for repeated detector hits.

Next:

- Tune detector-only confirmation rules on a positive/negative replay pack.
- Add a debug event type for detector-only candidates.
- Add track merge logic so detector-only tracks can merge back into pose tracks.
- Make BoT-SORT the default only after negative replay validates false alarm behavior.

## Phase 2 Dataset Work

Use current local data first:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe scripts\audit_fall_data_assets.py
```

Rebuild a higher-recall detector dataset:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe scripts\build_yolo_fall_detect_dataset.py `
  --frame-step 2 `
  --max-frames-per-video 120 `
  --output-dir D:\Program\model\fall_detection\data_processed\fall_detect_v2_recall
```

Needed data additions:

- More bending and kneeling negatives.
- More elderly-specific falls:
  - chair slip
  - bed-edge slip
  - slow collapse
  - side fall
  - half-body/edge fall
  - occluded fall
  - low-light fall

Do not train on random Bilibili/downloaded videos unless licensing and consent are clear. Use video platforms for failure-mode research and authorized test clips only.

## Phase 3 Detector v2 Training

Recommended first run:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe scripts\train_yolo_fall_detector.py `
  --data D:\Program\model\fall_detection\configs\fall_detect_dataset.yaml `
  --model yolo11s.pt `
  --epochs 120 `
  --batch 16 `
  --name yolo_fall_detector_v2_recall
```

Then evaluate:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe scripts\evaluate_yolo_detect.py `
  --weights D:\Program\model\fall_detection\runs\yolo_fall_detector_v2_recall\weights\best.pt `
  --split val `
  --name yolo_fall_detector_v2_recall_val_eval `
  --output reports\yolo_fall_detector_v2_recall_val_eval.json
```

Promotion gate:

- Overall recall >= 0.78
- `fallen` recall >= 0.75
- `fall + fallen` precision does not regress below 0.45
- No confirmed fall false positive on hard-negative replay clips.

## Phase 4 Benchmark Pack

Create a manifest with:

- all known positive fall clips
- sit-down negatives
- lie-down negatives
- bend/pickup negatives
- kneeling negatives
- edge/partial-body negatives
- empty/furniture-only negatives

Every model change must run:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe D:\Program\410health_new\health1\scripts\verify_fall_detection_video.py `
  --source C:\Users\YANG\Videos\Captures\跌倒.mp4 `
  --device 0
```

And the replay benchmark on the full manifest.

## Long-Term Differentiation

The product should outperform generic fall detectors by combining:

- detector branch for lying/fallen visibility
- pose temporal branch for transition dynamics
- post-fall immobility state machine
- wearable SOS/IMU confirmation
- per-room calibration
- per-elder baseline behavior
- injury-risk grading
- active learning from every false alarm and missed event
