from __future__ import annotations

import argparse
import json
import shutil
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
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def copy_if_exists(source: Path, target_dir: Path) -> str:
    target_dir.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        return "missing"
    shutil.copy2(source, target_dir / source.name)
    return "copied"


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a V3 promoted candidate package without replacing production files.")
    parser.add_argument("--registry", default=str(LAB / "configs" / "model_registry.v3.yaml"))
    parser.add_argument("--fusion", default=str(LAB / "configs" / "fusion_weights.v3.best.yaml"))
    parser.add_argument("--output-dir", default=str(LAB / "exports" / "promoted"))
    parser.add_argument("--profile-name", default="fall_v3_final_promoted")
    parser.add_argument("--force-promoted", action="store_true", help="Export as promotable even if replacement gates failed.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    weights_dir = output_dir / "weights"
    configs_dir = output_dir / "configs"
    reports_dir = output_dir / "reports"
    weights_dir.mkdir(exist_ok=True)
    configs_dir.mkdir(exist_ok=True)
    reports_dir.mkdir(exist_ok=True)

    registry = load_yaml(Path(args.registry))
    fusion = load_yaml(Path(args.fusion))
    gate = load_json(LAB / "reports" / "replacement_gate_report.v3.json")
    gate_promotable = bool(gate.get("promotable")) if isinstance(gate, dict) else False
    export_profile_name = args.profile_name if (gate_promotable or args.force_promoted) else f"{args.profile_name}_blocked"
    final_profile = fusion.get("fall_v3_final_promoted_candidate") or registry.get("profiles", {}).get("fall_v3_shadow_yolo26_pose", {})
    registry.setdefault("profiles", {})[export_profile_name] = {
        **final_profile,
        "description": (
            "Promoted V3 candidate package. Use only after replay gates pass."
            if gate_promotable or args.force_promoted
            else "Blocked V3 candidate. Exported for review only; do not use for production replacement."
        ),
        "promotion_gate_passed": bool(gate_promotable or args.force_promoted),
    }
    registry["default_profile"] = export_profile_name

    copied: dict[str, str] = {}
    for name, entry in registry.get("models", {}).items():
        for key in ("path", "fallback_path"):
            value = entry.get(key)
            if not value:
                continue
            source = Path(value)
            if not source.is_absolute():
                source = ROOT / source
            copied[f"{name}.{key}"] = copy_if_exists(source, weights_dir)

    (configs_dir / "model_registry.v3.promoted.yaml").write_text(
        yaml.safe_dump(registry, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    for config_name in [
        "vlm_review.v3.yaml",
        "scene_roi_profiles.v3.yaml",
        "evaluation_gates.yaml",
        "alert_rules.v3_hard_negative_guard.yaml",
        "alert_rules.v3_high_recall.yaml",
    ]:
        copy_if_exists(LAB / "configs" / config_name, configs_dir)
    for report_name in [
        "fall_detection_v3_upgrade_status.md",
        "bootstrap_v3_upgrade_lab.json",
        "fusion_search.v3.json",
        "hard_negative_mining.v3.json",
        "vlm_review_eval.v3.json",
        "replacement_gate_report.v3.md",
        "replacement_gate_report.v3.json",
    ]:
        copy_if_exists(LAB / "reports" / report_name, reports_dir)

    rollback = [
        "# Rollback To Current Fall Detection",
        "",
        "Unset candidate registry configuration and return to the production registry/profile:",
        "",
        "```env",
        "FALL_DETECTION_MODEL_REGISTRY_PATH=",
        "FALL_DETECTION_PROFILE=private_scene_fusion_v2",
        "```",
        "",
        "Restart the backend after changing the environment.",
        "",
    ]
    (output_dir / "rollback_to_private_scene_fusion_v2.md").write_text("\n".join(rollback), encoding="utf-8")

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(output_dir),
        "profile_name": export_profile_name,
        "promotion_gate_passed": bool(gate_promotable or args.force_promoted),
        "copied": copied,
        "registry": str(configs_dir / "model_registry.v3.promoted.yaml"),
        "note": (
            "This package passed the recorded gate or was force-exported."
            if gate_promotable or args.force_promoted
            else "This package is blocked for production replacement. Keep production on private_scene_fusion_v2."
        ),
    }
    (output_dir / "package_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
