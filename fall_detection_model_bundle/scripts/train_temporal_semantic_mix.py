from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from temporal_semantic_utils import (
    parse_falldb_skeleton,
    semantic_features_from_falldb_rows,
    semantic_features_from_pose_sequence,
)
from train_temporal_gru import video_key_from_path


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data_processed"
WEIGHTS = ROOT / "weights"
RUNS = ROOT / "runs"
POSITIVE_LABELS = {"fall", "fallen", "fall_event", "fall_transition"}
HARD_NEGATIVE_LABELS = {"lying", "lie_down", "sit_down", "sitting"}


class SemanticTemporalNet(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int = 128, nhead: int = 4, num_layers: int = 2) -> None:
        super().__init__()
        self.input_proj = nn.Linear(input_dim, hidden_dim)
        self.conv = nn.Sequential(
            nn.Conv1d(hidden_dim, hidden_dim, kernel_size=3, padding=1),
            nn.GELU(),
            nn.Conv1d(hidden_dim, hidden_dim, kernel_size=3, padding=2, dilation=2),
            nn.GELU(),
            nn.Conv1d(hidden_dim, hidden_dim, kernel_size=3, padding=4, dilation=4),
            nn.GELU(),
        )
        enc = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=nhead,
            dim_feedforward=hidden_dim * 4,
            dropout=0.1,
            batch_first=True,
            activation="gelu",
        )
        self.transformer = nn.TransformerEncoder(enc, num_layers=num_layers)
        self.attn = nn.Linear(hidden_dim, 1)
        self.head = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.GELU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.input_proj(x)
        y = self.conv(x.transpose(1, 2)).transpose(1, 2)
        x = self.transformer(x + y)
        a = torch.softmax(self.attn(x), dim=1)
        pooled = (x * a).sum(dim=1)
        maxpooled = x.max(dim=1).values
        return self.head(torch.cat([pooled, maxpooled], dim=1)).squeeze(-1)


def focal_bce_with_logits(logits: torch.Tensor, targets: torch.Tensor, weights: torch.Tensor, alpha: float = 0.65, gamma: float = 2.0) -> torch.Tensor:
    bce = nn.functional.binary_cross_entropy_with_logits(logits, targets, reduction="none")
    probs = torch.sigmoid(logits)
    pt = targets * probs + (1.0 - targets) * (1.0 - probs)
    alpha_t = targets * alpha + (1.0 - targets) * (1.0 - alpha)
    return (alpha_t * (1.0 - pt).pow(gamma) * bce * weights).mean()


class WeightedSequenceDataset(Dataset):
    def __init__(self, xs: list[np.ndarray], ys: list[int], ws: list[float]) -> None:
        self.xs = [torch.from_numpy(x) for x in xs]
        self.ys = torch.tensor(ys, dtype=torch.float32)
        self.ws = torch.tensor(ws, dtype=torch.float32)

    def __len__(self) -> int:
        return len(self.xs)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        return self.xs[idx], self.ys[idx], self.ws[idx]


@dataclass
class SplitData:
    train_x: list[np.ndarray]
    train_y: list[int]
    train_w: list[float]
    val_x: list[np.ndarray]
    val_y: list[int]
    val_w: list[float]
    test_x: list[np.ndarray]
    test_y: list[int]
    test_w: list[float]


def _window_samples(frame_features: np.ndarray, label_track: np.ndarray, hard_negative_track: np.ndarray, window_size: int, stride: int, positive_ratio: float, hard_negative_weight: float) -> tuple[list[np.ndarray], list[int], list[float]]:
    xs, ys, ws = [], [], []
    for start in range(0, len(frame_features) - window_size + 1, stride):
        end = start + window_size
        pos_mean = float(label_track[start:end].mean())
        label = 1 if pos_mean >= positive_ratio else 0
        weight = 1.25 if label == 1 else (hard_negative_weight if float(hard_negative_track[start:end].mean()) >= 0.3 else 1.0)
        xs.append(frame_features[start:end].astype(np.float32))
        ys.append(label)
        ws.append(weight)
    return xs, ys, ws


