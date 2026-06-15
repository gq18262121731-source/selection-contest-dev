from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ModelFinetunePaths:
    project_root: Path
    llama_factory_root: Path

    @property
    def config_dir(self) -> Path:
        return self.project_root / "configs" / "llm_finetune"

    @property
    def eval_dir(self) -> Path:
        return self.project_root / "evals" / "health_llm"

    @property
    def export_dir(self) -> Path:
        return self.project_root / "data" / "llm_finetune"

    @property
    def runtime_dir(self) -> Path:
        return self.project_root / "runtime_logs" / "llm_finetune"


class ModelFinetuneService:
    """Read-only management surface for the LLM fine-tuning subsystem.

    The service deliberately avoids touching camera, alarm, or agent runtime
    state. It only reads/writes fine-tuning assets and runs bounded scripts.
    """

    def __init__(self, *, project_root: Path, llama_factory_root: Path | None = None) -> None:
        self.paths = ModelFinetunePaths(
            project_root=project_root,
            llama_factory_root=llama_factory_root or Path("D:/Program/LLaMA-Factory"),
        )

    def overview(self) -> dict[str, Any]:
        capability = self.capability_snapshot()
        return {
            "architecture": [
                {"name": "data", "title": "数据层", "status": self._data_status()},
                {"name": "training", "title": "训练层", "status": self._training_status(capability)},
                {"name": "evaluation", "title": "评测层", "status": self._evaluation_status()},
                {"name": "deployment", "title": "部署层", "status": self._adapter_status()},
            ],
            "capability": capability,
            "templates": self.training_templates(),
            "datasets": self.dataset_exports(),
            "eval_gates": self.eval_gates(),
            "adapters": self.adapter_registry(),
            "commands": self.commands(),
        }

    def capability_snapshot(self) -> dict[str, Any]:
        script = self.paths.project_root / "scripts" / "model_tuning_capabilities.ps1"
        if not script.exists():
            return {"ok": False, "error": f"missing capability script: {script}"}
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                cwd=self.paths.project_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
        except Exception as exc:  # pragma: no cover - defensive runtime path
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        if proc.returncode != 0:
            return {"ok": False, "error": proc.stderr.strip() or proc.stdout.strip()}
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"raw": proc.stdout}
        return {"ok": True, **payload}

    def training_templates(self) -> list[dict[str, Any]]:
        templates: list[dict[str, Any]] = []
        for path in sorted(self.paths.config_dir.glob("qwen_*.yaml")):
            text = path.read_text(encoding="utf-8")
            templates.append(
                {
                    "name": path.stem,
                    "path": str(path),
                    "strategy": self._infer_strategy(path.name, text),
                    "accelerators": self._infer_accelerators(text),
                    "command": f"cd {self.paths.llama_factory_root} && llamafactory-cli train {path}",
                }
            )
        return templates

    def dataset_exports(self) -> list[dict[str, Any]]:
        config_path = self.paths.config_dir / "datasets.yaml"
        exports: list[dict[str, Any]] = []
        expected = {
            "health_sft": "health_sft.jsonl",
            "tool_trace_sft": "tool_trace_sft.jsonl",
            "fall_alert_preference": "fall_alert_preference.jsonl",
            "safety_refusal": "safety_refusal.jsonl",
        }
        for key, file_name in expected.items():
            path = self.paths.export_dir / file_name
            exports.append(
                {
                    "name": key,
                    "path": str(path),
                    "exists": path.exists(),
                    "rows": self._count_jsonl(path),
                    "config_exists": config_path.exists(),
                }
            )
        return exports

    def adapter_registry(self) -> dict[str, Any]:
        path = self.paths.config_dir / "adapters.json"
        if not path.exists():
            return {"version": 0, "routes": [], "error": "missing adapter registry"}
        payload = json.loads(path.read_text(encoding="utf-8"))
        routes = []
        for route in payload.get("routes", []):
            adapter_path = Path(str(route.get("adapter_path", "")))
            routes.append({**route, "path_exists": adapter_path.exists()})
        return {**payload, "routes": routes}

    def eval_gates(self) -> dict[str, Any]:
        gates_path = self.paths.eval_dir / "gates.json"
        if not gates_path.exists():
            return {"exists": False, "suites": []}
        payload = json.loads(gates_path.read_text(encoding="utf-8"))
        suites = []
        for suite in payload.get("required_suites", []):
            path = self.paths.eval_dir / suite
            suites.append({"name": suite, "exists": path.exists(), "cases": self._count_jsonl(path)})
        return {**payload, "exists": True, "suites": suites}

    def export_seed_datasets(self) -> dict[str, Any]:
        script = self.paths.project_root / "scripts" / "export_llm_finetune_dataset.py"
        summary = self.paths.runtime_dir / "last_export_summary.json"
        self.paths.runtime_dir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [
                sys.executable,
                str(script),
                "--output-dir",
                str(self.paths.export_dir),
                "--summary",
                str(summary),
            ],
            cwd=self.paths.project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if proc.returncode != 0:
            return {"ok": False, "error": proc.stderr.strip() or proc.stdout.strip()}
        return {"ok": True, "summary": json.loads(summary.read_text(encoding="utf-8"))}

    def run_eval_gates(self) -> dict[str, Any]:
        script = self.paths.project_root / "scripts" / "eval_finetuned_llm.py"
        output = self.paths.runtime_dir / "last_eval_result.json"
        self.paths.runtime_dir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [sys.executable, str(script), "--eval-dir", str(self.paths.eval_dir), "--output", str(output)],
            cwd=self.paths.project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if proc.returncode != 0:
            return {"ok": False, "error": proc.stderr.strip() or proc.stdout.strip()}
        return {"ok": True, "result": json.loads(output.read_text(encoding="utf-8"))}

    def commands(self) -> list[dict[str, str]]:
        return [
            {
                "name": "启动微调工作台",
                "command": "powershell -ExecutionPolicy Bypass -File scripts/start_model_tuning_console.ps1",
            },
            {
                "name": "启动 GPU 版 LLaMA-Factory",
                "command": "powershell -ExecutionPolicy Bypass -File scripts/start_llamafactory_gpu_stack.ps1 -Build",
            },
            {
                "name": "启动 CUDA Devel 版 LLaMA-Factory",
                "command": "powershell -ExecutionPolicy Bypass -File scripts/start_llamafactory_devel_stack.ps1 -Build",
            },
            {
                "name": "验证 GPU 微调镜像",
                "command": "powershell -ExecutionPolicy Bypass -File scripts/verify_llamafactory_gpu_images.ps1",
            },
            {
                "name": "检查微调能力",
                "command": "powershell -ExecutionPolicy Bypass -File scripts/model_tuning_capabilities.ps1",
            },
            {
                "name": "导出领域数据集",
                "command": "python scripts/export_llm_finetune_dataset.py --output-dir data/llm_finetune",
            },
            {
                "name": "运行离线评测门禁",
                "command": "python scripts/eval_finetuned_llm.py --eval-dir evals/health_llm",
            },
        ]

    def _data_status(self) -> str:
        exports = self.dataset_exports()
        return "ready" if all(item["exists"] and item["rows"] > 0 for item in exports) else "needs_export"

    def _training_status(self, capability: dict[str, Any]) -> str:
        ready = capability.get("native_ready", {}) if capability.get("ok") else {}
        docker_ready = capability.get("docker_ready", {}) if capability.get("ok") else {}
        if docker_ready.get("high_perf_devel_available"):
            return "native_ready_gpu_devel_available"
        if docker_ready.get("high_perf_training_available"):
            return "native_ready_gpu_available"
        if docker_ready.get("gpu_stack_configured"):
            return "native_ready_gpu_route_configured"
        if ready.get("qlora_4bit_8bit") and ready.get("preference_training"):
            return "native_ready"
        if ready.get("sft_lora"):
            return "baseline_ready"
        return "blocked"

    def _evaluation_status(self) -> str:
        gates = self.eval_gates()
        suites = gates.get("suites", [])
        return "ready" if suites and all(item["exists"] and item["cases"] > 0 for item in suites) else "incomplete"

    def _adapter_status(self) -> str:
        routes = self.adapter_registry().get("routes", [])
        if routes and all(route.get("path_exists") for route in routes):
            return "ready"
        return "registered" if routes else "missing"

    @staticmethod
    def _count_jsonl(path: Path) -> int:
        if not path.exists():
            return 0
        with path.open("r", encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())

    @staticmethod
    def _infer_strategy(name: str, text: str) -> str:
        if "dpo" in name or "stage: dpo" in text:
            return "DPO preference alignment"
        if "qlora" in name or "quantization_bit: 4" in text:
            return "QLoRA low-VRAM SFT"
        if "tool" in name:
            return "Tool-call SFT"
        if "safety" in name:
            return "Safety SFT"
        return "LoRA SFT"

    @staticmethod
    def _infer_accelerators(text: str) -> list[str]:
        accelerators: list[str] = []
        if "quantization_bit: 4" in text:
            accelerators.append("4-bit quantization")
        if "gradient_checkpointing: true" in text:
            accelerators.append("gradient checkpointing")
        if "packing: true" in text:
            accelerators.append("sequence packing")
        if "paged_adamw" in text:
            accelerators.append("paged optimizer")
        return accelerators
