[CmdletBinding()]
param(
    [string]$InstalledLauncher = (Join-Path $env:LOCALAPPDATA "Go2VideoBridgeLauncher\Go2VideoBridgeLauncher.ps1")
)

$ErrorActionPreference = "Stop"
$PowerShellPath = (Get-Command powershell.exe -ErrorAction Stop).Source

function Invoke-Launcher {
    param([string]$Uri)

    $Process = Start-Process `
        -FilePath $PowerShellPath `
        -ArgumentList "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", "`"$InstalledLauncher`"", "`"$Uri`"" `
        -WindowStyle Hidden `
        -PassThru `
        -Wait
    return $Process.ExitCode
}

function Assert-Equal {
    param($Actual, $Expected, [string]$Message)
    if ($Actual -ne $Expected) {
        throw "$Message Expected=$Expected Actual=$Actual"
    }
}

if (-not (Test-Path -LiteralPath $InstalledLauncher -PathType Leaf)) {
    throw "Installed launcher was not found: $InstalledLauncher"
}

$ConfigPath = Join-Path (Split-Path -Parent $InstalledLauncher) "launcher.config.json"
$Config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
Assert-Equal ([int]$Config.version) 2 "Configuration version mismatch."
$ActualHash = (Get-FileHash -LiteralPath ([string]$Config.bridgeStartScript) -Algorithm SHA256).Hash.ToUpperInvariant()
Assert-Equal $ActualHash ([string]$Config.bridgeStartScriptSha256).ToUpperInvariant() "Bridge script hash mismatch."

Assert-Equal (Invoke-Launcher "go2bridge://start?cmd=calc.exe") 2 "Query parameters must be rejected."
Assert-Equal (Invoke-Launcher "go2bridge://start/") 2 "Extra URI paths must be rejected."
Assert-Equal (Invoke-Launcher "go2bridge://anything") 2 "Unknown actions must be rejected."

$StatusExit = Invoke-Launcher "go2bridge://status"
if ($StatusExit -eq 0) {
    $Before = Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction Stop
    1..10 | ForEach-Object {
        Assert-Equal (Invoke-Launcher "go2bridge://start") 10 "A running service must not be started again."
    }
    $After = Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction Stop
    Assert-Equal ([int]$After[0].OwningProcess) ([int]$Before[0].OwningProcess) "Repeated start changed the bridge process."
}
elseif ($StatusExit -ne 3) {
    throw "Unexpected launcher status exit code: $StatusExit"
}

Write-Host "GO2_LAUNCHER_TESTS_OK"
