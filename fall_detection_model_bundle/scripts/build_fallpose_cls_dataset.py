from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FALLPOSE_EXTRACTED = ROOT / "data_public" / "fallpose" / "extracted"
OUTPUT_ROOT = ROOT / "data_processed" / "fallpose_cls"

CLASS_MAP = {
    1: "standing",
    2: "sitting",
    3: "lying",
    4: "bending",
    5: "crawling",
    6: "other",
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


def copy_dataset(split_map: dict[str, list[Path]], out_root: Path, step: int) -> dict[str, dict[str, int]]:
    counts = {split: {name: 0 for name in CLASS_MAP.values()} for split in split_map}
    for split, seqs in split_map.items():
        for seq_dir in seqs:
            inner = resolve_inner_dir(seq_dir)
            with (inner / "labels.csv").open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    idx = int(row["index"])
                    class_id = int(row["class"])
                    if (idx - 1) % step != 0:
                        continue
                    class_name = CLASS_MAP[class_id]
                    src = inner / "rgb" / f"rgb_{idx:04d}.png"
                    if not src.exists():
                        continue
                    dst = out_root / split / class_name / f"{seq_dir.name}_{idx:04d}.png"
                    shutil.copy2(src, dst)
                    counts[split][class_name] += 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a YOLO classification dataset from Fall Pose sequences.")
    parser.add_argument("--output-dir", default=str(OUTPUT_ROOT))
    parser.add_argument("--frame-step", type=int, default=2, help="Keep every Nth frame to control dataset size.")
    args = parser.parse_args()

    seqs = get_completed_sequences()
    split_map = split_sequences(seqs)
    out_root = Path(args.output_dir)
    prepare_dirs(out_root)
    counts = copy_dataset(split_map, out_root, step=args.frame_step)

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
