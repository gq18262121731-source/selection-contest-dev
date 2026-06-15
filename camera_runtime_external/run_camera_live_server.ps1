param(
    [string]$Config = "camera_live_config.json",
    [string]$CameraIp = "192.168.8.253",
    [string]$Username = "admin",
    [string]$Password = "admin",
    [ValidateSet("av0_1", "av0_0")]
    [string]$Stream = "av0_1",
    [ValidateSet("tcp", "udp")]
    [string]$Transport = "tcp",
    [int]$RtspPort = 554,
    [int]$ListenPort = 8090
)

$pythonCandidates = @(
    "C:\Users\YANG\.conda\envs\AI\python.exe",
    "C:\Users\YANG\.conda\envs\health\python.exe"
)
$python = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) {
    Write-Host "No usable Python runtime was found."
    exit 2
}

$script = Join-Path $PSScriptRoot "camera_runtime_main.py"
if (-not (Test-Path $script)) {
    Write-Host "camera_runtime_main.py was not found."
    exit 3
}

Write-Host "Using Python:" $python
Write-Host "Starting local viewer on http://127.0.0.1:$ListenPort/viewer"

if ($Config -eq "camera_live_config.json") {
    $cfgPath = Join-Path $PSScriptRoot $Config
    if (Test-Path $cfgPath) {
        $raw = Get-Content $cfgPath -Raw | ConvertFrom-Json
        $raw.viewer.listen_port = $ListenPort
        $raw.camera.host = $CameraIp
        $raw.camera.username = $Username
        $raw.camera.password = $Password
        $raw.camera.rtsp_port = $RtspPort
        $raw.camera.transport = $Transport
        $raw.camera.stream = $Stream
        $tempConfig = Join-Path $PSScriptRoot "camera_live_config.runtime.json"
        $raw | ConvertTo-Json -Depth 6 | Set-Content -Path $tempConfig -Encoding UTF8
        $Config = (Resolve-Path $tempConfig).Path
    }
}

& $python $script `
  --config $Config `
  --stream $Stream
