param(
    [string]$BackendEnv = "health",
    [int]$BackendPort = 8000,
    [switch]$StartFrontend,
    [switch]$StartCameraRuntime
)

$ErrorActionPreference = "Stop"
$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$backendUrl = "http://127.0.0.1:$BackendPort"

Write-Host "Project: $projectRoot"
Write-Host "Backend URL: $backendUrl"

function Test-HttpOk {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

if (Test-HttpOk "$backendUrl/healthz") {
    Write-Host "Backend already healthy: $backendUrl/healthz" -ForegroundColor Green
} else {
    Write-Host "Starting backend in conda env '$BackendEnv'..."
    Start-Process -FilePath "conda" -ArgumentList @(
        "run", "-n", $BackendEnv, "python", "-m", "uvicorn",
        "backend.main:app", "--host", "0.0.0.0", "--port", "$BackendPort", "--reload"
    ) -WorkingDirectory $projectRoot

    for ($i = 1; $i -le 60; $i++) {
        Start-Sleep -Seconds 1
        if (Test-HttpOk "$backendUrl/healthz") {
            Write-Host "Backend is healthy after $i seconds." -ForegroundColor Green
            break
        }
        Write-Host "Waiting for backend... $i"
    }
}

if ($StartCameraRuntime) {
    $cameraScript = Join-Path $projectRoot "camera_runtime_external\run_camera_live_server.ps1"
    if (Test-Path $cameraScript) {
        Write-Host "Starting camera runtime: $cameraScript"
        Start-Process -FilePath "powershell" -ArgumentList @(
            "-ExecutionPolicy", "Bypass", "-File", $cameraScript
        ) -WorkingDirectory $projectRoot
    } else {
        Write-Host "Camera runtime script not found: $cameraScript" -ForegroundColor Yellow
    }
}

if ($StartFrontend) {
    $frontendRoot = Join-Path $projectRoot "frontend\vue-dashboard"
    Write-Host "Starting frontend dev server..."
    Start-Process -FilePath "powershell" -ArgumentList @(
        "-NoExit", "-Command", "npm run dev"
    ) -WorkingDirectory $frontendRoot
}

Write-Host ""
Write-Host "Next useful commands:"
Write-Host "  conda run -n health-diagnostics python scripts\diagnostics\watch_camera_stream.py --duration 30"
Write-Host "  conda run -n health-diagnostics python scripts\diagnostics\probe_camera_status.py"
Write-Host "  conda run -n health-diagnostics powershell -ExecutionPolicy Bypass -File scripts\diagnostics\run_all_diagnostics.ps1"
