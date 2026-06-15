# Private Room Fall Shooting Script (2026-05-04)

## Goal

Record a small but high-value private replay pack from the real deployed camera so the second joint calibration round can answer:

- Will true falls still confirm?
- Will bend / sit / lie / edge-entry stop producing false alarms?
- Which profile or rule set is safest for live rollout?

## Global Rules

- Use the real deployed camera and the same live stream path used by the system.
- Do not crop, trim, zoom, or edit the videos.
- Keep the camera fixed during the whole capture session.
- Prefer `.mp4`.
- Each clip should be 8 to 20 seconds.
- Leave 2 to 3 seconds of standing or neutral scene before the main action.
- Leave 2 to 5 seconds after the action completes.
- Only one main person in frame unless the clip explicitly tests clutter.

## File Naming

Store all files under:

- `data/fall_replay_benchmark/inputs`

Recommended names:

1. `room_fall_user_01.mp4`
2. `room_fall_side_02.mp4`
3. `room_bend_pickup_01.mp4`
4. `room_bend_pickup_02.mp4`
5. `room_sit_down_fast_01.mp4`
6. `room_lie_down_controlled_01.mp4`
7. `room_edge_entry_partial_01.mp4`
8. `room_walkthrough_01.mp4`
9. `room_empty_negative_01.mp4`

## Current Progress

Already available:

- `room_fall_user_01.mp4`
  - user-provided private room fall clip
  - copied into:
    - `data/fall_replay_benchmark/inputs/room_fall_user_01.mp4`
- `live_room_negative_20260504.mp4`
  - recorded room empty negative clip

Still needed for the complete private pack:

- `room_fall_side_02.mp4`
- `room_bend_pickup_01.mp4`
- `room_bend_pickup_02.mp4`
- `room_sit_down_fast_01.mp4`
- `room_lie_down_controlled_01.mp4`
- `room_edge_entry_partial_01.mp4`
- `room_walkthrough_01.mp4`
- `room_empty_negative_01.mp4`

## Capture Script

### Positive clips

#### 1. `room_fall_user_01.mp4`

Status:

- already captured
- use this as the first positive baseline clip

Action:

- no further action needed unless you want to replace it with a cleaner take

Pass condition:

- file opens correctly
- body transition from upright to down is visible
- clip remains unedited

#### 2. `room_fall_side_02.mp4`

Action:

- Stand near the usual monitored area, but choose a different starting angle than `room_fall_user_01.mp4`.
- Walk 1 to 2 steps.
- Perform a controlled sideways fall.
- Stay down for 3 to 5 seconds.

Pass condition:

- Fall direction differs from `room_fall_user_01.mp4`
- Camera still sees the full transition from upright to down

### Negative clips

#### 3. `room_bend_pickup_01.mp4`

Action:

- Walk into the center zone.
- Bend fully and pick up an object from the floor.
- Return to standing.

Pass condition:

- Motion looks like a realistic daily action, not a staged half bend

#### 4. `room_bend_pickup_02.mp4`

Action:

- Repeat the same class of motion, but from a slightly different position or facing direction.

Pass condition:

- Different body orientation than clip 3

#### 5. `room_sit_down_fast_01.mp4`

Action:

- Sit down quickly on a chair or bed edge.
- Remain seated.

Pass condition:

- Transition is brisk enough that a weak model might confuse it with a fall

#### 6. `room_lie_down_controlled_01.mp4`

Action:

- Move from standing or sitting into a controlled lie-down on bed or floor.
- Do not collapse.

Pass condition:

- Slow, intentional posture change

#### 7. `room_edge_entry_partial_01.mp4`

Action:

- Enter and leave near the bottom or side edge so only part of the body is visible for part of the clip.

Pass condition:

- This should reproduce the partial-body pattern that often causes false positives

#### 8. `room_walkthrough_01.mp4`

Action:

- Normal walking through the room with no unusual posture

Pass condition:

- Natural pace, no stopping to pose

#### 9. `room_empty_negative_01.mp4`

Action:

- Keep the room empty or only with background clutter for 10 to 15 seconds

Pass condition:

- No person in frame

## Optional Stress Clips

If you want a stronger third round later, add:

- `room_crouch_recover_01.mp4`
- `room_two_people_cross_01.mp4`
- `room_occlusion_fall_like_01.mp4`
- `room_robot_or_screen_interference_01.mp4`

## Immediate Post-Capture Checklist

For every recorded file, confirm:

- file opens normally
- duration is at least 8 seconds
- the intended action is clearly visible
- no editing was applied
- filename matches the action

## Second-Round Benchmark Command

```powershell
C:\Users\Test1\.conda\envs\health\python.exe scripts\fall_detection_replay_benchmark.py `
  --source room_fall_user_01=data/fall_replay_benchmark/inputs/room_fall_user_01.mp4 `
  --source room_fall_side_02=data/fall_replay_benchmark/inputs/room_fall_side_02.mp4 `
  --source room_bend_pickup_01=data/fall_replay_benchmark/inputs/room_bend_pickup_01.mp4 `
  --source room_bend_pickup_02=data/fall_replay_benchmark/inputs/room_bend_pickup_02.mp4 `
  --source room_sit_down_fast_01=data/fall_replay_benchmark/inputs/room_sit_down_fast_01.mp4 `
  --source room_lie_down_controlled_01=data/fall_replay_benchmark/inputs/room_lie_down_controlled_01.mp4 `
  --source room_edge_entry_partial_01=data/fall_replay_benchmark/inputs/room_edge_entry_partial_01.mp4 `
  --source room_walkthrough_01=data/fall_replay_benchmark/inputs/room_walkthrough_01.mp4 `
  --source room_empty_negative_01=data/fall_replay_benchmark/inputs/room_empty_negative_01.mp4 `
  --source ur_fall_01=data/fall_replay_benchmark/public/ur_fall_cam0_small/fall-01-cam0.mp4 `
  --source ur_fall_05=data/fall_replay_benchmark/public/ur_fall_cam0_small/fall-05-cam0.mp4 `
  --source ur_adl_01=data/fall_replay_benchmark/public/ur_fall_cam0_small/adl-01-cam0.mp4 `
  --source ur_adl_10=data/fall_replay_benchmark/public/ur_fall_cam0_small/adl-10-cam0.mp4 `
  --profile private_scene_fusion_v2 `
  --profile public_fusion_v2 `
  --threshold 0.65 `
  --threshold 0.70 `
  --process-every 2 `
  --alert-rules D:\Program\model\fall_detection\configs\alert_rules.yaml `
  --alert-rules D:\health1\configs\fall_detection\room_camera_alert_rules.yaml `
  --injury-rules D:\Program\model\fall_detection\configs\injury_rules.yaml `
  --injury-rules D:\health1\configs\fall_detection\room_camera_injury_rules.yaml
```

## Decision Rule After Round Two

- If room negatives are clean and room positives still confirm:
  - the candidate is acceptable for live rollout
- If public positives confirm but room positives fail:
  - domain mismatch still exists, do not ship the config
- If room negatives still confirm falsely:
  - prioritize room-specific alert rules before raising threshold again
