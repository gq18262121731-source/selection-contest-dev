param(
    [string]$CondaEnv = "health"
)

$ErrorActionPreference = "Stop"

function Resolve-EnvPython {
    param([string]$CondaEnv)

    $candidates = @(
        (Join-Path $env:USERPROFILE ".conda\envs\$CondaEnv\python.exe"),
        (Join-Path $env:USERPROFILE "miniconda3\envs\$CondaEnv\python.exe"),
        (Join-Path $env:USERPROFILE "anaconda3\envs\$CondaEnv\python.exe"),
        (Join-Path $env:LOCALAPPDATA "anaconda3\envs\$CondaEnv\python.exe")
    ) | Where-Object { $_ }

    foreach ($path in $candidates) {
        if (Test-Path $path) {
            return $path
        }
    }

    throw "Cannot find python.exe for conda env '$CondaEnv'. The project is configured to run only inside that conda environment."
}
