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

from train_temporal_gru import normalize_pose, video_key_from_path


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data_processed"
WEIGHTS = ROOT / "weights"
RUNS = ROOT / "runs"

POSITIVE_LABELS = {"fall", "fallen", "fall_event", "fall_transition"}
HARD_NEGATIVE_LABELS = {"lying", "lie_down", "sit_down", "sitting"}


def focal_bce_with_logits(logits: torch.Tensor, targets: torch.Tensor, weights: torch.Tensor, alpha: float = 0.65, gamma: float = 2.0) -> torch.Tensor:
    bce = nn.functional.binary_cross_entropy_with_logits(logits, targets, reduction="none")
    probs = torch.sigmoid(logits)
    pt = targets * probs + (1.0 - targets) * (1.0 - probs)
    alpha_t = targets * alpha + (1.0 - targets) * (1.0 - alpha)
    focal = alpha_t * (1.0 - pt).pow(gamma) * bce
    return (focal * weights).mean()


def augment_frame_features(pose_features: np.ndarray, risk_cache_path: Path | None) -> np.ndarray:
    if risk_cache_path is None or not risk_cache_path.exists():
        zeros = np.zeros((pose_features.shape[0], 3), dtype=np.float32)
        return np.concatenate([pose_features, zeros], axis=1)
    risk = np.load(risk_cache_path)
    scores = risk["risk_scores"].reshape(-1, 1).astype(np.float32)
    delta = risk["risk_delta"].reshape(-1, 1).astype(np.float32)
    smooth = risk["risk_smooth"].reshape(-1, 1).astype(np.float32)
    n = min(pose_features.shape[0], scores.shape[0])
    if n < pose_features.shape[0]:
        pad = pose_features.shape[0] - n
        scores = np.pad(scores[:n], ((0, pad), (0, 0)), constant_values=0.0)
        delta = np.pad(delta[:n], ((0, pad), (0, 0)), constant_values=0.0)
        smooth = np.pad(smooth[:n], ((0, pad), (0, 0)), constant_values=0.0)
    else:
        scores = scores[: pose_features.shape[0]]
        delta = delta[: pose_features.shape[0]]
        smooth = smooth[: pose_features.shape[0]]
    return np.concatenate([pose_features, scores, delta, smooth], axis=1)


def build_samples(
    manifest: pd.DataFrame,
    pose_cache_dir: Path,
    risk_cache_dir: Path,
    window_size: int,
    stride: int,
    positive_ratio: float,
    hard_negative_weight: float,
) -> tuple[list[np.ndarray], list[int], list[float]]:
    features_list: list[np.ndarray] = []
    labels_list: list[int] = []
    weights_list: list[float] = []

    grouped = manifest.groupby("video_path")
    for video_path, rows in grouped:
        key = video_key_from_path(video_path)
        cache_path = pose_cache_dir / f"{key}.npz"
        meta_path = pose_cache_dir / f"{key}.json"
        risk_cache_path = risk_cache_dir / f"{key}.npz"
        if not cache_path.exists() or not meta_path.exists():
            continue

        cache = np.load(cache_path)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        pose_features = normalize_pose(cache["keypoints"], cache["boxes"])
        frame_features = augment_frame_features(pose_features, risk_cache_path if risk_cache_path.exists() else None)
        fps = float(meta["fps"])
        total_frames = frame_features.shape[0]
        if total_frames < window_size:
            continue

        label_track = np.zeros(total_frames, dtype=np.float32)
        hard_negative_track = np.zeros(total_frames, dtype=np.float32)
        ignore_track = np.zeros(total_frames, dtype=bool)

        for row in rows.itertuples(index=False):
            if row.dataset == "gmdcsa24":
                start_idx = max(0, int(math.floor(row.segment_start_s * fps)))
                end_idx = total_frames if row.segment_end_s < 0 else min(total_frames, int(math.ceil(row.segment_end_s * fps)))
                if end_idx <= start_idx:
                    continue
                if row.label_name in POSITIVE_LABELS:
                    label_track[start_idx:end_idx] = 1.0
                else:
                    label_track[start_idx:end_idx] = 0.0
                    if row.label_name in HARD_NEGATIVE_LABELS:
                        hard_negative_track[start_idx:end_idx] = 1.0
            elif row.dataset == "private_scene":
                start_idx = max(0, int(math.floor(row.segment_start_s * fps)))
                end_idx = total_frames if row.segment_end_s < 0 else min(total_frames, int(math.ceil(row.segment_end_s * fps)))
                if end_idx <= start_idx:
                    continue
                if row.label_name in POSITIVE_LABELS:
                    label_track[start_idx:end_idx] = 1.0
                else:
                    label_track[start_idx:end_idx] = 0.0
                    if row.label_name in HARD_NEGATIVE_LABELS:
                        hard_negative_track[start_idx:end_idx] = 1.0
            elif row.dataset == "urfd":
                if row.binary_label == 0:
                    label_track[:] = 0.0
                else:
                    split_idx = int(total_frames * 0.55)
                    ignore_track[: int(total_frames * 0.25)] = True
                    label_track[split_idx:] = 1.0

        for start in range(0, total_frames - window_size + 1, stride):
            end = start + window_size
            if ignore_track[start:end].any():
                continue
            pos_mean = float(label_track[start:end].mean())
            label = 1 if pos_mean >= positive_ratio else 0
            weight = 1.0
            if label == 0 and float(hard_negative_track[start:end].mean()) >= 0.3:
                weight = hard_negative_weight
            if label == 1:
                weight = 1.25
            features_list.append(frame_features[start:end].astype(np.float32))
            labels_list.append(label)
            weights_list.append(weight)

    return features_list, labels_list, weights_list


