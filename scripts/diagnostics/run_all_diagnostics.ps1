param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$Python = "python",
    [double]$Timeout = 8
)

$ErrorActionPreference = "Continue"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$checks = @(
    "probe_backend_health.py",
    "probe_camera_status.py",
    "probe_rtsp_matrix.py",
    "probe_camera_snapshot.py",
    "probe_health_score.py",
    "probe_fall_detection.py",
    "probe_auth_flow.py",
    "probe_device_flow.py",
    "probe_care_directory.py",
    "probe_agent.py",
    "probe_voice.py",
    "probe_omni.py",
    "probe_model_finetune.py"
)

$failed = 0
foreach ($check in $checks) {
    Write-Host ""
    Write-Host "==== $check ===="
    & $Python (Join-Path $scriptDir $check) --base-url $BaseUrl --timeout $Timeout
    if ($LASTEXITCODE -ne 0) {
        $failed += 1
        Write-Host "FAILED $check" -ForegroundColor Red
    } else {
        Write-Host "PASSED $check" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Diagnostics finished. Failed groups: $failed"
exit $failed
