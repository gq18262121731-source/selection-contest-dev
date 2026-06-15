# Next Phase Plan: Hard-Negative Evaluation and Data Expansion

Generated: 2026-05-06

## Goal

Move from single-clip validation to a product-grade evaluation loop:

- Positive falls must confirm reliably.
- Hard negatives such as sleeping, lying down, sitting down, walking, picking objects, bending, and occlusion must not produce confirmed fall alarms.
- Every false negative and false positive should become a training or rules-tuning item.

## Research Notes

Useful datasets and methods for the next phase:

- GMDCSA-24: strong next-phase source because it includes household scenes, fall-like ADL, occlusion, low resolution, different lighting, sleep, picking objects, and similar videos. Use it first for hard-negative replay and detector/temporal tuning.
- URFD: useful cross-dataset benchmark. Smoke replay already found one false negative: `fall-01-cam1.mp4` produced only `suspected_fall`, not `fall_confirmed`.
- UP-Fall: useful for future multimodal camera + wearable fusion.
- OmniFall: useful for broad non-commercial benchmark coverage; do not treat it as commercial training data without license review.
- Ultralytics BoT-SORT / ByteTrack: already integrated through `--pose-tracker`; BoT-SORT improved the local clip from 1 confirmed event to 2 confirmed events.
- MMAction2 / skeleton action recognition: next model-family candidate for improving transition-level action classification after the detector and replay loop are stable.

## Implemented Tooling

Added:

- `D:\Program\410health_new\health1\scripts\build_fall_replay_manifest.py`
- `D:\Program\410health_new\health1\scripts\run_fall_replay_manifest.py`

Generated manifest:

- `D:\Program\model\fall_detection\reports\fall_replay_manifest_hard_negative_v1.json`
- Total clips: 38
- Positive: 13
- Negative: 25

Smoke run:

- Summary: `D:\Program\410health_new\health1\data\fall_replay_manifest_runs\20260506_130402\manifest_replay_summary.json`
- Clips: 6 positives
- Passed: 5
- Failed: 1
- Failure: `urfd_fall_video_005`, source `fall-01-cam1.mp4`
- Observed issue: posture and detector produced suspicion, but temporal branches were `0.0`, so state did not confirm.

## Immediate Commands

Build manifest:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe D:\Program\410health_new\health1\scripts\build_fall_replay_manifest.py `
  --include-private-fall `
  --limit-positive-per-label 4 `
  --limit-negative-per-label 3 `
  --output D:\Program\model\fall_detection\reports\fall_replay_manifest_hard_negative_v1.json
```

Run full replay:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe D:\Program\410health_new\health1\scripts\run_fall_replay_manifest.py `
  --manifest D:\Program\model\fall_detection\reports\fall_replay_manifest_hard_negative_v1.json `
  --pose-tracker botsort `
  --device 0 `
  --timeout-seconds 900
```

Run v2 detector replay:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe D:\Program\410health_new\health1\scripts\run_fall_replay_manifest.py `
  --manifest D:\Program\model\fall_detection\reports\fall_replay_manifest_hard_negative_v1.json `
  --pose-tracker botsort `
  --fall-detector D:\Program\model\fall_detection\runs\yolo_fall_detector_v2_recall_probe\weights\best.pt `
  --device 0 `
  --timeout-seconds 900
```

## Next Engineering Tasks

1. Run the full 38-clip replay manifest.
2. Split failures into:
   - false negative positives
   - confirmed false alarms on negatives
   - suspected-only negatives
   - track fragmentation issues
3. Fix URFD false negative path:
   - current failure has `posture` max `0.786` and `detector` max `0.344`, but temporal scores are `0.0`.
   - add a low-confidence confirmation route for cross-dataset detector/posture agreement:
     - if `posture >= 0.70` and `detector >= 0.30` persists for N frames, confirm only if the track remains downed or immobile.
   - validate this against lying/sleep negatives before promotion.
4. Add detector-only candidate debug events:
   - event type `detector_candidate`
   - include detector score, affinity, label, and track id
5. Improve the dataset:
   - `bending` remains only 40 labels, too sparse.
   - add/label more bending, kneeling, sitting-down, lying-down, and sleep negatives.
6. Train detector v2 full:
   - current v2 probe improves offline metrics but does not help the local detector branch enough.
   - next run should add bending negatives and tune detector confidence thresholds.

## Promotion Gates

BoT-SORT can become the default only if:

- full positive confirmation rate >= current default
- confirmed false positives on negative clips = 0
- event count does not explode

Detector v2 can replace v1 only if:

- full replay improves or matches positive confirmations
- negative confirmed false alarms do not increase
- `fall/fallen` recall improves on a fixed val/test set
- lying/sleep negatives do not regress

## Data Policy

Do not train on random Bilibili or video-platform clips unless there is explicit authorization. Use web videos only for:

- qualitative failure-mode research
- inspiration for staged self-collection scripts
- authorized evaluation clips

Training data should come from:

- public datasets with reviewed licenses
- self-collected authorized elder-care scenes
- user-provided clips explicitly approved for model improvement
