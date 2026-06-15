$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDir = Join-Path $root "runtime_logs"
$pidFile = Join-Path $logDir "camera_runtime.pid"

if (Test-Path $pidFile) {
    $runtimePid = (Get-Content $pidFile -Raw).ToString().Trim()
    if ($runtimePid -match '^\d+$') {
        Stop-Process -Id ([int]$runtimePid) -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -eq 'python.exe' -and $_.CommandLine -match 'camera_runtime_main\.py|camera_live_server\.py') -or
    ($_.Name -eq 'powershell.exe' -and $_.CommandLine -match 'run_camera_live_server\.ps1|camera_runtime_main\.py|camera_live_server\.py')
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

Write-Host "Stopped camera runtime."
