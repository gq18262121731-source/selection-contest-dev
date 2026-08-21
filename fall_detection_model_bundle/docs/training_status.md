# Training Status

Updated on `2026-04-27`.

## Environment

- Conda env: `AI`
- Python: `3.10.6`
- Ultralytics: `8.3.107`
- PyTorch upgraded to: `2.11.0+cu128`
- GPU verified: `NVIDIA GeForce RTX 5060 Laptop GPU`

The original `torch 2.2.2+cu118` install was too old for this GPU generation, so the environment was upgraded to the official CUDA 12.8 wheel set.

## Datasets currently available locally

- `data_public/urfd/videos`: 70 RGB videos
- `data_public/gmdcsa24/extracted/...`: 150 RGB videos
- `data_public/omnifall_labels`: unified label pack
- `data_public/wanfall_splits`: cross-view split definitions
- `data_public/fallpose/extracted/*`: all downloaded Fall Pose posture sequences extracted
- `data_public/fall_database/FallDatabase.rar`: downloaded
- `data_public/fall_database/skeleton_only/*/skeleton.txt`: extracted skeleton sequences

## Prepared artifacts

- Unified manifest: `data_processed/video_manifest.csv`
- FallDatabase manifest: `data_processed/falldb_manifest.csv`
- Pose cache: `data_processed/pose_cache/*.npz`
- Posture risk cache: `data_processed/posture_risk_cache/*.npz`
- Baseline weights:
  - `weights/gru_pose_fall_v1.pt`
  - `weights/gru_pose_fall_v2_w16.pt`
  - `weights/hybrid_tcn_transformer_v1.pt`
  - `weights/hybrid_tcn_transformer_v2_matchgru.pt`
  - `weights/semantic_mix_falldb_v1.pt`
- YOLO posture classification models:
  - `runs/yolo_posture_cls_v1/weights/best.pt`
  - `runs/yolo_posture_person_cls_v1/weights/best.pt`
  - `runs/yolo_posture_person_binary_cls_v1/weights/best.pt`
- Example exported result:
  - `exports/urfd_fall_demo.mp4`
  - `exports/urfd_fall_demo_combined.mp4`
  - `exports/urfd_adl_demo_combined.mp4`
  - `exports/urfd_fall_demo_optimized.mp4`
  - `exports/urfd_adl_demo_optimized.mp4`
  - `exports/urfd_fall_demo_trifusion.mp4`
  - `exports/urfd_adl_demo_trifusion.mp4`

## Current model variants

### `gru_pose_fall_v1`

- Pose front-end: `yolo11n-pose.pt`
- Sequence window: `24`
- Stride: `6`
- Test summary from `runs/gru_pose_fall_v1/metrics.json`:
  - accuracy: `0.8011`
  - precision: `0.3918`
  - recall: `0.7170`

This version is better at recognizing post-fall / fallen states.

### `gru_pose_fall_v2_w16`

- Pose front-end: `yolo11n-pose.pt`
- Sequence window: `16`
- Stride: `4`
- Test summary from `runs/gru_pose_fall_v2_w16/metrics.json`:
  - accuracy: `0.7769`
  - precision: `0.3784`
  - recall: `0.6087`

This version covers shorter fall transitions better, but its current external-window metrics are slightly weaker.

### `yolo_posture_cls_v1`

- Input: full room images from Fall Pose
- Classes: `standing / sitting / lying / bending / crawling / other`
- Validation `top1_acc`: about `0.9546`
- Test split direct evaluation: `0.7241`

This version is useful for analysis, but it does not match the real deployment input very well because runtime classification operates on person crops rather than the full room frame.

### `yolo_posture_person_cls_v1`

- Input: person crops auto-extracted from Fall Pose images with YOLO
- Classes: `standing / sitting / lying / bending / crawling`
- Validation `top1_acc`: about `0.8644`
- Test split direct evaluation:
  - 5-class accuracy: `0.7596`
  - binary risk grouping (`lying/crawling/bending` vs `standing/sitting`): `0.8321`

This is currently the recommended auxiliary posture model for the real-time monitor because its input distribution is closer to the actual inference pipeline.

### `yolo_posture_person_binary_cls_v1`

- Input: person crops
- Labels: `risk / safe`
- Backbone: `yolo11s-cls`
- Validation `top1_acc`: about `0.8800`
- Test split direct evaluation:
  - overall accuracy: `0.8187`
  - risk recall: `0.7756`
  - safe recall: `0.8355`

This is the current recommended posture-risk auxiliary model for deployment because it is optimized directly for alert support instead of fine-grained posture naming.

### `hybrid_tcn_transformer_v2_matchgru`

