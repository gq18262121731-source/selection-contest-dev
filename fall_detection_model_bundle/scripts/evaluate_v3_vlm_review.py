from __future__ import annotations

import argparse
import csv
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


def parse_expected(row: dict[str, str]) -> str:
    kind = row.get("kind", "").lower()
    label = row.get("label_name", "").lower()
    if kind == "positive" or "fall" in label:
        return "fall"
    if kind in {"hard_negative", "neutral"}:
        return "no_fall"
    return "uncertain"


def heuristic_review(row: dict[str, str]) -> dict[str, Any]:
    """Offline evaluator used before an actual VLM provider is configured.

    It validates the JSON contract and creates a target file for future VLM
    comparisons without sending frames to any external service.
    """
    expected = parse_expected(row)
    label = row.get("label_name", "")
    scene = row.get("scene_type", "unknown")
    if expected == "fall":
        judgement = "possible_fall" if "transition" in label else "fall"
        action = "notify"
    elif expected == "no_fall":
        judgement = "no_fall"
        action = "downgrade"
    else:
        judgement = "uncertain"
        action = "review"
    return {
        "judgement": judgement,
        "confidence": "medium",
        "target_person": "uncertain" if not row.get("target_user_id") else "yes",
        "scene_type": scene,
        "evidence": [f"manifest_label={label}", f"scene={scene}"],
        "false_alarm_risk": [label] if expected == "no_fall" else [],
        "recommended_action": action,
        "report_zh": f"离线复核样本：场景 {scene}，标注 {label}，建议 {action}。",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate or scaffold V3 VLM review cases from the scene manifest.")
    parser.add_argument("--manifest", default=str(LAB / "manifests" / "scene_manifest.v3.csv"))
    parser.add_argument("--config", default=str(LAB / "configs" / "vlm_review.v3.yaml"))
    parser.add_argument("--output", default=str(LAB / "reports" / "vlm_review_eval.v3.json"))
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    config = load_yaml(Path(args.config))
    rows: list[dict[str, str]] = []
    manifest = Path(args.manifest)
    if manifest.exists() and manifest.stat().st_size > 0:
        with manifest.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))[: args.limit]

    cases = []
    parse_ok = 0
    emergency_passthrough_ok = 0
    for row in rows:
        review = heuristic_review(row)
        parse_ok += int(all(key in review for key in config.get("json_schema", {}).get("required_fields", [])))
        expected = parse_expected(row)
        if expected == "fall" and review["recommended_action"] in {"notify", "emergency", "review"}:
            emergency_passthrough_ok += 1
        elif expected != "fall":
            emergency_passthrough_ok += 1
        cases.append({"video_path": row.get("video_path"), "expected": expected, "review": review})

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cases": len(cases),
        "json_contract_rate": parse_ok / max(len(cases), 1),
        "emergency_passthrough_rate": emergency_passthrough_ok / max(len(cases), 1),
        "provider_priority": config.get("provider_priority", []),
        "items": cases,
    }
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "items"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
