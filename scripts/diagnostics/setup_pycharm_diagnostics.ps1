param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$EnvName = "health-diagnostics",
    [string]$PythonExe = "C:\Users\YANG\.conda\envs\health-diagnostics\python.exe",
    [string]$PyCharmExe = "D:\PyCharm\PyCharm Community Edition 2023.3.4\bin\pycharm64.exe",
    [switch]$OpenPyCharm,
    [switch]$RunSmoke
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==== $Message ====" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-WarnLine {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Ensure-DiagnosticsEnv {
    Write-Step "Checking conda environment"
    $envList = conda env list
    if ($LASTEXITCODE -ne 0) {
        throw "conda env list failed. Please make sure conda is available in PATH."
    }
    if ($envList -match "^\s*$EnvName\s+") {
        Write-Ok "Conda env exists: $EnvName"
    } else {
        Write-WarnLine "Conda env '$EnvName' not found. Creating it now..."
        conda create -n $EnvName python=3.11 requests websockets -y
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create conda env: $EnvName"
        }
        Write-Ok "Conda env created: $EnvName"
    }

    if (-not (Test-Path $PythonExe)) {
        throw "Python interpreter not found: $PythonExe"
    }
    & $PythonExe -c "import requests, websockets; print('python ok')"
    if ($LASTEXITCODE -ne 0) {
        throw "Diagnostic interpreter cannot import requests/websockets."
    }
    Write-Ok "Interpreter ready: $PythonExe"
}

function New-PythonRunConfiguration {
    param(
        [string]$Name,
        [string]$Script,
        [string]$Parameters
    )
    $safeFileName = ($Name -replace "[^A-Za-z0-9_]+", "_")
    $target = Join-Path $ProjectRoot ".idea\runConfigurations\$safeFileName.xml"
    $scriptPath = "`$PROJECT_DIR`$/$Script"
    $xml = @"
<component name="ProjectRunConfigurationManager">
  <configuration default="false" name="$Name" type="PythonConfigurationType" factoryName="Python">
    <module name="health" />
    <option name="INTERPRETER_OPTIONS" value="" />
    <option name="PARENT_ENVS" value="true" />
    <envs>
      <env name="PYTHONUNBUFFERED" value="1" />
    </envs>
    <option name="SDK_HOME" value="$PythonExe" />
    <option name="WORKING_DIRECTORY" value="`$PROJECT_DIR`$" />
    <option name="IS_MODULE_SDK" value="false" />
    <option name="ADD_CONTENT_ROOTS" value="true" />
    <option name="ADD_SOURCE_ROOTS" value="true" />
    <option name="SCRIPT_NAME" value="$scriptPath" />
    <option name="PARAMETERS" value="$Parameters" />
    <method v="2" />
  </configuration>
</component>
"@
    Set-Content -Path $target -Value $xml -Encoding UTF8
    Write-Ok "Run configuration written: $target"
}

function Write-RunConfigurations {
    Write-Step "Writing PyCharm run configurations"
    Ensure-Directory (Join-Path $ProjectRoot ".idea")
    Ensure-Directory (Join-Path $ProjectRoot ".idea\runConfigurations")

    New-PythonRunConfiguration -Name "Diagnostics Backend Health" -Script "scripts/diagnostics/probe_backend_health.py" -Parameters "--timeout 30"
    New-PythonRunConfiguration -Name "Diagnostics Camera Status" -Script "scripts/diagnostics/probe_camera_status.py" -Parameters "--timeout 30"
    New-PythonRunConfiguration -Name "Diagnostics Camera Stream Watch" -Script "scripts/diagnostics/watch_camera_stream.py" -Parameters "--timeout 10"
    New-PythonRunConfiguration -Name "Diagnostics RTSP Matrix" -Script "scripts/diagnostics/probe_rtsp_matrix.py" -Parameters "--timeout 2"
    New-PythonRunConfiguration -Name "Diagnostics Health Score" -Script "scripts/diagnostics/probe_health_score.py" -Parameters "--timeout 30"
    New-PythonRunConfiguration -Name "Diagnostics Health WebSocket Watch" -Script "scripts/diagnostics/watch_health_ws.py" -Parameters "--timeout 10"
    New-PythonRunConfiguration -Name "Diagnostics Model Finetune" -Script "scripts/diagnostics/probe_model_finetune.py" -Parameters "--timeout 30"
}

function Open-PyCharmProject {
    if (-not $OpenPyCharm) {
        return
    }
    Write-Step "Opening PyCharm"
    if (-not (Test-Path $PyCharmExe)) {
        throw "PyCharm executable not found: $PyCharmExe"
    }
    Start-Process -FilePath $PyCharmExe -ArgumentList $ProjectRoot
    Write-Ok "PyCharm launched for project: $ProjectRoot"
}

function Run-SmokeChecks {
    if (-not $RunSmoke) {
        return
    }
    Write-Step "Running smoke diagnostics"
    & $PythonExe (Join-Path $ProjectRoot "scripts\diagnostics\probe_backend_health.py") --timeout 30
    & $PythonExe (Join-Path $ProjectRoot "scripts\diagnostics\probe_health_score.py") --timeout 30
    & $PythonExe (Join-Path $ProjectRoot "scripts\diagnostics\probe_camera_status.py") --timeout 30
}

Write-Step "PyCharm diagnostics setup"
Write-Host "ProjectRoot: $ProjectRoot"
Write-Host "EnvName:     $EnvName"
Write-Host "PythonExe:   $PythonExe"
Write-Host "PyCharmExe:  $PyCharmExe"

Ensure-DiagnosticsEnv
Write-RunConfigurations
Open-PyCharmProject
Run-SmokeChecks

Write-Step "Done"
Write-Ok "PyCharm diagnostics are ready."
Write-Host "In PyCharm Terminal, run:"
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\diagnostics\run_pycharm_diagnostics.ps1"
Write-Host ""
Write-Host "Or use the Run Configuration dropdown and select one of:"
Write-Host "  Diagnostics Backend Health"
Write-Host "  Diagnostics Camera Status"
Write-Host "  Diagnostics Camera Stream Watch"
Write-Host "  Diagnostics RTSP Matrix"
Write-Host "  Diagnostics Health Score"
Write-Host "  Diagnostics Health WebSocket Watch"
Write-Host "  Diagnostics Model Finetune"