def build_rgb_samples(manifest: pd.DataFrame, pose_cache_dir: Path, window_size: int, stride: int, positive_ratio: float, hard_negative_weight: float) -> tuple[list[np.ndarray], list[int], list[float]]:
    xs, ys, ws = [], [], []
    for video_path, rows in manifest.groupby("video_path"):
        key = video_key_from_path(video_path)
        pose_cache_path = pose_cache_dir / f"{key}.npz"
        meta_path = pose_cache_dir / f"{key}.json"
        if not pose_cache_path.exists() or not meta_path.exists():
            continue
        cache = np.load(pose_cache_path)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        features = semantic_features_from_pose_sequence(cache["keypoints"], cache["boxes"])
        fps = float(meta["fps"])
        if len(features) < window_size:
            continue
        label_track = np.zeros(len(features), dtype=np.float32)
        hard_negative_track = np.zeros(len(features), dtype=np.float32)
        ignore_track = np.zeros(len(features), dtype=bool)
        for row in rows.itertuples(index=False):
            if row.dataset == "gmdcsa24":
                start_idx = max(0, int(math.floor(row.segment_start_s * fps)))
                end_idx = len(features) if row.segment_end_s < 0 else min(len(features), int(math.ceil(row.segment_end_s * fps)))
                if row.label_name in POSITIVE_LABELS:
                    label_track[start_idx:end_idx] = 1.0
                else:
                    if row.label_name in HARD_NEGATIVE_LABELS:
                        hard_negative_track[start_idx:end_idx] = 1.0
            elif row.dataset == "private_scene":
                start_idx = max(0, int(math.floor(row.segment_start_s * fps)))
                end_idx = len(features) if row.segment_end_s < 0 else min(len(features), int(math.ceil(row.segment_end_s * fps)))
                if row.label_name in POSITIVE_LABELS:
                    label_track[start_idx:end_idx] = 1.0
                else:
                    if row.label_name in HARD_NEGATIVE_LABELS:
                        hard_negative_track[start_idx:end_idx] = 1.0
            elif row.dataset == "urfd":
                if row.binary_label == 1:
                    split_idx = int(len(features) * 0.55)
                    ignore_track[: int(len(features) * 0.25)] = True
                    label_track[split_idx:] = 1.0
        sub_x, sub_y, sub_w = _window_samples(features[~ignore_track] if ignore_track.any() else features, label_track[~ignore_track] if ignore_track.any() else label_track, hard_negative_track[~ignore_track] if ignore_track.any() else hard_negative_track, window_size, stride, positive_ratio, hard_negative_weight)
        xs.extend(sub_x)
        ys.extend(sub_y)
        ws.extend(sub_w)
    return xs, ys, ws


def build_falldb_samples(manifest: pd.DataFrame, window_size: int, stride: int) -> tuple[list[np.ndarray], list[int], list[float]]:
    xs, ys, ws = [], [], []
    for row in manifest.itertuples(index=False):
        raw = parse_falldb_skeleton(Path(row.sequence_path))
        features = semantic_features_from_falldb_rows(raw)
        if len(features) < window_size:
            continue
        label_track = np.zeros(len(features), dtype=np.float32)
        if row.binary_label == 1:
            start_idx = int(len(features) * 0.55)
            label_track[start_idx:] = 1.0
        hard_track = np.zeros(len(features), dtype=np.float32)
        sub_x, sub_y, sub_w = _window_samples(features, label_track, hard_track, window_size, stride, 0.5, 1.0)
        xs.extend(sub_x)
        ys.extend(sub_y)
        ws.extend([w * 1.15 for w in sub_w])
    return xs, ys, ws


def prepare_splits(video_manifest_path: Path, falldb_manifest_path: Path, pose_cache_dir: Path, window_size: int, stride: int, positive_ratio: float, hard_negative_weight: float) -> SplitData:
    video_manifest = pd.read_csv(video_manifest_path)
    video_manifest = video_manifest[video_manifest["dataset"].isin(["gmdcsa24", "urfd", "private_scene"])]
    falldb_manifest = pd.read_csv(falldb_manifest_path)

    train_video = video_manifest[video_manifest["split"] == "train"]
    val_video = video_manifest[video_manifest["split"] == "val"]
    test_video = video_manifest[video_manifest["split"].isin(["test", "external"])]

    train_x1, train_y1, train_w1 = build_rgb_samples(train_video, pose_cache_dir, window_size, stride, positive_ratio, hard_negative_weight)
    val_x1, val_y1, val_w1 = build_rgb_samples(val_video, pose_cache_dir, window_size, stride, positive_ratio, hard_negative_weight)
    test_x1, test_y1, test_w1 = build_rgb_samples(test_video, pose_cache_dir, window_size, stride, positive_ratio, hard_negative_weight)

    train_fb = falldb_manifest[falldb_manifest["split"] == "train"]
    val_fb = falldb_manifest[falldb_manifest["split"] == "val"]
    test_fb = falldb_manifest[falldb_manifest["split"] == "test"]
    train_x2, train_y2, train_w2 = build_falldb_samples(train_fb, window_size, stride)
    val_x2, val_y2, val_w2 = build_falldb_samples(val_fb, window_size, stride)
    test_x2, test_y2, test_w2 = build_falldb_samples(test_fb, window_size, stride)

    return SplitData(
        train_x1 + train_x2, train_y1 + train_y2, train_w1 + train_w2,
        val_x1 + val_x2, val_y1 + val_y2, val_w1 + val_w2,
        test_x1 + test_x2, test_y1 + test_y2, test_w1 + test_w2,
    )


