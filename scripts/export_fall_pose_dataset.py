from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
from tqdm import tqdm
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export YOLO-pose temporal windows for fall TCN training.")
    parser.add_argument("manifest", type=Path, help="JSON manifest with video and fall events.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ROOT / "data" / "fall_eval" / "pose_tcn_dataset.npz",
        help="Output .npz dataset path.",
    )
    parser.add_argument(
        "--pose-model",
        type=Path,
        default=ROOT / "fall_detection_model_bundle" / "yolo11n-pose.pt",
        help="YOLO pose model path.",
    )
    parser.add_argument("--sequence-length", type=int, default=32)
    parser.add_argument("--stride", type=int, default=4)
    parser.add_argument("--imgsz", type=int, default=384)
    parser.add_argument("--conf", type=float, default=0.2)
    parser.add_argument(
        "--min-positive-overlap",
        type=float,
        default=0.25,
        help="Minimum temporal overlap ratio between a window and fall event to label it positive.",
    )
    parser.add_argument("--max-frames", type=int, default=0, help="Optional cap for quick smoke tests.")
    return parser.parse_args()


def load_manifest(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ValueError("Manifest must be a list or an object with an items list.")
    return items


def resolve_path(path: str, *, base: Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate
    return (base.parent / candidate).resolve()


def fall_events(item: dict[str, Any]) -> list[tuple[float, float]]:
    events: list[tuple[float, float]] = []
    for event in item.get("events") or []:
        label = str(event.get("label") or event.get("status") or "").lower()
        if label != "fall":
            continue
        start = float(event.get("start_s", event.get("start_sec", 0.0)))
        end = float(event.get("end_s", event.get("end_sec", start)))
        if end > start:
            events.append((start, end))
    return events


def extract_pose_features(
    model: YOLO,
    video_path: Path,
    *,
    imgsz: int,
    conf: float,
    max_frames: int,
) -> tuple[np.ndarray, float]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if max_frames > 0:
        total = min(total, max_frames) if total > 0 else max_frames
    device: str | int = 0 if torch.cuda.is_available() else "cpu"
    features: list[np.ndarray] = []
    frame_index = 0
    progress_total = total if total > 0 else None
    with tqdm(total=progress_total, unit="frame", desc=f"pose-export {video_path.name}") as bar:
        while True:
            if max_frames > 0 and frame_index >= max_frames:
                break
            ok, frame = capture.read()
            if not ok:
                break
            height, width = frame.shape[:2]
            with torch.inference_mode():
                result = model.predict(frame, verbose=False, imgsz=imgsz, conf=conf, device=device)[0]
            features.append(best_person_feature(result, width=width, height=height))
            frame_index += 1
            bar.update(1)
    capture.release()
    if not features:
        raise RuntimeError(f"No frames exported: {video_path}")
    return np.stack(features, axis=0).astype(np.float32), fps


def best_person_feature(result: Any, *, width: int, height: int) -> np.ndarray:
    keypoints = result.keypoints
    if keypoints is None or keypoints.xy is None or len(keypoints.xy) == 0:
        return np.zeros((17 * 5,), dtype=np.float32)
    xy_all = keypoints.xy.detach().cpu().numpy()
    conf_all = keypoints.conf.detach().cpu().numpy() if keypoints.conf is not None else np.zeros(xy_all.shape[:2], dtype=np.float32)
    best_index = 0
    best_area = -1.0
    boxes = getattr(result, "boxes", None)
    if boxes is not None and boxes.xyxy is not None and len(boxes.xyxy) == len(xy_all):
        for index, box in enumerate(boxes.xyxy.detach().cpu().numpy()):
            x1, y1, x2, y2 = [float(v) for v in box]
            area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
            if area > best_area:
                best_area = area
                best_index = index
    xy = xy_all[best_index]
    scores = conf_all[best_index]
    visible = scores >= 0.2
    if visible.any():
        xs = xy[visible, 0]
        ys = xy[visible, 1]
        center_x = float((xs.min() + xs.max()) * 0.5)
        center_y = float((ys.min() + ys.max()) * 0.5)
        scale = max(float(xs.max() - xs.min()), float(ys.max() - ys.min()), 1.0)
    else:
        center_x = width * 0.5
        center_y = height * 0.5
        scale = max(width, height, 1)
    normalized: list[float] = []
    for (x, y), score in zip(xy, scores):
        normalized.extend(
            [
                (float(x) - center_x) / scale,
                (float(y) - center_y) / scale,
                float(score),
            ]
        )
    velocity = np.zeros((17, 2), dtype=np.float32)
    base = np.asarray(normalized, dtype=np.float32).reshape(17, 3)
    return np.concatenate([base.reshape(-1), velocity.reshape(-1)], axis=0).astype(np.float32)


def add_motion_channels(sequence: np.ndarray) -> np.ndarray:
    shaped = sequence.reshape(sequence.shape[0], 17, 5)
    xy = shaped[:, :, :2]
    velocity = np.zeros_like(xy)
    velocity[1:] = xy[1:] - xy[:-1]
    shaped[:, :, 3:5] = velocity
    return shaped.reshape(sequence.shape[0], -1)


def window_label(start_s: float, end_s: float, events: list[tuple[float, float]], min_overlap: float) -> int:
    duration = max(1e-6, end_s - start_s)
    for event_start, event_end in events:
        overlap = max(0.0, min(end_s, event_end) - max(start_s, event_start))
        center = (start_s + end_s) * 0.5
        if overlap / duration >= min_overlap or event_start <= center <= event_end:
            return 1
    return 0


def main() -> int:
    args = parse_args()
    items = load_manifest(args.manifest.expanduser())
    if not args.pose_model.exists():
        raise FileNotFoundError(args.pose_model)
    model = YOLO(str(args.pose_model))
    all_sequences: list[np.ndarray] = []
    all_labels: list[int] = []
    metadata: list[dict[str, Any]] = []

    for item in items:
        video_path = resolve_path(str(item.get("video") or ""), base=args.manifest)
        events = fall_events(item)
        frame_features, fps = extract_pose_features(
            model,
            video_path,
            imgsz=args.imgsz,
            conf=args.conf,
            max_frames=args.max_frames,
        )
        if frame_features.shape[0] < args.sequence_length:
            continue
        for start in range(0, frame_features.shape[0] - args.sequence_length + 1, max(1, args.stride)):
            end = start + args.sequence_length
            start_s = start / fps
            end_s = end / fps
            sequence = add_motion_channels(frame_features[start:end].copy())
            label = window_label(start_s, end_s, events, args.min_positive_overlap)
            all_sequences.append(sequence)
            all_labels.append(label)
            metadata.append(
                {
                    "name": item.get("name") or video_path.stem,
                    "video": str(video_path),
                    "start_frame": start,
                    "end_frame": end - 1,
                    "start_s": round(start_s, 3),
                    "end_s": round(end_s, 3),
                    "label": label,
                }
            )

    if not all_sequences:
        raise RuntimeError("No pose windows exported.")

    x = np.stack(all_sequences, axis=0).astype(np.float32)
    y = np.asarray(all_labels, dtype=np.float32)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output, x=x, y=y, metadata=np.asarray(metadata, dtype=object))
    sidecar = args.output.with_suffix(args.output.suffix + ".json")
    sidecar.write_text(
        json.dumps(
            {
                "output": str(args.output),
                "items": len(items),
                "samples": int(x.shape[0]),
                "sequence_length": int(x.shape[1]),
                "feature_dim": int(x.shape[2]),
                "positive_samples": int(y.sum()),
                "negative_samples": int((y == 0).sum()),
                "pose_model": str(args.pose_model),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[pose-export] wrote {args.output}")
    print(f"[pose-export] summary {sidecar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
