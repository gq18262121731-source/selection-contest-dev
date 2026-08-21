param(
    [string]$CondaEnv = "llamafactory",
    [int]$Port = 7860,
    [string]$ProbeHost = "127.0.0.1",
    [string]$LLaMAFactoryRoot = "D:\Program\LLaMA-Factory",
    [switch]$SkipCapabilityCheck
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent

if (!(Test-Path $LLaMAFactoryRoot)) {
    throw "LLaMA-Factory root not found: $LLaMAFactoryRoot"
}

. (Join-Path $PSScriptRoot "conda_env.ps1")

function Test-TuningConsoleReady {
    param(
        [string]$ProbeHost,
        [int]$ProbePort
    )

    try {
        $resp = Invoke-WebRequest -Uri "http://$ProbeHost`:$ProbePort/" -UseBasicParsing -TimeoutSec 3
        return $resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500
    }
    catch {
        return $false
    }
}

$existingPids = @(
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
)

if ($existingPids.Count -gt 0) {
    if (Test-TuningConsoleReady -ProbeHost $ProbeHost -ProbePort $Port) {
        Write-Host "Model tuning console already running on port $Port."
        exit 0
    }
}

$python = Resolve-EnvPython -CondaEnv $CondaEnv

if (-not $SkipCapabilityCheck) {
    $capabilityProbe = @'
import importlib.util
import json
import platform

mods = [
    "llamafactory",
    "transformers",
    "torch",
    "peft",
    "trl",
    "bitsandbytes",
    "datasets",
    "evaluate",
    "accelerate",
    "gradio",
    "deepspeed",
    "flash_attn",
    "unsloth",
    "vllm",
]

out = {
    "platform": platform.platform(),
    "modules": {name: bool(importlib.util.find_spec(name)) for name in mods},
    "notes": [],
}

try:
    import torch

    out["torch_version"] = getattr(torch, "__version__", "")
    out["cuda_available"] = bool(torch.cuda.is_available())
    out["cuda_device_count"] = int(torch.cuda.device_count())
    out["cuda_name"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else ""
except Exception as exc:
    out["torch_error"] = f"{type(exc).__name__}: {exc}"

if platform.system().lower() == "windows":
    out["notes"].append(
        "Native Windows is suitable for WebUI, SFT/LoRA, QLoRA when bitsandbytes is available, "
        "and DPO/ORPO/KTO through TRL. DeepSpeed, flash_attn, vLLM and Unsloth are Linux/Docker-first capabilities."
    )

print(json.dumps(out, ensure_ascii=False))
'@
    $capabilityJson = $capabilityProbe | & $python -
    Write-Host "Model tuning capability check: $capabilityJson"
}

$env:GRADIO_SERVER_NAME = "0.0.0.0"
$env:GRADIO_SERVER_PORT = "$Port"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:LLAMA_FACTORY_ROOT = $LLaMAFactoryRoot
$env:DISABLE_VERSION_CHECK = "1"
$env:PATH = "$(Split-Path $python -Parent);$(Join-Path (Split-Path $python -Parent) 'Scripts');$env:PATH"

Set-Location $LLaMAFactoryRoot
& $python (Join-Path $repoRoot "scripts\model_tuning_console_entry.py")
exit $LASTEXITCODE
