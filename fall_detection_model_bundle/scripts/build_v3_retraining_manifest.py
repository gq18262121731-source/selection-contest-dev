from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "v3_upgrade_lab"


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_mined_items(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return [item for item in payload["items"] if isinstance(item, dict)]
    return []


def priority_for(item: dict[str, Any]) -> int:
    failure_type = str(item.get("failure_type") or "")
    if failure_type == "confirmed_false_positive_hard_negative":
        return 1
    if failure_type == "missed_confirmed_positive":
        return 2
    return 3


def recommended_action(item: dict[str, Any]) -> str:
    failure_type = str(item.get("failure_type") or "")
    if failure_type == "confirmed_false_positive_hard_negative":
        return "add_as_hard_negative; verify state-machine guard; add VLM downgrade example"
    if failure_type == "missed_confirmed_positive":
        return "add_positive_segment; strengthen detector/temporal recall; review fall transition labels"
    return "manual_review"


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert mined V3 failures into a retraining/action manifest.")
    parser.add_argument("--input", default=str(LAB / "reports" / "hard_negative_mining.v3.json"))
    parser.add_argument("--output", default=str(LAB / "manifests" / "retraining_manifest.v3.csv"))
    parser.add_argument("--json-output", default=str(LAB / "reports" / "retraining_manifest.v3.json"))
    args = parser.parse_args()

    items = load_mined_items(Path(args.input))
    rows: list[dict[str, Any]] = []
    for item in items:
        rows.append(
            {
                "priority": priority_for(item),
                "failure_type": item.get("failure_type", ""),
                "source": item.get("source", ""),
                "label": item.get("label", ""),
                "expected_kind": item.get("expected_kind", ""),
                "candidate": item.get("candidate", ""),
                "confirmed_count": item.get("confirmed_count", 0),
                "suspected_count": item.get("suspected_count", 0),
                "max_fall_score": item.get("max_fall_score", 0.0),
                "recommended_action": recommended_action(item),
                "status": "todo",
            }
        )
    rows.sort(key=lambda row: (int(row["priority"]), str(row["source"])))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        with output.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    else:
        output.write_text("", encoding="utf-8")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": len(rows),
        "priority_1": sum(1 for row in rows if row["priority"] == 1),
        "priority_2": sum(1 for row in rows if row["priority"] == 2),
        "csv": str(output),
        "rows": rows,
    }
    Path(args.json_output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
