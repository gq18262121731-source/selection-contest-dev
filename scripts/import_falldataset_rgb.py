from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import cv2


CLASS_MAP = {
    0: "empty",
    1: "standing",
    2: "sitting",
    3: "lying",
    4: "bending",
    5: "crawling",
    6: "empty",
}

TARGET_MAP = {
    "standing": "normal",
    "sitting": "sitting",
    "lying": "lying",
    "bending": "bending",
    "crawling": "bending",
}
ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import falldataset.com RGB image sequences as labeled videos.")
    parser.add_argument(
        "--source-root",
        type=Path,
        default=ROOT / "data" / "fall_eval" / "downloads" / "falldataset" / "extracted",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "data" / "fall_eval" / "videos",
    )
    parser.add_argument("--fps", type=float, default=10.0)
    parser.add_argument("--min-frames", type=int, default=24)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def read_labels(path: Path) -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            index = int(row["index"])
            cls = int(row["class"])
            label = CLASS_MAP.get(cls, "unknown")
            rows.append((index, label))
    return rows


def contiguous_segments(rows: list[tuple[int, str]]) -> list[tuple[str, list[int]]]:
    segments: list[tuple[str, list[int]]] = []
    current_label: str | None = None
    current_indices: list[int] = []
    for index, label in rows:
        if label != current_label:
            if current_label is not None:
                segments.append((current_label, current_indices))
            current_label = label
            current_indices = [index]
        else:
            current_indices.append(index)
    if current_label is not None:
        segments.append((current_label, current_indices))
    return segments


def write_video(rgb_dir: Path, indices: list[int], output: Path, *, fps: float, overwrite: bool) -> dict[str, object]:
    if output.exists() and not overwrite:
        return {"output": str(output), "frames": len(indices), "skipped": True}
    first_path = rgb_dir / f"rgb_{indices[0]:04d}.png"
    first = cv2.imread(str(first_path))
    if first is None:
        raise RuntimeError(f"Could not read frame: {first_path}")
    height, width = first.shape[:2]
    output.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"Could not write video: {output}")
    written = 0
    for index in indices:
        frame_path = rgb_dir / f"rgb_{index:04d}.png"
        frame = cv2.imread(str(frame_path))
        if frame is None:
            continue
        if frame.shape[1] != width or frame.shape[0] != height:
            frame = cv2.resize(frame, (width, height))
        writer.write(frame)
        written += 1
    writer.release()
    return {"output": str(output), "frames": written, "skipped": False}


def main() -> int:
    args = parse_args()
    imported: list[dict[str, object]] = []
    for labels_path in sorted(args.source_root.rglob("labels.csv")):
        clip_root = labels_path.parent
        clip_id = clip_root.name
        rgb_dir = clip_root / "rgb"
        if not rgb_dir.exists():
            continue
        for segment_index, (label, indices) in enumerate(contiguous_segments(read_labels(labels_path))):
            target_label = TARGET_MAP.get(label)
            if target_label is None or len(indices) < args.min_frames:
                continue
            output = args.output_root / target_label / f"falldataset_{clip_id}_{segment_index:03d}_{label}.mp4"
            item = write_video(rgb_dir, indices, output, fps=args.fps, overwrite=args.overwrite)
            duration = float(item["frames"]) / max(1e-6, args.fps)
            imported.append(
                {
                    "source": "falldataset.com",
                    "source_clip": clip_id,
                    "source_label": label,
                    "target_label": target_label,
                    "segment_index": segment_index,
                    "duration_s": round(duration, 3),
                    **item,
                }
            )
    index = args.output_root.parent / "imported_falldataset_rgb.json"
    index.write_text(
        json.dumps(
            {
                "source": "https://falldataset.com/",
                "class_map": CLASS_MAP,
                "target_map": TARGET_MAP,
                "items": imported,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"imported": len(imported), "index": str(index)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
