param(
    [string]$Config = "camera_live_config.json",
    [string]$CameraIp = "192.168.8.248",
    [string]$Username = "admin",
    [string]$Password = "admin",
    [ValidateSet("av0_1", "av0_0")]
    [string]$Stream = "av0_1",
    [ValidateSet("tcp", "udp")]
    [string]$Transport = "tcp",
    [int]$RtspPort = 554,
    [int]$ListenPort = 8090
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDir = Join-Path $root "runtime_logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$pythonCandidates = @(
    "C:\Users\YANG\.conda\envs\AI\python.exe",
    "C:\Users\YANG\.conda\envs\health\python.exe"
)
$python = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) {
    Write-Host "No usable Python runtime was found."
    exit 2
}

$script = Join-Path $root "camera_runtime_main.py"
if (-not (Test-Path $script)) {
    Write-Host "camera_runtime_main.py was not found."
    exit 3
}

$targets = @()
$targets += Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and $_.CommandLine -match 'camera_runtime_main\.py|camera_live_server\.py'
}
$targets += Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'powershell.exe' -and $_.CommandLine -match 'run_camera_live_server\.ps1|camera_runtime_main\.py|camera_live_server\.py'
}

$targets | Group-Object ProcessId | ForEach-Object {
    Stop-Process -Id $_.Name -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 2

$cfgPath = Join-Path $root $Config
if (-not (Test-Path $cfgPath)) {
    Write-Host "Config file not found: $cfgPath"
    exit 4
}

$raw = Get-Content $cfgPath -Raw | ConvertFrom-Json
$raw.viewer.listen_port = $ListenPort
$raw.camera.host = $CameraIp
$raw.camera.username = $Username
$raw.camera.password = $Password
$raw.camera.rtsp_port = $RtspPort
$raw.camera.transport = $Transport
$raw.camera.stream = $Stream

$runtimeConfig = Join-Path $root "camera_live_config.runtime.json"
$raw | ConvertTo-Json -Depth 6 | Set-Content -Path $runtimeConfig -Encoding UTF8

$stdout = Join-Path $logDir "camera_runtime.stdout.log"
$stderr = Join-Path $logDir "camera_runtime.stderr.log"
$pidFile = Join-Path $logDir "camera_runtime.pid"

$proc = Start-Process -FilePath $python `
    -ArgumentList @($script, "--config", $runtimeConfig, "--stream", $Stream, "--listen-port", "$ListenPort") `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -PassThru

$proc.Id | Set-Content -Path $pidFile -Encoding ASCII

Start-Sleep -Seconds 5
Write-Host "Started camera runtime."
Write-Host ("PID: " + $proc.Id)
Write-Host ("Viewer: http://127.0.0.1:" + $ListenPort + "/viewer")
Write-Host ("Health: http://127.0.0.1:" + $ListenPort + "/api/v1/camera/health")
