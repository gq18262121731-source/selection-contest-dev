from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "v3_upgrade_lab"


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_replay_summaries() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted((LAB / "reports").glob("replay_matrix_*/summary.json")):
        payload = load_json(path)
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    item["_summary_path"] = str(path)
                    items.append(item)
    return items


def best_replay_status(items: list[dict[str, Any]]) -> dict[str, Any]:
    positives = [i for i in items if str(i.get("expected_kind")) in {"positive", "fall"}]
    negatives = [i for i in items if str(i.get("expected_kind")) in {"negative", "normal", "hard_negative"}]
    any_positive_confirmed = any(int(i.get("confirmed_count") or 0) > 0 for i in positives)
    any_negative_confirmed = any(int(i.get("confirmed_count") or 0) > 0 for i in negatives)
    return {
        "positive_runs": len(positives),
        "negative_runs": len(negatives),
        "any_positive_confirmed": any_positive_confirmed,
        "any_negative_confirmed": any_negative_confirmed,
        "positive_failures": [i for i in positives if not i.get("passed")],
        "negative_failures": [i for i in negatives if not i.get("passed")],
    }


def detector_status() -> dict[str, Any]:
    v3_results = LAB / "experiments" / "yolo_detector" / "yolo26n_fall_detector_v3_cpu_refine" / "results.csv"
    probe_results = LAB / "experiments" / "yolo_detector" / "yolo26n_fall_detector_v3_cpu_probe" / "results.csv"
    return {
        "v3_detector_path": str(LAB / "weights" / "yolo26" / "yolo26_fall_detector_v3_best.pt"),
        "v3_detector_exists": (LAB / "weights" / "yolo26" / "yolo26_fall_detector_v3_best.pt").exists(),
        "cpu_probe_results_csv": str(probe_results) if probe_results.exists() else "",
        "cpu_refine_results_csv": str(v3_results) if v3_results.exists() else "",
        "baseline_detector_reference": str(ROOT / "weights" / "yolo_fall_detector_v1.pt"),
        "decision": "blocked_from_promotion_until_metrics_exceed_baseline",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Write V3 replacement gate report.")
    parser.add_argument("--output", default=str(LAB / "reports" / "replacement_gate_report.v3.md"))
    parser.add_argument("--json-output", default=str(LAB / "reports" / "replacement_gate_report.v3.json"))
    args = parser.parse_args()

    replay = best_replay_status(load_replay_summaries())
    detector = detector_status()
    promotable = (
        replay["positive_runs"] > 0
        and replay["negative_runs"] > 0
        and replay["any_positive_confirmed"]
        and not replay["any_negative_confirmed"]
        and detector["decision"] != "blocked_from_promotion_until_metrics_exceed_baseline"
    )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "promotable": promotable,
        "replay": replay,
        "detector": detector,
        "required_to_promote": [
            "YOLO26 detector validation metrics must match or exceed baseline detector.",
            "At least one positive private-scene replay must reach confirmed_fall.",
            "Hard-negative private-scene replay must have zero confirmed_fall.",
            "Run on CUDA or equivalent accelerator for full training, not CPU probe only.",
            "Add authorized scene videos for bedroom/living_room/corridor/bathroom categories.",
        ],
    }
    Path(args.json_output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Fall Detection V3 Replacement Gate",
        "",
        f"Generated: {report['generated_at']}",
        "",
        f"Promotable now: `{str(promotable).lower()}`",
        "",
        "## Decision",
        "",
    ]
    if promotable:
        lines.append("V3 passed the configured gates and may be promoted through shadow/gray rollout.")
    else:
        lines.append("V3 is **not safe to promote as a full replacement yet**. The current production detector/profile must remain active.")
    lines.extend(
        [
            "",
            "## Evidence",
            "",
            f"- Positive replay runs: {replay['positive_runs']}",
            f"- Negative/hard-negative replay runs: {replay['negative_runs']}",
            f"- Any positive confirmed: {replay['any_positive_confirmed']}",
            f"- Any negative confirmed: {replay['any_negative_confirmed']}",
            f"- V3 detector exists: {detector['v3_detector_exists']}",
            f"- Detector decision: {detector['decision']}",
            "",
            "## Required Before Replacement",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in report["required_to_promote"])
    lines.extend(
        [
            "",
            "## Safe Current Action",
            "",
            "Keep `FALL_DETECTION_PROFILE=private_scene_fusion_v2` for production. Use V3 only in replay/shadow mode until these gates pass.",
            "",
        ]
    )
    Path(args.output).write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"promotable": promotable, "output": args.output}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
