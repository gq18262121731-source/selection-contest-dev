from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "data_processed" / "fallpose_person_cls"
OUTPUT_ROOT = ROOT / "data_processed" / "fallpose_person_binary_cls"

RISK_CLASSES = {"lying", "crawling", "bending"}
SAFE_CLASSES = {"standing", "sitting"}


def prepare_dirs(out_root: Path) -> None:
    if out_root.exists():
        shutil.rmtree(out_root)
    for split in ("train", "val", "test"):
        (out_root / split / "risk").mkdir(parents=True, exist_ok=True)
        (out_root / split / "safe").mkdir(parents=True, exist_ok=True)


def copy_grouped(split: str, out_root: Path, train_safe_ratio: float) -> dict[str, int]:
    split_root = SOURCE_ROOT / split
    risk_files = []
    safe_files = []

    for cls in sorted(RISK_CLASSES):
        risk_files.extend(sorted((split_root / cls).glob("*.png")))
    for cls in sorted(SAFE_CLASSES):
        safe_files.extend(sorted((split_root / cls).glob("*.png")))

    if split == "train" and train_safe_ratio > 0:
        cap = max(1, int(len(risk_files) * train_safe_ratio))
        if len(safe_files) > cap:
            step = max(1, len(safe_files) // cap)
            safe_files = safe_files[::step][:cap]

    for src in risk_files:
        dst = out_root / split / "risk" / src.name
        shutil.copy2(src, dst)
    for src in safe_files:
        dst = out_root / split / "safe" / src.name
        shutil.copy2(src, dst)

    return {"risk": len(risk_files), "safe": len(safe_files)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a binary safe/risk dataset from person-crop posture classes.")
    parser.add_argument("--output-dir", default=str(OUTPUT_ROOT))
    parser.add_argument("--train-safe-ratio", type=float, default=1.2, help="Cap train safe samples to ratio * risk samples.")
    args = parser.parse_args()

    out_root = Path(args.output_dir)
    prepare_dirs(out_root)
    stats = {}
    for split in ("train", "val", "test"):
        stats[split] = copy_grouped(split, out_root, args.train_safe_ratio)

    print(f"[saved] {out_root}")
    for split, split_stats in stats.items():
        print(split, split_stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
