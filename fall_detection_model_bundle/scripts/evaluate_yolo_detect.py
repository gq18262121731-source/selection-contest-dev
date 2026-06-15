from __future__ import annotations

import argparse
import json
from pathlib import Path

from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]


def metric_value(metrics, key: str) -> float | None:
    value = getattr(metrics.box, key, None)
    if value is None:
        return None
    try:
        return float(value)
    except TypeError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a YOLO detection model and write a compact metrics report.")
    parser.add_argument("--weights", default=str(ROOT / "runs" / "yolo_fall_detector_v1" / "weights" / "best.pt"))
    parser.add_argument("--data", default=str(ROOT / "configs" / "fall_detect_dataset.yaml"))
    parser.add_argument("--split", default="test", choices=["train", "val", "test"])
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.001)
    parser.add_argument("--iou", type=float, default=0.6)
    parser.add_argument("--project", default=str(ROOT / "runs"))
    parser.add_argument("--name", default="yolo_fall_detector_eval")
    parser.add_argument("--output", default=str(ROOT / "reports" / "yolo_fall_detector_eval.json"))
    args = parser.parse_args()

    model = YOLO(args.weights)
    metrics = model.val(
        data=args.data,
        split=args.split,
        imgsz=args.imgsz,
        conf=args.conf,
        iou=args.iou,
        project=args.project,
        name=args.name,
        plots=True,
        save_json=True,
    )

    report = {
        "weights": str(args.weights),
        "data": str(args.data),
        "split": args.split,
        "precision": metric_value(metrics, "mp"),
        "recall": metric_value(metrics, "mr"),
        "map50": metric_value(metrics, "map50"),
        "map50_95": metric_value(metrics, "map"),
        "results_dir": str(metrics.save_dir),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
