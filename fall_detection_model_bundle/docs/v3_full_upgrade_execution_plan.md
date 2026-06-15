# Fall Detection V3 Full Upgrade Execution Plan

This plan upgrades the existing fall-detection system without replacing the
current production path until candidate models pass replay and hard-negative
gates.

## 0. Safety Boundary

- Production default stays on `configs/model_registry.yaml` and
  `private_scene_fusion_v2`.
- V3 uses `v3_upgrade_lab/configs/model_registry.v3.yaml`.
- Backend switching is explicit through `FALL_DETECTION_MODEL_REGISTRY_PATH`;
  an empty value preserves current behavior.
- V3 first runs in replay or shadow mode. It must not emit production alarms
  until promotion gates pass.

## 1. Replaceable Components

| Layer | Current | V3 candidate pool | Promotion decision |
| --- | --- | --- | --- |
| Person/pose perception | YOLO11n-pose | YOLO26n/s-pose, RTMPose, RTMO, RTMW | Choose by keypoint stability, FPS, multi-person robustness |
| Fall/object detector | YOLO11/custom detector | YOLO26 fall/fallen/lying/sitting/bending detector | Choose by recall and hard-negative false positives |
| Tracking | ByteTrack/BoT-SORT options | BoT-SORT default probe, OC-SORT/StrongSORT later | Choose by target-user identity stability |
| Temporal action | GRU, hybrid TCN/Transformer | TCN v3, Transformer v3, ST-GCN, 2s-AGCN, PoseC3D | Choose by transition detection and delay |
| Semantic review | Qwen/Omni logic | Qwen3-VL/InternVL/GLM vision adapter | Use only for review/report, not emergency blocking |
| Deployment | PyTorch/Ultralytics | ONNX, TensorRT, OpenVINO | Choose after candidate is accurate |
| Data tooling | ad hoc scripts | CVAT, FiftyOne, Label Studio, Albumentations | Use for closed-loop hard-negative mining |

## 2. One-Pass Implementation Already Added

- `v3_upgrade_lab/` isolated lab.
- V3 model registry and shadow profiles.
- Candidate stack manifest.
- V3 dataset taxonomy and evaluation gates.
- Scene taxonomy and ROI profile templates.
- High-recall and hard-negative state-machine rule profiles.
- YOLO26 bootstrap/downloader script.
- V3 detector training script.
- Pose front-end comparison script.
- Replay matrix script for baseline vs V3 candidates.
- Scene-aware manifest builder.
- Hard-negative/false-negative mining script.
- Replay-driven fusion search script.
- VLM review JSON-contract evaluator.
- Promoted package exporter with rollback instructions.
- Full pipeline dry-run runner.
- Status report generator.
- Optional backend model-registry setting.

## 3. Execution Commands

Prepare the lab and download candidate YOLO26 weights:

```powershell
conda run -n health python .\fall_detection_model_bundle\scripts\bootstrap_v3_upgrade_lab.py --download
```

Install optional V3 tooling after confirming environment size and CUDA version:

```powershell
powershell -ExecutionPolicy Bypass -File .\fall_detection_model_bundle\v3_upgrade_lab\install_v3_tools.ps1
```

Download the currently supported public data sources:

```powershell
conda run -n health python .\fall_detection_model_bundle\scripts\download_public_datasets.py --datasets gmdcsa24 urfd fallpose --extract
```

Train the V3 detector after the V3 YOLO-format dataset is prepared:

```powershell
conda run -n health python .\fall_detection_model_bundle\scripts\train_yolo_fall_detector_v3.py
```

Compare pose front ends on a local video:

```powershell
conda run -n health python .\fall_detection_model_bundle\scripts\compare_v3_pose_frontends.py --source .\data\fall_replay_benchmark\inputs\sample.mp4
```

Run a replay matrix:

```powershell
conda run -n health python .\fall_detection_model_bundle\scripts\run_v3_replay_matrix.py `
  --source positive_demo=positive=D:\path\to\fall.mp4 `
  --source sleep_demo=hard_negative=D:\path\to\sleep.mp4
```

Run the full scaffold/dry-run pipeline:

```powershell
conda run -n health python .\fall_detection_model_bundle\scripts\run_v3_full_pipeline_dryrun.py
```

Use V3 in backend only for shadow testing:

```env
FALL_DETECTION_MODEL_REGISTRY_PATH=D:\Program\health(5-12)\fall_detection_model_bundle\v3_upgrade_lab\configs\model_registry.v3.yaml
FALL_DETECTION_PROFILE=fall_v3_shadow_yolo26_pose
```

## 4. Promotion Gates

- Confirmed fall recall must be at least current baseline.
- Confirmed false positives on hard negatives must be zero.
- Average confirmation latency must be <= 1.5 seconds.
- P95 confirmation latency must be <= 3 seconds.
- Runtime FPS must be at least 90% of the baseline.
- Target-user misbinding must be <= 1%.
- VLM review may downgrade suspicious events, but it must not block emergency
  alarm passthrough.

## 5. Data Rule

Do not train on random internet clips unless use rights are explicit. Use public
datasets only after license review, and prioritize authorized project-site
footage for final tuning.

## 6. Full Optimization Loop

The V3 optimization loop is intentionally broader than detector fine-tuning:

1. Build a scene-aware manifest from authorized local videos and sidecars.
2. Compare pose front ends on the same frames: YOLO11, YOLO26, RTMPose/RTMO.
3. Train YOLO26 detector candidates for high recall and hard-negative guard.
4. Export pose caches from the best pose front ends.
5. Train temporal candidates across 16/24/32/48-frame windows.
6. Mine replay failures into hard-negative and false-negative manifests.
7. Search fusion weights under the constraint that hard-negative confirmed
   false positives remain zero.
8. Evaluate VLM review contract and emergency passthrough behavior.
9. Export a promoted candidate package only after replay evidence is present.
10. Keep rollback to `private_scene_fusion_v2` one environment change away.
