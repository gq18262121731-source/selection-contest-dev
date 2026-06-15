from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
from ultralytics import YOLO

from train_temporal_gru import GRUFallNet, normalize_pose, video_key_from_path


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data_processed"

POSITIVE_LABELS = {"fall", "fallen"}


def load_gru_model(weights_path: Path) -> GRUFallNet:
    ckpt = torch.load(weights_path, map_location="cpu")
    model = GRUFallNet(ckpt["input_dim"])
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    return model


def posture_risk_score(model: YOLO, crop: np.ndarray) -> float:
    if crop.size == 0:
        return 0.0
    result = model.predict(crop, verbose=False, imgsz=384)[0]
    probs = result.probs
    if probs is None:
        return 0.0
    scores = probs.data.detach().cpu().numpy()
    names = model.names
    label_set = set(names.values())
    if label_set == {"risk", "safe"}:
        risk_idx = next(idx for idx, name in names.items() if name == "risk")
        return float(scores[risk_idx])
    mapping = {name: idx for idx, name in names.items()}
    score = 0.0
    score += float(scores[mapping.get("lying", 0)]) * 0.9 if "lying" in mapping else 0.0
    score += float(scores[mapping.get("crawling", 0)]) * 0.6 if "crawling" in mapping else 0.0
    score += float(scores[mapping.get("bending", 0)]) * 0.25 if "bending" in mapping else 0.0
    score -= float(scores[mapping.get("standing", 0)]) * 0.35 if "standing" in mapping else 0.0
    score -= float(scores[mapping.get("sitting", 0)]) * 0.15 if "sitting" in mapping else 0.0
    return float(max(0.0, min(1.0, score)))


def extract_frame_crop(video_path: Path, frame_number: int, box: np.ndarray) -> np.ndarray:
    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return np.zeros((0, 0, 3), dtype=np.uint8)
    x1, y1, x2, y2 = box.astype(int)
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(frame.shape[1], x2)
    y2 = min(frame.shape[0], y2)
    if x2 <= x1 or y2 <= y1:
        return np.zeros((0, 0, 3), dtype=np.uint8)
    return frame[y1:y2, x1:x2]


def build_window_records(manifest: pd.DataFrame, cache_dir: Path, gru_model: GRUFallNet, posture_model: YOLO, window_size: int, stride: int) -> list[dict]:
    records = []
    grouped = manifest.groupby("video_path")
    for video_path_str, rows in grouped:
        video_path = Path(video_path_str)
        key = video_key_from_path(video_path_str)
        cache_path = cache_dir / f"{key}.npz"
        meta_path = cache_dir / f"{key}.json"
        if not cache_path.exists() or not meta_path.exists():
            continue

        cache = np.load(cache_path)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        frame_features = normalize_pose(cache["keypoints"], cache["boxes"])
        boxes = cache["boxes"]
        fps = float(meta["fps"])
        native_fps = float(meta["native_fps"])
        sample_stride = int(meta["stride"])
        total_frames = frame_features.shape[0]
        if total_frames < window_size:
            continue

        label_track = np.zeros(total_frames, dtype=np.int64)
        ignore_track = np.zeros(total_frames, dtype=bool)
        for row in rows.itertuples(index=False):
            if row.dataset == "gmdcsa24":
                start_idx = max(0, int(math.floor(row.segment_start_s * fps)))
                end_idx = total_frames if row.segment_end_s < 0 else min(total_frames, int(math.ceil(row.segment_end_s * fps)))
                if end_idx <= start_idx:
                    continue
                label_track[start_idx:end_idx] = 1 if row.label_name in POSITIVE_LABELS else 0
            elif row.dataset == "urfd":
                if row.binary_label == 0:
                    label_track[:] = 0
                else:
                    split_idx = int(total_frames * 0.55)
                    ignore_track[: int(total_frames * 0.25)] = True
                    label_track[split_idx:] = 1

        for start in range(0, total_frames - window_size + 1, stride):
            end = start + window_size
            if ignore_track[start:end].any():
                continue
            window_label = int(label_track[start:end].mean() >= 0.5)
            features = frame_features[start:end]
            with torch.no_grad():
                gru_prob = torch.sigmoid(gru_model(torch.from_numpy(features).unsqueeze(0))).item()

            mid_idx = start + window_size // 2
            sampled_box = boxes[mid_idx]
            frame_number = int(mid_idx * sample_stride)
            crop = extract_frame_crop(video_path, frame_number, sampled_box)
            posture_prob = posture_risk_score(posture_model, crop)
            records.append(
                {
                    "video": video_path.name,
                    "label": window_label,
                    "gru_prob": float(gru_prob),
                    "posture_prob": float(posture_prob),
                }
            )
    return records


def score_metrics(labels: np.ndarray, scores: np.ndarray, threshold: float) -> dict[str, float]:
    preds = (scores >= threshold).astype(int)
    tp = int(((preds == 1) & (labels == 1)).sum())
    fp = int(((preds == 1) & (labels == 0)).sum())
    fn = int(((preds == 0) & (labels == 1)).sum())
    tn = int(((preds == 0) & (labels == 0)).sum())
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    acc = (tp + tn) / max(tp + fp + fn + tn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)
    return {"threshold": threshold, "acc": acc, "precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate GRU + posture fusion on held-out windows.")
    parser.add_argument("--manifest", default=str(PROCESSED / "video_manifest.csv"))
    parser.add_argument("--cache-dir", default=str(PROCESSED / "pose_cache"))
    parser.add_argument("--gru-weights", default=str(ROOT / "weights" / "gru_pose_fall_v1.pt"))
    parser.add_argument("--posture-weights", default=str(ROOT / "runs" / "yolo_posture_person_binary_cls_v1" / "weights" / "best.pt"))
    parser.add_argument("--window-size", type=int, default=24)
    parser.add_argument("--stride", type=int, default=6)
    args = parser.parse_args()

    manifest = pd.read_csv(args.manifest)
    manifest = manifest[manifest["split"].isin(["test", "external"])]
    gru_model = load_gru_model(Path(args.gru_weights))
    posture_model = YOLO(args.posture_weights)
    records = build_window_records(manifest, Path(args.cache_dir), gru_model, posture_model, args.window_size, args.stride)
    df = pd.DataFrame(records)
    labels = df["label"].to_numpy(dtype=int)

    print(f"windows={len(df)} positives={labels.sum()} negatives={(labels == 0).sum()}")
    for name, scores in {
        "gru_only": df["gru_prob"].to_numpy(dtype=float),
        "posture_only": df["posture_prob"].to_numpy(dtype=float),
        "fuse_0.8_0.2": (df["gru_prob"] * 0.8 + df["posture_prob"] * 0.2).to_numpy(dtype=float),
        "fuse_0.7_0.3": (df["gru_prob"] * 0.7 + df["posture_prob"] * 0.3).to_numpy(dtype=float),
        "fuse_0.6_0.4": (df["gru_prob"] * 0.6 + df["posture_prob"] * 0.4).to_numpy(dtype=float),
    }.items():
        best = None
        for threshold in np.arange(0.3, 0.96, 0.05):
            metrics = score_metrics(labels, scores, float(threshold))
            if best is None or metrics["f1"] > best["f1"]:
                best = metrics
        print(name, best)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
