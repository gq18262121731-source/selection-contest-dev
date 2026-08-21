# Fall Detection Self-Check Report

Date: `2026-04-30`

Scope:
- Verify whether the local fall-detection model is deployed and runnable.
- Verify whether the model is receiving live camera frames.
- Verify whether the model can emit fall-related events.
- Verify whether multimodal review is actually integrated into the live system.
- Verify whether confirmed fall events are converted into system alarms and front-end popups.
- Assess current model quality and define an improvement path, including retraining if needed.

## 1. Executive Summary

The current system is **partially working but not reliable enough for production fall warning**.

What is confirmed:
- The local fall-detection model bundle is present on disk and the online process is running.
- The model is receiving live frames from the camera relay.
- The model has already produced `fall_confirmed` events at least twice during this session.
- The front-end video card and backend video relay are both working now.

What is not working correctly:
- Real confirmed fall events are **not reliably appearing as active system alarms**.
- The live chain does **not** currently use the optional multimodal/VLM review module.
- The model shows obvious false positives, including:
  - misclassifying the robot in the room as a person-like target,
  - misclassifying image-edge fragments,
  - relying too heavily on posture risk in many cases.
- Most detections stop at `suspected_fall`; only a small fraction upgrade to `fall_confirmed`.

Bottom line:
- The system is **not in a “no model / no input” state**.
- The core problem is now a combination of:
  - unstable model behavior in the current scene,
  - missing live multimodal second-pass review,
  - and a backend event-to-alarm ingestion gap for real fall events.

## 2. Environment Checked

Project root:
- `D:\health1`

Model root:
- `D:\Program\model\fall_detection`

Key runtime endpoints:
- `http://127.0.0.1:8000/healthz`
- `http://127.0.0.1:8000/api/v1/camera/status`
- `http://127.0.0.1:8000/api/v1/camera/stream-status`
- `http://127.0.0.1:8000/api/v1/camera/fall-detection/status`
- `http://127.0.0.1:8000/api/v1/alarms`

## 3. What Was Verified

### 3.1 Model assets exist locally

Verified local files:
- `D:\Program\model\fall_detection\weights\gru_pose_fall_v1.pt`
- `D:\Program\model\fall_detection\weights\hybrid_tcn_transformer_private_real_v1.pt`
- `D:\Program\model\fall_detection\weights\semantic_mix_falldb_private_real_v1.pt`
- `D:\Program\model\fall_detection\weights\yolo_fall_detector_v1.pt`
- `D:\Program\model\fall_detection\runs\yolo_posture_person_binary_cls_v1\weights\best.pt`
- `D:\Program\model\fall_detection\yolo11n-pose.pt`

Conclusion:
- The local model bundle is present and complete enough to run online fall detection.

### 3.2 Live camera frames are reaching the model

Observed:
- `GET /api/v1/camera/stream-status` returned:
  - `running=true`
  - `active_url=rtsp://.../tcp/av0_1`
  - `source_fps≈14.5`
- `GET /api/v1/camera/fall-detection/status` returned:
  - `enabled=true`
  - `running=true`
  - `process_running=true`
- The active fall-detection process command line was:
  - `--source http://127.0.0.1:8000/api/v1/camera/stream.mjpg`

Evidence:
- The latest model events in `D:\health1\data\fall_events\camera_events.jsonl` show:
  - `"source": "http://127.0.0.1:8000/api/v1/camera/stream.mjpg"`

Conclusion:
- The model is not idle.
- The model is receiving backend-relayed live camera frames.

### 3.3 The model is capable of emitting fall events

Observed in `D:\health1\data\fall_events\camera_events.jsonl`:
- event totals:
  - `state_changed`: `54`
  - `fall_confirmed`: `2`
  - `status`: `3`

Confirmed fall events found:
- `track_id=8`, `fall_score≈0.5686`, `severity=L2`
- `track_id=18`, `fall_score≈0.7001`, `severity=L2`

Conclusion:
- The model does have real event-generation capability.
- This is not a “zero detection” pipeline.

