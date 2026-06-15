param(
    [string]$ComposeFile = "configs\llm_finetune\docker-compose.llamafactory-gpu.yml",
    [switch]$Build,
    [switch]$NoCache
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$composePath = Join-Path $projectRoot $ComposeFile

if (!(Test-Path $composePath)) {
    throw "Compose file not found: $composePath"
}

$dockerInfo = docker info --format "{{.ServerVersion}}" 2>$null
if (!$dockerInfo) {
    throw "Docker daemon is not available. Start Docker Desktop and retry."
}

if ($Build) {
    if ($NoCache) {
        docker compose -f $composePath --profile devel build --no-cache llamafactory-gpu-devel
    } else {
        docker compose -f $composePath --profile devel build llamafactory-gpu-devel
    }
}

docker compose -f $composePath --profile devel up -d llamafactory-gpu-devel
docker compose -f $composePath --profile devel ps llamafactory-gpu-devel

Write-Host ""
Write-Host "GPU Devel LLaMA-Factory WebUI: http://127.0.0.1:7862"
Write-Host "GPU Devel LLaMA-Factory API:   http://127.0.0.1:8002"
