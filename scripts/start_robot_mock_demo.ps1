[CmdletBinding()]
param(
    [string]$PythonCommand = "",
    [int]$GatewayPort = 8090,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$SkipFrontend,
    [switch]$KeepDemoData
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$GatewayRoot = Get-ChildItem -LiteralPath "E:\" -Directory |
    ForEach-Object { Join-Path $_.FullName "go2_dev\go2-gateway" } |
    Where-Object { Test-Path -LiteralPath $_ } |
    Select-Object -First 1
$FrontendRoot = Join-Path $ProjectRoot "frontend\vue-dashboard"
$ArtifactRoot = Join-Path $ProjectRoot "artifacts\robot_mock_acceptance"
$RuntimeRoot = Join-Path $ArtifactRoot "runtime"
$LogRoot = Join-Path $ArtifactRoot "logs"
$ManifestPath = Join-Path $RuntimeRoot "process-manifest.json"
$DemoDatabase = Join-Path $ProjectRoot "data\robot_mock_demo.db"
$FormalDatabase = Join-Path $ProjectRoot "data\app.db"

function Assert-PortAvailable {
    param([int]$Port)
    $probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    try {
        $probe.Start()
    } catch {
        throw "Port $Port is already occupied. Stop that service explicitly or choose an alternate demo port."
    } finally {
        $probe.Stop()
    }
}

function Invoke-JsonRequest {
    param(
        [ValidateSet("GET", "POST")][string]$Method,
        [string]$Uri,
        [hashtable]$Body
    )
    if ($Method -eq "GET") {
        return Invoke-RestMethod -Method Get -Uri $Uri -TimeoutSec 4
    }
    return Invoke-RestMethod -Method Post -Uri $Uri -ContentType "application/json" `
        -Body ($Body | ConvertTo-Json -Depth 12) -TimeoutSec 4
}

function Wait-JsonEndpoint {
    param([string]$Uri, [int]$Attempts = 60)
    for ($index = 0; $index -lt $Attempts; $index++) {
        try {
            return Invoke-RestMethod -Method Get -Uri $Uri -TimeoutSec 2
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    throw "Service did not become ready: $Uri"
}

function Start-OwnedProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [hashtable]$Environment
    )
    $previous = @{}
    foreach ($key in $Environment.Keys) {
        $previous[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
        [Environment]::SetEnvironmentVariable($key, [string]$Environment[$key], "Process")
    }
    try {
        $stdout = Join-Path $LogRoot "$Name.stdout.log"
        $stderr = Join-Path $LogRoot "$Name.stderr.log"
        $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList `
            -WorkingDirectory $WorkingDirectory -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
    } finally {
        foreach ($key in $Environment.Keys) {
            [Environment]::SetEnvironmentVariable($key, $previous[$key], "Process")
        }
    }
    return @{
        name = $Name
        pid = $process.Id
        executable = $FilePath
        started_at = $process.StartTime.ToUniversalTime().ToString("o")
        stdout = $stdout
        stderr = $stderr
        working_directory = $WorkingDirectory
    }
}

New-Item -ItemType Directory -Force -Path $RuntimeRoot, $LogRoot, (Split-Path $DemoDatabase) | Out-Null
if (-not (Test-Path -LiteralPath $GatewayRoot)) { throw "go2-gateway directory not found: $GatewayRoot" }
if (-not (Test-Path -LiteralPath (Join-Path $FrontendRoot "node_modules"))) {
    throw "Frontend node_modules is missing. Install the existing lockfile dependencies first."
}

$defaultHealthPython = Join-Path $env:USERPROFILE ".conda\envs\health\python.exe"
$PythonPath = if ($PythonCommand) {
    (Get-Command $PythonCommand -ErrorAction Stop).Source
} elseif (Test-Path -LiteralPath $defaultHealthPython) {
    $defaultHealthPython
} else {
    (Get-Command python -ErrorAction Stop).Source
}
& $PythonPath -c "import fastapi, uvicorn, requests, websockets" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Python environment is missing the existing backend runtime dependencies." }
$NodePath = (Get-Command node -ErrorAction Stop).Source

if (Test-Path -LiteralPath $ManifestPath) {
    $oldManifest = Get-Content -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
    $running = @($oldManifest.processes | Where-Object {
        $entry = $_
        $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
        if (-not $process) { return $false }
        try {
            $recorded = [DateTime]::Parse([string]$entry.started_at).ToUniversalTime()
            return [Math]::Abs(($process.StartTime.ToUniversalTime() - $recorded).TotalSeconds) -le 3
        } catch {
            return $false
        }
    })
    if ($running.Count -gt 0) {
        throw "A recorded Mock demo stack is still running. Use stop_robot_mock_demo.ps1 first."
    }
}

Assert-PortAvailable $GatewayPort
Assert-PortAvailable $BackendPort
if (-not $SkipFrontend) { Assert-PortAvailable $FrontendPort }

$formalHashBefore = if (Test-Path -LiteralPath $FormalDatabase) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $FormalDatabase).Hash
} else { $null }
$processes = @()

