# Private Scene Workflow

This workflow is the recommended path for adapting the current fall detector to your own camera scene.

## 1. Collect private videos

Save your own camera or stream recordings into:

`D:\Program\model\fall_detection\data_private\camera_scene\raw_videos`

You can also capture directly with:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\capture_scene_video.py --source 0
```

## 2. Annotate events

For each private video, create event-level annotations:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\annotate_fall_events.py --video D:\Program\model\fall_detection\data_private\camera_scene\raw_videos\your_video.mp4 --output D:\Program\model\fall_detection\data_private\camera_scene\annotations\your_video.json
```

Recommended labels:

- `fall`
- `fallen`
- `lie_down`
- `sit_down`
- `bending`
- `walking`
- `other`
- `recovery`

## 3. Build the private manifest

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\build_private_manifest.py
```

This creates:

`D:\Program\model\fall_detection\data_processed\private_scene_manifest.csv`

## 4. Merge private and public manifests

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\merge_video_manifests.py
```

This creates:

`D:\Program\model\fall_detection\data_processed\video_manifest_adapted.csv`

## 5. Extract pose and posture-risk caches for the new videos

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\extract_pose_cache.py --manifest D:\Program\model\fall_detection\data_processed\video_manifest_adapted.csv --datasets private_scene
```

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\extract_posture_risk_cache.py --manifest D:\Program\model\fall_detection\data_processed\video_manifest_adapted.csv
```

## 6. Directional re-training

Retrain the hybrid temporal branch:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\train_temporal_tcn_transformer.py --manifest D:\Program\model\fall_detection\data_processed\video_manifest_adapted.csv --run-name hybrid_tcn_transformer_private_v1
```

Retrain the semantic mixed branch:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\train_temporal_semantic_mix.py --video-manifest D:\Program\model\fall_detection\data_processed\video_manifest_adapted.csv --run-name semantic_mix_falldb_private_v1
```

## 7. Search final fusion weights

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\search_fusion_weights.py --manifest D:\Program\model\fall_detection\data_processed\video_manifest_adapted.csv --hybrid-weights D:\Program\model\fall_detection\weights\hybrid_tcn_transformer_private_v1.pt --semantic-weights D:\Program\model\fall_detection\weights\semantic_mix_falldb_private_v1.pt
```

Use the returned weights and threshold in:

`D:\Program\model\fall_detection\scripts\realtime_fall_monitor.py`

## Completed local validation

### Dry-run validation

The pipeline has already been dry-run validated with two example videos:

- `data_private/camera_scene/dryrun_videos/scene_fall_dryrun.mp4`
- `data_private/camera_scene/dryrun_videos/scene_safe_dryrun.mp4`

### Real private-scene validation

The pipeline has also been validated with real local camera recordings:

- `data_private/camera_scene/raw_videos/private_scene_cam_2.mp4`
- `data_private/camera_scene/raw_videos/private_scene_cam_3.mp4`

Their event annotations are stored in:

- `data_private/camera_scene/annotations/private_scene_cam_2.json`
- `data_private/camera_scene/annotations/private_scene_cam_3.json`

The final searched profile after private-scene adaptation is:

- `gru_weight = 0.15`
- `hybrid_weight = 0.50`
- `semantic_weight = 0.00`
- `posture_weight = 0.35`
- `threshold = 0.65`

Saved at:

- `data_processed/private_scene_final_profile.json`

This is the current best profile for the presently available private-scene samples. It should still be re-searched again after more real camera videos are added.
