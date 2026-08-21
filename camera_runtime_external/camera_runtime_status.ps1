$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDir = Join-Path $root "runtime_logs"
$pidFile = Join-Path $logDir "camera_runtime.pid"
$configPath = Join-Path $root "camera_live_config.json"

$headers = @{}
if (Test-Path $configPath) {
    $cfg = Get-Content $configPath -Raw | ConvertFrom-Json
    if ($cfg.viewer.auth_enabled -eq $true) {
        $pair = "$($cfg.viewer.auth_username):$($cfg.viewer.auth_password)"
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($pair)
        $token = [Convert]::ToBase64String($bytes)
        $headers["Authorization"] = "Basic $token"
    }
}

if (Test-Path $pidFile) {
    $runtimePid = (Get-Content $pidFile -Raw).ToString().Trim()
    Write-Host ("PID file: " + $runtimePid)
} else {
    Write-Host "PID file: missing"
}

Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and $_.CommandLine -match 'camera_runtime_main\.py|camera_live_server\.py'
} | Select-Object ProcessId,Name,CommandLine

try {
    Invoke-WebRequest -Uri 'http://127.0.0.1:8090/api/v1/camera/health' -Headers $headers -UseBasicParsing -TimeoutSec 5 |
        Select-Object -ExpandProperty Content
} catch {
    Write-Host ('HEALTH_ERROR: ' + $_.Exception.Message)
}