def evaluate(model: nn.Module, loader: DataLoader, device: torch.device, threshold: float) -> dict[str, float]:
    model.eval()
    total = 0
    correct = 0
    loss_sum = 0.0
    tp = fp = fn = tn = 0
    with torch.no_grad():
        for xb, yb, wb in loader:
            xb = xb.to(device)
            yb = yb.to(device)
            wb = wb.to(device)
            logits = model(xb)
            loss = focal_bce_with_logits(logits, yb, wb)
            probs = torch.sigmoid(logits)
            preds = (probs >= threshold).float()
            total += yb.numel()
            correct += (preds == yb).sum().item()
            loss_sum += loss.item() * yb.numel()
            tp += ((preds == 1) & (yb == 1)).sum().item()
            fp += ((preds == 1) & (yb == 0)).sum().item()
            fn += ((preds == 0) & (yb == 1)).sum().item()
            tn += ((preds == 0) & (yb == 0)).sum().item()
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)
    return {"loss": loss_sum / max(total, 1), "accuracy": correct / max(total, 1), "precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn, "tn": tn, "threshold": threshold}


def select_best_threshold(model: nn.Module, loader: DataLoader, device: torch.device) -> tuple[float, dict[str, float]]:
    best = None
    best_thr = 0.5
    for thr in np.arange(0.3, 0.91, 0.05):
        metrics = evaluate(model, loader, device, float(thr))
        if best is None or metrics["f1"] > best["f1"]:
            best = metrics
            best_thr = float(thr)
    assert best is not None
    return best_thr, best


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a semantic temporal model mixed with FallDatabase skeletons.")
    parser.add_argument("--video-manifest", default=str(PROCESSED / "video_manifest.csv"))
    parser.add_argument("--falldb-manifest", default=str(PROCESSED / "falldb_manifest.csv"))
    parser.add_argument("--pose-cache-dir", default=str(PROCESSED / "pose_cache"))
    parser.add_argument("--window-size", type=int, default=24)
    parser.add_argument("--stride", type=int, default=6)
    parser.add_argument("--positive-ratio", type=float, default=0.5)
    parser.add_argument("--hard-negative-weight", type=float, default=2.2)
    parser.add_argument("--epochs", type=int, default=16)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=8e-4)
    parser.add_argument("--run-name", default="semantic_mix_falldb_v1")
    args = parser.parse_args()

    split_data = prepare_splits(Path(args.video_manifest), Path(args.falldb_manifest), Path(args.pose_cache_dir), args.window_size, args.stride, args.positive_ratio, args.hard_negative_weight)
    if not split_data.train_x or not split_data.val_x:
        raise RuntimeError("No samples were built.")

    train_ds = WeightedSequenceDataset(split_data.train_x, split_data.train_y, split_data.train_w)
    val_ds = WeightedSequenceDataset(split_data.val_x, split_data.val_y, split_data.val_w)
    test_ds = WeightedSequenceDataset(split_data.test_x, split_data.test_y, split_data.test_w)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False)
    test_loader = DataLoader(test_ds, batch_size=args.batch_size, shuffle=False)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    input_dim = split_data.train_x[0].shape[-1]
    model = SemanticTemporalNet(input_dim=input_dim).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)

    run_dir = RUNS / args.run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    best_path = WEIGHTS / f"{args.run_name}.pt"
    history = []
    best_f1 = -1.0
    best_thr = 0.5

    for epoch in range(1, args.epochs + 1):
        model.train()
        for xb, yb, wb in train_loader:
            xb = xb.to(device)
            yb = yb.to(device)
            wb = wb.to(device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(xb)
            loss = focal_bce_with_logits(logits, yb, wb)
            loss.backward()
            optimizer.step()
        train_metrics = evaluate(model, train_loader, device, 0.5)
        thr, val_metrics = select_best_threshold(model, val_loader, device)
        history.append({"epoch": epoch, "train": train_metrics, "val": val_metrics})
        print(f"[epoch {epoch}] train_acc={train_metrics['accuracy']:.4f} val_acc={val_metrics['accuracy']:.4f} val_f1={val_metrics['f1']:.4f} val_thr={thr:.2f}")
        if val_metrics["f1"] > best_f1:
            best_f1 = val_metrics["f1"]
            best_thr = thr
            torch.save({"model_state": model.state_dict(), "input_dim": input_dim, "model_type": "semantic_temporal_mix", "best_threshold": best_thr}, best_path)

    ckpt = torch.load(best_path, map_location=device)
    model.load_state_dict(ckpt["model_state"])
    test_metrics = evaluate(model, test_loader, device, float(ckpt["best_threshold"]))
    report = {
        "history": history,
        "test_metrics": test_metrics,
        "train_samples": len(train_ds),
        "val_samples": len(val_ds),
        "test_samples": len(test_ds),
        "window_size": args.window_size,
        "stride": args.stride,
        "best_threshold": float(ckpt["best_threshold"]),
    }
    report_path = run_dir / "metrics.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(test_metrics, indent=2))
    print(f"[saved] {best_path}")
    print(f"[saved] {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
