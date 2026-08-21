from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".wmv"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def count_files(root: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not root.exists():
        return counts
    for path in root.rglob("*"):
        if path.is_file():
            suffix = path.suffix.lower() or "<none>"
            counts[suffix] += 1
    return counts


def count_yolo_labels(label_root: Path) -> dict[str, int]:
    counts: Counter[str] = Counter()
    if not label_root.exists():
        return {}
    for label_file in label_root.rglob("*.txt"):
        for line in label_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            parts = line.strip().split()
            if parts:
                counts[parts[0]] += 1
    return dict(counts)


def split_counts(dataset_root: Path) -> dict[str, dict[str, int]]:
    payload: dict[str, dict[str, int]] = {}
    for split in ["train", "val", "test"]:
        image_dir = dataset_root / "images" / split
        label_dir = dataset_root / "labels" / split
        payload[split] = {
            "images": sum(1 for path in image_dir.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTS)
            if image_dir.exists()
            else 0,
            "label_files": sum(1 for path in label_dir.rglob("*.txt")) if label_dir.exists() else 0,
        }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit local fall-detection datasets and training assets.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--output", default=str(ROOT / "reports" / "fall_data_asset_audit.json"))
    args = parser.parse_args()

    root = Path(args.root).resolve()
    public_counts = count_files(root / "data_public")
    processed_counts = count_files(root / "data_processed")
    fall_detect_root = root / "data_processed" / "fall_detect"
    pose_cache_root = root / "data_processed" / "pose_cache"

    payload = {
        "root": str(root),
        "data_public": {
            "total_files": int(sum(public_counts.values())),
            "videos": int(sum(count for ext, count in public_counts.items() if ext in VIDEO_EXTS)),
            "images": int(sum(count for ext, count in public_counts.items() if ext in IMAGE_EXTS)),
            "by_extension": dict(sorted(public_counts.items())),
        },
        "data_processed": {
            "total_files": int(sum(processed_counts.values())),
            "pose_cache_npz": len(list(pose_cache_root.glob("*.npz"))) if pose_cache_root.exists() else 0,
            "pose_cache_meta": len(list(pose_cache_root.glob("*.json"))) if pose_cache_root.exists() else 0,
            "by_extension": dict(sorted(processed_counts.items())),
        },
        "fall_detect_dataset": {
            "root": str(fall_detect_root),
            "splits": split_counts(fall_detect_root),
            "label_class_counts": count_yolo_labels(fall_detect_root / "labels"),
        },
        "recommended_next_commands": [
            "python scripts/build_yolo_fall_detect_dataset.py --frame-step 2 --max-frames-per-video 120",
            "python scripts/train_yolo_fall_detector.py --model yolo11s.pt --epochs 120 --batch 16 --name yolo_fall_detector_v2_recall",
            "python scripts/evaluate_yolo_detect.py --weights runs/yolo_fall_detector_v2_recall/weights/best.pt",
        ],
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"[audit] wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
