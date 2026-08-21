# Vision Model Optimization Plan

## Problem Diagnosis

1. Target identity was too easy to accept from body-only evidence. The previous
   body profile used bounding-box geometry, area ratio, and posture label. Those
   features are useful as tracking hints, but they are not identity features.
   This explains cases where another person in the room was shown as the target.
2. Match caching could preserve a previous target decision after the target left
   the frame. Track reuse was helpful for latency, but it amplified false
   positives when a new or weakly matched person appeared.
3. Fall detection still had a single-frame decision path. A one-frame detector
   or posture-classifier spike can fire on sitting, bending, occlusion, or camera
   blur. Mature fall systems generally combine pose, tracking, and temporal
   sequence evidence.

## References Studied And Kept Locally

- `third_party/vision_references/fall-detection-mediapipe-transformer`
  - Source: https://github.com/punpayut/Fall-Detection
  - Useful content retained: pose keypoint extraction, skeleton normalization,
    30/60-frame sequence processing, Raspberry Pi real-time inference example.
  - Unused content removed: notebooks, demo images, Hugging Face app assets,
    nested `.git`.
- `third_party/vision_references/person-detector-tracking-reid`
  - Source: https://github.com/ms-shashank/Person-Detector-and-Tracking
  - Useful content retained: YOLO + DeepSORT + OSNet ReID example and README.
  - Unused content removed: nested `.git`.
- Existing local reference:
  - `third_party/pose_reference/mmpose`

## External Findings

- Ultralytics YOLO supports object detection, tracking, classification, and pose
  estimation in one ecosystem, which matches the current stack.
- DeepSORT/DeepSORT-Realtime supports appearance embeddings and TorchReID
  integration; this is the right direction for stable target identity across
  occlusion and re-entry.
- Torchreid provides deep person re-identification models, including OSNet and
  OSNet-AIN, which are more appropriate for body identity than handcrafted box
  ratios.
- The retained fall-detection reference reports stronger results from temporal
  pose Transformer models than LSTM/Bi-LSTM baselines, especially with 60-frame
  pose sequences.

## Changes Integrated Now

1. Target identity hardening:
   - If a target user has face embeddings, a new match now requires face
     evidence or very strong body appearance evidence. Body geometry alone is
     treated as a ranking hint, not identity.
   - Body-only matching remains possible only for users registered without any
     face embedding, and only with high body similarity plus sufficient detector
     confidence.
   - Cache reuse now requires the same track id, a recent face-confirmed match,
     and a stricter body similarity threshold.
   - Registration now stores a lightweight body appearance embedding based on
     HSV histograms from the detected person crop. Existing user records are
     backfilled from saved registration photos on service load.
   - Added an opt-in OSNet/Torchreid adapter inspired by downloaded GitHub
     ReID projects. It is disabled by default and does not install dependencies
     or download weights unless explicitly configured.

2. Target-only fall verification:
   - Added a per-session temporal window over target ROI fall scores, pose
     labels, keypoint quality, and posture events.
   - Weak single-frame fall detections are downgraded to `suspected` unless
     supported by high detector confidence, strong fall score, risky pose, or
     repeated risky frames.
   - Each fall result now includes `temporal_verification` diagnostics so the UI
     or logs can explain why a frame was confirmed or downgraded.

3. Offline evaluation:
   - Added `scripts/evaluate_target_fall_manifest.py` for labeled frame
     manifests with columns `path,target_present,fall[,session_id]`.
   - The script reports target identity precision/recall/false-positive-rate
     and fall detection precision/recall/false-positive-rate.

## Next Optimization Stages

1. Build the validation gate before more training:
   - Use `data/vision_bootstrap/manifests/fall_frames_manifest.csv` and
     `data/vision_bootstrap/manifests/identity_negatives_manifest.csv` as the
     first public-data smoke set.
   - Add local camera false positives into the same manifest format before any
     threshold or model swap is accepted.

2. Replace lightweight body appearance with real ReID:
   - Validate the optional `TARGET_REID_ENABLED=1` OSNet adapter with local
     weights and compare it against the current HSV embedding on the manifest.
   - Keep `TARGET_REID_ENABLED` off until local tests show lower false-positive
     rate without excessive target-miss rate.
   - Store multiple deep target body embeddings from registration images.
   - Match by cosine distance with background-masked crops when segmentation is
     available.

3. Improve target tracking:
   - Move from plain ByteTrack geometry to BoT-SORT or DeepSORT with appearance
     embeddings.
   - Require `n_init` consecutive frames before a new target track is trusted.
   - Expire target lock immediately when the target track is missing and no face
     confirmation is available.

4. Improve fall model accuracy:
   - Build a validation set from local room-camera videos: target present,
     target absent, bending, sitting, lying, occlusion, walking, and real/simulated
     falls.
   - Evaluate by class-specific precision/recall, not only aggregate accuracy.
   - Train a temporal pose model on 30/60-frame sequences using YOLO-pose or
     MediaPipe-style normalized keypoints.
   - Keep the current YOLO detector as one signal, not the sole fall decision.

5. Deployment guardrails:
   - Add confusion-case replay tests before every model swap.
   - Log identity evidence separately from fall evidence.
   - Surface `target_not_localized`, `filtered_non_target`, `suspected`, and
     `fall` as distinct UI states.
