# Fall Detection V3 Upgrade Status

Generated: 2026-05-18T09:03:23.741774+00:00

## Isolation

- Production registry remains `fall_detection_model_bundle/configs/model_registry.yaml`.
- V3 registry is `fall_detection_model_bundle/v3_upgrade_lab/configs/model_registry.v3.yaml`.
- Backend can switch only when `FALL_DETECTION_MODEL_REGISTRY_PATH` is explicitly configured.

## Candidate Weights

- `yolo26n-pose.pt`: present
- `yolo26s-pose.pt`: present
- `yolo26n.pt`: present
- `yolo26s.pt`: present
- `yolo26n-seg.pt`: present

## Candidate Profiles

- `fall_v3_shadow_yolo26_pose`: Shadow profile: YOLO26 pose front-end with current temporal ensemble. Does not become production without replay gates.
- `fall_v3_recall_probe`: High-recall probe for finding false negatives; use replay only, not production.
- `fall_v3_hard_negative_guard`: Conservative profile for sleep, lying, bending, sitting, and occlusion negatives.

## Tool Probe

- `fiftyone`: missing
- `albumentations`: missing
- `label-studio`: missing
- `onnx`: missing
- `onnxruntime`: installed
- `onnxruntime-gpu`: installed
- `mmpose`: missing
- `mmdet`: missing
- `mmengine`: missing
- `mmcv`: missing
- `mmaction2`: missing

## Execution Order

1. Run `bootstrap_v3_upgrade_lab.py --download` to pull candidate YOLO26 weights.
2. Download/prepare public and private authorized datasets into the V3 lab.
3. Train `train_yolo_fall_detector_v3.py` on the V3 dataset.
4. Extract pose caches for YOLO26 and RTMPose/OpenMMLab candidates.
5. Train temporal candidates: TCN/Transformer first, then ST-GCN/2s-AGCN/PoseC3D through MMAction2.
6. Run `run_v3_replay_matrix.py` against positive and hard-negative clips.
7. Promote only if hard-negative confirmed false positives are zero and positive recall is not worse than baseline.

## Non-Negotiable Gates

- No direct replacement of production weights before replay evidence exists.
- No random internet clips for training unless explicit rights are confirmed.
- Qwen/VLM review can downgrade or explain suspicious events, but cannot block emergency confirmed alarms.
