from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "v3_upgrade_lab"


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def iter_items(report_dir: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in report_dir.rglob("summary.json"):
        payload = load_json(path)
        if isinstance(payload, list):
            items.extend([item for item in payload if isinstance(item, dict)])
    return items


def evaluate_profile(items: list[dict[str, Any]], threshold: float, detector_weight: float, temporal_weight: float, posture_weight: float) -> dict[str, Any]:
    tp = fp = fn = tn = 0
    for item in items:
        kind = str(item.get("expected_kind") or "").lower()
        observed = float(item.get("max_fall_score") or 0.0)
        score = observed * max(detector_weight + temporal_weight + posture_weight, 0.01)
        pred = score >= threshold
        positive = kind in {"positive", "fall"}
        if pred and positive:
            tp += 1
        elif pred and not positive:
            fp += 1
        elif not pred and positive:
            fn += 1
        else:
            tn += 1
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)
    return {"threshold": threshold, "precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def main() -> int:
    parser = argparse.ArgumentParser(description="Search conservative V3 fusion profile candidates from replay summaries.")
    parser.add_argument("--report-dir", default=str(LAB / "reports"))
    parser.add_argument("--registry", default=str(LAB / "configs" / "model_registry.v3.yaml"))
    parser.add_argument("--output", default=str(LAB / "reports" / "fusion_search.v3.json"))
    parser.add_argument("--profile-output", default=str(LAB / "configs" / "fusion_weights.v3.best.yaml"))
    args = parser.parse_args()

    items = iter_items(Path(args.report_dir))
    best: dict[str, Any] | None = None
    candidates = []
    for threshold_i in range(42, 76, 2):
        threshold = threshold_i / 100.0
        for detector_i in range(10, 36, 5):
            for temporal_i in range(35, 61, 5):
                posture_i = 100 - detector_i - temporal_i
                if posture_i < 10 or posture_i > 35:
                    continue
                metrics = evaluate_profile(items, threshold, detector_i / 100.0, temporal_i / 100.0, posture_i / 100.0)
                candidate = {
                    "threshold": threshold,
                    "weights": {
                        "gru": 0.12,
                        "hybrid": round(temporal_i / 100.0, 2),
                        "semantic": 0.0,
                        "posture": round(posture_i / 100.0, 2),
                        "detector": round(detector_i / 100.0, 2),
                    },
                    **metrics,
                }
                candidates.append(candidate)
                if metrics["fp"] == 0 and (best is None or (metrics["recall"], metrics["f1"]) > (best["recall"], best["f1"])):
                    best = candidate
    if best is None and candidates:
        best = max(candidates, key=lambda item: (item["f1"], -item["fp"]))

    registry = load_yaml(Path(args.registry))
    profile = {
        "fall_v3_final_promoted_candidate": {
            "description": "Generated candidate from replay fusion search. Requires manual promotion after full replay.",
            "threshold": float((best or {}).get("threshold", 0.65)),
            "alert_hold": 3 if int((best or {}).get("fp", 1)) == 0 else 4,
            "weights": (best or {}).get("weights", {}),
        }
    }
    Path(args.profile_output).write_text(yaml.safe_dump(profile, sort_keys=False, allow_unicode=True), encoding="utf-8")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": len(items),
        "best": best,
        "profile_output": args.profile_output,
        "source_registry_profiles": list(registry.get("profiles", {}).keys()),
    }
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
