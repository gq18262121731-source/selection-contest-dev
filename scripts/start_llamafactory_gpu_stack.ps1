param(
    [string]$ComposeFile = "configs\llm_finetune\docker-compose.llamafactory-gpu.yml",
    [switch]$Build,
    [switch]$PullBase,
    [switch]$NoCache
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$composePath = Join-Path $projectRoot $ComposeFile
$llamaRoot = "D:\Program\LLaMA-Factory"
$baseImage = "nvidia/cuda:12.8.1-base-ubuntu24.04"

if (!(Test-Path $composePath)) {
    throw "Compose file not found: $composePath"
}
if (!(Test-Path $llamaRoot)) {
    throw "LLaMA-Factory root not found: $llamaRoot"
}

$dockerInfo = docker info --format "{{.ServerVersion}}" 2>$null
if (!$dockerInfo) {
    throw "Docker daemon is not available. Start Docker Desktop and retry."
}

if ($PullBase) {
    docker pull $baseImage
}

if ($Build) {
    if ($NoCache) {
        docker compose -f $composePath build --no-cache
    } else {
        docker compose -f $composePath build
    }
}

docker compose -f $composePath up -d
docker compose -f $composePath ps

Write-Host ""
Write-Host "GPU LLaMA-Factory WebUI: http://127.0.0.1:7861"
Write-Host "GPU LLaMA-Factory API:   http://127.0.0.1:8001"