try {
    $gatewayEnvironment = @{
        GO2_MODE = "mock"
        GO2_CONTROL_ENABLED = "false"
        GO2_READ_ONLY_MODE = "false"
        GO2_VOICE_MODE = "mock"
        GO2_ROBOT_IP = "127.0.0.1"
        UNITREE_ROBOT_IP = "127.0.0.1"
        GO2_NETWORK_INTERFACE = "mock0"
        UNITREE_NETWORK_INTERFACE = "mock0"
        GO2_REQUIRE_DDS_STATE = "false"
        UNITREE_REQUIRE_DDS_STATE = "false"
        GO2_TASK_AUDIT_LOG_PATH = (Join-Path $LogRoot "gateway-task-events.jsonl")
        HEALTH_NEW_CALLBACK_URL = ""
        HEALTH_NEW_CALLBACK_TOKEN = ""
    }
    $processes += Start-OwnedProcess -Name "go2-gateway-mock" -FilePath $PythonPath `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$GatewayPort", "--workers", "1") `
        -WorkingDirectory $GatewayRoot -Environment $gatewayEnvironment

    $gatewayBaseUrl = "http://127.0.0.1:$GatewayPort"
    $capabilities = Wait-JsonEndpoint "$gatewayBaseUrl/api/navigation/capabilities"
    if ($capabilities.data.provider -ne "mock" -or $capabilities.data.real_motion_enabled -ne $false) {
        throw "Gateway safety contract rejected: provider must be mock and real_motion_enabled must be false."
    }

    $scenario = Invoke-JsonRequest POST "$gatewayBaseUrl/api/navigation/mock/scenario" @{
        request_id = "robot-demo-bootstrap-scenario"
        scenario = "robot_ready"
    }
    $mapping = Invoke-JsonRequest POST "$gatewayBaseUrl/api/navigation/mapping/start" @{
        request_id = "robot-demo-bootstrap-mapping-start"
        session_name = "养老活动区模拟建图"
    }
    $sessionId = [string]$mapping.data.session_id
    Invoke-JsonRequest POST "$gatewayBaseUrl/api/navigation/mapping/stop" @{
        request_id = "robot-demo-bootstrap-mapping-stop"
        session_id = $sessionId
    } | Out-Null
    $savedMap = Invoke-JsonRequest POST "$gatewayBaseUrl/api/navigation/maps/save" @{
        request_id = "robot-demo-bootstrap-map-save"
        session_id = $sessionId
        name = "养老活动区演示地图"
        confirmed = $true
    }
    $mapId = [string]$savedMap.data.map_id
    if (-not $mapId) { throw "Gateway did not return the active Mock map ID." }

    if (-not $KeepDemoData) {
        & $PythonPath (Join-Path $PSScriptRoot "cleanup_robot_mock_demo.py") `
            --database $DemoDatabase --all-demo `
            --output (Join-Path $RuntimeRoot "startup-cleanup.json") | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Mock demo cleanup failed." }
    }
    & $PythonPath (Join-Path $PSScriptRoot "seed_robot_mock_demo.py") `
        --database $DemoDatabase --map-id $mapId `
        --output (Join-Path $RuntimeRoot "seed-summary.json") | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Mock demo seed failed." }

    $databaseUrl = "sqlite+aiosqlite:///$($DemoDatabase.Replace('\', '/'))"
    $backendEnvironment = @{
        DATABASE_URL = $databaseUrl
        ROBOT_GATEWAY_ENABLED = "true"
        ROBOT_GATEWAY_BASE_URL = $gatewayBaseUrl
        ROBOT_GATEWAY_TIMEOUT_SECONDS = "2.0"
        OFFLINE_ONLY_RUNTIME = "true"
    }
    $processes += Start-OwnedProcess -Name "health-new-backend" -FilePath $PythonPath `
        -ArgumentList @("-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "$BackendPort", "--workers", "1") `
        -WorkingDirectory $ProjectRoot -Environment $backendEnvironment
    $backendBaseUrl = "http://127.0.0.1:$BackendPort"
    $backendCapabilities = Wait-JsonEndpoint "$backendBaseUrl/api/v1/robot/navigation/capabilities"
    if ($backendCapabilities.data.provider -ne "mock" -or $backendCapabilities.data.real_motion_enabled -ne $false) {
        throw "Main-system safety contract rejected: provider must be mock and real_motion_enabled must be false."
    }

    if (-not $SkipFrontend) {
        $viteEntry = Join-Path $FrontendRoot "node_modules\vite\bin\vite.js"
        $frontendEnvironment = @{
            VITE_API_BASE = "$backendBaseUrl/api/v1"
            VITE_WS_BASE = "ws://127.0.0.1:$BackendPort"
        }
        $processes += Start-OwnedProcess -Name "vue-dashboard" -FilePath $NodePath `
            -ArgumentList @($viteEntry, "--host", "127.0.0.1", "--port", "$FrontendPort") `
            -WorkingDirectory $FrontendRoot -Environment $frontendEnvironment
        Wait-JsonEndpoint "http://127.0.0.1:$FrontendPort" | Out-Null
    }

    $manifest = @{
        status = "running"
        provider = "mock"
        real_motion_enabled = $false
        robot_ip_contact_allowed = $false
        ros2_enabled = $false
        database = $DemoDatabase
        formal_database = $FormalDatabase
        formal_database_sha256_before = $formalHashBefore
        gateway_base_url = $gatewayBaseUrl
        backend_base_url = $backendBaseUrl
        frontend_base_url = if ($SkipFrontend) { $null } else { "http://127.0.0.1:$FrontendPort" }
        ports = @{ gateway = $GatewayPort; backend = $BackendPort; frontend = $FrontendPort }
        active_map_id = $mapId
        scenario = $scenario.data.mock_scenario
        started_at = (Get-Date).ToUniversalTime().ToString("o")
        processes = $processes
    }
    $manifest | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 -LiteralPath $ManifestPath
    Write-Host "Robot Mock demo stack started safely."
    Write-Host "Manifest: $ManifestPath"
    Write-Host "Frontend: http://127.0.0.1:$FrontendPort/#/robot-status"
} catch {
    foreach ($entry in @($processes | Sort-Object { $_.name -eq "go2-gateway-mock" })) {
        Stop-Process -Id $entry.pid -Force -ErrorAction SilentlyContinue
    }
    throw
}
