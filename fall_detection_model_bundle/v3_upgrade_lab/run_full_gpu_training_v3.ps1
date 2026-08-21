$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Python = if ($env:V3_PYTHON) { $env:V3_PYTHON } else { "C:\Users\YANG\.conda\envs\AI\python.exe" }

Write-Host "[V3] Repo root: $RepoRoot"
Write-Host "[V3] Python: $Python"

& $Python -c "import torch; print('torch', torch.__version__); print('cuda', torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu')"

& $Python "$RepoRoot\fall_detection_model_bundle\scripts\import_v3_existing_assets.py"
& $Python "$RepoRoot\fall_detection_model_bundle\scripts\build_v3_scene_manifest.py"

& $Python "$RepoRoot\fall_detection_model_bundle\scripts\train_yolo_fall_detector_v3.py" `
  --data "$RepoRoot\fall_detection_model_bundle\v3_upgrade_lab\configs\fall_detect_v3_existing_dataset.yaml" `
  --model "$RepoRoot\fall_detection_model_bundle\v3_upgrade_lab\weights\yolo26\yolo26s.pt" `
  --epochs 180 `
  --imgsz 768 `
  --batch 16 `
  --device 0 `
  --workers 4 `
  --name yolo26s_fall_detector_v3_full_gpu `
  --patience 35

& $Python "$RepoRoot\fall_detection_model_bundle\scripts\run_v3_replay_matrix.py" `
  --source "scene_fall=positive=$RepoRoot\fall_detection_model_bundle\v3_upgrade_lab\datasets\private_dryrun_videos\scene_fall_dryrun.mp4" `
  --source "scene_safe=hard_negative=$RepoRoot\fall_detection_model_bundle\v3_upgrade_lab\datasets\private_dryrun_videos\scene_safe_dryrun.mp4" `
  --profile fall_v3_shadow_yolo26_pose `
  --profile fall_v3_hard_negative_guard `
  --profile fall_v3_recall_probe `
  --process-every 1 `
  --pose-tracker bytetrack `
  --timeout-seconds 900

& $Python "$RepoRoot\fall_detection_model_bundle\scripts\mine_v3_hard_negatives.py"
& $Python "$RepoRoot\fall_detection_model_bundle\scripts\build_v3_retraining_manifest.py"
& $Python "$RepoRoot\fall_detection_model_bundle\scripts\search_v3_fusion_from_replay.py"
& $Python "$RepoRoot\fall_detection_model_bundle\scripts\evaluate_v3_vlm_review.py"
& $Python "$RepoRoot\fall_detection_model_bundle\scripts\write_v3_replacement_gate_report.py"
& $Python "$RepoRoot\fall_detection_model_bundle\scripts\export_v3_promoted_package.py"

Write-Host "[V3] Full GPU training pipeline finished. Check v3_upgrade_lab\reports\replacement_gate_report.v3.md"