class WeightedSequenceDataset(Dataset):
    def __init__(self, sequences: list[np.ndarray], labels: list[int], weights: list[float]) -> None:
        self.sequences = [torch.from_numpy(x) for x in sequences]
        self.labels = torch.tensor(labels, dtype=torch.float32)
        self.weights = torch.tensor(weights, dtype=torch.float32)

    def __len__(self) -> int:
        return len(self.sequences)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        return self.sequences[idx], self.labels[idx], self.weights[idx]


class DilatedResidualBlock(nn.Module):
    def __init__(self, channels: int, dilation: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv1d(channels, channels, kernel_size=3, padding=dilation, dilation=dilation),
            nn.BatchNorm1d(channels),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Conv1d(channels, channels, kernel_size=1),
            nn.BatchNorm1d(channels),
        )
        self.act = nn.GELU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.act(x + self.net(x))


class HybridTCNTransformer(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int = 160, nhead: int = 4, num_layers: int = 2) -> None:
        super().__init__()
        self.input_proj = nn.Linear(input_dim, hidden_dim)
        self.tcn = nn.Sequential(
            DilatedResidualBlock(hidden_dim, 1),
            DilatedResidualBlock(hidden_dim, 2),
            DilatedResidualBlock(hidden_dim, 4),
        )
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=nhead,
            dim_feedforward=hidden_dim * 4,
            dropout=0.1,
            batch_first=True,
            activation="gelu",
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.attn = nn.Linear(hidden_dim, 1)
        self.head = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.GELU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.input_proj(x)
        tcn_out = self.tcn(x.transpose(1, 2)).transpose(1, 2)
        x = self.transformer(x + tcn_out)
        attn_weights = torch.softmax(self.attn(x), dim=1)
        pooled = (x * attn_weights).sum(dim=1)
        maxpooled = x.max(dim=1).values
        feat = torch.cat([pooled, maxpooled], dim=1)
        return self.head(feat).squeeze(-1)


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


def prepare_splits(
    manifest_path: Path,
    pose_cache_dir: Path,
    risk_cache_dir: Path,
    window_size: int,
    stride: int,
    positive_ratio: float,
    hard_negative_weight: float,
) -> SplitData:
    manifest = pd.read_csv(manifest_path)
    manifest = manifest[manifest["dataset"].isin(["gmdcsa24", "urfd", "private_scene"])]
    train = manifest[manifest["split"] == "train"]
    val = manifest[manifest["split"] == "val"]
    test = manifest[manifest["split"].isin(["test", "external"])]
    train_x, train_y, train_w = build_samples(train, pose_cache_dir, risk_cache_dir, window_size, stride, positive_ratio, hard_negative_weight)
    val_x, val_y, val_w = build_samples(val, pose_cache_dir, risk_cache_dir, window_size, stride, positive_ratio, hard_negative_weight)
    test_x, test_y, test_w = build_samples(test, pose_cache_dir, risk_cache_dir, window_size, stride, positive_ratio, hard_negative_weight)
    return SplitData(train_x, train_y, train_w, val_x, val_y, val_w, test_x, test_y, test_w)


