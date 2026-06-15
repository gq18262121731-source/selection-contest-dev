param(
    [string]$PythonExe = "C:\Users\YANG\.conda\envs\health-diagnostics\python.exe",
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [int]$Timeout = 30,
    [int]$StreamDuration = 12,
    [switch]$SkipStream,
    [switch]$SkipRtsp
)

$ErrorActionPreference = "Continue"
$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")

function Invoke-Diagnostic {
    param(
        [string]$Title,
        [string]$Script,
        [string[]]$ArgsList = @()
    )
    Write-Host ""
    Write-Host "==== $Title ====" -ForegroundColor Cyan
    $scriptPath = Join-Path $projectRoot $Script
    & $PythonExe $scriptPath @ArgsList
    $exit = $LASTEXITCODE
    if ($exit -eq 0) {
        Write-Host "PASSED: $Title" -ForegroundColor Green
    } else {
        Write-Host "FAILED: $Title (exit=$exit)" -ForegroundColor Red
    }
    $script:LastDiagnosticExit = $exit
}

Write-Host ""
Write-Host "PyCharm visible diagnostics runner" -ForegroundColor Cyan
Write-Host "Project:   $projectRoot"
Write-Host "Python:    $PythonExe"
Write-Host "Base URL:  $BaseUrl"
Write-Host ""

if (-not (Test-Path $PythonExe)) {
    Write-Host "Python interpreter not found: $PythonExe" -ForegroundColor Red
    exit 2
}

$failed = 0
Invoke-Diagnostic "Backend Health" "scripts\diagnostics\probe_backend_health.py" @("--base-url", $BaseUrl, "--timeout", "$Timeout")
if ($script:LastDiagnosticExit -ne 0) { $failed += 1 }
Invoke-Diagnostic "Health Score" "scripts\diagnostics\probe_health_score.py" @("--base-url", $BaseUrl, "--timeout", "$Timeout")
if ($script:LastDiagnosticExit -ne 0) { $failed += 1 }
Invoke-Diagnostic "Camera Status" "scripts\diagnostics\probe_camera_status.py" @("--base-url", $BaseUrl, "--timeout", "$Timeout")
if ($script:LastDiagnosticExit -ne 0) { $failed += 1 }
Invoke-Diagnostic "Model Finetune" "scripts\diagnostics\probe_model_finetune.py" @("--base-url", $BaseUrl, "--timeout", "$Timeout")
if ($script:LastDiagnosticExit -ne 0) { $failed += 1 }

if (-not $SkipRtsp) {
    Invoke-Diagnostic "RTSP Matrix" "scripts\diagnostics\probe_rtsp_matrix.py" @("--timeout", "2", "--hosts", "192.168.8.248", "192.168.8.253", "--ports", "554", "10554", "--transports", "tcp", "--streams", "av0_1", "av0_0")
    if ($script:LastDiagnosticExit -ne 0) { $failed += 1 }
}

if (-not $SkipStream) {
    Invoke-Diagnostic "Camera Stream Watch" "scripts\diagnostics\watch_camera_stream.py" @("--base-url", $BaseUrl, "--timeout", "5", "--duration", "$StreamDuration")
    if ($script:LastDiagnosticExit -ne 0) { $failed += 1 }
}

Write-Host ""
Write-Host "==== Summary ====" -ForegroundColor Cyan
if ($failed -eq 0) {
    Write-Host "All diagnostic groups passed." -ForegroundColor Green
} else {
    Write-Host "Diagnostic groups with failures: $failed" -ForegroundColor Yellow
    Write-Host "For camera failures: check current camera IP, RTSP port, power, and whether Windows can reach the camera from WLAN." -ForegroundColor Yellow
}

exit $failed
