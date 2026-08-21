# Fall Detection Benchmark Rollout Plan

## Goal

Turn the current camera fall-alert path into a stable demo loop:

1. The UI only pops up and rings for newly detected fall events.
2. The backend rejects obvious partial-body and edge-fragment false positives.
3. We gather a repeatable local replay pack.
4. We compare multiple model/runtime configurations against the same clips.
5. We promote the winning configuration into live mode.

## Execution Plan

### Phase 1. Stop false login popups

- Keep active alarms in the system, but do not replay old fall overlays on every login.
- Only present full-screen fall overlay and alarm audio for fall incidents that are new in the current session.
- Keep SOS behavior unchanged.

### Phase 2. Harden fall-event admission

- Reject partial-body events touching the top or bottom frame edge unless detector support is present.
- Preserve high-confidence full-body events.
- Keep demo/simulated events fail-open so internal testing flows still work.

### Phase 3. Build local replay inventory

- Scan likely local roots for benchmark clips:
  - project folder
  - external model folder
  - user Videos / Downloads / Desktop
- Rank likely useful clips by filename keywords such as `fall`, `camera`, `screen`, `record`, `test`.
- Save a machine-readable inventory report.

### Phase 4. Run first replay matrix

- Candidate first-pass matrix:
  - profiles: `private_scene_fusion_v2`, `public_fusion_v2`
  - thresholds: `0.60`, `0.65`, `0.70`
  - process-every: `1`, `2`
  - rule files: default vs `room_camera_*`
- Evaluate:
  - `confirmed_count`
  - `suspected_count`
  - `post_fall_count`
  - branch dominance
  - whether false partial-body sequences still confirm

### Phase 5. Promote the winner to live mode

- Write the selected values to `.env`
- Restart backend fall-detection worker
- Verify:
  - no popup on login without a new fall
  - live camera still streams
  - a simulated fall still reaches popup/audio

## Acceptance Criteria

- Logging into the dashboard does not replay stale fall popups from earlier sessions.
- The current observed “partial head at frame bottom” false positive no longer becomes an active fall alarm.
- A replay inventory report exists under `data/fall_replay_benchmark/inputs/`.
- The replay tool can compare multiple profiles and thresholds in one run.
- We can name a concrete live configuration to keep or reject after the first matrix run.
