param(
    [string]$CondaEnv = 'health',
    [string]$ListenHost = '0.0.0.0',
    [int]$Port = 8000,
    [switch]$Reload
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
. (Join-Path $PSScriptRoot 'conda_env.ps1')

$args = @('-m', 'uvicorn', 'backend.main:app', '--host', $ListenHost, '--port', "$Port")
if ($Reload) {
    $args += '--reload'
}

$python = Resolve-EnvPython -CondaEnv $CondaEnv
& $python @args
exit $LASTEXITCODE
