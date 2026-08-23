# Go2 P4.5 Freeze Record

## Status

- Phase: `P4.5 Flutter animated GLB integration`
- Status: `DONE`
- State: `FROZEN`
- Frozen on: `2026-08-23`
- Ready for demo: `PASS`
- Next phase: `P5 real Go2 status integration`

## Frozen Asset

- Repository asset: `mobile/flutter_app/assets/models/go2/go2_mobile.glb`
- Flutter asset path: `assets/models/go2/go2_mobile.glb`
- Source frozen GLB: `C:\Users\13010\Downloads\go2_mobile_kine2go_v1.glb`
- Size: `43,258,296` bytes
- SHA-256: `3F67CC92218347FC3B1B34F9B0BC096FD564FD7DE0F22CE41448DCB890FA6756`
- Included animations: `Idle`, `Walk`
- Network loading: `DISABLED`

The GLB is copied from the P4.4 frozen export and is bundled as a local
Flutter asset. Switching animations does not recreate or reload the model.

## Animation Mapping

```text
RobotMode.following -> Walk
all other RobotMode values -> Idle
```

The mapping is implemented in:

- `mobile/flutter_app/lib/features/robot/models/robot_status.dart`
- `mobile/flutter_app/lib/features/robot/models/robot_animation_mapper.dart`
- `mobile/flutter_app/lib/features/robot/controllers/robot_3d_controller.dart`

The controller waits for both required clips with bounded polling, avoids
duplicate playback calls, handles unavailable clips, and stops playback
initialization after disposal.

## Frozen Upstream Phase

- P4.4 commit: `f7b8dc1 fix(go2): 调整步态预览机位避免关节遮挡错觉`
- P4.4 Blender/FK hierarchy: `FROZEN`
- P4.4 Kine2Go DOF mapping, joint axes, centers, signs, offsets, mesh parents,
  Idle action, and Walk action: `FROZEN`

P4.5 does not regenerate, reinterpret, or retarget the Blender animation
pipeline.

## Flutter Integration

- Local asset declaration: `assets/models/go2/`
- 3D viewer package: `flutter_3d_controller: ^1.3.1`
- Viewer initialization: `PASS`
- Runtime animation discovery: `PASS`
- `Idle` playback: `PASS`
- `Walk` playback: `PASS`
- Robot mode mapping: `PASS`
- Idle/Walk switching: `PASS`
- Model reload during switching: `PASS` (no reload observed)
- Page re-entry 10 times: `PASS`
- Animation switching 20 times: `PASS`
- Resource release: `PASS` for the accepted emulator validation scope

The Android emulator exposed the runtime animation list as:

```text
[Idle, Walk]
```

Pixel validation observed no changes during static `Idle` playback and
857/52,290 changed samples during `Walk` playback, confirming that the walk
clip was visibly advancing.

## Verification

```text
SCOPED_FLUTTER_TESTS: PASS (10 tests)
SCOPED_FLUTTER_ANALYZE: PASS
DEBUG_APK_BUILD: PASS
APK_EMBEDDED_GLB_HASH: PASS
APK_EMBEDDED_GLB_SIZE: PASS
GLB_ANIMATIONS: ["Idle", "Walk"]
READY_FOR_DEMO: PASS
```

Commands used:

```powershell
cd D:\guosai\mobile\flutter_app
flutter test
flutter analyze lib/features/robot test/robot_status_test.dart
flutter build apk --debug --no-pub
```

The full repository has pre-existing analyzer findings outside the Robot
scope; this freeze only claims the scoped Robot analysis result.

## P5 Boundary

This phase uses the existing debug/demo `RobotProvider` state. It does not
connect to a real Go2 status topic, WebSocket, DDS stream, or backend status
API. Real robot status synchronization remains P5.

## Acceptance

```text
ANIMATED_GLB_LOAD: PASS
GLB_ANIMATIONS: ["Idle", "Walk"]
IDLE_PLAYBACK: PASS
WALK_PLAYBACK: PASS
ROBOT_MODE_MAPPING: PASS
MODE_SWITCH: PASS
NO_MODEL_RELOAD_ON_SWITCH: PASS
PAGE_REENTER_10X: PASS
ANIMATION_SWITCH_20X: PASS
RESOURCE_RELEASE: PASS
READY_FOR_DEMO: PASS
```
