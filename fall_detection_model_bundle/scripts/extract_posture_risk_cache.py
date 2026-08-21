from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from ultralytics import YOLO

from train_temporal_gru import video_key_from_path


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data_processed"


def crop_with_margin(frame: np.ndarray, box: np.ndarray, margin: float = 0.12) -> np.ndarray:
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = box.astype(int)
    bw = max(0, x2 - x1)
    bh = max(0, y2 - y1)
    mx = int(bw * margin)
    my = int(bh * margin)
    x1 = max(0, x1 - mx)
    y1 = max(0, y1 - my)
    x2 = min(w, x2 + mx)
    y2 = min(h, y2 + my)
    if x2 <= x1 or y2 <= y1:
        return np.zeros((0, 0, 3), dtype=np.uint8)
    return frame[y1:y2, x1:x2]


def posture_risk_score(model: YOLO, crop: np.ndarray, imgsz: int) -> tuple[float, str]:
    if crop.size == 0:
        return 0.0, "unknown"
    result = model.predict(crop, verbose=False, imgsz=imgsz)[0]
    probs = result.probs
    if probs is None:
        return 0.0, "unknown"
    names = model.names
    top1 = int(probs.top1)
    label = names[top1]
    values = probs.data.detach().cpu().numpy()
    label_set = set(names.values())
    if label_set == {"risk", "safe"}:
        risk_idx = next(idx for idx, name in names.items() if name == "risk")
        return float(values[risk_idx]), label
    mapping = {name: idx for idx, name in names.items()}
    score = 0.0
    if "lying" in mapping:
        score += float(values[mapping["lying"]]) * 0.9
    if "crawling" in mapping:
        score += float(values[mapping["crawling"]]) * 0.6
    if "bending" in mapping:
        score += float(values[mapping["bending"]]) * 0.25
    if "standing" in mapping:
        score -= float(values[mapping["standing"]]) * 0.35
    if "sitting" in mapping:
        score -= float(values[mapping["sitting"]]) * 0.15
    return float(max(0.0, min(1.0, score))), label


def process_video(video_path: Path, pose_cache_path: Path, meta_path: Path, model: YOLO, output_dir: Path, imgsz: int) -> None:
    cache = np.load(pose_cache_path)
    boxes = cache["boxes"]
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    stride = int(meta["stride"])
    fps = float(meta["fps"])

    out_key = video_key_from_path(str(video_path))
    out_npz = output_dir / f"{out_key}.npz"
    out_json = output_dir / f"{out_key}.json"
    if out_npz.exists() and out_json.exists():
        print(f"[skip] {video_path.name}")
        return

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video_path}")

    risk_scores = []
    labels = []
    frame_idx = 0
    sample_idx = 0
    while sample_idx < len(boxes):
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % stride != 0:
            frame_idx += 1
            continue
        crop = crop_with_margin(frame, boxes[sample_idx])
        score, label = posture_risk_score(model, crop, imgsz)
        risk_scores.append(score)
        labels.append(label)
        sample_idx += 1
        frame_idx += 1
    cap.release()

    scores = np.asarray(risk_scores, dtype=np.float32)
    if len(scores) < len(boxes):
        pad = len(boxes) - len(scores)
        scores = np.pad(scores, (0, pad), mode="constant", constant_values=0.0)
        labels.extend(["unknown"] * pad)
    delta = np.concatenate([[0.0], np.diff(scores)]).astype(np.float32)
    smooth = pd.Series(scores).rolling(window=3, min_periods=1).mean().to_numpy(dtype=np.float32)
    np.savez_compressed(out_npz, risk_scores=scores, risk_delta=delta, risk_smooth=smooth)
    out_json.write_text(
        json.dumps(
            {
                "video_path": str(video_path),
                "fps": fps,
                "stride": stride,
                "frames": int(len(boxes)),
                "top1_labels": labels,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[saved] {out_npz.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract per-frame posture risk scores aligned with pose cache.")
    parser.add_argument("--manifest", default=str(PROCESSED / "video_manifest.csv"))
    parser.add_argument("--pose-cache-dir", default=str(PROCESSED / "pose_cache"))
    parser.add_argument("--output-dir", default=str(PROCESSED / "posture_risk_cache"))
    parser.add_argument("--posture-weights", default=str(ROOT / "runs" / "yolo_posture_person_binary_cls_v1" / "weights" / "best.pt"))
    parser.add_argument("--imgsz", type=int, default=384)
    parser.add_argument("--limit-videos", type=int, default=None)
    args = parser.parse_args()

    manifest = pd.read_csv(args.manifest)
    videos = manifest["video_path"].drop_duplicates().tolist()
    if args.limit_videos:
        videos = videos[: args.limit_videos]

    pose_cache_dir = Path(args.pose_cache_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    model = YOLO(args.posture_weights)

    for idx, video in enumerate(videos, start=1):
        video_path = Path(video)
        key = video_key_from_path(video)
        pose_cache_path = pose_cache_dir / f"{key}.npz"
        meta_path = pose_cache_dir / f"{key}.json"
        if not pose_cache_path.exists() or not meta_path.exists():
            continue
        print(f"[{idx}/{len(videos)}] {video_path.name}")
        process_video(video_path, pose_cache_path, meta_path, model, output_dir, args.imgsz)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