### 3.4 The current live system is not actually using multimodal review

Observed:
- The optional multimodal script exists:
  - `D:\Program\model\fall_detection\scripts\llm_fall_review.py`
- The review config exists:
  - `D:\Program\model\fall_detection\configs\llm_review.yaml`
- The script requires:
  - `SILICONFLOW_API_KEY`
- Current environment check:
  - `SILICONFLOW_API_KEY_SET=False`
- Repo search did not show any live backend integration invoking `llm_fall_review.py` from the fall alarm path.

Conclusion:
- The current online warning chain is **not** using the optional multimodal/VLM review.
- The deployed live system is best described as:
  - a **multi-branch vision + temporal fusion model**,
  - **not** a true end-to-end multimodal fall review pipeline.

## 4. Key Findings

### 4.1 The model did recognize the “screen playback” test at least twice

Critical evidence:
- `D:\health1\data\fall_events\snapshots\track8_fall_confirmed_0000400840.jpg`
- `D:\health1\data\fall_events\snapshots\track18_fall_confirmed_0000412440.jpg`

Inspection result:
- Both confirmed-fall snapshots clearly show a fall video being displayed on a screen and then captured by the room camera.

Conclusion:
- The model can, at least sometimes, recognize the played fall video.
- Therefore the user-facing “system had no reaction” is **not explained by total model failure alone**.

### 4.2 The model also shows clear false positives

Critical evidence:
- `D:\health1\data\fall_events\snapshots\track46_state_changed_0000696440.jpg`
- `D:\health1\data\fall_events\snapshots\track29_state_changed_0000534120.jpg`

Inspection result:
- One snapshot shows the robot being boxed as a target.
- Another snapshot shows a large false region at the frame edge.

Conclusion:
- The current model is unstable in the real scene.
- It is vulnerable to:
  - non-human human-like objects,
  - truncated subjects,
  - edge fragments,
  - posture-only false alarms.

### 4.3 Most events remain at `suspected_fall`

Observed pattern from JSONL:
- Many detections have:
  - `gru=0`
  - `hybrid=0`
  - `semantic=0`
  - `posture` high
  - `detector=0`
- This means the system is often reacting mainly to static posture risk, not a convincing temporal fall transition.

Interpretation:
- Possible reasons:
  - tracked target is too small,
  - target is not stable long enough for temporal windows,
  - screen-playback geometry is very different from the training scene,
  - ROI / target scale / camera angle reduce temporal branch usefulness.

### 4.4 Real confirmed events are not reliably becoming active fall alarms

Observed:
- `camera_events.jsonl` contains `2` real `fall_confirmed` events.
- `GET /api/v1/alarms` only showed `1` fall alarm, and it was the **demo/simulated** alarm, already acknowledged.
- `GET /api/v1/alarms?active_only=true` showed **no active fall alarm**.

Important implication:
- There is a likely break or suppression in the chain:

`model event -> _handle_fall_detection_event -> AlarmService -> persisted alarm -> websocket -> popup`

Current evidence suggests:
- the event log tail is working,
- but the real online fall event is not reliably surviving to the active alarm list.

This is likely one of the direct reasons why the user saw:
- no warning popup,
- no persistent fall alarm in the UI.

## 5. Root Cause Assessment

### Root Cause A: The live chain is not truly multimodal

Severity: `High`

The current runtime does not automatically invoke the optional VLM review step. The model can only use its internal visual/temporal branches in the live path.

Impact:
- no second-pass confirmation for ambiguous cases,
- no semantic rejection of screen artifacts / robot / unusual scene context,
- no reliable “final reviewer” before user-facing escalation.

### Root Cause B: Real fall events are not reliably ingested as active alarms

Severity: `Critical`

Even when `fall_confirmed` appears in the model JSONL, the active alarm API does not reliably reflect it.

Impact:
- no popup,
- no stable operator-facing warning,
- apparent “system no reaction” even when the model did react.

### Root Cause C: The current scene adaptation is weak

