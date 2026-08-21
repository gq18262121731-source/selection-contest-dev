[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Uri = ""
)

$ErrorActionPreference = "Stop"
$LauncherVersion = "1.1.0"
$ExpectedServiceId = "go2-wireless-camera"
$ExpectedApiVersion = "1"
$AllowedUris = @(
    "go2bridge://start",
    "go2bridge://status"
)
$InstallRoot = Split-Path -Parent $PSCommandPath
$ConfigPath = Join-Path $InstallRoot "launcher.config.json"
$LogsRoot = Join-Path $InstallRoot "logs"
$LauncherLogPath = Join-Path $LogsRoot "launcher.jsonl"
$BridgePort = 8093
$BridgeStatusUrl = "http://127.0.0.1:$BridgePort/status"
$Mutex = $null
$MutexAcquired = $false

New-Item -ItemType Directory -Path $LogsRoot -Force | Out-Null

function Write-LauncherLog {
    param(
        [string]$Action,
        [int]$Code,
        [string]$Message,
        [hashtable]$Details = @{}
    )

    $Entry = [ordered]@{
        timestamp = (Get-Date).ToString("o")
        launcherVersion = $LauncherVersion
        action = $Action
        code = $Code
        message = $Message
        details = $Details
    }
    Add-Content -LiteralPath $LauncherLogPath -Value ($Entry | ConvertTo-Json -Compress -Depth 5) -Encoding UTF8
}

function Complete-Launcher {
    param(
        [string]$Action,
        [int]$Code,
        [string]$Message,
        [hashtable]$Details = @{}
    )

    Write-LauncherLog -Action $Action -Code $Code -Message $Message -Details $Details
    if ($MutexAcquired -and $null -ne $Mutex) {
        $Mutex.ReleaseMutex()
    }
    if ($null -ne $Mutex) {
        $Mutex.Dispose()
    }
    exit $Code
}

function Get-BridgeServiceIdentity {
    $Connection = Get-NetTCPConnection -LocalPort $BridgePort -State Listen -ErrorAction SilentlyContinue
    if ($null -eq $Connection) {
        return [pscustomobject]@{ State = "Offline"; ProcessId = $null; Reason = "Port is not listening." }
    }

    try {
        $Status = Invoke-RestMethod -Uri $BridgeStatusUrl -TimeoutSec 2 -Headers @{ Accept = "application/json" }
        if ($Status.serviceId -eq $ExpectedServiceId -and [string]$Status.apiVersion -eq $ExpectedApiVersion) {
            return [pscustomobject]@{
                State = "Known"
                ProcessId = [int]$Connection[0].OwningProcess
                Reason = "Expected Go2 bridge service responded."
            }
        }
        return [pscustomobject]@{
            State = "Unknown"
            ProcessId = [int]$Connection[0].OwningProcess
            Reason = "Port responded without the expected service identity."
        }
    }
    catch {
        return [pscustomobject]@{
            State = "Unknown"
            ProcessId = [int]$Connection[0].OwningProcess
            Reason = "Port is occupied but the status contract is unavailable."
        }
    }
}

if ($AllowedUris -notcontains $Uri) {
    Complete-Launcher -Action "rejected" -Code 2 -Message "URI is not in the fixed action allowlist."
}

$Action = if ($Uri -eq "go2bridge://status") { "status" } else { "start" }
$Identity = Get-BridgeServiceIdentity

if ($Action -eq "status") {
    if ($Identity.State -eq "Known") {
        Complete-Launcher -Action $Action -Code 0 -Message "Go2 video bridge service is healthy." -Details @{ processId = $Identity.ProcessId }
    }
    if ($Identity.State -eq "Unknown") {
        Complete-Launcher -Action $Action -Code 30 -Message "Port 8093 is occupied by an unknown service." -Details @{ processId = $Identity.ProcessId }
    }
    Complete-Launcher -Action $Action -Code 3 -Message "Go2 video bridge service is offline."
}

