from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "v3_upgrade_lab"


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def ensure_dirs() -> None:
    for relative in [
        "weights/yolo26",
        "weights/openmmlab",
        "datasets",
        "manifests",
        "pose_cache",
        "experiments",
        "reports",
        "exports",
        "configs",
    ]:
        (LAB / relative).mkdir(parents=True, exist_ok=True)


def run_command(command: list[str], *, cwd: Path | None = None, timeout: int = 600) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd or ROOT),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return False, f"{exc.__class__.__name__}: {exc}"
    output = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part)
    return completed.returncode == 0, output[-4000:]


def download_ultralytics_models(model_names: list[str], *, dry_run: bool = False) -> list[dict[str, Any]]:
    target_dir = LAB / "weights" / "yolo26"
    target_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for model_name in model_names:
        target = target_dir / model_name
        if target.exists():
            results.append({"model": model_name, "status": "exists", "path": str(target)})
            continue
        if dry_run:
            results.append({"model": model_name, "status": "planned", "path": str(target)})
            continue
        script = (
            "from pathlib import Path\n"
            "from ultralytics import YOLO\n"
            f"name = {model_name!r}\n"
            "model = YOLO(name)\n"
            "path = Path(getattr(model, 'ckpt_path', '') or name)\n"
            "print(path.resolve() if path.exists() else path)\n"
        )
        ok, output = run_command([sys.executable, "-c", script], cwd=target_dir, timeout=900)
        downloaded = target_dir / model_name
        if downloaded.exists():
            results.append({"model": model_name, "status": "downloaded", "path": str(downloaded)})
        elif ok:
            found = next(target_dir.glob(model_name), None)
            if found is not None:
                results.append({"model": model_name, "status": "downloaded", "path": str(found)})
            else:
                results.append({"model": model_name, "status": "ok_unverified", "output": output})
        else:
            results.append({"model": model_name, "status": "failed", "error": output})
    return results


def probe_packages(packages: list[str]) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    import_names = {
        "mmaction2": "mmaction",
        "label-studio": "label_studio",
        "onnxruntime-gpu": "onnxruntime",
    }
    for package in packages:
        module = import_names.get(package, package.replace("-", "_"))
        ok, output = run_command([sys.executable, "-c", f"import {module}; print(getattr({module}, '__version__', 'installed'))"])
        results.append({"package": package, "module": module, "status": "installed" if ok else "missing", "detail": output})
    return results


def download_tool_wheels(packages: list[str], *, dry_run: bool = False) -> list[dict[str, str]]:
    wheel_dir = LAB / "tools" / "wheels"
    wheel_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, str]] = []
    for package in packages:
        if dry_run:
            results.append({"package": package, "status": "planned", "target_dir": str(wheel_dir)})
            continue
        ok, output = run_command(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--no-deps",
                "--dest",
                str(wheel_dir),
                package,
            ],
            cwd=LAB,
            timeout=600,
        )
        results.append(
            {
                "package": package,
                "status": "downloaded" if ok else "failed",
                "target_dir": str(wheel_dir),
                "detail": output,
            }
        )
    return results


def write_tool_install_scripts(packages: list[str]) -> None:
    ps1 = LAB / "install_v3_tools.ps1"
    package_args = " ".join(packages)
    ps1.write_text(
        "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                "$python = if ($env:V3_PYTHON) { $env:V3_PYTHON } else { 'python' }",
                f"& $python -m pip install {package_args}",
                "# OpenMMLab packages can be installed separately when GPU/CUDA versions are fixed:",
                "# & $python -m pip install -U openmim",
                "# & $python -m mim install mmengine mmcv mmdet mmpose mmaction2",
                "",
            ]
        ),
        encoding="utf-8",
    )


def copy_baseline_registry_snapshot() -> None:
    source = ROOT / "configs" / "model_registry.yaml"
    target = LAB / "configs" / "model_registry.baseline.snapshot.yaml"
    if source.exists() and not target.exists():
        shutil.copy2(source, target)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the isolated fall-detection V3 upgrade lab.")
    parser.add_argument("--download", action="store_true", help="Download candidate Ultralytics model weights.")
    parser.add_argument("--download-tools", action="store_true", help="Download no-dependency wheels for optional V3 tools.")
    parser.add_argument("--dry-run", action="store_true", help="Create files and report planned downloads without network work.")
    args = parser.parse_args()

    ensure_dirs()
    copy_baseline_registry_snapshot()
    stack = load_yaml(LAB / "configs" / "candidate_stack.yaml")
    yolo_models = stack.get("weights", {}).get("ultralytics", {}).get("models", [])
    packages = list(stack.get("tools", {}).get("python_packages", []))
    packages.extend(stack.get("weights", {}).get("openmmlab", {}).get("packages", []))
    write_tool_install_scripts(packages)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lab": str(LAB),
        "download_requested": bool(args.download),
        "dry_run": bool(args.dry_run),
        "ultralytics": [],
        "packages": probe_packages(packages),
        "tool_wheels": [],
    }
    if args.download or args.dry_run:
        report["ultralytics"] = download_ultralytics_models(yolo_models, dry_run=args.dry_run)
    if args.download_tools or args.dry_run:
        report["tool_wheels"] = download_tool_wheels(packages, dry_run=args.dry_run)

    report_path = LAB / "reports" / "bootstrap_v3_upgrade_lab.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