def evaluate(model: nn.Module, loader: DataLoader, device: torch.device, threshold: float = 0.5) -> dict[str, float]:
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
    return {
        "loss": loss_sum / max(total, 1),
        "accuracy": correct / max(total, 1),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "threshold": threshold,
    }


def select_best_threshold(model: nn.Module, loader: DataLoader, device: torch.device) -> tuple[float, dict[str, float]]:
    best_threshold = 0.5
    best_metrics = None
    for threshold in np.arange(0.3, 0.91, 0.05):
        metrics = evaluate(model, loader, device, threshold=float(threshold))
        if best_metrics is None or metrics["f1"] > best_metrics["f1"]:
            best_metrics = metrics
            best_threshold = float(threshold)
    assert best_metrics is not None
    return best_threshold, best_metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a temporal TCN+Transformer hybrid fall detector.")
    parser.add_argument("--manifest", default=str(PROCESSED / "video_manifest.csv"))
    parser.add_argument("--pose-cache-dir", default=str(PROCESSED / "pose_cache"))
    parser.add_argument("--risk-cache-dir", default=str(PROCESSED / "posture_risk_cache"))
    parser.add_argument("--window-size", type=int, default=24)
    parser.add_argument("--stride", type=int, default=4)
    parser.add_argument("--positive-ratio", type=float, default=0.3)
    parser.add_argument("--hard-negative-weight", type=float, default=2.0)
    parser.add_argument("--epochs", type=int, default=18)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=8e-4)
    parser.add_argument("--run-name", default="hybrid_tcn_transformer_v1")
    args = parser.parse_args()

    split_data = prepare_splits(
        Path(args.manifest),
        Path(args.pose_cache_dir),
        Path(args.risk_cache_dir),
        args.window_size,
        args.stride,
        args.positive_ratio,
        args.hard_negative_weight,
    )
    if not split_data.train_x or not split_data.val_x:
        raise RuntimeError("No training or validation samples were built. Extract pose and posture risk cache first.")

    train_ds = WeightedSequenceDataset(split_data.train_x, split_data.train_y, split_data.train_w)
    val_ds = WeightedSequenceDataset(split_data.val_x, split_data.val_y, split_data.val_w)
    test_ds = WeightedSequenceDataset(split_data.test_x, split_data.test_y, split_data.test_w)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False)
    test_loader = DataLoader(test_ds, batch_size=args.batch_size, shuffle=False)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    input_dim = split_data.train_x[0].shape[-1]
    model = HybridTCNTransformer(input_dim=input_dim).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)

    run_dir = RUNS / args.run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    WEIGHTS.mkdir(parents=True, exist_ok=True)
    best_path = WEIGHTS / f"{args.run_name}.pt"

    best_val_f1 = -1.0
    best_threshold = 0.5
    history = []
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

        train_metrics = evaluate(model, train_loader, device, threshold=0.5)
        epoch_best_threshold, val_metrics = select_best_threshold(model, val_loader, device)
        row = {"epoch": epoch, "train": train_metrics, "val": val_metrics}
        history.append(row)
        print(
            f"[epoch {epoch}] train_acc={train_metrics['accuracy']:.4f} "
            f"val_acc={val_metrics['accuracy']:.4f} val_f1={val_metrics['f1']:.4f} val_thr={epoch_best_threshold:.2f}"
        )
        if val_metrics["f1"] > best_val_f1:
            best_val_f1 = val_metrics["f1"]
            best_threshold = epoch_best_threshold
            torch.save(
                {
                    "model_state": model.state_dict(),
                    "input_dim": input_dim,
                    "model_type": "hybrid_tcn_transformer",
                    "window_size": args.window_size,
                    "stride": args.stride,
                    "best_threshold": best_threshold,
                },
                best_path,
            )

    checkpoint = torch.load(best_path, map_location=device)
    model.load_state_dict(checkpoint["model_state"])
    test_metrics = evaluate(model, test_loader, device, threshold=float(checkpoint["best_threshold"]))
    report = {
        "history": history,
        "test_metrics": test_metrics,
        "train_samples": len(train_ds),
        "val_samples": len(val_ds),
        "test_samples": len(test_ds),
        "window_size": args.window_size,
        "stride": args.stride,
        "best_threshold": float(checkpoint["best_threshold"]),
    }
    report_path = run_dir / "metrics.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(test_metrics, indent=2))
    print(f"[saved] {best_path}")
    print(f"[saved] {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
