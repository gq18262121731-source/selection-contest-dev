from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate fall-event JSON summaries against a small labeled video manifest."
    )
    parser.add_argument(
        "manifest",
        type=Path,
        help="JSON manifest with items containing prediction_json and events.",
    )
    parser.add_argument(
        "--iou-threshold",
        type=float,
        default=0.20,
        help="Minimum temporal IoU for a predicted fall segment to match a labeled fall event.",
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def event_iou(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_start = float(left["start_s"])
    left_end = float(left["end_s"])
    right_start = float(right["start_s"])
    right_end = float(right["end_s"])
    inter = max(0.0, min(left_end, right_end) - max(left_start, right_start))
    union = max(left_end, right_end) - min(left_start, right_start)
    return inter / union if union > 0 else 0.0


def normalize_label_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in events:
        label = str(item.get("label") or item.get("status") or "").lower()
        if label != "fall":
            continue
        start = float(item.get("start_s", item.get("start_sec", 0.0)))
        end = float(item.get("end_s", item.get("end_sec", start)))
        if end <= start:
            continue
        normalized.append({"status": "fall", "start_s": start, "end_s": end})
    return normalized


def evaluate_item(item: dict[str, Any], *, iou_threshold: float) -> dict[str, Any]:
    prediction_path = Path(item["prediction_json"]).expanduser()
    prediction = load_json(prediction_path)
    predicted = [
        {
            "status": "fall",
            "start_s": float(segment["start_s"]),
            "end_s": float(segment["end_s"]),
            "max_fall_score": float(segment.get("max_fall_score", 0.0)),
        }
        for segment in prediction.get("fall_segments", [])
    ]
    labels = normalize_label_events(list(item.get("events") or []))

    matched_predictions: set[int] = set()
    matches: list[dict[str, Any]] = []
    for label_index, label in enumerate(labels):
        best_index = -1
        best_iou = 0.0
        for pred_index, pred in enumerate(predicted):
            if pred_index in matched_predictions:
                continue
            iou = event_iou(label, pred)
            if iou > best_iou:
                best_iou = iou
                best_index = pred_index
        if best_index >= 0 and best_iou >= iou_threshold:
            matched_predictions.add(best_index)
            matches.append(
                {
                    "label_index": label_index,
                    "prediction_index": best_index,
                    "iou": round(best_iou, 4),
                    "start_error_s": round(predicted[best_index]["start_s"] - label["start_s"], 3),
                    "end_error_s": round(predicted[best_index]["end_s"] - label["end_s"], 3),
                }
            )

    true_positive = len(matches)
    false_positive = max(0, len(predicted) - true_positive)
    false_negative = max(0, len(labels) - true_positive)
    return {
        "name": item.get("name") or prediction_path.stem,
        "prediction_json": str(prediction_path),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "predicted_fall_events": len(predicted),
        "labeled_fall_events": len(labels),
        "matches": matches,
    }


def main() -> int:
    args = parse_args()
    manifest = load_json(args.manifest.expanduser())
    items = manifest.get("items") if isinstance(manifest, dict) else manifest
    if not isinstance(items, list):
        raise ValueError("Manifest must be a list or an object with an items list.")

    results = [evaluate_item(item, iou_threshold=args.iou_threshold) for item in items]
    tp = sum(int(item["true_positive"]) for item in results)
    fp = sum(int(item["false_positive"]) for item in results)
    fn = sum(int(item["false_negative"]) for item in results)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    report = {
        "iou_threshold": args.iou_threshold,
        "metrics": {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
        },
        "items": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
