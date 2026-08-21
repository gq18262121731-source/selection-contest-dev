# Fall Detection Joint Calibration Plan (2026-05-04)

## Objective

Complete the final high-value calibration step for the camera fall-detection chain:

- add a balanced positive/negative replay pack
- verify that obvious staged falls still trigger
- verify that bend / sit / pick-up / empty-room clips do not trigger
- only then decide whether live thresholds should change

This plan is intentionally offline-first so we do not destabilize the live community/family/elder flows while tuning the model.

## Principles

1. Do not change live thresholds before replay evidence is available.
2. Public datasets are support data, not the final source of truth.
3. Private room-camera clips are the final authority for live rollout.
4. Positive and negative clips must be judged together.
5. Every threshold change must have a rollback path.

## Sample Strategy

### A. Private room-camera clips

These are mandatory because the deployed camera angle, lens distortion, lighting, partial-body framing, and room clutter differ from public benchmarks.

Minimum target pack:

- 2 staged fall clips
- 2 bend / pick-up clips
- 2 sit-down or lie-down transition clips
- 2 empty-room / routine-movement negatives

Recommended duration:

- 8 to 20 seconds each

Recommended framing:

- use the real deployed camera
- keep the same RTSP stream and resolution path used by live mode
- include edge-entry, partial-body, and occlusion cases

### B. Public support clips

These are useful to ensure the detector still fires on obvious falls even after we tighten thresholds.

Chosen public source:

- UR Fall Detection Dataset official page
  - https://fenix.ur.edu.pl/~mkepski/ds/uf.html

Implemented support:

- manifest: [ur_fall_cam0_small.json](D:/health1/data/fall_replay_benchmark/manifests/ur_fall_cam0_small.json:1)
- downloader: [download_fall_benchmark_assets.py](D:/health1/scripts/download_fall_benchmark_assets.py:1)

## Execution Plan

### Phase 1. Lock current live baseline

Keep current live values:

- `FALL_DETECTION_PROFILE=private_scene_fusion_v2`
- `FALL_DETECTION_THRESHOLD_OVERRIDE=0.65`
- `FALL_DETECTION_PROCESS_EVERY_OVERRIDE=2`

Reason:

- this baseline has already passed a room negative smoke run with zero events

### Phase 2. Build the replay pack

1. Record private room negatives and positives
2. Download the small UR public support pack
3. Store all sources under:
   - `data/fall_replay_benchmark/inputs`
   - `data/fall_replay_benchmark/public`
4. Maintain a manifest file for traceability

Implemented helper:

- [joint_calibration_manifest.example.json](D:/health1/data/fall_replay_benchmark/manifests/joint_calibration_manifest.example.json:1)

### Phase 3. Run the comparison matrix

Run the same pack across:

- `private_scene_fusion_v2`
- `public_fusion_v2`
- thresholds `0.65`, `0.70`
- process stride `2`

Only widen the matrix after the first pack is stable.

### Phase 4. Score pass/fail

Positive clips should:

- produce at least one `fall_confirmed` or confirmed high-risk equivalent

Negative clips should:

- produce zero `fall_confirmed`
- ideally zero `suspected_fall`

Tie-break rule:

- prefer the highest threshold that still preserves positive detection

### Phase 5. Live rollout

Only apply a new live config when:

- all negative room clips are clean
- staged room falls still confirm
- public support falls still confirm

After rollout:

1. restart backend fall worker
2. observe live event log for 15 to 30 minutes
3. confirm no login-time false popup residue
4. confirm family-side push dispatch still carries `elder_id` and `family_ids`

## What Was Implemented Today

1. Public dataset manifest support
2. Public dataset downloader script
3. Camera fall-alert user-context mapping for push dispatch
4. A real room negative clip recorded from the current camera stream:
   - `live_room_negative_20260504.mp4`
5. A first matrix run on that room negative clip
6. A downloaded public support pack from the official UR Fall dataset:
   - `fall-01-cam0.mp4`
   - `fall-05-cam0.mp4`
   - `adl-01-cam0.mp4`
   - `adl-10-cam0.mp4`

## First Calibration Result

Run directory:

- [20260504_112330/report.md](D:/health1/data/fall_replay_benchmark/20260504_112330/report.md:1)

Tested matrix:

- `private_scene_fusion_v2`, threshold `0.65`, stride `2`
- `private_scene_fusion_v2`, threshold `0.70`, stride `2`
- `public_fusion_v2`, threshold `0.65`, stride `2`
- `public_fusion_v2`, threshold `0.70`, stride `2`

Observed:

- all 4 combinations produced `0` events on the recorded room negative clip

Current recommendation:

- keep the live baseline unchanged until positive room-fall clips are added

## Joint Public/Private Replay Result

Run directories:

- [20260504_113337/report.md](D:/health1/data/fall_replay_benchmark/20260504_113337/report.md:1)
- [20260504_113518/report.md](D:/health1/data/fall_replay_benchmark/20260504_113518/report.md:1)

Observed with `private_scene_fusion_v2`, `process_every=2`:

