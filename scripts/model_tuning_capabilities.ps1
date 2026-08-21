param(
    [string]$CondaEnv = "llamafactory",
    [string]$LLaMAFactoryRoot = "D:\Program\LLaMA-Factory"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "conda_env.ps1")

$python = Resolve-EnvPython -CondaEnv $CondaEnv
if (!(Test-Path $LLaMAFactoryRoot)) {
    throw "LLaMA-Factory root not found: $LLaMAFactoryRoot"
}

$probe = @'
import importlib.util
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

modules = [
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

result = {
    "platform": platform.platform(),
    "python": None,
    "modules": {name: bool(importlib.util.find_spec(name)) for name in modules},
    "native_ready": {},
    "docker_ready": {},
    "datasets": {},
    "v1_datasets": {},
    "linux_or_docker_first": ["deepspeed", "flash_attn", "unsloth", "vllm"],
    "recommendations": [],
}

try:
    import sys

    result["python"] = sys.executable
except Exception:
    pass

try:
    import torch

    result["torch_version"] = getattr(torch, "__version__", "")
    result["cuda_available"] = bool(torch.cuda.is_available())
    result["cuda_device_count"] = int(torch.cuda.device_count())
    result["cuda_name"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else ""
except Exception as exc:
    result["torch_error"] = f"{type(exc).__name__}: {exc}"

root = Path.cwd()
project_root = Path(os.environ.get("HEALTH_PROJECT_ROOT", root))
data_dir = root / "data"
dataset_info_path = data_dir / "dataset_info.json"
expected_datasets = {
    "health_monitoring_single": "single_turn_monitoring_focus_zh_medical.jsonl",
    "health_monitoring_multi": "multi_turn_monitoring_focus_zh_medical.jsonl",
    "health_public_single": "single_turn_public_zh_medical.jsonl",
    "health_public_multi": "multi_turn_public_zh_medical.jsonl",
    "reason_tool_use_demo_50": "reason_tool_use_demo_50.jsonl",
    "glaive_toolcall_zh_demo": "glaive_toolcall_zh_demo.json",
    "dpo_zh_demo": "dpo_zh_demo.json",
}
try:
    dataset_info = json.loads(dataset_info_path.read_text(encoding="utf-8"))
    for key, file_name in expected_datasets.items():
        entry = dataset_info.get(key)
        result["datasets"][key] = {
            "registered": entry is not None,
            "file_name": file_name,
            "file_exists": (data_dir / file_name).is_file(),
            "formatting": entry.get("formatting", "alpaca") if isinstance(entry, dict) else None,
            "ranking": bool(entry.get("ranking", False)) if isinstance(entry, dict) else False,
        }
except Exception as exc:
    result["dataset_error"] = f"{type(exc).__name__}: {exc}"

for yaml_name, data_name in {
    "v1_sft_demo.yaml": "v1_sft_demo.jsonl",
    "v1_dpo_demo.yaml": "v1_dpo_demo.jsonl",
}.items():
    yaml_path = data_dir / yaml_name
    data_path = data_dir / data_name
    result["v1_datasets"][yaml_name] = {
        "yaml_exists": yaml_path.is_file(),
        "data_file": data_name,
        "data_exists": data_path.is_file(),
        "uses_local_file": data_name in yaml_path.read_text(encoding="utf-8") if yaml_path.is_file() else False,
    }

result["native_ready"]["webui"] = result["modules"]["llamafactory"] and result["modules"]["gradio"]
result["native_ready"]["sft_lora"] = all(result["modules"][name] for name in ["torch", "transformers", "peft", "datasets", "accelerate"])
result["native_ready"]["qlora_4bit_8bit"] = result["native_ready"]["sft_lora"] and result["modules"]["bitsandbytes"]
result["native_ready"]["preference_training"] = result["native_ready"]["sft_lora"] and result["modules"]["trl"]
result["native_ready"]["hf_evaluation"] = result["modules"]["evaluate"]
result["native_ready"]["vllm_serving"] = result["modules"]["vllm"] and platform.system().lower() != "windows"
result["native_ready"]["deepspeed_zero"] = result["modules"]["deepspeed"] and platform.system().lower() != "windows"
result["native_ready"]["flash_attention"] = result["modules"]["flash_attn"] and platform.system().lower() != "windows"
result["native_ready"]["unsloth_acceleration"] = result["modules"]["unsloth"] and platform.system().lower() != "windows"

compose_path = project_root / "configs" / "llm_finetune" / "docker-compose.llamafactory-gpu.yml"
start_gpu_stack = project_root / "scripts" / "start_llamafactory_gpu_stack.ps1"
docker_info = {
    "cli": shutil.which("docker") is not None,
    "compose_file": compose_path.is_file(),
    "start_script": start_gpu_stack.is_file(),
    "daemon": False,
    "server_version": "",
    "gpu_runtime_verified": False,
    "rtx50_base_image_exists": False,
    "health_image_exists": False,
    "health_image_cuda_tensor_ok": False,
    "health_image_torch": "",
    "health_image_cuda_name": "",
    "health_image_modules": {},
    "devel_image_exists": False,
    "devel_image_cuda_tensor_ok": False,
    "devel_image_torch": "",
    "devel_image_cuda_name": "",
    "devel_image_modules": {},
    "devel_image_nvcc": False,
    "devel_container_running": False,
    "container_running": False,
    "webui_url": "http://127.0.0.1:7861",
    "api_url": "http://127.0.0.1:8001",
    "devel_webui_url": "http://127.0.0.1:7862",
    "devel_api_url": "http://127.0.0.1:8002",
}
if docker_info["cli"]:
    try:
        info_proc = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        docker_info["daemon"] = info_proc.returncode == 0
        docker_info["server_version"] = info_proc.stdout.strip() if info_proc.returncode == 0 else ""
    except Exception as exc:
        docker_info["error"] = f"{type(exc).__name__}: {exc}"
    if docker_info["daemon"]:
        checks = {
            "gpu_runtime_verified": [
                "docker",
                "image",
                "inspect",
                "nvidia/cuda:12.8.1-base-ubuntu24.04",
            ],
            "rtx50_base_image_exists": ["docker", "image", "inspect", "nvidia/cuda:12.8.1-base-ubuntu24.04"],
            "health_image_exists": ["docker", "image", "inspect", "health-llamafactory-gpu:latest"],
            "devel_image_exists": ["docker", "image", "inspect", "health-llamafactory-gpu-devel:latest"],
        }
        for key, cmd in checks.items():
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                docker_info[key] = proc.returncode == 0
            except Exception:
                docker_info[key] = False
        try:
            ps_proc = subprocess.run(
                [
                    "docker",
                    "ps",
                    "--filter",
                    "name=health-llamafactory-gpu",
                    "--format",
                    "{{.Names}}",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            docker_info["container_running"] = "health-llamafactory-gpu" in ps_proc.stdout
        except Exception:
            docker_info["container_running"] = False
        try:
            devel_ps_proc = subprocess.run(
                [
                    "docker",
                    "ps",
                    "--filter",
                    "name=health-llamafactory-gpu-devel",
                    "--format",
                    "{{.Names}}",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            docker_info["devel_container_running"] = "health-llamafactory-gpu-devel" in devel_ps_proc.stdout
        except Exception:
            docker_info["devel_container_running"] = False

        def probe_docker_image(image_name: str) -> dict:
            probe_code = r"""
import importlib.util, json, subprocess
mods = ["llamafactory", "torch", "deepspeed", "flash_attn", "vllm", "unsloth", "liger_kernel"]
result = {"modules": {name: importlib.util.find_spec(name) is not None for name in mods}}
try:
    import torch
    result["torch"] = getattr(torch, "__version__", "")
    result["cuda_available"] = bool(torch.cuda.is_available())
    result["cuda_name"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else ""
    result["cuda_capability"] = torch.cuda.get_device_capability(0) if torch.cuda.is_available() else None
    if torch.cuda.is_available():
        x = torch.ones((1,), device="cuda")
        result["cuda_tensor_ok"] = float(x.cpu()[0]) == 1.0
    else:
        result["cuda_tensor_ok"] = False
except Exception as exc:
    result["cuda_tensor_ok"] = False
    result["error"] = f"{type(exc).__name__}: {exc}"
try:
    nvcc = subprocess.run(["nvcc", "-V"], capture_output=True, text=True, timeout=10)
    result["nvcc"] = nvcc.returncode == 0
except Exception:
    result["nvcc"] = False
print(json.dumps(result, ensure_ascii=False, default=str))
"""
            try:
                probe_proc = subprocess.run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--gpus",
                        "all",
                        image_name,
                        "python",
                        "-c",
                        probe_code,
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=45,
                )
                if probe_proc.returncode == 0:
                    return json.loads(probe_proc.stdout.strip().splitlines()[-1])
                return {"error": (probe_proc.stderr or probe_proc.stdout).strip()[-800:]}
            except Exception as exc:
                return {"error": f"{type(exc).__name__}: {exc}"}

        if docker_info["health_image_exists"]:
            probe_payload = probe_docker_image("health-llamafactory-gpu:latest")
            docker_info["health_image_cuda_tensor_ok"] = bool(probe_payload.get("cuda_tensor_ok"))
            docker_info["health_image_torch"] = str(probe_payload.get("torch", ""))
            docker_info["health_image_cuda_name"] = str(probe_payload.get("cuda_name", ""))
            docker_info["health_image_modules"] = probe_payload.get("modules", {})
            docker_info["health_image_nvcc"] = bool(probe_payload.get("nvcc", False))
            if probe_payload.get("error"):
                docker_info["health_image_error"] = str(probe_payload.get("error"))
        if docker_info["devel_image_exists"]:
            devel_probe_payload = probe_docker_image("health-llamafactory-gpu-devel:latest")
            docker_info["devel_image_cuda_tensor_ok"] = bool(devel_probe_payload.get("cuda_tensor_ok"))
            docker_info["devel_image_torch"] = str(devel_probe_payload.get("torch", ""))
            docker_info["devel_image_cuda_name"] = str(devel_probe_payload.get("cuda_name", ""))
            docker_info["devel_image_modules"] = devel_probe_payload.get("modules", {})
            docker_info["devel_image_nvcc"] = bool(devel_probe_payload.get("nvcc", False))
            if devel_probe_payload.get("error"):
                docker_info["devel_image_error"] = str(devel_probe_payload.get("error"))

result["docker_ready"] = {
    **docker_info,
    "gpu_stack_configured": docker_info["daemon"] and docker_info["compose_file"] and docker_info["start_script"],
    "high_perf_training_route_configured": docker_info["daemon"] and docker_info["compose_file"],
    "high_perf_training_available": docker_info["daemon"] and docker_info["health_image_cuda_tensor_ok"],
    "high_perf_devel_available": docker_info["daemon"] and docker_info["devel_image_cuda_tensor_ok"] and docker_info["devel_image_nvcc"],
    "deepspeed_zero": docker_info["daemon"] and docker_info["devel_image_cuda_tensor_ok"] and docker_info["devel_image_modules"].get("deepspeed", False),
    "flash_attention": docker_info["daemon"] and docker_info["devel_image_cuda_tensor_ok"] and docker_info["devel_image_modules"].get("flash_attn", False),
    "vllm_serving_route": docker_info["daemon"] and docker_info["devel_image_cuda_tensor_ok"] and docker_info["devel_image_modules"].get("vllm", False),
    "unsloth_route": docker_info["daemon"] and docker_info["devel_image_cuda_tensor_ok"] and docker_info["devel_image_modules"].get("unsloth", False),
}

if platform.system().lower() == "windows":
    result["recommendations"].append(
        "Use native Windows for WebUI, SFT/LoRA, QLoRA and TRL preference training; use LLaMA-Factory docker/docker-cuda or WSL2 Linux for DeepSpeed, FlashAttention, vLLM and Unsloth."
    )
if not result["native_ready"]["qlora_4bit_8bit"]:
    result["recommendations"].append("Install bitsandbytes in the selected conda environment before selecting 4-bit/8-bit quantization.")
if not result["native_ready"]["hf_evaluation"]:
    result["recommendations"].append("Install evaluate to enable Hugging Face metric evaluation workflows.")
if any(not item["registered"] or not item["file_exists"] for item in result["datasets"].values()):
    result["recommendations"].append("Register all local JSON/JSONL datasets in data/dataset_info.json before selecting them in the WebUI.")
if any(not item["yaml_exists"] or not item["data_exists"] or not item["uses_local_file"] for item in result["v1_datasets"].values()):
    result["recommendations"].append("Point v1 dataset YAML files at their local JSONL files before testing the v1 trainer/data engine.")

print(json.dumps(result, ensure_ascii=False, indent=2))
'@

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:LLAMA_FACTORY_ROOT = $LLaMAFactoryRoot
$env:HEALTH_PROJECT_ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $LLaMAFactoryRoot
$probe | & $python -