try {
    $UserSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $MutexName = "Local\Go2VideoBridgeLauncher.$UserSid"
    $Mutex = New-Object System.Threading.Mutex($false, $MutexName)
    $MutexAcquired = $Mutex.WaitOne(0)
    if (-not $MutexAcquired) {
        Complete-Launcher -Action $Action -Code 10 -Message "Another launcher request is already in progress."
    }

    $Identity = Get-BridgeServiceIdentity
    if ($Identity.State -eq "Known") {
        Complete-Launcher -Action $Action -Code 10 -Message "Go2 video bridge service is already running." -Details @{ processId = $Identity.ProcessId }
    }
    if ($Identity.State -eq "Unknown") {
        Complete-Launcher -Action $Action -Code 30 -Message "Port 8093 is occupied by an unknown service." -Details @{ processId = $Identity.ProcessId }
    }

    if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
        Complete-Launcher -Action $Action -Code 50 -Message "Launcher configuration is missing."
    }

    $Config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([int]$Config.version -lt 2) {
        Complete-Launcher -Action $Action -Code 50 -Message "Launcher configuration is outdated. Reinstall the launcher."
    }
    if ([string]$Config.serviceId -ne $ExpectedServiceId -or [string]$Config.apiVersion -ne $ExpectedApiVersion) {
        Complete-Launcher -Action $Action -Code 50 -Message "Launcher configuration targets an incompatible bridge service."
    }

    $BridgeStartScript = [string]$Config.bridgeStartScript
    if ([string]::IsNullOrWhiteSpace($BridgeStartScript)) {
        Complete-Launcher -Action $Action -Code 50 -Message "Bridge start script is not configured."
    }

    $ResolvedBridgeScript = [System.IO.Path]::GetFullPath($BridgeStartScript)
    if ([System.IO.Path]::GetFileName($ResolvedBridgeScript) -cne "start_sta_wireless.ps1") {
        Complete-Launcher -Action $Action -Code 50 -Message "Configured bridge script is not an approved start_sta_wireless.ps1 file."
    }
    if (-not (Test-Path -LiteralPath $ResolvedBridgeScript -PathType Leaf)) {
        Complete-Launcher -Action $Action -Code 20 -Message "Configured bridge start script does not exist."
    }

    $ExpectedHash = ([string]$Config.bridgeStartScriptSha256).ToUpperInvariant()
    $ActualHash = (Get-FileHash -LiteralPath $ResolvedBridgeScript -Algorithm SHA256).Hash.ToUpperInvariant()
    if ([string]::IsNullOrWhiteSpace($ExpectedHash) -or $ExpectedHash -ne $ActualHash) {
        Complete-Launcher -Action $Action -Code 21 -Message "Bridge start script hash does not match the installed configuration." -Details @{ actualHash = $ActualHash }
    }

    if ($Config.requireSignature -eq $true) {
        $Signature = Get-AuthenticodeSignature -LiteralPath $ResolvedBridgeScript
        if ($Signature.Status -ne "Valid") {
            Complete-Launcher -Action $Action -Code 22 -Message "Bridge start script signature is not valid." -Details @{ signatureStatus = [string]$Signature.Status }
        }
    }

    $PowerShellPath = (Get-Command powershell.exe -ErrorAction Stop).Source
    $EscapedScript = '"' + $ResolvedBridgeScript.Replace('"', '""') + '"'
    $Arguments = "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File $EscapedScript -NoOpenBrowser"
    $StartStdout = Join-Path $LogsRoot "bridge-start.stdout.log"
    $StartStderr = Join-Path $LogsRoot "bridge-start.stderr.log"

    $StartedProcess = Start-Process `
        -FilePath $PowerShellPath `
        -ArgumentList $Arguments `
        -WindowStyle Hidden `
        -RedirectStandardOutput $StartStdout `
        -RedirectStandardError $StartStderr `
        -PassThru

    Complete-Launcher -Action $Action -Code 0 -Message "Bridge start request was accepted." -Details @{
        processId = $StartedProcess.Id
        scriptHash = $ActualHash
        signatureRequired = [bool]$Config.requireSignature
    }
}
catch {
    Complete-Launcher -Action $Action -Code 40 -Message "PowerShell launcher failed." -Details @{ error = $_.Exception.Message }
}
