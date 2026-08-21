[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ManifestPath = Join-Path $ProjectRoot "artifacts\robot_mock_acceptance\runtime\process-manifest.json"
$DemoDatabase = Join-Path $ProjectRoot "data\robot_mock_demo.db"
$FormalDatabase = Join-Path $ProjectRoot "data\app.db"

if (-not (Test-Path -LiteralPath $ManifestPath)) {
    throw "Mock demo process manifest is missing. Run start_robot_mock_demo.ps1 first."
}
$manifest = Get-Content -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
if ($manifest.status -ne "running") { throw "The recorded Mock demo stack is not running." }
if ($manifest.provider -ne "mock" -or $manifest.real_motion_enabled -ne $false) {
    throw "Manifest violates the frozen Mock safety contract."
}
if ($manifest.robot_ip_contact_allowed -ne $false -or $manifest.ros2_enabled -ne $false) {
    throw "Manifest enables a forbidden real-device or ROS2 path."
}
$gatewayUri = [Uri]$manifest.gateway_base_url
if ($gatewayUri.Host -notin @("127.0.0.1", "localhost", "::1")) {
    throw "Gateway target is not loopback; refusing to validate a possible robot address."
}

$processChecks = foreach ($entry in $manifest.processes) {
    $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
    [ordered]@{ name = $entry.name; pid = $entry.pid; running = [bool]$process }
}
if ($processChecks.running -contains $false) { throw "One or more recorded demo processes are not running." }

$gatewayCapabilities = Invoke-RestMethod -Uri "$($manifest.gateway_base_url)/api/navigation/capabilities" -TimeoutSec 4
$gatewayState = Invoke-RestMethod -Uri "$($manifest.gateway_base_url)/api/navigation/state" -TimeoutSec 4
$backendCapabilities = Invoke-RestMethod -Uri "$($manifest.backend_base_url)/api/v1/robot/navigation/capabilities" -TimeoutSec 4
$backendState = Invoke-RestMethod -Uri "$($manifest.backend_base_url)/api/v1/robot/navigation/state" -TimeoutSec 4
$backendPoints = Invoke-RestMethod -Uri "$($manifest.backend_base_url)/api/v1/robot/navigation/points?map_id=map_mock_0001" -TimeoutSec 4
$backendRoutes = Invoke-RestMethod -Uri "$($manifest.backend_base_url)/api/v1/robot/navigation/routes?map_id=map_mock_0001" -TimeoutSec 4
foreach ($value in @($gatewayCapabilities.data, $gatewayState.data, $backendCapabilities.data, $backendState.data)) {
    if ($value.provider -ne "mock" -or $value.real_motion_enabled -ne $false) {
        throw "A live response violates provider=mock / real_motion_enabled=false."
    }
}
$expectedPointNames = @{
    "robot-demo-home" = "机器人待命点"
    "robot-demo-observation-elderly-activity" = "活动区观察点"
    "robot-demo-patrol-01" = "客厅巡逻点"
    "robot-demo-patrol-02" = "走廊巡逻点"
    "robot-demo-patrol-03" = "门口巡逻点"
}
foreach ($pointId in $expectedPointNames.Keys) {
    $point = @($backendPoints.data | Where-Object { $_.point_id -eq $pointId })
    if ($point.Count -ne 1) {
        throw "Fixed demonstration point is missing: $pointId"
    }
}
$demoRoute = @($backendRoutes.data | Where-Object { $_.route_id -eq "robot-demo-patrol-route" })
if ($demoRoute.Count -ne 1) {
    throw "Fixed demonstration patrol route is missing."
}
if (-not (Test-Path -LiteralPath $DemoDatabase)) { throw "Dedicated demo SQLite database is missing." }
$probe = Join-Path (Split-Path $DemoDatabase) "robot_mock_demo.write-probe"
"probe" | Set-Content -Encoding ASCII -LiteralPath $probe
Remove-Item -LiteralPath $probe

$formalHash = if (Test-Path -LiteralPath $FormalDatabase) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $FormalDatabase).Hash
} else { $null }
if ($manifest.formal_database_sha256_before -and $formalHash -ne $manifest.formal_database_sha256_before) {
    throw "Formal data/app.db changed after the Mock demo stack was started."
}

$optionalVideo = $false
$videoProbe = [System.Net.Sockets.TcpClient]::new()
try {
    $connect = $videoProbe.BeginConnect("127.0.0.1", 8093, $null, $null)
    $optionalVideo = $connect.AsyncWaitHandle.WaitOne(250) -and $videoProbe.Connected
} finally {
    $videoProbe.Close()
}
$result = [ordered]@{
    checked_at = (Get-Date).ToUniversalTime().ToString("o")
    provider = "mock"
    real_motion_enabled = $false
    processes = $processChecks
    ports = @{
        gateway = $manifest.ports.gateway
        backend = $manifest.ports.backend
        frontend = $manifest.ports.frontend
        optional_video_8093 = $optionalVideo
    }
    gateway_state = $gatewayState.data
    backend_state = $backendState.data
    fixed_demo_data = @{
        map_id = "map_mock_0001"
        point_names = $expectedPointNames
        route_id = "robot-demo-patrol-route"
        route_name = "日常巡查路线"
        camera_id = "camera_01"
        area_id = "elderly_activity_area"
    }
    database = $DemoDatabase
    formal_database_sha256 = $formalHash
}
$output = Join-Path $ProjectRoot "artifacts\robot_mock_acceptance\runtime\health-check.json"
$result | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 -LiteralPath $output
$result | ConvertTo-Json -Depth 5
