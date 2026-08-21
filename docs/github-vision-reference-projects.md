# GitHub Vision Reference Projects

The following projects were downloaded outside this repository under
`D:\Program` so their dependencies, examples, and working trees do not pollute
the current project environment.

## Downloaded Projects

| Local path | Upstream | Main value | License note |
| --- | --- | --- | --- |
| `D:\Program\github_punpayut_Fall-Detection` | https://github.com/punpayut/Fall-Detection | MediaPipe keypoint extraction, 30/60-frame pose sequence processing, Transformer/TFLite fall-classification workflow | MIT |
| `D:\Program\github_ms-shashank_Person-Detector-and-Tracking` | https://github.com/ms-shashank/Person-Detector-and-Tracking | YOLOv8 + DeepSORT + OSNet person re-identification example | No license file found locally; used as a design reference only |
| `D:\Program\github_mikel-brostrom_boxmot` | https://github.com/mikel-brostrom/boxmot | BoT-SORT/StrongSORT/DeepOCSORT style tracker and ReID plumbing references | AGPL-3.0, do not copy code into this project without license review |
| `D:\Program\github_KaiyangZhou_deep-person-reid` | https://github.com/KaiyangZhou/deep-person-reid | Torchreid / OSNet implementation and feature-extractor design | MIT |

## Local Cleanup

The projects were curated after download so they remain useful references
without becoming unrelated bulk data:

- Removed nested `.git` folders from all downloaded references.
- Removed demo images, notebooks, Hugging Face demo assets, examples, tests,
  CI folders, Docker files, and lock files where they were not needed.
- Kept algorithm source, README/license files, ReID model code, tracker code,
  and fall-detection keypoint/sequence processing code.
- No dependency installation was run from these projects.

## Fusion Into This Project

1. Target identity:
   - Current project now has body appearance embeddings in
     `backend/services/target_user_service.py`.
   - `backend/services/optional_reid_embedding_service.py` adds an opt-in
     OSNet/Torchreid adapter inspired by `deep-person-reid` and the YOLO +
     OSNet tracking reference.
   - The adapter is disabled by default. It does not install packages or
     download weights.

2. Fall detection:
   - Target-only fall detection now uses target ROI gating and temporal
     verification in `backend/services/target_user_fall_service.py`.
   - The 30/60-frame pose-sequence direction from `Fall-Detection` is kept as
     the next training path for real video clips.

3. Tracking:
   - BoxMOT was kept outside the repo as a reference for future BoT-SORT or
     StrongSORT migration.
   - Because BoxMOT is AGPL-3.0, no BoxMOT source code was copied into this
     project.

## Optional Deep ReID Activation

Default behavior remains the local lightweight HSV body appearance embedding.
To experiment with deep OSNet ReID without changing requirements:

```powershell
$env:TARGET_REID_ENABLED="1"
$env:TARGET_REID_SOURCE_DIR="D:\Program\github_KaiyangZhou_deep-person-reid"
$env:TARGET_REID_WEIGHTS="D:\Program\model\reid\osnet_x0_25.pth"
```

If no local weights are available, the adapter stays inactive unless
`TARGET_REID_ALLOW_PRETRAINED_DOWNLOAD=1` is explicitly set.
