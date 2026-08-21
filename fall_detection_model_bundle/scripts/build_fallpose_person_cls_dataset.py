from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path

import cv2
from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
FALLPOSE_EXTRACTED = ROOT / "data_public" / "fallpose" / "extracted"
OUTPUT_ROOT = ROOT / "data_processed" / "fallpose_person_cls"

CLASS_MAP = {
    1: "standing",
    2: "sitting",
    3: "lying",
    4: "bending",
    5: "crawling",
}


def resolve_inner_dir(seq_dir: Path) -> Path:
    candidate = seq_dir / seq_dir.name
    if (candidate / "labels.csv").exists() and (candidate / "rgb").exists():
        return candidate
    return seq_dir


def get_completed_sequences() -> list[Path]:
    seqs = []
    for seq_dir in sorted(FALLPOSE_EXTRACTED.iterdir(), key=lambda p: int(p.name)):
        inner = resolve_inner_dir(seq_dir)
        if (inner / "labels.csv").exists() and (inner / "rgb").exists():
            seqs.append(seq_dir)
    return seqs


def split_sequences(seqs: list[Path]) -> dict[str, list[Path]]:
    if len(seqs) < 3:
        return {"train": seqs, "val": [], "test": []}
    test_n = max(1, round(len(seqs) * 0.15))
    val_n = max(1, round(len(seqs) * 0.2))
    train_n = max(1, len(seqs) - val_n - test_n)
    return {
        "train": seqs[:train_n],
        "val": seqs[train_n : train_n + val_n],
        "test": seqs[train_n + val_n :],
    }


def prepare_dirs(out_root: Path) -> None:
    if out_root.exists():
        shutil.rmtree(out_root)
    for split in ("train", "val", "test"):
        for class_name in CLASS_MAP.values():
            (out_root / split / class_name).mkdir(parents=True, exist_ok=True)


def detect_person_box(model: YOLO, image_path: Path) -> tuple[int, int, int, int] | None:
    result = model.predict(str(image_path), verbose=False, imgsz=640, conf=0.2, max_det=1)[0]
    if result.boxes is None or len(result.boxes) == 0:
        return None
    box = result.boxes.xyxy[0].detach().cpu().numpy().astype(int)
    return int(box[0]), int(box[1]), int(box[2]), int(box[3])


def crop_with_margin(image, box: tuple[int, int, int, int], margin: float = 0.12):
    h, w = image.shape[:2]
    x1, y1, x2, y2 = box
    bw = x2 - x1
    bh = y2 - y1
    mx = int(bw * margin)
    my = int(bh * margin)
    x1 = max(0, x1 - mx)
    y1 = max(0, y1 - my)
    x2 = min(w, x2 + mx)
    y2 = min(h, y2 + my)
    return image[y1:y2, x1:x2]


def build_dataset(split_map: dict[str, list[Path]], out_root: Path, frame_step: int, detector: YOLO) -> dict[str, dict[str, int]]:
    counts = {split: {name: 0 for name in CLASS_MAP.values()} for split in split_map}
    skipped = 0
    for split, seqs in split_map.items():
        for seq_dir in seqs:
            inner = resolve_inner_dir(seq_dir)
            with (inner / "labels.csv").open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    idx = int(row["index"])
                    class_id = int(row["class"])
                    if class_id not in CLASS_MAP:
                        continue
                    if (idx - 1) % frame_step != 0:
                        continue
                    class_name = CLASS_MAP[class_id]
                    image_path = inner / "rgb" / f"rgb_{idx:04d}.png"
                    if not image_path.exists():
                        continue
                    image = cv2.imread(str(image_path))
                    if image is None:
                        skipped += 1
                        continue
                    box = detect_person_box(detector, image_path)
                    if box is None:
                        skipped += 1
                        continue
                    crop = crop_with_margin(image, box)
                    if crop.size == 0:
                        skipped += 1
                        continue
                    dst = out_root / split / class_name / f"{seq_dir.name}_{idx:04d}.png"
                    cv2.imwrite(str(dst), crop)
                    counts[split][class_name] += 1
    print(f"skipped={skipped}")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Build person-crop posture classification dataset from Fall Pose.")
    parser.add_argument("--output-dir", default=str(OUTPUT_ROOT))
    parser.add_argument("--frame-step", type=int, default=2)
    parser.add_argument("--detector", default="yolo11n-pose.pt")
    args = parser.parse_args()

    seqs = get_completed_sequences()
    split_map = split_sequences(seqs)
    out_root = Path(args.output_dir)
    prepare_dirs(out_root)
    detector = YOLO(args.detector)
    counts = build_dataset(split_map, out_root, args.frame_step, detector)

    print(f"[saved] {out_root}")
    print("sequences:")
    for split, items in split_map.items():
        print(split, [p.name for p in items])
    print("counts:")
    for split, split_counts in counts.items():
        print(split, split_counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
