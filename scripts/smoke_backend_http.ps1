param(
    [string]$CondaEnv = 'health',
    [string]$ListenHost = '127.0.0.1',
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
. (Join-Path $PSScriptRoot 'conda_env.ps1')

$python = Resolve-EnvPython -CondaEnv $CondaEnv
$proc = Start-Process -FilePath $python -ArgumentList @('-m', 'uvicorn', 'backend.main:app', '--host', $ListenHost, '--port', "$Port") -WorkingDirectory $root -PassThru
try {
    $baseUrl = "http://$ListenHost`:$Port"
    $ready = $false
    for ($i = 0; $i -lt 25; $i++) {
        Start-Sleep -Seconds 1
        try {
            $resp = Invoke-RestMethod -Uri "$baseUrl/healthz" -TimeoutSec 2
            if ($resp.status -eq 'ok') {
                $ready = $true
                break
            }
        }
        catch {
        }
    }

    if (-not $ready) {
        throw 'Backend did not become ready in time.'
    }

    $healthz = Invoke-RestMethod -Uri "$baseUrl/healthz"
    $system = Invoke-RestMethod -Uri "$baseUrl/api/v1/system/info"
    $devices = Invoke-RestMethod -Uri "$baseUrl/api/v1/devices"

    [pscustomobject]@{
        healthz = $healthz
        system_info = $system
        device_count = @($devices).Count
    } | ConvertTo-Json -Depth 6
}
finally {
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force
    }
}
