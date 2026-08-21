[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ManifestPath = Join-Path $ProjectRoot "artifacts\robot_mock_acceptance\runtime\process-manifest.json"
if (-not (Test-Path -LiteralPath $ManifestPath)) {
    Write-Host "No robot Mock demo process manifest exists; nothing to stop."
    exit 0
}

$manifest = Get-Content -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
$stopped = @()
$skipped = @()
$ownedProcesses = @($manifest.processes)
[array]::Reverse($ownedProcesses)
foreach ($entry in $ownedProcesses) {
    $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
    if (-not $process) {
        $skipped += @{ name = $entry.name; pid = $entry.pid; reason = "already_stopped" }
        continue
    }
    $recorded = [DateTime]::Parse([string]$entry.started_at).ToUniversalTime()
    $actual = $process.StartTime.ToUniversalTime()
    if ([Math]::Abs(($actual - $recorded).TotalSeconds) -gt 3) {
        $skipped += @{ name = $entry.name; pid = $entry.pid; reason = "pid_reused_start_time_mismatch" }
        continue
    }
    Stop-Process -Id $entry.pid -Force
    Wait-Process -Id $entry.pid -Timeout 10 -ErrorAction SilentlyContinue
    $stopped += @{ name = $entry.name; pid = $entry.pid }
}

$manifest.status = "stopped"
$manifest | Add-Member -Force -NotePropertyName stopped_at `
    -NotePropertyValue (Get-Date).ToUniversalTime().ToString("o")
$manifest | Add-Member -Force -NotePropertyName stopped_processes -NotePropertyValue $stopped
$manifest | Add-Member -Force -NotePropertyName skipped_processes -NotePropertyValue $skipped
$manifest | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 -LiteralPath $ManifestPath
Write-Host "Stopped only processes owned by this Mock demo manifest: $($stopped.Count)"
if ($skipped.Count -gt 0) {
    Write-Warning "$($skipped.Count) process entries were not terminated; inspect the manifest."
}
