from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.dependencies import get_target_user_fall_service


TRUE_VALUES = {"1", "true", "yes", "y", "target", "fall", "present"}


def _as_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in TRUE_VALUES


def _read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _resolve_image_path(manifest_path: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return (manifest_path.parent / candidate).resolve()


def _empty_metrics() -> dict[str, int]:
    return {"tp": 0, "tn": 0, "fp": 0, "fn": 0}


def _update_binary(metrics: dict[str, int], *, expected: bool, actual: bool) -> None:
    if expected and actual:
        metrics["tp"] += 1
    elif not expected and not actual:
        metrics["tn"] += 1
    elif not expected and actual:
        metrics["fp"] += 1
    else:
        metrics["fn"] += 1


def _summarize(metrics: dict[str, int]) -> dict[str, float | int]:
    tp = metrics["tp"]
    tn = metrics["tn"]
    fp = metrics["fp"]
    fn = metrics["fn"]
    total = tp + tn + fp + fn
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    false_positive_rate = fp / max(1, fp + tn)
    accuracy = (tp + tn) / max(1, total)
    return {
        **metrics,
        "total": total,
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "false_positive_rate": round(false_positive_rate, 4),
    }


def evaluate_manifest(
    *,
    manifest_path: Path,
    speed_mode: str,
    include_details: bool,
) -> dict[str, Any]:
    rows = _read_manifest(manifest_path)
    service = get_target_user_fall_service()
    target_metrics = _empty_metrics()
    fall_metrics = _empty_metrics()
    details: list[dict[str, Any]] = []

    for index, row in enumerate(rows, start=1):
        image_path = _resolve_image_path(manifest_path, row.get("path") or row.get("image") or "")
        expected_target = _as_bool(row.get("target_present"))
        expected_fall = _as_bool(row.get("fall"))
        session_id = row.get("session_id") or f"eval-{index}"

        if not image_path.exists():
            details.append({"index": index, "path": str(image_path), "error": "IMAGE_NOT_FOUND"})
            continue

        result = service.detect(
            image_path.read_bytes(),
            include_annotated_image=False,
            target_only=True,
            session_id=session_id,
            speed_mode=speed_mode,
        )
        target_match = result.get("target_match") or {}
        fall_result = result.get("fall_result") or {}
        actual_target = bool(target_match.get("matched")) and result.get("status") != "filtered_non_target"
        actual_fall = bool(fall_result.get("fall_detected")) or str(fall_result.get("status") or "") == "fall"

        _update_binary(target_metrics, expected=expected_target, actual=actual_target)
        _update_binary(fall_metrics, expected=expected_fall, actual=actual_fall)

        if include_details:
            details.append(
                {
                    "index": index,
                    "path": str(image_path),
                    "expected_target": expected_target,
                    "actual_target": actual_target,
                    "expected_fall": expected_fall,
                    "actual_fall": actual_fall,
                    "status": result.get("status"),
                    "target_match": target_match,
                    "fall_status": fall_result.get("status"),
                    "temporal_verification": fall_result.get("temporal_verification"),
                }
            )

    return {
        "manifest": str(manifest_path),
        "speed_mode": speed_mode,
        "target_identity": _summarize(target_metrics),
        "fall_detection": _summarize(fall_metrics),
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate target identity and target-only fall detection on labeled frames.")
    parser.add_argument("manifest", type=Path, help="CSV with columns: path,target_present,fall[,session_id]")
    parser.add_argument("--speed-mode", default="balanced", choices=["balanced", "low_latency", "fast", "turbo"])
    parser.add_argument("--details", action="store_true", help="Include per-frame results in the JSON output.")
    parser.add_argument("--output", type=Path, default=None, help="Optional path to write JSON metrics.")
    args = parser.parse_args()

    payload = evaluate_manifest(
        manifest_path=args.manifest.resolve(),
        speed_mode=args.speed_mode,
        include_details=args.details,
    )
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
