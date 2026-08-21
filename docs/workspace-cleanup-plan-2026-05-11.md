# Workspace Cleanup Plan - 2026-05-11

This workspace currently contains several independent work streams. Do not reset or delete changes blindly.

## Keep as camera-source work

- `backend/api/camera_api.py`
- `backend/api/camera_source_api.py`
- `backend/main.py`
- `backend/services/camera_audio_hub.py`
- `backend/services/camera_service.py`
- `backend/services/camera_source_registry.py`
- `backend/services/camera_stream_hub.py`
- `frontend/vue-dashboard/src/api/client.ts`
- `frontend/vue-dashboard/src/components/CameraMonitorCard.vue`
- `frontend/vue-dashboard/src/components/CameraRegistrationPanel.vue`
- `frontend/vue-dashboard/src/views/FamilyPage.vue`
- `scripts/camera_direct_probe.py`
- `docs/camera-source-layer.md`

## Keep as fall-detection/model work

- `fall_detection_model_bundle/README.md`
- `fall_detection_model_bundle/configs/`
- `fall_detection_model_bundle/docs/`
- `fall_detection_model_bundle/reports/`
- `fall_detection_model_bundle/runtime_bridge/`
- `fall_detection_model_bundle/scripts/`
- `fall_detection_model_bundle/weights/`
- `fall_detection_model_bundle/runs/yolo_posture_person_binary_cls_v1/weights/best.pt`
- `backend/config.py`
- `backend/dependencies.py`
- `backend/services/fall_frame_test_service.py`
- `backend/services/target_user_fall_service.py`
- `backend/services/target_user_service.py`

## Treat as generated/local artifacts

- `Ultralytics/`
- `.codex_tmp_docs/`
- `fall_detection_model_bundle/data_processed/`
- `fall_detection_model_bundle/data_public/`
- `fall_detection_model_bundle/outputs/`
- `fall_detection_model_bundle/runs/yolo_posture_person_cls_fallpose_baseline_v1/`
- `fall_detection_model_bundle/runs/yolo_posture_person_cls_fallpose_baseline_v1-2/`

These are now ignored by `.gitignore`.

Approximate local size check:

- `fall_detection_model_bundle/data_public/`: 3459 MB
- `fall_detection_model_bundle/data_processed/`: 243 MB
- `fall_detection_model_bundle/runs/`: 36 MB
- `fall_detection_model_bundle/weights/`: 34 MB

Conclusion: commit model code/configs/selected weights, but do not commit extracted public datasets or generated training outputs.

## Separate review required

- `agent/`
- `backend/resources/`
- `backend/services/pose_*`
- `backend/services/posture_*`
- `backend/services/target_pose_service.py`
- `frontend/vue-dashboard/src/components/*Pose*`
- `frontend/vue-dashboard/src/views/DebugPage.vue`
- `pose_detection_model_bundle/`
- `docs/papers/`
- `docs/papers_stage2/`
- `摄像头说明书/`

These may be useful, but they are not part of the camera registration cleanup. Review them before staging.

## Current git issue

The git index is temporarily locked by running `git.exe` processes. If staging/unstaging fails with `index.lock` or permission errors, close Git GUI/IDE integrations or stop the stuck git processes, then rerun status.
