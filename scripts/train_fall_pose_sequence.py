from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.models.fall_pose_tcn_model import FallPoseTCNModel


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a lightweight TCN on exported YOLO-pose fall windows.")
    parser.add_argument(
        "dataset",
        type=Path,
        nargs="?",
        default=ROOT / "data" / "fall_eval" / "pose_tcn_dataset.npz",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ROOT / "fall_detection_model_bundle" / "weights" / "pose_tcn_fall_v2.pt",
    )
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument(
        "--allow-single-class",
        action="store_true",
        help="Allow smoke-test training when the dataset has only one class. Not useful for real accuracy.",
    )
    return parser.parse_args()


def load_dataset(path: Path) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    data = np.load(path, allow_pickle=True)
    x = data["x"].astype(np.float32)
    y = data["y"].astype(np.float32)
    metadata = [dict(item) for item in data.get("metadata", np.asarray([], dtype=object)).tolist()]
    return x, y, metadata


def split_indices(y: np.ndarray, val_ratio: float) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(42)
    train_parts: list[np.ndarray] = []
    val_parts: list[np.ndarray] = []
    for label in sorted(set(int(v) for v in y.tolist())):
        indices = np.where(y.astype(int) == label)[0]
        rng.shuffle(indices)
        val_count = max(1, int(round(len(indices) * val_ratio))) if len(indices) > 1 else 0
        val_parts.append(indices[:val_count])
        train_parts.append(indices[val_count:])
    train = np.concatenate([part for part in train_parts if len(part)], axis=0)
    val = np.concatenate([part for part in val_parts if len(part)], axis=0) if any(len(part) for part in val_parts) else train.copy()
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


def metrics_from_logits(logits: torch.Tensor, labels: torch.Tensor) -> dict[str, float]:
    probs = torch.sigmoid(logits)
    preds = (probs >= 0.5).float()
    tp = float(((preds == 1) & (labels == 1)).sum().item())
    fp = float(((preds == 1) & (labels == 0)).sum().item())
    fn = float(((preds == 0) & (labels == 1)).sum().item())
    tn = float(((preds == 0) & (labels == 0)).sum().item())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = (tp + tn) / max(1.0, tp + fp + fn + tn)
    return {"accuracy": accuracy, "precision": precision, "recall": recall, "f1": f1}


def evaluate(model: FallPoseTCNModel, loader: DataLoader, device: torch.device, criterion: nn.Module) -> dict[str, float]:
    model.eval()
    losses: list[float] = []
    logits_all: list[torch.Tensor] = []
    labels_all: list[torch.Tensor] = []
    with torch.no_grad():
        for batch_x, batch_y in loader:
            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)
            logits = model(batch_x)
            loss = criterion(logits, batch_y)
            losses.append(float(loss.item()))
            logits_all.append(logits.detach().cpu())
            labels_all.append(batch_y.detach().cpu())
    if not logits_all:
        return {"loss": 0.0, "accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0}
    metrics = metrics_from_logits(torch.cat(logits_all), torch.cat(labels_all))
    metrics["loss"] = float(np.mean(losses)) if losses else 0.0
    return metrics


def main() -> int:
    args = parse_args()
    x, y, metadata = load_dataset(args.dataset.expanduser())
    classes = sorted(set(int(v) for v in y.tolist()))
    if len(classes) < 2 and not args.allow_single_class:
        raise SystemExit(
            "Dataset has only one class. Add normal/sitting/lying/bending videos, or use --allow-single-class for a smoke test."
        )

    train_idx, val_idx = split_indices(y, args.val_ratio)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train_set = TensorDataset(torch.from_numpy(x[train_idx]), torch.from_numpy(y[train_idx]))
    val_set = TensorDataset(torch.from_numpy(x[val_idx]), torch.from_numpy(y[val_idx]))
    train_loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_set, batch_size=args.batch_size, shuffle=False)

    model = FallPoseTCNModel(input_dim=int(x.shape[2])).to(device)
    pos = float(y[train_idx].sum())
    neg = float(len(train_idx) - pos)
    pos_weight = torch.tensor([neg / max(1.0, pos)], dtype=torch.float32, device=device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)

    best_state: dict[str, torch.Tensor] | None = None
    best_metrics: dict[str, float] = {}
    best_score = -1.0
    history: list[dict[str, Any]] = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        train_losses: list[float] = []
        for batch_x, batch_y in train_loader:
            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(batch_x)
            loss = criterion(logits, batch_y)
            loss.backward()
            optimizer.step()
            train_losses.append(float(loss.item()))
        val_metrics = evaluate(model, val_loader, device, criterion)
        val_metrics["train_loss"] = float(np.mean(train_losses)) if train_losses else 0.0
        val_metrics["epoch"] = epoch
        history.append(val_metrics)
        score = val_metrics["f1"] if len(classes) >= 2 else -val_metrics["loss"]
        if score > best_score:
            best_score = score
            best_metrics = val_metrics
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
        print(
            f"epoch={epoch:03d} train_loss={val_metrics['train_loss']:.4f} "
            f"val_loss={val_metrics['loss']:.4f} f1={val_metrics['f1']:.4f} recall={val_metrics['recall']:.4f}"
        )

    if best_state is not None:
        model.load_state_dict(best_state)
    model.save(
        args.output,
        metadata={
            "dataset": str(args.dataset),
            "samples": int(x.shape[0]),
            "sequence_length": int(x.shape[1]),
            "feature_dim": int(x.shape[2]),
            "positive_samples": int(y.sum()),
            "negative_samples": int((y == 0).sum()),
            "classes": classes,
            "best_metrics": best_metrics,
            "warning": "single-class smoke model" if len(classes) < 2 else None,
        },
    )
    report = args.output.with_suffix(args.output.suffix + ".json")
    report.write_text(json.dumps({"best_metrics": best_metrics, "history": history, "metadata_count": len(metadata)}, indent=2), encoding="utf-8")
    print(f"[pose-tcn] saved {args.output}")
    print(f"[pose-tcn] report {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
