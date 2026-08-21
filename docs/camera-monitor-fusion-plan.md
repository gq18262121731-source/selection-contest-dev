# Camera Monitor Fusion Plan

## Goal

Improve camera streaming smoothness and the family-side monitoring experience by selectively merging proven features from the `codex/camera-monitor` branch into the current system, without replacing the stronger video relay and fall-detection pipeline already present in this repository.

## What We Compared

- Source branch: `https://github.com/gq18262121731-source/410health/tree/codex/camera-monitor`
- Commit reviewed: `f55fc15 feat: add mobile camera listen support`
- Current repo baseline: local `D:\health1`

## Key Decision

Do **not** replace the current backend camera video relay. The current repository already has a stronger camera stream hub with keep-warm behavior, relay status, and fallback handling. Replacing it with the branch version would reduce stability.

## Safe, High-Value Features Selected

1. Backend camera audio diagnostics
2. Backend camera audio listen websocket
3. Mobile family camera page
4. Mobile login page server origin hint
5. Family-side quick entry into the camera monitor page

## Features Intentionally Not Merged

1. Replacing `camera_stream_hub.py`
   - Reason: current repo implementation is more advanced and more stable.
2. Full talkback / two-way audio bridge
   - Reason: the branch documentation itself shows this still depends on vendor SDK / ActiveX / gateway assumptions and is not robust enough for a safe default merge.
3. Blindly switching stream profiles or transport modes
   - Reason: those changes need device-specific validation and can hurt live video reliability if applied without replay or on-device testing.

## Implementation Plan

### Phase 1. Backend capability merge

- Add audio-related camera settings:
  - `CAMERA_AUDIO_RTSP_PATH`
  - `CAMERA_AUDIO_SAMPLE_RATE`
  - `CAMERA_AUDIO_GATEWAY_URL`
  - `CAMERA_SDK_DLL_DIR`
  - `CAMERA_ACTIVEX_CLSID`
- Extend `CameraService` with:
  - RTSP audio probing
  - SDK / ActiveX diagnostics
  - masked URL reporting
- Add `CameraAudioHub` to relay a single RTSP audio stream to multiple websocket listeners.
- Expose APIs:
  - `GET /api/v1/camera/audio/status`
  - `GET /api/v1/camera/audio/stream-status`
  - `WS /ws/camera/audio/listen`

### Phase 2. Mobile experience merge

- Add family camera feature module in Flutter:
  - models
  - repository
  - provider
  - screen
  - audio-player abstraction
- Register `CameraRepository` in the existing app provider graph.
- Add a family-home card that opens the live camera monitor page.
- Add a login-screen server origin hint so users can see the current backend endpoint before logging in.

### Phase 3. Verification

- Backend compile check
- Pytest against camera audio diagnostics and existing fall-detection tests
- Flutter format
- Flutter static analysis
- Runtime checks:
  - health endpoint
  - camera status endpoint
  - camera audio status endpoint
  - camera audio listen websocket frame receipt

## What Was Actually Implemented

### Backend

- `backend/config.py`
- `backend/services/camera_service.py`
- `backend/services/camera_audio_hub.py`
- `backend/dependencies.py`
- `backend/api/camera_api.py`
- `backend/main.py`
- `.env`
- `.env.example`

### Mobile

- `mobile/flutter_app/lib/main.dart`
- `mobile/flutter_app/lib/features/auth/screens/login_screen.dart`
- `mobile/flutter_app/lib/features/care/screens/family_home_screen.dart`
- `mobile/flutter_app/lib/features/camera/...`

### Tests

- `tests/test_camera_audio_service.py`

## Verification Results

- Backend python compile: passed
- Pytest in project environment: passed
- Flutter format: passed
- Flutter analyze: no blocking errors after compatibility downgrade for web PCM playback
- Runtime API checks:
  - `/healthz`: passed
  - `/api/v1/camera/status`: passed
  - `/api/v1/camera/audio/status`: passed
  - `/api/v1/camera/audio/stream-status`: passed
  - `/ws/camera/audio/listen`: received live binary audio chunk successfully

## Current Tradeoffs

- Browser / Flutter web PCM playback is intentionally downgraded to a visible unsupported state in this build.
  - Reason: the imported branch implementation was not compatible with the current Flutter SDK surface and would have made the mobile client unstable.
- Backend audio listen is live and verified.
- Full two-way talkback is still deferred until vendor SDK compatibility is validated.

## Next Recommended Steps

1. Add a browser-compatible PCM playback path using a verified Flutter-web-compatible audio stack.
2. Add a dedicated camera diagnostics page in the web dashboard so stream FPS, listener count, and audio-track readiness are visible to operators.
3. Feed recorded room videos through the replay benchmark pipeline to tune stream profile, JPEG quality, and fall-detection cadence together.
4. If true talkback is required, isolate it behind an optional feature flag and validate it only with the exact camera model and SDK package in use.
