param(
    [string]$EnvPath = 'D:\conda-envs\ai-health-iot',
    [string]$ProxyUrl = '',
    [switch]$SkipConnectivityCheck,
    [switch]$UseYamlInstall
)

$ErrorActionPreference = 'Stop'

function Write-Step($Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Invoke-Conda {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Args
    )

    $env:CONDA_NO_PLUGINS = 'true'

    $condaPath = (Get-Command conda.exe -ErrorAction SilentlyContinue).Source
    if (-not $condaPath) {
        $condaPath = (Get-Command conda.bat -ErrorAction SilentlyContinue).Source
    }
    if (-not $condaPath) {
        $condaPath = (Get-Command conda -ErrorAction SilentlyContinue).Source
    }

    if (-not $condaPath) {
        throw 'Unable to locate conda executable; ensure conda is installed and on PATH.'
    }

    & $condaPath @Args
    if ($LASTEXITCODE -ne 0) {
        throw "Conda command failed: conda $($Args -join ' ')"
    }
}

function Invoke-CondaRunPython {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Args
    )

    $condaPath = (Get-Command conda.exe -ErrorAction SilentlyContinue).Source
    if (-not $condaPath) {
        $condaPath = (Get-Command conda.bat -ErrorAction SilentlyContinue).Source
    }
    if (-not $condaPath) {
        $condaPath = (Get-Command conda -ErrorAction SilentlyContinue).Source
    }

    if (-not $condaPath) {
        throw 'Unable to locate conda executable; ensure conda is installed and on PATH.'
    }

    & $condaPath run -p $EnvPath python @Args
    if ($LASTEXITCODE -ne 0) {
        throw "Conda run python failed: python $($Args -join ' ')"
    }
}

Write-Step 'Preparing conda runtime'
conda config --set solver classic | Out-Null
conda config --set report_errors false | Out-Null
$env:CONDA_NO_PLUGINS = 'true'

if ($ProxyUrl) {
    Write-Step "Applying proxy $ProxyUrl"
    $env:HTTP_PROXY = $ProxyUrl
    $env:HTTPS_PROXY = $ProxyUrl
}

if (-not $SkipConnectivityCheck) {
    Write-Step 'Checking connectivity to conda repo'
    try {
        $null = Invoke-WebRequest -Uri 'https://repo.anaconda.com/pkgs/main/win-64/repodata.json' -Method Head -TimeoutSec 20
        Write-Host 'Connectivity check passed.' -ForegroundColor Green
    }
    catch {
        Write-Warning 'Connectivity check failed. If you are using a proxy client, switch it to TUN/global mode or pass -ProxyUrl http://127.0.0.1:7890'
        throw
    }
}

$parent = Split-Path $EnvPath -Parent
if (-not (Test-Path $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}

if (Test-Path $EnvPath) {
    Write-Warning "Environment path already exists: $EnvPath"
}

if ($UseYamlInstall) {
    Write-Step 'Creating environment from YAML'
    Invoke-Conda -- env create --solver classic -p $EnvPath -f environment/conda-environment.yml
}
else {
    Write-Step 'Creating base environment'
    Invoke-Conda -- create --solver classic -p $EnvPath python=3.9 pip nodejs=20 -y

    Write-Step 'Installing CUDA-enabled PyTorch stack'
    Invoke-Conda -- install --solver classic -p $EnvPath pytorch=2.0.1 torchvision=0.15.2 torchaudio=2.0.2 pytorch-cuda=11.7 -c pytorch -c nvidia -y

    Write-Step 'Installing core scientific and backend packages'
    Invoke-Conda -- install --solver classic -p $EnvPath `
        numpy=1.24.4 pandas=2.0.3 scipy=1.10.1 scikit-learn=1.0.2 `
        matplotlib=3.7.5 seaborn=0.13.2 pyyaml=6.0.2 lxml=4.9.3 pillow=10.4.0 `
        requests=2.32.3 beautifulsoup4=4.12.3 pyparsing=3.1.4 certifi=2025.1.31 `
        charset-normalizer=3.4.1 jinja2=3.1.6 psutil=7 tqdm=4.67.1 `
        fastapi=0.115.8 uvicorn=0.34.0 sqlalchemy=2.0.37 aiosqlite=0.21 `
        pydantic=2.11.3 pytest=8.3.4 pytest-asyncio=0.25.2 -c conda-forge -y

    Write-Step 'Installing pip-only packages'
    Invoke-CondaRunPython -m pip install --upgrade pip
    Invoke-CondaRunPython -m pip install `
        'httpx>=0.27,<1' `
        'chromadb==0.5.23' `
        'pydantic-settings>=2.10.1,<3' `
        'bleak>=0.22,<0.24' `
        'paho-mqtt>=2.1,<3' `
        'pyserial>=3.5,<4' `
        'ollama>=0.4.5,<1' `
        'langchain==1.2.0' `
        'langchain-core>=1.0,<2.0' `
        'langchain-community>=0.4,<0.5' `
        'langgraph>=1.0,<2.0' `
        'langchain-openai>=1.0,<2.0' `
        'langchain-ollama>=1.0,<2.0' `
        'langchain-qwq>=0.3.4,<1' `
        'openai>=1.30,<2'
}

Write-Step 'Verifying torch CUDA availability'
& conda run -p $EnvPath python -c "import torch; print('torch=', torch.__version__); print('cuda_available=', torch.cuda.is_available()); print('cuda_version=', torch.version.cuda)"
if ($LASTEXITCODE -ne 0) {
    throw 'Torch verification failed.'
}

Write-Step 'Done'
Write-Host "Environment created at: $EnvPath" -ForegroundColor Green
Write-Host "Activate it with: conda activate $EnvPath" -ForegroundColor Yellow
