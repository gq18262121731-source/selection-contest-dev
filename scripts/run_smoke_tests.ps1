param(
    [string]$CondaEnv = 'health',
    [switch]$BuildFrontend
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
. (Join-Path $PSScriptRoot 'conda_env.ps1')

$tests = @(
    'tests\test_parser.py',
    'tests\test_alarm_service.py',
    'tests\test_agent_analysis.py',
    'tests\test_health_api.py',
    'tests\test_chat_api.py'
)

$python = Resolve-EnvPython -CondaEnv $CondaEnv
$cacheDir = Join-Path $env:TEMP 'ai_health_pytest_cache'
& $python -m pytest -o cache_dir=$cacheDir @tests
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($BuildFrontend) {
    Push-Location 'frontend\vue-dashboard'
    try {
        if (-not (Test-Path 'node_modules')) {
            npm.cmd install
        }
        npm.cmd run build
        exit $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}
