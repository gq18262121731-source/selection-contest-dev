[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProtocolRoot = "HKCU:\Software\Classes\go2bridge"
$InstallRoot = Join-Path $env:LOCALAPPDATA "Go2VideoBridgeLauncher"

if (Test-Path -Path $ProtocolRoot) {
    Remove-Item -Path $ProtocolRoot -Recurse -Force
}

if (Test-Path -LiteralPath $InstallRoot -PathType Container) {
    Remove-Item -LiteralPath $InstallRoot -Recurse -Force
}

Write-Host "Go2 video bridge launcher removed for the current Windows user."
