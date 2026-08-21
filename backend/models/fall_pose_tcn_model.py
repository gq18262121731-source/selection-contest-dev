from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
from torch import Tensor, nn


class Chomp1d(nn.Module):
    def __init__(self, chomp_size: int) -> None:
        super().__init__()
        self.chomp_size = chomp_size

    def forward(self, x: Tensor) -> Tensor:
        if self.chomp_size <= 0:
            return x
        return x[:, :, :-self.chomp_size].contiguous()


class TemporalBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, *, kernel_size: int, dilation: int, dropout: float) -> None:
        super().__init__()
        padding = (kernel_size - 1) * dilation
        self.net = nn.Sequential(
            nn.Conv1d(in_channels, out_channels, kernel_size, padding=padding, dilation=dilation),
            Chomp1d(padding),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Conv1d(out_channels, out_channels, kernel_size, padding=padding, dilation=dilation),
            Chomp1d(padding),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        self.downsample = nn.Conv1d(in_channels, out_channels, 1) if in_channels != out_channels else nn.Identity()

    def forward(self, x: Tensor) -> Tensor:
        return torch.relu(self.net(x) + self.downsample(x))


class FallPoseTCNModel(nn.Module):
    """Lightweight pose-sequence classifier for fall event refinement.

    Input shape is [batch, sequence, features], where features are normalized
    COCO keypoints flattened as x/y/conf plus optional motion channels.
    """

    def __init__(
        self,
        *,
        input_dim: int,
        hidden_channels: tuple[int, ...] = (64, 64, 96),
        kernel_size: int = 3,
        dropout: float = 0.15,
    ) -> None:
        super().__init__()
        self.input_dim = input_dim
        self.hidden_channels = hidden_channels
        self.kernel_size = kernel_size
        self.dropout = dropout
        layers: list[nn.Module] = []
        channels = (input_dim, *hidden_channels)
        for index in range(len(hidden_channels)):
            layers.append(
                TemporalBlock(
                    channels[index],
                    channels[index + 1],
                    kernel_size=kernel_size,
                    dilation=2**index,
                    dropout=dropout,
                )
            )
        self.tcn = nn.Sequential(*layers)
        self.head = nn.Sequential(
            nn.AdaptiveAvgPool1d(1),
            nn.Flatten(),
            nn.Linear(hidden_channels[-1], 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 1),
        )

    def forward(self, sequence: Tensor) -> Tensor:
        x = sequence.transpose(1, 2)
        return self.head(self.tcn(x)).squeeze(-1)

    def predict_proba(self, sequence: Tensor) -> Tensor:
        return torch.sigmoid(self.forward(sequence))

    def save(self, path: str | Path, *, metadata: dict[str, Any] | None = None) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "input_dim": self.input_dim,
                "hidden_channels": self.hidden_channels,
                "kernel_size": self.kernel_size,
                "dropout": self.dropout,
                "state_dict": self.state_dict(),
                "metadata": metadata or {},
            },
            target,
        )

    @classmethod
    def load(cls, path: str | Path, map_location: str | torch.device = "cpu") -> "FallPoseTCNModel":
        checkpoint = torch.load(Path(path), map_location=map_location)
        model = cls(
            input_dim=int(checkpoint["input_dim"]),
            hidden_channels=tuple(int(item) for item in checkpoint.get("hidden_channels", (64, 64, 96))),
            kernel_size=int(checkpoint.get("kernel_size", 3)),
            dropout=float(checkpoint.get("dropout", 0.15)),
        )
        model.load_state_dict(checkpoint["state_dict"])
        model.to(map_location if isinstance(map_location, torch.device) else torch.device(str(map_location)))
        model.eval()
        return model
