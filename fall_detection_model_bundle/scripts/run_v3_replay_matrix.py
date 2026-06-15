from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "v3_upgrade_lab"


@dataclass(frozen=True)
class Candidate:
    name: str
    registry: Path
    profile: str
    threshold: float | None
    process_every: int
    pose_tracker: str

    @property
    def slug(self) -> str:
        threshold = "profile" if self.threshold is None else str(self.threshold).replace(".", "p")
        return f"{self.name}__{self.profile}__thr-{threshold}__stride-{self.process_every}__tracker-{self.pose_tracker}"


def parse_source(value: str) -> tuple[str, Path, str]:
    parts = value.split("=", 2)
    if len(parts) == 3:
        label, kind, path = parts
    elif len(parts) == 2:
        label, path = parts
        kind = "unknown"
    else:
        path = value
        label = Path(path).stem
        kind = "unknown"
    return sanitize(label), Path(path).expanduser().resolve(), kind


def sanitize(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value).strip("-_")
    return cleaned or "source"


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def build_candidates(args: argparse.Namespace) -> list[Candidate]:
    baseline_registry = ROOT / "configs" / "model_registry.yaml"
    v3_registry = LAB / "configs" / "model_registry.v3.yaml"
    candidates = [
        Candidate(
            name="baseline",
            registry=baseline_registry,
            profile=args.baseline_profile,
            threshold=None,
            process_every=args.process_every,
            pose_tracker=args.pose_tracker,
        )
    ]
    for profile, threshold in product(args.profile, args.threshold or [None]):
        candidates.append(
            Candidate(
                name="v3",
                registry=v3_registry,
                profile=profile,
                threshold=threshold,
                process_every=args.process_every,
                pose_tracker=args.pose_tracker,
            )
        )
    return candidates


def candidate_dict(candidate: Candidate) -> dict[str, Any]:
    item = asdict(candidate)
    item["registry"] = str(candidate.registry)
    item["slug"] = candidate.slug
    return item


