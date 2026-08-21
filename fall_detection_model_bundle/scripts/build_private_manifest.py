from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data_private" / "camera_scene" / "annotations"
DEFAULT_OUTPUT = ROOT / "data_processed" / "private_scene_manifest.csv"

POSITIVE_LABELS = {"fall", "fallen", "fall_event", "fall_transition"}


def assign_splits(video_paths: list[Path]) -> dict[str, str]:
    video_paths = sorted(video_paths)
    n = len(video_paths)
    if n <= 2:
        return {str(p): ("train" if i == 0 else "test") for i, p in enumerate(video_paths)}
    train_n = max(1, round(n * 0.6))
    val_n = max(1, round(n * 0.2))
    split_map = {}
    for i, p in enumerate(video_paths):
        if i < train_n:
            split_map[str(p)] = "train"
        elif i < train_n + val_n:
            split_map[str(p)] = "val"
        else:
            split_map[str(p)] = "test"
    return split_map


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a manifest from private scene event annotations.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    files = sorted(input_dir.rglob("*.json"))
    if not files:
        raise RuntimeError(f"No annotation JSON files found in {input_dir}")

    payloads = []
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        payloads.append((path, data))

    split_map = assign_splits([Path(data["video_path"]) for _, data in payloads])

    rows = []
    for ann_path, data in payloads:
        video_path = Path(data["video_path"])
        split = split_map[str(video_path)]
        segments = data.get("segments", [])
        if not segments:
            rows.append(
                {
                    "dataset": "private_scene",
                    "split": split,
                    "video_path": str(video_path),
                    "video_key": video_path.stem,
                    "segment_start_s": 0.0,
                    "segment_end_s": float(data.get("total_frames", 0) / max(data.get("fps", 20.0), 1e-6)),
                    "label_name": "other",
                    "binary_label": 0,
                    "subject": -1,
                    "camera": -1,
                    "weak_label": 0,
                    "annotation_path": str(ann_path),
                }
            )
            continue
        for seg in segments:
            label_name = seg["label"]
            rows.append(
                {
                    "dataset": "private_scene",
                    "split": split,
                    "video_path": str(video_path),
                    "video_key": video_path.stem,
                    "segment_start_s": float(seg["start_s"]),
                    "segment_end_s": float(seg["end_s"]),
                    "label_name": label_name,
                    "binary_label": 1 if label_name in POSITIVE_LABELS else 0,
                    "subject": -1,
                    "camera": -1,
                    "weak_label": 0,
                    "annotation_path": str(ann_path),
                }
            )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False)
    print(f"[saved] {out_path}")
    print(df.groupby(["split", "binary_label"]).size().to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
