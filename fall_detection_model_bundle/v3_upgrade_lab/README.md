# Fall Detection V3 Upgrade Lab

This lab is isolated from the production fall-detection profile. It is for
downloading candidate models, preparing data manifests, training replacement
weights, and replaying benchmarks before any model is promoted.

Production remains on `configs/model_registry.yaml` and
`private_scene_fusion_v2` unless the backend is explicitly configured with:

```powershell
FALL_DETECTION_MODEL_REGISTRY_PATH=D:\Program\health(5-12)\fall_detection_model_bundle\v3_upgrade_lab\configs\model_registry.v3.yaml
FALL_DETECTION_PROFILE=fall_v3_shadow_yolo26_pose
```

Promotion rule: V3 profiles must first run in shadow/replay mode and produce a
report under `v3_upgrade_lab/reports` showing no regression on hard negatives.
