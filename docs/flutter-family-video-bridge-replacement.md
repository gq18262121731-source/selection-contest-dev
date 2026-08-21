# Flutter family video bridge replacement

This stage keeps the family camera page and player structure intact, and only
switches the processed-video source/status path to the reserved video bridge.

## Existing family video module

- Video page: `mobile/flutter_app/lib/features/camera/screens/family_camera_screen.dart`
- Route/lifecycle owner: `mobile/flutter_app/lib/features/camera/screens/family_camera_route.dart`
- Global player state: `mobile/flutter_app/lib/features/camera/providers/camera_provider.dart`
- Backend API/WS access: `mobile/flutter_app/lib/features/camera/repositories/camera_repository.dart`
- Camera/video models: `mobile/flutter_app/lib/features/camera/models/camera_models.dart`
- Local browser preview: `mobile/flutter_app/lib/features/camera/widgets/local_camera_preview*.dart`
- Audio monitor: `mobile/flutter_app/lib/features/camera/audio/*.dart`

## Confirmed player type

The family client does not use FLV, HLS, MJPEG, or WebRTC plugins.

- Remote video is a WebSocket image-frame stream.
- The UI renders frames through the existing `Image.memory` player surface.
- Existing processed stream fallback remains `/ws/camera/processed`.
- Existing raw stream remains `/ws/camera`.

## Replacement scope

Processed video now reads bridge status from:

```http
GET /api/v1/video-bridge/status
```

The bridge record may provide:

- `stream_type`: currently supports `ws_image` for the existing Flutter player.
- `stream_url`: optional absolute or relative WebSocket URL for the new video service.
- `snapshot_url`: optional snapshot fallback URL.
- `risk`, `fall_state`, `fall_prob`, `target`, `track_id`, FPS, and stale-state fields.

When `stream_url` is missing, the family client falls back to the existing
`/ws/camera/processed` path. This keeps the current main-system player usable
until the standalone video service is ready.

## Preserved behavior

- Old camera code is not deleted.
- The family camera page layout, elder-friendly spacing, action strip, audio
  controls, PTZ panel, diagnostics panel, and global alarm listener are kept.
- Flutter does not run YOLO, pose, tracking, or fall-state logic for bridge
  video.
- Flutter does not draw boxes or skeletons for bridge video; overlay is expected
  to be composed by the video service.
- Alarm POST and alarm WebSocket logic are unchanged.

## Files changed in this stage

- `backend/models/video_bridge_model.py`
- `backend/services/video_adapter.py`
- `tests/test_video_bridge_api.py`
- `mobile/flutter_app/lib/features/camera/models/camera_models.dart`
- `mobile/flutter_app/lib/features/camera/repositories/camera_repository.dart`
- `mobile/flutter_app/lib/features/camera/providers/camera_provider.dart`
- `mobile/flutter_app/lib/features/camera/screens/family_camera_screen.dart`
