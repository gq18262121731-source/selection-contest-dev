param(
    [string]$BackendEnv = "health",
    [string]$FrontendHost = "0.0.0.0",
    [int]$FrontendPort = 5173,
    [string]$TuningEnv = "llamafactory",
    [int]$TuningPort = 7860
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent

Start-Process powershell -ArgumentList @(
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $PSScriptRoot "start_server.ps1"),
    "-CondaEnv", $BackendEnv
) -WindowStyle Hidden

Start-Process powershell -ArgumentList @(
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $PSScriptRoot "start_frontend.ps1"),
    "-ListenHost", $FrontendHost,
    "-Port", $FrontendPort
) -WindowStyle Hidden

Start-Process powershell -ArgumentList @(
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $PSScriptRoot "start_model_tuning_console.ps1"),
    "-CondaEnv", $TuningEnv,
    "-Port", $TuningPort
) -WindowStyle Hidden

Write-Host "Local stack startup triggered: backend(8000) + frontend($FrontendPort) + tuning($TuningPort)"
