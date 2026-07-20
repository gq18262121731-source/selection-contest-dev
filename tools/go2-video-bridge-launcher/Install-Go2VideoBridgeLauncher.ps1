[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$BridgeStartScript
)

$ErrorActionPreference = "Stop"
$LauncherVersion = "1.1.0"
$ServiceId = "go2-wireless-camera"
$ApiVersion = "1"

if ($env:OS -ne "Windows_NT") {
    throw "The Go2 video bridge launcher can only be installed on Windows."
}

$ResolvedBridgeScript = [System.IO.Path]::GetFullPath($BridgeStartScript)
if ([System.IO.Path]::GetFileName($ResolvedBridgeScript) -cne "start_sta_wireless.ps1") {
    throw "BridgeStartScript must point to the approved start_sta_wireless.ps1 file."
}
if (-not (Test-Path -LiteralPath $ResolvedBridgeScript -PathType Leaf)) {
    throw "Bridge start script was not found: $ResolvedBridgeScript"
}

$SourceLauncher = Join-Path $PSScriptRoot "Go2VideoBridgeLauncher.ps1"
if (-not (Test-Path -LiteralPath $SourceLauncher -PathType Leaf)) {
    throw "Launcher source file is missing: $SourceLauncher"
}

$InstallRoot = Join-Path $env:LOCALAPPDATA "Go2VideoBridgeLauncher"
$InstalledLauncher = Join-Path $InstallRoot "Go2VideoBridgeLauncher.ps1"
$LogsRoot = Join-Path $InstallRoot "logs"
New-Item -ItemType Directory -Path $LogsRoot -Force | Out-Null
Copy-Item -LiteralPath $SourceLauncher -Destination $InstalledLauncher -Force

$ScriptHash = (Get-FileHash -LiteralPath $ResolvedBridgeScript -Algorithm SHA256).Hash.ToUpperInvariant()
$Signature = Get-AuthenticodeSignature -LiteralPath $ResolvedBridgeScript
$RequireSignature = $Signature.Status -eq "Valid"
$Config = [ordered]@{
    version = 2
    launcherVersion = $LauncherVersion
    serviceId = $ServiceId
    apiVersion = $ApiVersion
    bridgeStartScript = $ResolvedBridgeScript
    bridgeStartScriptSha256 = $ScriptHash
    requireSignature = $RequireSignature
    installedAt = (Get-Date).ToString("o")
}
$Config | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $InstallRoot "launcher.config.json") -Encoding UTF8

$PowerShellPath = (Get-Command powershell.exe -ErrorAction Stop).Source
$ProtocolRoot = "HKCU:\Software\Classes\go2bridge"
$CommandKey = Join-Path $ProtocolRoot "shell\open\command"
$DefaultIconKey = Join-Path $ProtocolRoot "DefaultIcon"

New-Item -Path $ProtocolRoot -Force | Out-Null
Set-Item -Path $ProtocolRoot -Value "URL:Go2 Video Bridge Protocol"
New-ItemProperty -Path $ProtocolRoot -Name "URL Protocol" -Value "" -PropertyType String -Force | Out-Null
New-ItemProperty -Path $ProtocolRoot -Name "FriendlyTypeName" -Value "Go2 Video Bridge Launcher" -PropertyType String -Force | Out-Null

New-Item -Path $DefaultIconKey -Force | Out-Null
Set-Item -Path $DefaultIconKey -Value "$PowerShellPath,0"

New-Item -Path $CommandKey -Force | Out-Null
$ProtocolCommand = '"{0}" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "{1}" "%1"' -f $PowerShellPath, $InstalledLauncher
Set-Item -Path $CommandKey -Value $ProtocolCommand

$RegisteredCommand = (Get-Item -Path $CommandKey).GetValue("")
if ($RegisteredCommand -ne $ProtocolCommand) {
    throw "Protocol registration verification failed."
}

Write-Host "Go2 video bridge launcher installed for the current Windows user."
Write-Host "Protocol: go2bridge://start"
Write-Host "Launcher version: $LauncherVersion"
Write-Host "Launcher: $InstalledLauncher"
Write-Host "Bridge script: $ResolvedBridgeScript"
Write-Host "Bridge script SHA-256: $ScriptHash"
Write-Host "Authenticode required: $RequireSignature"
