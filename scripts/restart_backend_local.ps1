param(
    [string]$PythonPath = "python",
    [string]$RepoRoot = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}

$processes = Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -match "uvicorn|backend.main:app|frame_analysis_worker" }

foreach ($process in $processes) {
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 2

Start-Process `
    -FilePath $PythonPath `
    -ArgumentList @("-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory $RepoRoot `
    -WindowStyle Hidden

Start-Sleep -Seconds 8

try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8000/healthz" -TimeoutSec 8 |
        ConvertTo-Json -Compress
} catch {
    $_.Exception.Message
}
