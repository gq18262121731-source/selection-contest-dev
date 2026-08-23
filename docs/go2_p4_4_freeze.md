# Go2 P4.4 Freeze Record

## Status

- Phase: `P4.4 Kine2Go calibrated Walk -> Blender Action -> GLB`
- Status: `DONE`
- State: `FROZEN`
- Frozen on: `2026-08-23`
- Next phase: `P4.5 Flutter animated GLB integration`

## Locked Calibration

```text
FR: 7, 11, 15
FL: 6, 10, 14
RR: 9, 13, 17
RL: 8, 12, 16
```

- Blender local rotation equals the Kine2Go absolute joint angle.
- Joint sign is `+1` for all 12 active joints.
- Walk source frames are `402-443`, producing 42 samples at 60 FPS.
- The last six samples use the verified Hermite loop transition.
- World X/Y motion and accumulated yaw are not applied.
- Idle uses the legal static Kine2Go standing pose.

## Acceptance

```text
WALK_ACTION: PASS
IDLE_ACTION: PASS
WALK_LOOP: PASS
JOINT_LIMIT: PASS
FOOT_CONTACT_VISUAL: PASS
MESH_COLLISION_VISUAL: PASS
GLB_EXPORT: PASS
GLB_ANIMATIONS: PASS
READY_FOR_FLUTTER: PASS
```

The exported GLB contains the named animations `Idle` and `Walk`. Four combined
phase views and eight isolated samples for each leg confirmed rigid Link
continuity. The previously reported detached joint was a far-side Thigh
occlusion in the old preview camera, not an FK or Mesh-parenting fault.

## Frozen Surfaces

P4.5 and later work must not modify the following without reopening P4.4 and
rerunning its calibration and visual acceptance:

- Kine2Go DOF column mapping
- Source cycle and loop transition
- 12DOF FK hierarchy
- Joint centers, axes, signs, and offsets
- Mesh parent assignments
- Idle and Walk source Actions

## Local Deliverables

- Blend: `C:\Users\13010\Downloads\Go2_kine2go_final_v1.blend`
- GLB: `C:\Users\13010\Downloads\go2_mobile_kine2go_v1.glb`
- Report: `reports/go2_kine2go_animation_report.json`
- Preview: `reports/go2_kine2go_preview/go2_kine2go_walk_preview.mp4`

P4.5 may copy the frozen GLB into Flutter assets and map application state to
`Idle` or `Walk`. It must not regenerate or reinterpret the Blender pipeline.
