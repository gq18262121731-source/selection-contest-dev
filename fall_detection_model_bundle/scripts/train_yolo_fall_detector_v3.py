from __future__ import annotations

import argparse
from pathlib import Path

from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "v3_upgrade_lab"


def main() -> int:
    parser = argparse.ArgumentParser(description="Train the V3 YOLO fall detector without touching production weights.")
    parser.add_argument("--data", default=str(LAB / "configs" / "fall_detect_v3_dataset.yaml"))
    parser.add_argument("--model", default=str(LAB / "weights" / "yolo26" / "yolo26s.pt"))
    parser.add_argument("--epochs", type=int, default=180)
    parser.add_argument("--imgsz", type=int, default=768)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--optimizer", default="AdamW")
    parser.add_argument("--close-mosaic", type=int, default=20)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--device", default="0")
    parser.add_argument("--name", default="yolo26_fall_detector_v3")
    parser.add_argument("--patience", type=int, default=35)
    parser.add_argument("--export-target", default="", help="Optional explicit path for the exported best.pt candidate.")
    parser.add_argument(
        "--update-default-candidate",
        action="store_true",
        help="Also overwrite v3_upgrade_lab/weights/yolo26/yolo26_fall_detector_v3_best.pt.",
    )
    args = parser.parse_args()

    project = LAB / "experiments" / "yolo_detector"
    project.mkdir(parents=True, exist_ok=True)
    model_path = Path(args.model)
    model = YOLO(str(model_path if model_path.exists() else args.model))
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        optimizer=args.optimizer,
        close_mosaic=args.close_mosaic,
        project=str(project),
        name=args.name,
        device=args.device,
        workers=args.workers,
        patience=args.patience,
        cos_lr=True,
        degrees=5.0,
        translate=0.08,
        scale=0.5,
        shear=2.0,
        fliplr=0.5,
        hsv_h=0.015,
        hsv_s=0.35,
        hsv_v=0.25,
    )
    best = project / args.name / "weights" / "best.pt"
    if best.exists():
        if args.export_target:
            export_target = Path(args.export_target)
        else:
            export_target = LAB / "weights" / "yolo26" / f"{args.name}_best.pt"
        export_target.parent.mkdir(parents=True, exist_ok=True)
        export_target.write_bytes(best.read_bytes())
        print(f"Exported candidate detector: {export_target}")
        if args.update_default_candidate:
            default_target = LAB / "weights" / "yolo26" / "yolo26_fall_detector_v3_best.pt"
            default_target.write_bytes(best.read_bytes())
            print(f"Updated default V3 detector candidate: {default_target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
