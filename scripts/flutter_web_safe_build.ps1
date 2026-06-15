param(
    [string]$FlutterPath = "D:\tools\flutter\bin\flutter.bat",
    [string]$AppDir = "",
    [int]$TimeoutSeconds = 240,
    [switch]$KillExisting,
    [switch]$CleanFlutterLock,
    [switch]$ServeAfterBuild,
    [int]$ServePort = 5182,
    [string]$ServePython = "python"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($AppDir)) {
    $AppDir = Join-Path $repoRoot "mobile\\flutter_app"
}

function Stop-ProcessTree {
    param([int]$RootProcessId)

    try {
        $children = Get-CimInstance Win32_Process |
            Where-Object { $_.ParentProcessId -eq $RootProcessId }
        foreach ($child in $children) {
            Stop-ProcessTree -RootProcessId $child.ProcessId
        }
    } catch {
        Write-Host "WARN: unable to enumerate child processes: $($_.Exception.Message)"
    }

    try {
        Stop-Process -Id $RootProcessId -Force -ErrorAction SilentlyContinue
    } catch {
        Write-Host "WARN: unable to stop process ${RootProcessId}: $($_.Exception.Message)"
    }
}

if (-not (Test-Path -LiteralPath $FlutterPath)) {
    throw "Flutter executable not found: $FlutterPath"
}
if (-not (Test-Path -LiteralPath $AppDir)) {
    throw "Flutter app directory not found: $AppDir"
}

$logDir = Join-Path $repoRoot "runtime_logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stdoutLog = Join-Path $logDir "flutter_web_build_$stamp.out.log"
$stderrLog = Join-Path $logDir "flutter_web_build_$stamp.err.log"

if ($KillExisting) {
    Write-Host "Stopping existing flutter/dart processes..."
    Get-Process -Name flutter,dart -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-ProcessTree -RootProcessId $_.Id }
}

if ($CleanFlutterLock) {
    $cacheDir = Join-Path (Split-Path -Parent $FlutterPath) "cache"
    $locks = @(
        (Join-Path $cacheDir "lockfile"),
        (Join-Path $cacheDir "flutter.bat.lock")
    )
    foreach ($lock in $locks) {
        if (Test-Path -LiteralPath $lock) {
            Write-Host "Removing Flutter lock: $lock"
            Remove-Item -LiteralPath $lock -Force
        }
    }
}

$startedAt = Get-Date
$buildArgs = @("build", "web", "--debug", "--no-wasm-dry-run")
Write-Host "Starting Flutter build..."
Write-Host "Command: $FlutterPath $($buildArgs -join ' ')"
Write-Host "Logs: $stdoutLog"

$process = Start-Process `
    -FilePath $FlutterPath `
    -ArgumentList $buildArgs `
    -WorkingDirectory $AppDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

$completed = Wait-Process -Id $process.Id -Timeout $TimeoutSeconds -ErrorAction SilentlyContinue
if ($null -eq $completed -and -not $process.HasExited) {
    Write-Host "Flutter build timed out after $TimeoutSeconds seconds. Killing process tree..."
    Stop-ProcessTree -RootProcessId $process.Id
    Write-Host "STDERR tail:"
    Get-Content -LiteralPath $stderrLog -Tail 80 -ErrorAction SilentlyContinue
    Write-Host "STDOUT tail:"
    Get-Content -LiteralPath $stdoutLog -Tail 120 -ErrorAction SilentlyContinue
    throw "FLUTTER_WEB_BUILD_TIMEOUT"
}

$artifact = Join-Path $AppDir "build\web\main.dart.js"
$artifactInfo = Get-Item -LiteralPath $artifact -ErrorAction SilentlyContinue
$artifactFresh = $artifactInfo -ne $null -and $artifactInfo.LastWriteTime -ge $startedAt.AddSeconds(-5)
$stdoutText = Get-Content -LiteralPath $stdoutLog -Raw -ErrorAction SilentlyContinue
$reportedBuilt = $stdoutText -match "Built build\\web"

if ($process.ExitCode -ne 0 -and -not $artifactFresh -and -not $reportedBuilt) {
    Write-Host "Flutter build failed with exit code $($process.ExitCode)."
    Write-Host "STDERR tail:"
    Get-Content -LiteralPath $stderrLog -Tail 120 -ErrorAction SilentlyContinue
    Write-Host "STDOUT tail:"
    Get-Content -LiteralPath $stdoutLog -Tail 160 -ErrorAction SilentlyContinue
    throw "FLUTTER_WEB_BUILD_FAILED"
}

if (-not (Test-Path -LiteralPath $artifact)) {
    throw "Flutter build finished but artifact is missing: $artifact"
}
$artifactInfo = Get-Item -LiteralPath $artifact
if (-not $reportedBuilt -and $artifactInfo.LastWriteTime -lt $startedAt.AddSeconds(-5)) {
    throw "Flutter build artifact was not refreshed: $($artifactInfo.LastWriteTime)"
}

Write-Host "Flutter build completed."
Write-Host "Artifact: $($artifactInfo.FullName)"
Write-Host "Updated: $($artifactInfo.LastWriteTime)"

if ($ServeAfterBuild) {
    Write-Host "Starting static preview on http://127.0.0.1:$ServePort/"
    $serveArgs = @("-m", "http.server", "$ServePort", "--bind", "127.0.0.1")
    Start-Process `
        -FilePath $ServePython `
        -ArgumentList $serveArgs `
        -WorkingDirectory (Join-Path $AppDir "build\web") `
        -WindowStyle Hidden `
        -PassThru | Out-Null
}
