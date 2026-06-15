# Fall Detection V3 Replacement Gate

Generated: 2026-05-18T12:26:33.142987+00:00

Promotable now: `false`

## Decision

V3 is **not safe to promote as a full replacement yet**. The current production detector/profile must remain active.

## Evidence

- Positive replay runs: 15
- Negative/hard-negative replay runs: 15
- Any positive confirmed: False
- Any negative confirmed: True
- V3 detector exists: True
- Detector decision: blocked_from_promotion_until_metrics_exceed_baseline

## Required Before Replacement

- YOLO26 detector validation metrics must match or exceed baseline detector.
- At least one positive private-scene replay must reach confirmed_fall.
- Hard-negative private-scene replay must have zero confirmed_fall.
- Run on CUDA or equivalent accelerator for full training, not CPU probe only.
- Add authorized scene videos for bedroom/living_room/corridor/bathroom categories.

## Safe Current Action

Keep `FALL_DETECTION_PROFILE=private_scene_fusion_v2` for production. Use V3 only in replay/shadow mode until these gates pass.
