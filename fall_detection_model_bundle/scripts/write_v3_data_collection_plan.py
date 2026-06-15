from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "v3_upgrade_lab"


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Write concrete V3 data collection and labeling plan.")
    parser.add_argument("--output", default=str(LAB / "reports" / "data_collection_plan.v3.md"))
    parser.add_argument("--json-output", default=str(LAB / "reports" / "data_collection_plan.v3.json"))
    args = parser.parse_args()

    taxonomy = load_yaml(LAB / "configs" / "scene_taxonomy.v3.yaml")
    scene_types = taxonomy.get("scene_types", {})
    plan = []
    for scene, info in scene_types.items():
        negatives = info.get("required_negatives", [])
        plan.append(
            {
                "scene_type": scene,
                "minimum_positive_clips": 8,
                "minimum_hard_negative_clips_per_action": 6,
                "required_negatives": negatives,
                "capture_notes": info.get("risk_context", ""),
                "sidecar_required_fields": taxonomy.get("metadata_fields", []),
            }
        )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "minimum_total_positive_clips": sum(item["minimum_positive_clips"] for item in plan),
        "minimum_total_hard_negative_clips": sum(
            len(item["required_negatives"]) * item["minimum_hard_negative_clips_per_action"] for item in plan
        ),
        "plan": plan,
    }
    Path(args.json_output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# V3 Data Collection Plan",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "This plan lists the minimum authorized scene data needed before V3 can replace the current production fall model.",
        "",
    ]
    for item in plan:
        lines.extend(
            [
                f"## {item['scene_type']}",
                "",
                f"- Positive fall clips: {item['minimum_positive_clips']}",
                f"- Hard-negative clips per action: {item['minimum_hard_negative_clips_per_action']}",
                f"- Notes: {item['capture_notes']}",
                f"- Required hard negatives: {', '.join(item['required_negatives']) or 'none'}",
                "",
            ]
        )
    lines.extend(
        [
            "## Sidecar Example",
            "",
            "```json",
            json.dumps(
                {
                    "label": "fall_transition",
                    "kind": "positive",
                    "scene_type": "living_room_far_view",
                    "segment_start_s": 2.4,
                    "segment_end_s": 6.8,
                    "target_user_id": "elder_demo_001",
                    "camera_id": "CAMERA-192.168.8.254",
                    "lighting": "normal",
                    "distance_level": "far",
                    "occlusion_level": "partial",
                    "multi_person": False,
                    "target_visible": True,
                    "authorized_for_training": True,
                },
                ensure_ascii=False,
                indent=2,
            ),
            "```",
            "",
        ]
    )
    Path(args.output).write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"output": args.output, "json_output": args.json_output}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
