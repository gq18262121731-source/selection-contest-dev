# Mobile SOS Push Rollout Status

Updated: 2026-05-01

## Goal

Make family mobile clients receive SOS alerts reliably across these states:

- App in foreground
- App in background while process is still alive
- App after websocket interruption
- App after OS suspension or termination

## Current Status

### Done in this repo now

- Family websocket alarms are scope-filtered to related devices only.
- Family foreground SOS popup is stable and uses queue hydration on startup.
- Foreground dialogs are scheduled safely on the next frame.
- Local high-priority system notifications are shown when the app is not in foreground.
- Android notification permission plumbing is in place.
- WebSocket disconnect fallback refresh is in place.
- Backend now stores mobile installation registrations per authenticated user.
- Flutter auto-registers the current installation after login.
- Backend notification dispatch now resolves target family installations for each SOS.

### Verified behaviors

- Community and family clients receive the same SOS event in foreground-online scenarios.
- Family startup no longer misses an already-active SOS in `alarm_queue`.
- If the app is backgrounded but still alive, SOS can surface through local system notification.
- Backend can tell which family installation should receive a given SOS.

### Not fully solved yet

- If the mobile app has been fully terminated by the OS, this repo still cannot guarantee immediate SOS delivery.
- True terminated-state delivery requires remote push providers such as FCM and APNs.

## Implemented Building Blocks

### Backend

- `backend/models/notification_model.py`
  - device registration and dispatch target models
- `backend/repositories/mobile_push_device_repo.py`
  - persistent mobile installation registry
- `backend/services/notification_service.py`
  - dispatch target resolution and push intent recording
- `backend/api/auth_api.py`
  - `GET /auth/mobile-devices`
  - `POST /auth/mobile-devices`
  - `DELETE /auth/mobile-devices/{installation_id}`

### Flutter

- `mobile/flutter_app/lib/core/services/app_notification_service.dart`
  - local SOS notification channel and sync logic
- `mobile/flutter_app/lib/core/services/mobile_device_registration_service.dart`
  - installation registration and revoke flow
- `mobile/flutter_app/lib/features/alarm/providers/alarm_provider.dart`
  - websocket fallback refresh
- `mobile/flutter_app/lib/features/alarm/widgets/global_alarm_listener.dart`
  - foreground dialog vs background notification coordination
- `mobile/flutter_app/lib/main.dart`
  - service wiring and startup sync

## Rollout Plan

### Phase P0

Objective: stabilize foreground and alive-background experience.

Status: complete

Acceptance:

- Foreground SOS shows dialog immediately on community and family clients.
- Existing SOS in `alarm_queue` is visible on family app startup.
- Backgrounded app with live process shows a system notification.
- Temporary websocket disconnect does not silently drop the alert.

### Phase P1

Objective: prepare server-driven targeting for remote push.

Status: substantially implemented

Done:

- Per-user mobile installation registry
- Login-time installation sync
- Logout-time installation revoke
- SOS dispatch target resolution
- Dispatch visibility in backend mobile push records

Remaining:

- expose installation health in admin/community tooling
- add metrics for stale installations
- optional retry/backoff policy for registration sync failures

Acceptance:

- Backend can answer which installations belong to a family account.
- SOS dispatch records show exact intended target installations.
- Multi-device family accounts can be targeted consistently.

### Phase P2

Objective: support lock-screen and terminated-state first-arrival alerts.

Status: not started in code

Required work:

- integrate Firebase Messaging in Flutter
- configure Android FCM
- configure iOS APNs plus Firebase
- register real remote push tokens instead of local placeholder tokens
- add background message handler
- convert remote push payload into the same SOS local-notification UX
- deep-link from notification tap back into the alarm detail flow

Acceptance:

- Android lock screen shows SOS promptly after backend dispatch.
- iOS lock screen shows SOS promptly after backend dispatch.
- SOS still arrives after app termination, subject to provider delivery guarantees.

### Phase P3

Objective: improve operational resilience and response workflow.

Status: planned

Suggested work:

- reminder escalation for unacknowledged SOS
- deduplication and collapse of repeated notifications
- delivery and acknowledgment telemetry
- optional SMS or phone fallback for prolonged non-response
- per-platform alert policy tuning

## Recommended Next Steps

1. Keep current P0 and P1 changes as the new baseline.
2. Start P2 with FCM token registration on Android first.
3. Add backend delivery telemetry before large-scale rollout.
4. After Android proves stable, complete APNs integration for iOS.

## Validation Commands

Backend:

```powershell
conda run -n health pytest tests/test_auth_mobile_devices_api.py tests/test_mobile_push_device_repo.py tests/test_notification_service.py tests/test_alarm_context_enrichment.py tests/test_alarm_api_scope.py tests/test_websocket_manager.py -q
```

Flutter:

```powershell
flutter test test/features/alarm/alarm_provider_test.dart test/widget_test.dart
flutter analyze lib/main.dart lib/core/network/api_client.dart lib/core/services/app_notification_service.dart lib/core/services/mobile_device_registration_service.dart lib/features/auth/providers/auth_provider.dart lib/features/auth/repositories/auth_repository.dart lib/features/session/services/session_manager.dart lib/features/alarm/providers/alarm_provider.dart lib/features/alarm/widgets/global_alarm_listener.dart
```

## References

- Firebase Cloud Messaging for Flutter: https://firebase.google.com/docs/cloud-messaging/flutter/receive?hl=zh-cn
- Android notification runtime permission: https://developer.android.com/develop/ui/views/notifications/notification-permission
- Apple notification authorization options: https://developer.apple.com/documentation/usernotifications/unauthorizationoptions
- flutter_local_notifications: https://pub.dev/packages/flutter_local_notifications
