# Fall Detection Replay Benchmark

This project now includes a reproducible offline replay tool:

- Script: [scripts/fall_detection_replay_benchmark.py](D:/health1/scripts/fall_detection_replay_benchmark.py)

It runs the external fall-detection model directly on local video files, stores the raw JSONL event log, and generates both:

- `summary.json`
- `report.md`

under a timestamped output folder like:

- `data/fall_replay_benchmark/20260503_120000/`

## Why this matters

Live camera testing is useful, but it is hard to compare changes fairly. Replay benchmarking lets us:

- replay the same clip after every threshold or logic change
- separate model weakness from camera-playback/domain-shift issues
- count `suspected_fall`, `fall_confirmed`, and `post_fall_monitoring` consistently
- inspect which score branch dominated each alert (`gru`, `hybrid`, `semantic`, `posture`, `detector`)

## Usage

Single clip:

```powershell
C:\Users\Test1\.conda\envs\health\python.exe scripts/fall_detection_replay_benchmark.py `
  --source direct=D:\clips\fall_case_01.mp4
```

A/B comparison:

```powershell
C:\Users\Test1\.conda\envs\health\python.exe scripts/fall_detection_replay_benchmark.py `
  --source direct=D:\clips\fall_case_01.mp4 `
  --source camera_playback=D:\clips\screen_recording_from_room_camera.mp4
```

Custom inference stride:

```powershell
C:\Users\Test1\.conda\envs\health\python.exe scripts/fall_detection_replay_benchmark.py `
  --source direct=D:\clips\fall_case_01.mp4 `
  --process-every 2
```

Matrix comparison across profiles and thresholds:

```powershell
C:\Users\Test1\.conda\envs\health\python.exe scripts/fall_detection_replay_benchmark.py `
  --source direct=D:\clips\fall_case_01.mp4 `
  --source negative=D:\clips\bend_pickup_01.mp4 `
  --profile private_scene_fusion_v2 `
  --profile public_fusion_v2 `
  --threshold 0.55 `
  --threshold 0.65 `
  --process-every 1 `
  --process-every 2
```

Compare external rule files:

```powershell
C:\Users\Test1\.conda\envs\health\python.exe scripts/fall_detection_replay_benchmark.py `
  --source direct=D:\clips\fall_case_01.mp4 `
  --alert-rules D:\Program\model\fall_detection\configs\alert_rules.yaml `
  --alert-rules D:\health1\configs\fall_detection\room_camera_alert_rules.yaml
```

Keep alert snapshots:

```powershell
C:\Users\Test1\.conda\envs\health\python.exe scripts/fall_detection_replay_benchmark.py `
  --source direct=D:\clips\fall_case_01.mp4 `
  --keep-snapshots
```

## What to compare

For every clip, watch these fields first:

- `confirmed_count`
- `suspected_count`
- `post_fall_count`
- `unique_track_count`
- `dominant_branch_counts`
- `confirmed_branch_counts`

Good signs:

- true fall clips produce at least one `fall_confirmed`
- normal activity clips stay low on `suspected_fall`
- confirmed alerts are not dominated only by `posture`
- `unique_track_count` does not explode on edge fragments or clutter

Bad signs:

- many `suspected_fall` but no `fall_confirmed`
- repeated confirmed alerts on the same obvious non-fall sequence
- `posture` dominating almost every alert
- one short clip creating many fragmented tracks

## Recommended benchmark pack

Build a small local regression set with:

1. Real or staged falls
2. Sit-down and lie-down negatives
3. Bend / pick-up negatives
4. Crawl / get-up transitions
5. Edge-entry / partial-body negatives
6. Robot / furniture / screen-playback negatives from your actual room

## Suggested external datasets

These are useful when you want to expand beyond your private clips:

- OmniFall paper: https://arxiv.org/abs/2505.19889
- UR Fall Detection Dataset: https://fenix.ur.edu.pl/~mkepski/ds/uf.html
- UP-Fall Dataset paper: https://www.mdpi.com/1424-8220/19/9/1988
- Fall posture dataset: https://falldataset.com/

## Current workflow recommendation

After each fall-logic or threshold change:

1. Run the replay benchmark on the same fixed clip pack.
2. Compare `report.md` against the previous run.
3. Only keep a threshold change if:
   - true-fall clips still confirm,
   - normal-activity clips show fewer suspected/confirmed events,
   - branch dominance shifts away from posture-only alerts.

## Applying the winner to live mode

Once a replay run clearly wins, copy the chosen values into `.env`:

- `FALL_DETECTION_PROFILE`
- `FALL_DETECTION_THRESHOLD_OVERRIDE`
- `FALL_DETECTION_PROCESS_EVERY_OVERRIDE`
- `FALL_DETECTION_ALERT_RULES_PATH`
- `FALL_DETECTION_INJURY_RULES_PATH`

The backend fall-detection worker now forwards those values directly to the external model process, so the live camera path can use the same calibrated configuration you validated offline.
