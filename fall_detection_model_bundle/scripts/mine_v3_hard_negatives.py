from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "v3_upgrade_lab"


def iter_summary_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.name.endswith(".json"):
            files.append(path)
        elif path.is_dir():
            files.extend(path.rglob("summary.json"))
            files.extend(path.rglob("*summary*.json"))
    return sorted(set(files))


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def normalize_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("summaries"), list):
            return [item for item in payload["summaries"] if isinstance(item, dict)]
        if "passed" in payload or "confirmed_count" in payload:
            return [payload]
    return []


def is_hard_negative_failure(item: dict[str, Any]) -> bool:
    kind = str(item.get("expected_kind") or item.get("kind") or "").lower()
    reason = str(item.get("failure_reason") or "").lower()
    confirmed = int(item.get("confirmed_count") or 0)
    return kind in {"negative", "normal", "hard_negative"} and (confirmed > 0 or reason == "confirmed_false_positive")


def is_positive_failure(item: dict[str, Any]) -> bool:
    kind = str(item.get("expected_kind") or item.get("kind") or "").lower()
    reason = str(item.get("failure_reason") or "").lower()
    confirmed = int(item.get("confirmed_count") or 0)
    return kind in {"positive", "fall"} and (confirmed <= 0 or reason == "missed_confirmed_fall")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mine replay reports for hard-negative and false-negative V3 training items.")
    parser.add_argument("--report-dir", action="append", default=[str(LAB / "reports")])
    parser.add_argument("--output", default=str(LAB / "manifests" / "hard_negative_mining.v3.csv"))
    parser.add_argument("--json-output", default=str(LAB / "reports" / "hard_negative_mining.v3.json"))
    args = parser.parse_args()

    report_files = iter_summary_files([Path(p).expanduser().resolve() for p in args.report_dir])
    rows: list[dict[str, Any]] = []
    for report_file in report_files:
        payload = load_json(report_file)
        for item in normalize_items(payload):
            failure_type = ""
            if is_hard_negative_failure(item):
                failure_type = "confirmed_false_positive_hard_negative"
            elif is_positive_failure(item):
                failure_type = "missed_confirmed_positive"
            if not failure_type:
                continue
            rows.append(
                {
                    "failure_type": failure_type,
                    "source": str(item.get("source") or ""),
                    "label": str(item.get("label") or ""),
                    "expected_kind": str(item.get("expected_kind") or ""),
                    "candidate": str((item.get("candidate") or {}).get("slug") or item.get("profile") or ""),
                    "confirmed_count": int(item.get("confirmed_count") or 0),
                    "suspected_count": int(item.get("suspected_count") or 0),
                    "max_fall_score": float(item.get("max_fall_score") or 0.0),
                    "failure_reason": str(item.get("failure_reason") or ""),
                    "report_file": str(report_file),
                }
            )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        with output.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    else:
        output.write_text("", encoding="utf-8")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "report_files": len(report_files),
        "mined_items": len(rows),
        "hard_negative_false_positives": sum(1 for row in rows if row["failure_type"] == "confirmed_false_positive_hard_negative"),
        "positive_misses": sum(1 for row in rows if row["failure_type"] == "missed_confirmed_positive"),
        "csv": str(output),
    }
    Path(args.json_output).write_text(json.dumps({"summary": summary, "items": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
