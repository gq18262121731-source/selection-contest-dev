param(
    [string]$ListenHost = '127.0.0.1',
    [int]$Port = 5173,
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$frontendDir = Join-Path $root 'frontend\vue-dashboard'
Set-Location $frontendDir

if (-not $SkipInstall -and -not (Test-Path 'node_modules')) {
    npm.cmd install
}

npm.cmd run dev -- --host $ListenHost --port $Port