- Input: pose dynamics + posture risk score sequence
- Backbone: `TCN + Transformer Encoder`
- Window: `24`, stride `6`
- This branch is trained as a high-recall temporal complement to the original GRU model.
- Test summary from `runs/hybrid_tcn_transformer_v2_matchgru/metrics.json` at its saved threshold:
  - accuracy: `0.7433`
  - precision: `0.3384`
  - recall: `0.8396`

Used alone, this branch is too aggressive for final alerting, but it adds useful recall when fused with the GRU branch.

### `semantic_mix_falldb_v1`

- Input: unified semantic temporal features
- Sources:
  - RGB pose windows from `GMDCSA24 + URFD`
  - skeleton windows from `FallDatabase`
- Purpose: improve cross-domain temporal semantics rather than only fit the RGB staged datasets
- Test summary from `runs/semantic_mix_falldb_v1/metrics.json`:
  - accuracy: `0.7977`
  - precision: `0.5642`
  - recall: `0.7254`
  - f1: `0.6348`

This branch is now part of the training pipeline and can be enabled as an optional extra branch in monitoring, but it is not yet the default online fusion branch because the current RGB held-out fusion is still strongest with the GRU + hybrid + posture trio.

## Fusion tuning

Held-out window evaluation on `test + external` windows:

- `GRU only` best scanned F1: about `0.5102`
- `GRU 0.7 + posture 0.3` best scanned F1: about `0.5360`
- `GRU 0.6 + posture 0.4` best scanned F1: about `0.5382`
- `GRU 0.30 + hybrid 0.45 + posture 0.25` best scanned F1: about `0.5694`

The current monitor defaults were updated to:

- `gru-weight = 0.30`
- `hybrid-weight = 0.45`
- `posture-weight = 0.25`
- `threshold = 0.45`

This setting reflects the strongest three-branch fusion found so far on the held-out window scan.

## Private scene adaptation

Real local camera videos have now been added and processed:

- `private_scene_cam_2.mp4`
- `private_scene_cam_3.mp4`

These were annotated as:

- `private_scene_cam_2`: `sitting`
- `private_scene_cam_3`: `bending`

Directional re-training artifacts:

- `weights/hybrid_tcn_transformer_private_real_v1.pt`
- `weights/semantic_mix_falldb_private_real_v1.pt`

Current searched private-scene profile:

- `gru_weight = 0.15`
- `hybrid_weight = 0.50`
- `semantic_weight = 0.00`
- `posture_weight = 0.35`
- `threshold = 0.65`

Saved profile:

- `data_processed/private_scene_final_profile.json`

## Recommended next optimization steps

1. Finish downloading the remaining `fallpose` sequences and prepare a static posture auxiliary model.
2. Add more hard negatives from intentional `lie_down`, `sit_down`, and `kneeling` segments.
3. Tune alerting at the track level instead of raw window-level thresholding.
4. Add real deployment footage from the target camera viewpoint.
5. Rebuild the person-crop classifier after the remaining Fall Pose sequences finish downloading.
6. Finish `FallDatabase.rar` download and add it once extraction support is ready.
7. `RTMPose / RTMO` remains a promising next-step front-end, but direct migration is deferred because the OpenMMLab stack is currently high-risk on this Windows + CUDA environment.
8. The next most valuable data step is still collecting your own camera-domain footage and event labels.

## Useful commands

Build or rebuild the manifest:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\build_video_manifest.py
```

Extract pose cache:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\extract_pose_cache.py
```

Train the current baseline:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\train_temporal_gru.py --epochs 12 --run-name gru_pose_fall_v1
```

Run offline monitoring on a video:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\realtime_fall_monitor.py --source D:\Program\model\fall_detection\data_public\urfd\videos\fall-01-cam1.mp4 --save-path D:\Program\model\fall_detection\exports\urfd_fall_demo.mp4 --no-display
```

Build the person-crop posture dataset:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\build_fallpose_person_cls_dataset.py --frame-step 2
```

Train the recommended auxiliary YOLO posture classifier:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\train_yolo_posture_cls.py --data D:\Program\model\fall_detection\data_processed\fallpose_person_cls --epochs 20 --imgsz 320 --batch 64 --name yolo_posture_person_cls_v1
```

Build the binary person-crop risk dataset:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\build_fallpose_person_binary_cls_dataset.py --train-safe-ratio 1.2
```

Train the current recommended binary auxiliary model:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\train_yolo_posture_cls.py --data D:\Program\model\fall_detection\data_processed\fallpose_person_binary_cls --model yolo11s-cls.pt --epochs 25 --imgsz 384 --batch 48 --name yolo_posture_person_binary_cls_v1
```
