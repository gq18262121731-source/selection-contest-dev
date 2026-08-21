from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.fall_event_state_machine import FallEventStateMachine, FallEventStateMachineConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Grid-search fall event smoothing parameters from saved frame records and labels."
    )
    parser.add_argument("manifest", type=Path, help="JSON manifest used by evaluate_fall_videos.py.")
    parser.add_argument("--iou-threshold", type=float, default=0.20)
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_label_events(events: list[dict[str, Any]]) -> list[dict[str, float]]:
    normalized: list[dict[str, float]] = []
    for item in events:
        label = str(item.get("label") or item.get("status") or "").lower()
        if label != "fall":
            continue
        start = float(item.get("start_s", item.get("start_sec", 0.0)))
        end = float(item.get("end_s", item.get("end_sec", start)))
        if end > start:
            normalized.append({"start_s": start, "end_s": end})
    return normalized


def summarize_segments(records: list[dict[str, Any]], fps: float) -> list[dict[str, float]]:
    segments: list[dict[str, float]] = []
    current: dict[str, float] | None = None
    for item in records:
        status = str(item["status"])
        if status != "fall":
            if current is not None:
                segments.append(current)
                current = None
            continue
        frame = int(item["frame"])
        score = float(item.get("fall_score") or 0.0)
        if current is None:
            current = {
                "start_s": frame / fps,
                "end_s": frame / fps,
                "max_fall_score": score,
            }
        else:
            current["end_s"] = frame / fps
            current["max_fall_score"] = max(current["max_fall_score"], score)
    if current is not None:
        segments.append(current)
    for item in segments:
        item["end_s"] += 1.0 / fps
    return segments


def event_iou(left: dict[str, float], right: dict[str, float]) -> float:
    inter = max(0.0, min(left["end_s"], right["end_s"]) - max(left["start_s"], right["start_s"]))
    union = max(left["end_s"], right["end_s"]) - min(left["start_s"], right["start_s"])
    return inter / union if union > 0 else 0.0


def evaluate(predicted: list[dict[str, float]], labels: list[dict[str, float]], threshold: float) -> dict[str, float]:
    matched: set[int] = set()
    tp = 0
    for label in labels:
        best_index = -1
        best_iou = 0.0
        for index, pred in enumerate(predicted):
            if index in matched:
                continue
            iou = event_iou(label, pred)
            if iou > best_iou:
                best_index = index
                best_iou = iou
        if best_index >= 0 and best_iou >= threshold:
            matched.add(best_index)
            tp += 1
    fp = max(0, len(predicted) - tp)
    fn = max(0, len(labels) - tp)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def simulate(records: list[dict[str, Any]], config: FallEventStateMachineConfig) -> list[dict[str, Any]]:
    machine = FallEventStateMachine(config)
    simulated: list[dict[str, Any]] = []
    for record in records:
        raw_result = record.get("raw_result")
        if not isinstance(raw_result, dict):
            raw_result = {
                "status": record.get("raw_status", record.get("status", "normal")),
                "fall_score": record.get("fall_score", 0.0),
                "scores": {"fall": record.get("fall_score", 0.0)},
                "detections": [],
            }
        result = machine.apply(raw_result)
        simulated.append(
            {
                "frame": int(record["frame"]),
                "status": result["status"],
                "fall_score": float(result.get("fall_score") or 0.0),
            }
        )
    return simulated


def main() -> int:
    args = parse_args()
    manifest = load_json(args.manifest.expanduser())
    items = manifest.get("items") if isinstance(manifest, dict) else manifest
    if not isinstance(items, list):
        raise ValueError("Manifest must be a list or an object with an items list.")

    dataset: list[dict[str, Any]] = []
    for item in items:
        prediction = load_json(Path(item["prediction_json"]).expanduser())
        frame_records = prediction.get("frame_records")
        if not frame_records:
            raise ValueError(
                f"{item['prediction_json']} has no frame_records. Re-run run_fall_media_demo.py with --save-frame-records."
            )
        dataset.append(
            {
                "fps": float(prediction.get("fps") or 25.0),
                "records": frame_records,
                "labels": normalize_label_events(list(item.get("events") or [])),
            }
        )

    candidates: list[dict[str, Any]] = []
    for window, confirm, hold, fall_threshold, suspected_threshold in itertools.product(
        [7, 9, 11, 13],
        [2, 3, 4],
        [8, 12, 16, 20],
        [0.66, 0.70, 0.72, 0.76],
        [0.36, 0.40, 0.42, 0.46],
    ):
        config = FallEventStateMachineConfig(
            window_frames=window,
            fall_confirm_frames=confirm,
            fall_hold_frames=hold,
            fall_score_threshold=fall_threshold,
            suspected_score_threshold=suspected_threshold,
        )
        total = {"tp": 0.0, "fp": 0.0, "fn": 0.0}
        for data in dataset:
            simulated = simulate(data["records"], config)
            predicted = summarize_segments(simulated, float(data["fps"]))
            metric = evaluate(predicted, data["labels"], args.iou_threshold)
            total["tp"] += metric["tp"]
            total["fp"] += metric["fp"]
            total["fn"] += metric["fn"]
        precision = total["tp"] / (total["tp"] + total["fp"]) if total["tp"] + total["fp"] else 0.0
        recall = total["tp"] / (total["tp"] + total["fn"]) if total["tp"] + total["fn"] else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        candidates.append(
            {
                "f1": round(f1, 4),
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "true_positive": int(total["tp"]),
                "false_positive": int(total["fp"]),
                "false_negative": int(total["fn"]),
                "params": config.as_dict(),
            }
        )

    candidates.sort(key=lambda item: (item["f1"], item["recall"], item["precision"]), reverse=True)
    print(json.dumps({"best": candidates[0], "top5": candidates[:5]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
