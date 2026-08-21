from __future__ import annotations

import argparse
from pathlib import Path

from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a YOLO classification model on Fall Pose posture classes.")
    parser.add_argument("--data", default=str(ROOT / "data_processed" / "fallpose_cls"))
    parser.add_argument("--model", default=str(ROOT / "yolo11n-cls.pt"))
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--batch", type=int, default=64)
    parser.add_argument("--device", default="auto", help="auto, cpu, cuda, or CUDA index")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--project", default=str(ROOT / "runs"))
    parser.add_argument("--name", default="yolo_posture_cls_v1")
    args = parser.parse_args()

    model = YOLO(args.model)
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project=args.project,
        name=args.name,
        device=args.device,
        workers=args.workers,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