Severity: `High`

The live scene contains:
- a service robot,
- clutter,
- truncated people at the frame edges,
- screen-playback testing instead of direct human falls.

The model shows:
- false positives on robot/edges,
- a heavy dependence on posture-only signals,
- sparse upgrades from `suspected_fall` to `fall_confirmed`.

Impact:
- unstable online behavior,
- low operator trust,
- missed or delayed escalation.

### Root Cause D: No local offline benchmark media was available for direct replay regression

Severity: `Medium`

The current machine does not have the public benchmark videos or the user’s exact test clip stored locally, so a full reproducible offline replay test against known videos could not be completed in this self-check pass.

Impact:
- online evidence is strong,
- but a clean “same clip offline vs via camera playback” A/B benchmark still needs to be added.

## 6. Current Capability Verdict

### Does the model currently have fall-detection capability?

Yes, but only partially reliable.

Reason:
- it emits `suspected_fall`,
- it has emitted `fall_confirmed`,
- it has injury grading logic,
- it has snapshot output.

However:
- it is not yet trustworthy enough as a production fall-warning system in the current scene.

### Is the current live deployment multimodal?

No, not in the strict sense expected by the user.

Current reality:
- live runtime uses a multi-branch computer-vision model,
- optional multimodal/VLM review exists only as a standalone script,
- no API key is configured,
- no automatic runtime hookup exists.

### Is the camera video being transmitted into the model?

Yes.

Verified by:
- running process source argument,
- event-log `source`,
- live stream status,
- active model process.

### Can the model successfully receive camera images and detect?

Yes, but with unstable quality.

It can:
- receive frames,
- emit events,
- sometimes confirm a fall.

It cannot yet be considered:
- robust,
- low-false-positive,
- or fully trustworthy for your real deployment scene.

## 7. Recommended Fix Plan

### Phase 1: Fix the event-to-alarm ingestion gap

Priority: `P0`

Actions:
- Add explicit logging inside `_handle_fall_detection_event()` for every accepted and rejected event.
- Log:
  - event type,
  - track id,
  - dedupe decision,
  - ROI decision,
  - score decision,
  - whether `AlarmService.evaluate_alarm_records()` returned an alarm.
- Add explicit logging in `AlarmService._upsert_alarm()` for:
  - fall cooldown suppression,
  - refresh suppression,
  - enqueue success.
- Verify that a real `fall_confirmed` event appears in:
  - `_handle_fall_detection_event`,
  - `_alarm_service._alarms`,
  - queue snapshot,
  - websocket broadcast.

Expected result:
- confirmed falls become real active alarms and can trigger the popup.

### Phase 2: Integrate the multimodal/VLM review for ambiguous or confirmed events

Priority: `P0`

Actions:
- Add `SILICONFLOW_API_KEY` securely to backend runtime configuration.
- Wire `llm_fall_review.py` into the live fall pipeline:
  - trigger on `suspected_fall`, `confirmed_fall`, `post_fall_monitoring`,
  - pass snapshot + detection context,
  - store returned judgement.
- Use VLM result to:
  - suppress obvious false alarms,
  - strengthen true falls,
  - enrich final severity/advice.

Recommended policy:
- if model says `suspected_fall` and VLM says `no_fall`, downgrade,
- if model says `confirmed_fall` and VLM says `real_fall`, keep/escalate,
- if VLM says `unclear`, keep observing and request more frames.

### Phase 3: Improve scene robustness before retraining

Priority: `P1`

Actions:
- Tighten ROI to exclude obvious clutter and edge regions.
- Add a minimum target-box size threshold.
- Add edge-margin rejection:
  - ignore targets truncated too heavily at frame borders.
- Add robot exclusion:
  - either via ignore zone,
  - or via human/robot discrimination rule before temporal scoring.
- Log which branch dominates each fall score to catch posture-only alarms.

Expected result:
- fewer robot and edge false positives,
- cleaner candidate tracks for temporal branches.

### Phase 4: Build a reproducible offline replay benchmark

