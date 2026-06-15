from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "v3_upgrade_lab"


def run_step(name: str, command: list[str]) -> dict[str, object]:
    completed = subprocess.run(command, cwd=str(ROOT.parent), text=True, capture_output=True, timeout=120, check=False)
    return {
        "name": name,
        "command": command,
        "returncode": completed.returncode,
        "ok": completed.returncode == 0,
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the V3 pipeline in dry-run/scaffold mode.")
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()

    py = args.python
    steps = [
        ("build_scene_manifest", [py, str(ROOT / "scripts" / "build_v3_scene_manifest.py")]),
        ("mine_hard_negatives", [py, str(ROOT / "scripts" / "mine_v3_hard_negatives.py")]),
        ("fusion_search", [py, str(ROOT / "scripts" / "search_v3_fusion_from_replay.py")]),
        ("vlm_eval", [py, str(ROOT / "scripts" / "evaluate_v3_vlm_review.py")]),
        ("export_promoted_package", [py, str(ROOT / "scripts" / "export_v3_promoted_package.py")]),
        ("write_status", [py, str(ROOT / "scripts" / "write_v3_upgrade_report.py")]),
    ]
    results = [run_step(name, command) for name, command in steps]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ok": all(bool(item["ok"]) for item in results),
        "steps": results,
    }
    out = LAB / "reports" / "v3_full_pipeline_dryrun.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "report": str(out)}, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
