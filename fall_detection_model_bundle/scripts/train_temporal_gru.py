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


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data_processed"
WEIGHTS = ROOT / "weights"
RUNS = ROOT / "runs"


POSITIVE_LABELS = {"fall", "fallen", "fall_event", "fall_transition"}


def normalize_pose(keypoints: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    features = []
    prev_xy = None
    for kp, box in zip(keypoints, boxes):
        x1, y1, x2, y2 = box
        w = max(x2 - x1, 1.0)
        h = max(y2 - y1, 1.0)
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0

        xy = kp[:, :2].copy()
        conf = kp[:, 2:3].copy()
        if h <= 1.0 or w <= 1.0:
            xy[:] = 0.0
            conf[:] = 0.0
        else:
            xy[:, 0] = (xy[:, 0] - cx) / h
            xy[:, 1] = (xy[:, 1] - cy) / h

        if prev_xy is None:
            vel = np.zeros_like(xy)
        else:
            vel = xy - prev_xy
        prev_xy = xy.copy()

        aspect = np.asarray([[w / h]], dtype=np.float32)
        center_y = np.asarray([[cy / max(y2, 1.0)]], dtype=np.float32)
        frame_feature = np.concatenate([xy.reshape(-1), conf.reshape(-1), vel.reshape(-1), aspect.reshape(-1), center_y.reshape(-1)])
        features.append(frame_feature.astype(np.float32))
    return np.asarray(features, dtype=np.float32)


def video_key_from_path(path: str) -> str:
    video_path = Path(path)
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


def build_samples(manifest: pd.DataFrame, cache_dir: Path, window_size: int, stride: int) -> tuple[list[np.ndarray], list[int]]:
    features_list: list[np.ndarray] = []
    labels_list: list[int] = []

    grouped = manifest.groupby("video_path")
    for video_path, rows in grouped:
        key = video_key_from_path(video_path)
        cache_path = cache_dir / f"{key}.npz"
        meta_path = cache_dir / f"{key}.json"
        if not cache_path.exists() or not meta_path.exists():
            continue

        cache = np.load(cache_path)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        frame_features = normalize_pose(cache["keypoints"], cache["boxes"])
        fps = float(meta["fps"])
        total_frames = frame_features.shape[0]

        if total_frames < window_size:
            continue

        label_track = np.zeros(total_frames, dtype=np.int64)
        ignore_track = np.zeros(total_frames, dtype=bool)

        for row in rows.itertuples(index=False):
            if row.dataset == "gmdcsa24":
                start_idx = max(0, int(math.floor(row.segment_start_s * fps)))
                if row.segment_end_s < 0:
                    end_idx = total_frames
                else:
                    end_idx = min(total_frames, int(math.ceil(row.segment_end_s * fps)))
                if end_idx <= start_idx:
                    continue
                if row.label_name in POSITIVE_LABELS:
                    label_track[start_idx:end_idx] = 1
                else:
                    label_track[start_idx:end_idx] = 0
            elif row.dataset == "private_scene":
                start_idx = max(0, int(math.floor(row.segment_start_s * fps)))
                if row.segment_end_s < 0:
                    end_idx = total_frames
                else:
                    end_idx = min(total_frames, int(math.ceil(row.segment_end_s * fps)))
                if end_idx <= start_idx:
                    continue
                if row.label_name in POSITIVE_LABELS:
                    label_track[start_idx:end_idx] = 1
                else:
                    label_track[start_idx:end_idx] = 0
            elif row.dataset == "urfd":
                # URFD has only clip-level labels, so we use a weak heuristic:
                # ADL clips are negative; fall clips are positive only in the latter half.
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
            features_list.append(frame_features[start:end])
            labels_list.append(window_label)

    return features_list, labels_list


class SequenceDataset(Dataset):
    def __init__(self, sequences: list[np.ndarray], labels: list[int]) -> None:
        self.sequences = [torch.from_numpy(x) for x in sequences]
        self.labels = torch.tensor(labels, dtype=torch.float32)

    def __len__(self) -> int:
        return len(self.sequences)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        return self.sequences[idx], self.labels[idx]


class GRUFallNet(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int = 128) -> None:
        super().__init__()
        self.gru = nn.GRU(input_dim, hidden_dim, batch_first=True, num_layers=2, dropout=0.2)
        self.head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim // 2, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.gru(x)
        return self.head(out[:, -1, :]).squeeze(-1)


@dataclass
class SplitData:
    train_x: list[np.ndarray]
    train_y: list[int]
    val_x: list[np.ndarray]
    val_y: list[int]
    test_x: list[np.ndarray]
    test_y: list[int]


def prepare_splits(manifest_path: Path, cache_dir: Path, window_size: int, stride: int) -> SplitData:
    manifest = pd.read_csv(manifest_path)
    manifest = manifest[manifest["dataset"].isin(["gmdcsa24", "urfd", "private_scene"])]
    train = manifest[manifest["split"] == "train"]
    val = manifest[manifest["split"] == "val"]
    test = manifest[manifest["split"].isin(["test", "external"])]
    train_x, train_y = build_samples(train, cache_dir, window_size, stride)
    val_x, val_y = build_samples(val, cache_dir, window_size, stride)
    test_x, test_y = build_samples(test, cache_dir, window_size, stride)
    return SplitData(train_x, train_y, val_x, val_y, test_x, test_y)


def evaluate(model: nn.Module, loader: DataLoader, device: torch.device) -> dict[str, float]:
    model.eval()
    total = 0
    correct = 0
    loss_sum = 0.0
    criterion = nn.BCEWithLogitsLoss()
    tp = fp = fn = 0
    with torch.no_grad():
        for xb, yb in loader:
            xb = xb.to(device)
            yb = yb.to(device)
            logits = model(xb)
            loss = criterion(logits, yb)
            probs = torch.sigmoid(logits)
            preds = (probs >= 0.5).float()
            total += yb.numel()
            correct += (preds == yb).sum().item()
            loss_sum += loss.item() * yb.numel()
            tp += ((preds == 1) & (yb == 1)).sum().item()
            fp += ((preds == 1) & (yb == 0)).sum().item()
            fn += ((preds == 0) & (yb == 1)).sum().item()
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    return {
        "loss": loss_sum / max(total, 1),
        "accuracy": correct / max(total, 1),
        "precision": precision,
        "recall": recall,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a temporal GRU fall detector from pose sequences.")
    parser.add_argument("--manifest", default=str(PROCESSED / "video_manifest.csv"))
    parser.add_argument("--cache-dir", default=str(PROCESSED / "pose_cache"))
    parser.add_argument("--window-size", type=int, default=24)
    parser.add_argument("--stride", type=int, default=6)
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--run-name", default="gru_pose_fall_v1")
    args = parser.parse_args()

    split_data = prepare_splits(Path(args.manifest), Path(args.cache_dir), args.window_size, args.stride)
    if not split_data.train_x or not split_data.val_x:
        raise RuntimeError("No training or validation samples were built. Extract pose cache first.")

    train_ds = SequenceDataset(split_data.train_x, split_data.train_y)
    val_ds = SequenceDataset(split_data.val_x, split_data.val_y)
    test_ds = SequenceDataset(split_data.test_x, split_data.test_y)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False)
    test_loader = DataLoader(test_ds, batch_size=args.batch_size, shuffle=False)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    input_dim = split_data.train_x[0].shape[-1]
    model = GRUFallNet(input_dim=input_dim).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    criterion = nn.BCEWithLogitsLoss()

    run_dir = RUNS / args.run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    WEIGHTS.mkdir(parents=True, exist_ok=True)
    best_path = WEIGHTS / f"{args.run_name}.pt"

    best_val = float("inf")
    history = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        for xb, yb in train_loader:
            xb = xb.to(device)
            yb = yb.to(device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(xb)
            loss = criterion(logits, yb)
            loss.backward()
            optimizer.step()

        train_metrics = evaluate(model, train_loader, device)
        val_metrics = evaluate(model, val_loader, device)
        row = {"epoch": epoch, "train": train_metrics, "val": val_metrics}
        history.append(row)
        print(f"[epoch {epoch}] train_acc={train_metrics['accuracy']:.4f} val_acc={val_metrics['accuracy']:.4f} val_recall={val_metrics['recall']:.4f}")
        if val_metrics["loss"] < best_val:
            best_val = val_metrics["loss"]
            torch.save({"model_state": model.state_dict(), "input_dim": input_dim}, best_path)

    checkpoint = torch.load(best_path, map_location=device)
    model.load_state_dict(checkpoint["model_state"])
    test_metrics = evaluate(model, test_loader, device)
    report = {
        "history": history,
        "test_metrics": test_metrics,
        "train_samples": len(train_ds),
        "val_samples": len(val_ds),
        "test_samples": len(test_ds),
        "window_size": args.window_size,
        "stride": args.stride,
    }
    report_path = run_dir / "metrics.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(test_metrics, indent=2))
    print(f"[saved] {best_path}")
    print(f"[saved] {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