- at `threshold=0.65`
  - `fall-01-cam0`: confirmed
  - `fall-05-cam0`: confirmed
  - `adl-01-cam0`: no confirmed fall
  - `adl-10-cam0`: false confirmed fall
  - `live_room_negative_20260504`: clean
- at `threshold=0.70`
  - `fall-01-cam0`: confirmed
  - `fall-05-cam0`: confirmed
  - `adl-01-cam0`: no confirmed fall
  - `adl-10-cam0`: false confirmed fall still present
  - `live_room_negative_20260504`: clean

Interpretation:

- raising only the global threshold from `0.65` to `0.70` does not remove the `adl-10` false positive
- the confirmed false positive is dominated by posture-driven evidence, so threshold-only tuning is not enough
- the next high-value step is not "keep raising threshold"
- the next high-value step is to add private bend / sit / pick-up clips and then compare:
  - current profile
  - alternative profile
  - room-specific alert rules

## Second-Round Partial Replay Result

Run directory:

- [20260504_115036/report.md](D:/health1/data/fall_replay_benchmark/20260504_115036/report.md:1)

Newly added private room positive:

- `room_fall_user_01.mp4`
  - copied into the workspace as:
    - `data/fall_replay_benchmark/inputs/room_fall_user_01.mp4`
  - measured properties:
    - resolution `1280x720`
    - frame rate `30 FPS`
    - duration `8.23s`

Compared candidates:

- `private_scene_fusion_v2`
- thresholds:
  - `0.65`
  - `0.70`
- default rules:
  - `D:\Program\model\fall_detection\configs\alert_rules.yaml`
  - `D:\Program\model\fall_detection\configs\injury_rules.yaml`
- room rules:
  - `D:\health1\configs\fall_detection\room_camera_alert_rules.yaml`
  - `D:\health1\configs\fall_detection\room_camera_injury_rules.yaml`

Observed:

- the new private room positive confirms under all tested combinations
- the room empty negative remains clean under all tested combinations
- default rules still keep:
  - `ur_adl_01` at `0 confirmed`
  - `ur_adl_10` at `1 confirmed`
- room rules make the public negatives materially worse:
  - `ur_adl_01` rises to `5 confirmed`
  - `ur_adl_10` rises to `4 confirmed`

Interpretation:

- the private room positive proves the detector can fire on the deployed camera domain
- the current room-specific rule pack is not safe for rollout
- the room rule pack amplifies posture-driven confirmations instead of suppressing them
- this means the next safe comparison is:
  - keep default rules as baseline
  - add more private negative room clips
  - only then compare profile changes or a revised room rule pack

Current live recommendation:

- do not change the live threshold
- do not enable `room_camera_alert_rules.yaml` in live mode
- keep:
  - `FALL_DETECTION_PROFILE=private_scene_fusion_v2`
  - `FALL_DETECTION_THRESHOLD_OVERRIDE=0.65`
  - `FALL_DETECTION_PROCESS_EVERY_OVERRIDE=2`

## Second-Round Available-Pack Full Matrix

Run directory:

- [20260504_121253/report.md](D:/health1/data/fall_replay_benchmark/20260504_121253/report.md:1)

Manifest:

- [joint_calibration_round2_available_20260504.json](D:/health1/data/fall_replay_benchmark/manifests/joint_calibration_round2_available_20260504.json:1)

Compared candidates:

- profiles:
  - `private_scene_fusion_v2`
  - `public_fusion_v2`
- thresholds:
  - `0.65`
  - `0.70`
- rules:
  - default alert and injury rules only

Observed:

- both profiles keep the current private room positive clip at:
  - `1 confirmed`
  - `5 suspected`
  - `2 post_fall`
- both profiles keep the room empty negative clip completely clean
- both profiles keep the two UR public positive clips confirmed
- both profiles keep `ur_adl_01` at:
  - `0 confirmed`
  - `9 suspected`
- both profiles still false-confirm `ur_adl_10`:
  - `1 confirmed`
  - `11 suspected`
- changing `0.65 -> 0.70` does not materially change the decision outcome

Profile interpretation:

- `public_fusion_v2` lowers score intensity on the negative support clips:
  - `ur_adl_01` max score drops from `0.371` to `0.279`
  - `ur_adl_10` max score drops from `0.527` to `0.468` at `threshold=0.65`
- however, that score reduction is not enough to remove the `ur_adl_10` false confirmation
- `private_scene_fusion_v2` remains the safer live baseline because:
  - it already matches the deployed camera domain
  - it preserves the current room positive clip
  - it does not regress the room empty negative

Current recommendation after the full matrix:

- keep live unchanged for now
- do not switch to `public_fusion_v2` yet
- keep `public_fusion_v2` as the first candidate for the next round after more private negatives are recorded
- prioritize collecting these private negatives next:
  - bend / pick-up
  - sit-down fast
  - controlled lie-down
  - edge-entry partial body
  - normal walkthrough

## Safe Next Step

The next operational step should be:

1. keep the already captured private room fall clip
2. add the missing private negatives:
   - bend / pick-up
   - sit-down fast
   - controlled lie-down
   - edge-entry partial body
   - normal walkthrough
3. add one more private room fall from a different direction
4. rerun the joint matrix with default rules as the baseline
5. compare profile changes only after the private negative pack is complete
