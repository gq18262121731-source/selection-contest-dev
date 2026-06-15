from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from train_temporal_gru import video_key_from_path


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data_processed"

CLASS_TO_ID = {
    "person": 0,
    "fall": 1,
    "fallen": 2,
    "sitting": 3,
    "sit_down": 3,
    "lying": 4,
    "lie_down": 4,
    "bending": 5,
}

POSITIVE_FALL_LABELS = {"fall", "fallen"}
SUPPORTED_LABELS = set(CLASS_TO_ID)


def label_for_time(rows: pd.DataFrame, t_s: float, is_urfd_fall: bool) -> str:
    if is_urfd_fall:
        return "fall" if t_s >= rows["duration_hint"].iloc[0] * 0.55 else "person"
    for row in rows.itertuples(index=False):
        end_s = float(row.segment_end_s)
        if end_s < 0:
            end_s = 1e9
        if float(row.segment_start_s) <= t_s <= end_s:
            label = str(row.label_name)
            return label if label in SUPPORTED_LABELS else "person"
    return "person"


def write_yolo_label(path: Path, class_id: int, box: np.ndarray, width: int, height: int) -> None:
    x1, y1, x2, y2 = box.astype(float)
    x1 = max(0.0, min(float(width - 1), x1))
    y1 = max(0.0, min(float(height - 1), y1))
    x2 = max(0.0, min(float(width - 1), x2))
    y2 = max(0.0, min(float(height - 1), y2))
    if x2 <= x1 or y2 <= y1:
        path.write_text("", encoding="utf-8")
        return
    cx = ((x1 + x2) / 2.0) / max(width, 1)
    cy = ((y1 + y2) / 2.0) / max(height, 1)
    bw = (x2 - x1) / max(width, 1)
    bh = (y2 - y1) / max(height, 1)
    path.write_text(f"{class_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n", encoding="utf-8")


def build_dataset(
    manifest_path: Path,
    pose_cache_dir: Path,
    output_dir: Path,
    frame_step: int,
    max_frames_per_video: int,
) -> dict[str, int]:
    manifest = pd.read_csv(manifest_path)
    manifest = manifest[manifest["dataset"].isin(["gmdcsa24", "urfd", "private_scene"])]
    counts: dict[str, int] = {}

    for split in ["train", "val", "test"]:
        (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    for video_path, rows in manifest.groupby("video_path"):
        key = video_key_from_path(video_path)
        cache_path = pose_cache_dir / f"{key}.npz"
        meta_path = pose_cache_dir / f"{key}.json"
        if not cache_path.exists() or not meta_path.exists():
            continue

        split = str(rows["split"].iloc[0])
        if split == "external":
            split = "test"
        if split not in {"train", "val", "test"}:
            continue

        cache = np.load(cache_path)
        boxes = cache["boxes"]
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        fps = float(meta["fps"])
        native_stride = int(meta.get("stride", 1))
        frame_total = int(meta.get("frames", len(boxes)))
        is_urfd_fall = str(rows["dataset"].iloc[0]) == "urfd" and int(rows["binary_label"].max()) == 1
        rows = rows.copy()
        rows["duration_hint"] = frame_total / max(fps, 1e-6)

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            continue
        written_for_video = 0
        for idx in range(0, min(len(boxes), frame_total), frame_step):
            if written_for_video >= max_frames_per_video:
                break
            t_s = idx / max(fps, 1e-6)
            label = label_for_time(rows, t_s, is_urfd_fall)
            class_id = CLASS_TO_ID.get(label, 0)
            frame_number = int(idx * native_stride)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            height, width = frame.shape[:2]
            image_name = f"{key}__{idx:05d}.jpg"
            label_name = f"{key}__{idx:05d}.txt"
            image_path = output_dir / "images" / split / image_name
            label_path = output_dir / "labels" / split / label_name
            cv2.imwrite(str(image_path), frame)
            write_yolo_label(label_path, class_id, boxes[idx], width, height)
            counts[label] = counts.get(label, 0) + 1
            written_for_video += 1
        cap.release()
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a weakly labeled YOLO fall detection dataset from video manifests and pose caches.")
    parser.add_argument("--manifest", default=str(PROCESSED / "video_manifest_adapted.csv"))
    parser.add_argument("--pose-cache-dir", default=str(PROCESSED / "pose_cache"))
    parser.add_argument("--output-dir", default=str(PROCESSED / "fall_detect"))
    parser.add_argument("--frame-step", type=int, default=3)
    parser.add_argument("--max-frames-per-video", type=int, default=80)
    args = parser.parse_args()

    counts = build_dataset(
        Path(args.manifest),
        Path(args.pose_cache_dir),
        Path(args.output_dir),
        args.frame_step,
        args.max_frames_per_video,
    )
    print(json.dumps({"output_dir": args.output_dir, "counts": counts}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
