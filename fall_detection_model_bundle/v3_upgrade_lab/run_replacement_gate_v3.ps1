$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Python = if ($env:V3_PYTHON) { $env:V3_PYTHON } else { "C:\Users\YANG\.conda\envs\health\python.exe" }

& $Python "$RepoRoot\fall_detection_model_bundle\scripts\mine_v3_hard_negatives.py"
& $Python "$RepoRoot\fall_detection_model_bundle\scripts\build_v3_retraining_manifest.py"
& $Python "$RepoRoot\fall_detection_model_bundle\scripts\search_v3_fusion_from_replay.py"
& $Python "$RepoRoot\fall_detection_model_bundle\scripts\evaluate_v3_vlm_review.py"
& $Python "$RepoRoot\fall_detection_model_bundle\scripts\write_v3_replacement_gate_report.py"
& $Python "$RepoRoot\fall_detection_model_bundle\scripts\export_v3_promoted_package.py"
