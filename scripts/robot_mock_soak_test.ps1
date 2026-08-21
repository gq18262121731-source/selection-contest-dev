[CmdletBinding()]
param(
    [double]$DurationMinutes = 45,
    [int]$SampleIntervalSeconds = 30,
    [int]$CycleIntervalSeconds = 300,
    [int]$GatewayPort = 8090,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [bool]$RestartOwnedStack = $true
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ManifestPath = Join-Path $ProjectRoot "artifacts\robot_mock_acceptance\runtime\process-manifest.json"
$FormalDatabase = Join-Path $ProjectRoot "data\app.db"
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$ArtifactRoot = Join-Path $ProjectRoot "artifacts\robot_mock_soak\$timestamp"
$BrowserScript = Join-Path $ProjectRoot "frontend\vue-dashboard\scripts\browser-qa-robot-mock-soak.cjs"
$StartScript = Join-Path $ProjectRoot "scripts\start_robot_mock_demo.ps1"
$CheckScript = Join-Path $ProjectRoot "scripts\check_robot_mock_demo.ps1"
$StopScript = Join-Path $ProjectRoot "scripts\stop_robot_mock_demo.ps1"
$CleanupScript = Join-Path $ProjectRoot "scripts\cleanup_robot_mock_demo.py"
$SeedScript = Join-Path $ProjectRoot "scripts\seed_robot_mock_demo.py"

if ($DurationMinutes -le 0) { throw "DurationMinutes must be positive." }
if ($SampleIntervalSeconds -lt 5) { throw "SampleIntervalSeconds must be at least 5." }
if ($CycleIntervalSeconds -lt 30) { throw "CycleIntervalSeconds must be at least 30." }
if (-not (Test-Path -LiteralPath $BrowserScript)) { throw "Browser soak script is missing: $BrowserScript" }

New-Item -ItemType Directory -Force -Path $ArtifactRoot | Out-Null
$formalHashBefore = if (Test-Path -LiteralPath $FormalDatabase) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $FormalDatabase).Hash
} else {
    $null
}

function Get-ManifestState {
    if (-not (Test-Path -LiteralPath $ManifestPath)) {
        return @{ running = $false; partial = $false; manifest = $null }
    }
    $manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $ManifestPath | ConvertFrom-Json
    $entries = @($manifest.processes)
    $matching = 0
    foreach ($entry in $entries) {
        $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
        if (-not $process) { continue }
        $recorded = [DateTime]::Parse([string]$entry.started_at).ToUniversalTime()
        if ([Math]::Abs(($process.StartTime.ToUniversalTime() - $recorded).TotalSeconds) -le 3) {
            $matching += 1
        }
    }
    return @{
        running = $entries.Count -gt 0 -and $matching -eq $entries.Count
        partial = $matching -gt 0 -and $matching -lt $entries.Count
        manifest = $manifest
    }
}

function Assert-MockManifest {
    param($Manifest)
    if ($Manifest.provider -ne "mock") { throw "Manifest provider is not mock." }
    if ($Manifest.real_motion_enabled -ne $false) { throw "Manifest real_motion_enabled is not false." }
    if ($Manifest.robot_ip_contact_allowed -ne $false) { throw "Manifest allows robot IP contact." }
    foreach ($baseUrl in @($Manifest.gateway_base_url, $Manifest.backend_base_url, $Manifest.frontend_base_url)) {
        $uri = [Uri]$baseUrl
        if ($uri.Host -notin @("127.0.0.1", "localhost")) {
            throw "Non-loopback service is forbidden in soak test: $baseUrl"
        }
    }
    if ([IO.Path]::GetFullPath([string]$Manifest.database) -eq [IO.Path]::GetFullPath($FormalDatabase)) {
        throw "Soak test cannot use the formal app.db."
    }
}

$state = Get-ManifestState
if ($state.partial) {
    throw "The recorded Mock stack is only partially running. Stop it explicitly before the soak test."
}

