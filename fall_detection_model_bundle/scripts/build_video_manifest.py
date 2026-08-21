from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "data_public"
PROCESSED = ROOT / "data_processed"


def load_id_map() -> dict[int, str]:
    path = PUBLIC / "omnifall_labels" / "labels" / "label2id.csv"
    df = pd.read_csv(path)
    return dict(zip(df["id"], df["label"]))


def build_gmdcsa24_manifest() -> pd.DataFrame:
    id2label = load_id_map()
    labels_path = PUBLIC / "omnifall_labels" / "labels" / "GMDCSA24.csv"
    base_dir = PUBLIC / "gmdcsa24" / "extracted" / "ekramalam-GMDCSA24-A-Dataset-for-Human-Fall-Detection-in-Videos-b5ac9f5"
    labels = pd.read_csv(labels_path)
    labels["label_name"] = labels["label"].map(id2label)

    split_frames = []
    for split in ("train", "val", "test"):
        split_path = PUBLIC / "wanfall_splits" / "splits" / "cv" / "gmdcsa24" / f"{split}.csv"
        split_df = pd.read_csv(split_path)
        split_df["split"] = split
        split_frames.append(split_df)
    splits = pd.concat(split_frames, ignore_index=True)
    split_map = dict(zip(splits["path"], splits["split"]))

    rows = []
    for row in labels.itertuples(index=False):
        split = split_map.get(row.path)
        if split is None:
            continue
        rel_path = row.path.replace("Subject_", "Actor ").replace("/", "\\") + ".mp4"
        video_path = base_dir / rel_path
        if not video_path.exists():
            continue
        rows.append(
            {
                "dataset": "gmdcsa24",
                "split": split,
                "video_path": str(video_path),
                "video_key": str(Path(rel_path).with_suffix("")).replace("\\", "/"),
                "segment_start_s": float(row.start),
                "segment_end_s": float(row.end),
                "label_name": row.label_name,
                "binary_label": 1 if row.label_name in {"fall", "fallen"} else 0,
                "subject": int(row.subject),
                "camera": int(row.cam),
                "weak_label": 0,
            }
        )
    return pd.DataFrame(rows)


def build_urfd_manifest() -> pd.DataFrame:
    videos_dir = PUBLIC / "urfd" / "videos"
    rows = []
    for video_path in sorted(videos_dir.glob("*.mp4")):
        stem = video_path.stem
        is_fall = stem.startswith("fall-")
        rows.append(
            {
                "dataset": "urfd",
                "split": "external",
                "video_path": str(video_path),
                "video_key": stem,
                "segment_start_s": 0.0,
                "segment_end_s": -1.0,
                "label_name": "fall_video" if is_fall else "adl",
                "binary_label": 1 if is_fall else 0,
                "subject": -1,
                "camera": 1 if "cam1" in stem else 0,
                "weak_label": 1,
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a unified manifest for public fall datasets.")
    parser.add_argument(
        "--output",
        default=str(PROCESSED / "video_manifest.csv"),
        help="Path to the output CSV file.",
    )
    args = parser.parse_args()

    PROCESSED.mkdir(parents=True, exist_ok=True)
    manifest = pd.concat([build_gmdcsa24_manifest(), build_urfd_manifest()], ignore_index=True)
    manifest.to_csv(args.output, index=False)
    print(f"[saved] {args.output}")
    print(manifest.groupby(["dataset", "split", "label_name"]).size().to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