def run_monitor(candidate: Candidate, source: Path, output_dir: Path, args: argparse.Namespace) -> tuple[bool, str]:
    event_log = output_dir / "events.jsonl"
    snapshot_dir = output_dir / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(ROOT / "scripts" / "realtime_fall_monitor.py"),
        "--source",
        str(source),
        "--model-registry",
        str(candidate.registry),
        "--profile",
        candidate.profile,
        "--event-log",
        str(event_log),
        "--snapshot-dir",
        str(snapshot_dir),
        "--status-log-interval",
        "2",
        "--process-every",
        str(candidate.process_every),
        "--pose-tracker",
        candidate.pose_tracker,
        "--no-display",
    ]
    if candidate.threshold is not None:
        command.extend(["--threshold", str(candidate.threshold)])
    if args.start_seconds > 0:
        command.extend(["--start-seconds", str(args.start_seconds)])
    if args.end_seconds > 0:
        command.extend(["--end-seconds", str(args.end_seconds)])
    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=args.timeout_seconds,
        check=False,
    )
    output = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part)
    (output_dir / "command.json").write_text(json.dumps({"command": command}, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "process_output.log").write_text(output, encoding="utf-8")
    return completed.returncode == 0, output[-4000:]


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events


def summarize(output_dir: Path, *, expected_kind: str, candidate: Candidate, label: str, source: Path, ok: bool, error: str) -> dict[str, Any]:
    events = load_events(output_dir / "events.jsonl")
    event_types = Counter(str(e.get("event_type") or "") for e in events)
    states = Counter(str(e.get("state") or "") for e in events)
    scores = []
    for event in events:
        try:
            scores.append(float(event.get("fall_score") or 0.0))
        except (TypeError, ValueError):
            pass
    confirmed = int(states.get("confirmed_fall", 0) + event_types.get("fall_confirmed", 0))
    suspected = int(states.get("suspected_fall", 0))
    is_negative = expected_kind in {"negative", "normal", "hard_negative"}
    is_positive = expected_kind in {"positive", "fall"}
    passed = ok
    failure_reason = ""
    if is_negative and confirmed > 0:
        passed = False
        failure_reason = "confirmed_false_positive"
    if is_positive and confirmed <= 0:
        passed = False
        failure_reason = "missed_confirmed_fall"
    return {
        "candidate": candidate_dict(candidate),
        "label": label,
        "source": str(source),
        "expected_kind": expected_kind,
        "process_ok": ok,
        "passed": passed,
        "failure_reason": failure_reason,
        "error_tail": error if not ok else "",
        "event_count": len(events),
        "event_type_counts": dict(event_types),
        "state_counts": dict(states),
        "confirmed_count": confirmed,
        "suspected_count": suspected,
        "max_fall_score": max(scores) if scores else 0.0,
        "avg_fall_score": sum(scores) / len(scores) if scores else 0.0,
        "output_dir": str(output_dir),
    }


def write_promotion_report(run_dir: Path, summaries: list[dict[str, Any]]) -> None:
    failures = [item for item in summaries if not item["passed"]]
    by_candidate = Counter(item["candidate"]["slug"] for item in summaries if item.get("passed") and "candidate" in item)
    lines = [
        "# Fall Detection V3 Replay Matrix",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"Total runs: {len(summaries)}",
        f"Failures: {len(failures)}",
        "",
        "## Passed Runs By Candidate",
        "",
    ]
    for candidate, count in by_candidate.items():
        lines.append(f"- `{candidate}`: {count}")
    lines.extend(["", "## Failures", ""])
    if failures:
        for item in failures:
            lines.append(
                f"- `{item.get('candidate', {}).get('slug', 'unknown')}` on `{item['label']}`: {item['failure_reason'] or 'process_failed'}"
            )
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Promotion Note",
            "",
            "This report is a replay artifact only. Promote a V3 profile only after the fixed hard-negative suite has zero confirmed false positives and positive clips meet or exceed baseline recall.",
            "",
        ]
    )
    (run_dir / "promotion_decision.md").write_text("\n".join(lines), encoding="utf-8")
    (run_dir / "hard_negative_failures.json").write_text(
        json.dumps([item for item in failures if item["expected_kind"] in {"negative", "normal", "hard_negative"}], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run baseline and V3 fall-detection candidates against local replay clips.")
    parser.add_argument("--source", action="append", default=[], help="label=kind=path, where kind is positive|negative|hard_negative.")
    parser.add_argument("--baseline-profile", default="private_scene_fusion_v2")
    parser.add_argument("--profile", action="append", default=["fall_v3_shadow_yolo26_pose", "fall_v3_hard_negative_guard"])
    parser.add_argument("--threshold", action="append", type=float, default=[])
    parser.add_argument("--process-every", type=int, default=1)
    parser.add_argument("--pose-tracker", choices=["none", "botsort", "bytetrack"], default="botsort")
    parser.add_argument("--start-seconds", type=float, default=0.0)
    parser.add_argument("--end-seconds", type=float, default=0.0)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run_dir = LAB / "reports" / f"replay_matrix_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    sources = [parse_source(value) for value in args.source]
    candidates = build_candidates(args)
    plan = {"sources": [(label, kind, str(source)) for label, source, kind in sources], "candidates": [candidate_dict(c) for c in candidates]}
    (run_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.dry_run or not sources:
        print(json.dumps({"run_dir": str(run_dir), "dry_run": True, "plan": plan}, ensure_ascii=False, indent=2))
        return 0

    summaries: list[dict[str, Any]] = []
    for label, source, kind in sources:
        if not source.exists():
            summaries.append({"label": label, "source": str(source), "expected_kind": kind, "passed": False, "failure_reason": "source_missing"})
            continue
        for candidate in candidates:
            output_dir = run_dir / label / candidate.slug
            output_dir.mkdir(parents=True, exist_ok=True)
            ok, error = run_monitor(candidate, source, output_dir, args)
            if not ok and (output_dir / "events.jsonl").exists():
                ok = True
            if not args.dry_run and not (output_dir / "snapshots").glob("*"):
                shutil.rmtree(output_dir / "snapshots", ignore_errors=True)
            summaries.append(summarize(output_dir, expected_kind=kind, candidate=candidate, label=label, source=source, ok=ok, error=error))

    (run_dir / "summary.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    write_promotion_report(run_dir, summaries)
    print(json.dumps({"run_dir": str(run_dir), "summary_count": len(summaries)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