Priority: `P1`

Actions:
- Save the user’s exact test clip locally.
- Run two A/B tests:
  - direct file -> model,
  - screen playback -> camera -> model.
- Measure:
  - `suspected_fall` count,
  - `fall_confirmed` count,
  - alarm generation,
  - popup generation,
  - false positives.

Expected result:
- clearly separate “model weakness” from “camera-playback domain shift”.

## 8. Retraining Recommendation

### When retraining is justified

Retraining is justified if either condition holds:
- the direct-file replay of your fall clip still fails or is unstable,
- or the model continues to false-positive on the current scene after the P0/P1 fixes.

### Recommended dataset strategy

Use a layered dataset strategy:

1. Public broad-coverage fall datasets
- OmniFall
- UR Fall Detection Dataset
- UP-Fall Detection Dataset
- falldataset.com posture data

2. Private scene adaptation data
- your actual room,
- your camera angle,
- your lighting,
- your robot,
- your furniture,
- your screen-playback tests,
- real human ADL negatives.

### Suggested public datasets

Verified sources:
- OmniFall paper: `https://arxiv.org/abs/2505.19889`
- UR Fall Detection Dataset: `https://fenix.ur.edu.pl/~mkepski/ds/uf.html`
- UP-Fall Detection Dataset: `https://www.mdpi.com/1424-8220/19/9/1988`
- Fall posture dataset: `https://falldataset.com/`

### Retraining roadmap

1. Build a private-scene dataset
- collect:
  - true falls,
  - fake falls,
  - sit-down,
  - lie-down intentionally,
  - bend / pick-up,
  - crawl,
  - stand-up after fall,
  - robot moving or static,
  - edge-entry / edge-exit people,
  - screen-playback clips.

2. Retrain the detector branch
- improve `weights/yolo_fall_detector_v1.pt`
- manually verify boxes for:
  - `fall`
  - `fallen`
  - `lying`
  - `sitting`
  - `bending`
  - `person`

3. Retrain temporal branches
- update:
  - `hybrid_tcn_transformer_private_real_v1.pt`
  - `semantic_mix_falldb_private_real_v1.pt`
- include the private scene in the training manifest.

4. Re-search fusion weights
- current private profile:
  - `gru=0.15`
  - `hybrid=0.45`
  - `semantic=0.00`
  - `posture=0.30`
  - `detector=0.10`
  - `threshold=0.65`
- after retraining, re-search the weights and threshold instead of keeping current defaults.

5. Reintroduce semantic branch carefully
- current semantic weight is `0.00`
- after private-scene retraining, test whether semantic fusion improves hard cases.

### “Excellent model” target

For this project, an excellent model should satisfy all of these:
- true falls are consistently promoted to `fall_confirmed`,
- screen-playback tests are either correctly handled or explicitly documented as unsupported,
- robot and edge false positives are rare,
- the alarm layer always receives and shows confirmed events,
- multimodal review reduces false alarms rather than adding latency without value,
- the final system is validated on your actual room and camera, not just public datasets.

## 9. Recommended Next Steps

Immediate next steps:
1. Instrument and fix real event -> alarm ingestion.
2. Integrate the optional VLM review into the live fall path.
3. Add scene filters for robot / edge / minimum box size.
4. Save and benchmark the exact user test clip offline.
5. Start private-scene adaptation and retraining if instability remains.

## 10. Final Assessment

Current system maturity:
- Video relay: `Working`
- Model runtime: `Working`
- Model event generation: `Working but unstable`
- Multimodal review: `Not integrated in live path`
- Real fall alarm ingestion: `Not reliable`
- Front-end popup for real fall alarms: `Blocked by upstream alarm gap`
- Scene robustness: `Not production-ready`

Final conclusion:
- The system is already beyond a prototype with “no model”.
- The main blocker is not camera transport anymore.
- The main blockers are:
  - missing live multimodal integration,
  - unreliable real-event alarm ingestion,
  - and insufficient scene adaptation / robustness.