$ownsStack = -not $state.running
$browserExitCode = $null
$databaseAudit = $null
try {
    if ($ownsStack) {
        & $StartScript -GatewayPort $GatewayPort -BackendPort $BackendPort -FrontendPort $FrontendPort
        if ($LASTEXITCODE -ne 0) { throw "Failed to start the isolated Mock stack." }
    }

    $state = Get-ManifestState
    if (-not $state.running) { throw "Mock stack is not fully running." }
    $manifest = $state.manifest
    Assert-MockManifest $manifest

    & $CheckScript
    if ($LASTEXITCODE -ne 0) { throw "Mock stack preflight check failed." }

    $healthBackend = @($manifest.processes | Where-Object { $_.name -eq "health-new-backend" } | Select-Object -First 1)
    $pythonPath = if ($healthBackend.Count -eq 1 -and (Test-Path -LiteralPath $healthBackend[0].executable)) {
        [string]$healthBackend[0].executable
    } else {
        (Get-Command python -ErrorAction Stop).Source
    }

    $previousEnvironment = @{
        ROBOT_SOAK_DURATION_MINUTES = $env:ROBOT_SOAK_DURATION_MINUTES
        ROBOT_SOAK_SAMPLE_INTERVAL_SECONDS = $env:ROBOT_SOAK_SAMPLE_INTERVAL_SECONDS
        ROBOT_SOAK_CYCLE_INTERVAL_SECONDS = $env:ROBOT_SOAK_CYCLE_INTERVAL_SECONDS
        ROBOT_SOAK_ARTIFACT_DIR = $env:ROBOT_SOAK_ARTIFACT_DIR
        ROBOT_SOAK_OWNS_STACK = $env:ROBOT_SOAK_OWNS_STACK
        ROBOT_SOAK_RESTART_OWNED_STACK = $env:ROBOT_SOAK_RESTART_OWNED_STACK
    }
    try {
        $env:ROBOT_SOAK_DURATION_MINUTES = [string]$DurationMinutes
        $env:ROBOT_SOAK_SAMPLE_INTERVAL_SECONDS = [string]$SampleIntervalSeconds
        $env:ROBOT_SOAK_CYCLE_INTERVAL_SECONDS = [string]$CycleIntervalSeconds
        $env:ROBOT_SOAK_ARTIFACT_DIR = $ArtifactRoot
        $env:ROBOT_SOAK_OWNS_STACK = if ($ownsStack) { "true" } else { "false" }
        $env:ROBOT_SOAK_RESTART_OWNED_STACK = if ($RestartOwnedStack) { "true" } else { "false" }

        $nodePath = (Get-Command node -ErrorAction Stop).Source
        & $nodePath $BrowserScript
        $browserExitCode = $LASTEXITCODE
        if ($browserExitCode -ne 0) { throw "Browser soak test failed with exit code $browserExitCode." }
    } finally {
        foreach ($key in $previousEnvironment.Keys) {
            [Environment]::SetEnvironmentVariable($key, $previousEnvironment[$key], "Process")
        }
    }

    $databasePath = [string]$manifest.database
    $auditSource = @'
import json
import sqlite3
import sys

path = sys.argv[1]
connection = sqlite3.connect(path, timeout=2.0)
connection.row_factory = sqlite3.Row
result = {
    "database": path,
    "integrity_check": connection.execute("PRAGMA integrity_check").fetchone()[0],
    "task_count": connection.execute("SELECT COUNT(*) FROM robot_tasks").fetchone()[0],
    "timeline_count": connection.execute("SELECT COUNT(*) FROM robot_task_timeline").fetchone()[0],
    "navigation_event_count": connection.execute("SELECT COUNT(*) FROM robot_navigation_events").fetchone()[0],
    "duplicate_task_ids": connection.execute(
        "SELECT COUNT(*) FROM (SELECT task_id FROM robot_tasks GROUP BY task_id HAVING COUNT(*) > 1)"
    ).fetchone()[0],
    "duplicate_timeline_states": connection.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT task_id, sequence, status, step, COUNT(*) AS count
            FROM robot_task_timeline
            GROUP BY task_id, sequence, status, step
            HAVING count > 1
        )
        """
    ).fetchone()[0],
}
print(json.dumps(result, ensure_ascii=False))
'@
    $auditJson = $auditSource | & $pythonPath - $databasePath
    if ($LASTEXITCODE -ne 0) { throw "SQLite audit failed." }
    $databaseAudit = $auditJson | ConvertFrom-Json
    $databaseAudit | ConvertTo-Json -Depth 8 |
        Set-Content -Encoding UTF8 -LiteralPath (Join-Path $ArtifactRoot "sqlite-audit.json")

    $lockMatches = @()
    foreach ($log in Get-ChildItem -LiteralPath (Join-Path $ProjectRoot "artifacts\robot_mock_acceptance\logs") -File -ErrorAction SilentlyContinue) {
        $matches = Select-String -LiteralPath $log.FullName -Pattern "database is locked|SQLite.*locked" -CaseSensitive:$false
        if ($matches) {
            $lockMatches += @($matches | ForEach-Object {
                @{ file = $log.FullName; line = $_.LineNumber; text = $_.Line }
            })
        }
    }
    $lockMatches | ConvertTo-Json -Depth 8 |
        Set-Content -Encoding UTF8 -LiteralPath (Join-Path $ArtifactRoot "sqlite-lock-scan.json")
    if ($lockMatches.Count -gt 0) { throw "SQLite lock errors were found in the Mock runtime logs." }
    if ($databaseAudit.integrity_check -ne "ok") { throw "SQLite integrity_check failed." }
    if ($databaseAudit.duplicate_task_ids -ne 0) { throw "Duplicate robot task IDs were detected." }
    if ($databaseAudit.duplicate_timeline_states -ne 0) { throw "Duplicate task timeline states were detected." }

    & $pythonPath $CleanupScript --database $databasePath
    if ($LASTEXITCODE -ne 0) { throw "Demo cleanup failed." }
    & $pythonPath $SeedScript --database $databasePath --map-id "map_mock_0001" `
        --output (Join-Path $ArtifactRoot "seed-summary.json")
    if ($LASTEXITCODE -ne 0) { throw "Demo seed restore failed." }
} finally {
    $formalHashAfter = if (Test-Path -LiteralPath $FormalDatabase) {
        (Get-FileHash -Algorithm SHA256 -LiteralPath $FormalDatabase).Hash
    } else {
        $null
    }
    $wrapperSummary = @{
        provider = "mock"
        real_motion_enabled = $false
        duration_minutes_requested = $DurationMinutes
        sample_interval_seconds = $SampleIntervalSeconds
        cycle_interval_seconds = $CycleIntervalSeconds
        owns_stack = $ownsStack
        browser_exit_code = $browserExitCode
        formal_database = $FormalDatabase
        formal_database_sha256_before = $formalHashBefore
        formal_database_sha256_after = $formalHashAfter
        formal_database_unchanged = $formalHashBefore -eq $formalHashAfter
        database_audit = $databaseAudit
        completed_at = (Get-Date).ToUniversalTime().ToString("o")
    }
    $wrapperSummary | ConvertTo-Json -Depth 10 |
        Set-Content -Encoding UTF8 -LiteralPath (Join-Path $ArtifactRoot "wrapper-summary.json")

    if ($ownsStack) {
        & $StopScript
    }
    if ($formalHashBefore -ne $formalHashAfter) {
        throw "Formal app.db changed during the soak test."
    }
}

Write-Host "Robot Mock soak test completed. Evidence: $ArtifactRoot"
