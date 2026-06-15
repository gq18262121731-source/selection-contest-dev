from __future__ import annotations

import argparse
from pathlib import Path

from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the YOLO posture classification model on an image folder split.")
    parser.add_argument("--weights", default=str(ROOT / "runs" / "yolo_posture_cls_v1" / "weights" / "best.pt"))
    parser.add_argument("--data-root", default=str(ROOT / "data_processed" / "fallpose_cls"))
    parser.add_argument("--split", default="test")
    args = parser.parse_args()

    model = YOLO(args.weights)
    split_dir = Path(args.data_root) / args.split
    names = model.names
    total = 0
    correct = 0
    per_class = {}

    for class_dir in sorted(p for p in split_dir.iterdir() if p.is_dir()):
        class_name = class_dir.name
        per_class.setdefault(class_name, {"total": 0, "correct": 0})
        for image_path in class_dir.glob("*.png"):
            result = model.predict(str(image_path), verbose=False, imgsz=320)[0]
            pred_name = names[int(result.probs.top1)]
            total += 1
            per_class[class_name]["total"] += 1
            if pred_name == class_name:
                correct += 1
                per_class[class_name]["correct"] += 1

    print(f"split={args.split} total={total} acc={correct / max(total, 1):.4f}")
    for class_name, stats in per_class.items():
        acc = stats["correct"] / max(stats["total"], 1)
        print(f"{class_name}: {stats['correct']}/{stats['total']} = {acc:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
