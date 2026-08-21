from __future__ import annotations

import argparse
import json
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


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def status(path: Path) -> str:
    return "present" if path.exists() else "missing"


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a concise V3 upgrade status and next-action report.")
    parser.add_argument("--output", default=str(LAB / "reports" / "fall_detection_v3_upgrade_status.md"))
    args = parser.parse_args()

    stack = load_yaml(LAB / "configs" / "candidate_stack.yaml")
    registry = load_yaml(LAB / "configs" / "model_registry.v3.yaml")
    bootstrap = load_json(LAB / "reports" / "bootstrap_v3_upgrade_lab.json")
    yolo_models = stack.get("weights", {}).get("ultralytics", {}).get("models", [])

    lines = [
        "# Fall Detection V3 Upgrade Status",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Isolation",
        "",
        "- Production registry remains `fall_detection_model_bundle/configs/model_registry.yaml`.",
        "- V3 registry is `fall_detection_model_bundle/v3_upgrade_lab/configs/model_registry.v3.yaml`.",
        "- Backend can switch only when `FALL_DETECTION_MODEL_REGISTRY_PATH` is explicitly configured.",
        "",
        "## Candidate Weights",
        "",
    ]
    for model_name in yolo_models:
        path = LAB / "weights" / "yolo26" / model_name
        lines.append(f"- `{model_name}`: {status(path)}")
    lines.extend(["", "## Candidate Profiles", ""])
    for profile, config in registry.get("profiles", {}).items():
        lines.append(f"- `{profile}`: {config.get('description', '')}")
    lines.extend(["", "## Tool Probe", ""])
    if isinstance(bootstrap, dict):
        for item in bootstrap.get("packages", []):
            lines.append(f"- `{item.get('package')}`: {item.get('status')}")
    else:
        lines.append("- Bootstrap has not been run yet.")
    lines.extend(
        [
            "",
            "## Execution Order",
            "",
            "1. Run `bootstrap_v3_upgrade_lab.py --download` to pull candidate YOLO26 weights.",
            "2. Download/prepare public and private authorized datasets into the V3 lab.",
            "3. Train `train_yolo_fall_detector_v3.py` on the V3 dataset.",
            "4. Extract pose caches for YOLO26 and RTMPose/OpenMMLab candidates.",
            "5. Train temporal candidates: TCN/Transformer first, then ST-GCN/2s-AGCN/PoseC3D through MMAction2.",
            "6. Run `run_v3_replay_matrix.py` against positive and hard-negative clips.",
            "7. Promote only if hard-negative confirmed false positives are zero and positive recall is not worse than baseline.",
            "",
            "## Non-Negotiable Gates",
            "",
            "- No direct replacement of production weights before replay evidence exists.",
            "- No random internet clips for training unless explicit rights are confirmed.",
            "- Qwen/VLM review can downgrade or explain suspicious events, but cannot block emergency confirmed alarms.",
            "",
        ]
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
