from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data_processed"


def make_cache_key(video_path: Path) -> str:
    parts = video_path.parts
    if "ekramalam-GMDCSA24-A-Dataset-for-Human-Fall-Detection-in-Videos-b5ac9f5" in parts:
        idx = parts.index("ekramalam-GMDCSA24-A-Dataset-for-Human-Fall-Detection-in-Videos-b5ac9f5")
        rel_parts = parts[idx + 1 :]
    elif "videos" in parts:
        idx = parts.index("videos")
        rel_parts = parts[idx + 1 :]
    else:
        rel_parts = parts[-2:]
    return "__".join(Path(*rel_parts).with_suffix("").parts)


def choose_person(result) -> tuple[np.ndarray, np.ndarray] | None:
    boxes = result.boxes
    keypoints = result.keypoints
    if boxes is None or keypoints is None or len(boxes) == 0:
        return None

    xyxy = boxes.xyxy.detach().cpu().numpy()
    conf = boxes.conf.detach().cpu().numpy()
    areas = (xyxy[:, 2] - xyxy[:, 0]) * (xyxy[:, 3] - xyxy[:, 1])
    idx = int(np.argmax(areas * conf))
    kp = keypoints.data[idx].detach().cpu().numpy()
    box = xyxy[idx]
    return kp, box


def process_video(model: YOLO, video_path: Path, target_fps: float) -> dict:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video_path}")

    native_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    stride = max(1, round(native_fps / target_fps))
    frame_idx = 0
    sampled = 0

    keypoints = []
    boxes = []
    timestamps = []

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % stride != 0:
            frame_idx += 1
            continue
        result = model.predict(frame, verbose=False, imgsz=640, conf=0.2, max_det=3)[0]
        picked = choose_person(result)
        if picked is None:
            keypoints.append(np.zeros((17, 3), dtype=np.float32))
            boxes.append(np.zeros((4,), dtype=np.float32))
        else:
            kp, box = picked
            keypoints.append(kp.astype(np.float32))
            boxes.append(box.astype(np.float32))
        timestamps.append(frame_idx / native_fps)
        sampled += 1
        frame_idx += 1

    cap.release()
    return {
        "fps": float(native_fps / stride),
        "native_fps": float(native_fps),
        "stride": int(stride),
        "frames": int(sampled),
        "timestamps": np.asarray(timestamps, dtype=np.float32),
        "keypoints": np.asarray(keypoints, dtype=np.float32),
        "boxes": np.asarray(boxes, dtype=np.float32),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract YOLO pose cache for videos in the manifest.")
    parser.add_argument("--manifest", default=str(PROCESSED / "video_manifest.csv"))
    parser.add_argument("--output-dir", default=str(PROCESSED / "pose_cache"))
    parser.add_argument("--model", default="yolo11n-pose.pt")
    parser.add_argument("--target-fps", type=float, default=10.0)
    parser.add_argument("--limit-videos", type=int, default=None)
    parser.add_argument("--datasets", nargs="+", default=["gmdcsa24", "urfd"])
    args = parser.parse_args()

    manifest = pd.read_csv(args.manifest)
    videos = manifest[manifest["dataset"].isin(args.datasets)]["video_path"].drop_duplicates().tolist()
    if args.limit_videos:
        videos = videos[: args.limit_videos]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    model = YOLO(args.model)

    for idx, video in enumerate(videos, start=1):
        video_path = Path(video)
        cache_key = make_cache_key(video_path)
        out_path = output_dir / f"{cache_key}.npz"
        meta_path = output_dir / f"{cache_key}.json"
        if out_path.exists() and meta_path.exists():
            print(f"[skip] {video_path.name}")
            continue
        print(f"[{idx}/{len(videos)}] {video_path.name}")
        data = process_video(model, video_path, args.target_fps)
        np.savez_compressed(
            out_path,
            timestamps=data["timestamps"],
            keypoints=data["keypoints"],
            boxes=data["boxes"],
        )
        meta = {
            "video_path": str(video_path),
            "cache_key": cache_key,
            "fps": data["fps"],
            "native_fps": data["native_fps"],
            "stride": data["stride"],
            "frames": data["frames"],
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print(f"[saved] {out_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
