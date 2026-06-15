from __future__ import annotations

import argparse
from pathlib import Path

from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a YOLO fall detection model.")
    parser.add_argument("--data", default=str(ROOT / "configs" / "fall_detect_dataset.yaml"))
    parser.add_argument("--model", default="yolo11s.pt")
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--optimizer", default="SGD")
    parser.add_argument("--close-mosaic", type=int, default=10)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--project", default=str(ROOT / "runs"))
    parser.add_argument("--name", default="yolo_fall_detector_v1")
    args = parser.parse_args()

    model = YOLO(args.model)
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        optimizer=args.optimizer,
        close_mosaic=args.close_mosaic,
        project=args.project,
        name=args.name,
        device=0,
        workers=args.workers,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
