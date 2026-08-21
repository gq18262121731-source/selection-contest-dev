from __future__ import annotations

import torch
from torch import Tensor, nn


class TemporalConvBlock(nn.Module):
    """Single temporal convolution block for future sequence modeling."""

    def __init__(self, in_channels: int, out_channels: int, kernel_size: int, dilation: int) -> None:
        super().__init__()
        padding = (kernel_size - 1) * dilation
        self.net = nn.Sequential(
            nn.Conv1d(
                in_channels=in_channels,
                out_channels=out_channels,
                kernel_size=kernel_size,
                dilation=dilation,
                padding=padding,
            ),
            nn.ReLU(),
            nn.BatchNorm1d(out_channels),
            nn.Conv1d(
                in_channels=out_channels,
                out_channels=out_channels,
                kernel_size=kernel_size,
                dilation=dilation,
                padding=padding,
            ),
            nn.ReLU(),
            nn.BatchNorm1d(out_channels),
        )
        self.residual = nn.Conv1d(in_channels, out_channels, kernel_size=1) if in_channels != out_channels else nn.Identity()

    def forward(self, inputs: Tensor) -> Tensor:
        outputs = self.net(inputs)
        outputs = outputs[..., : inputs.shape[-1]]
        residual = self.residual(inputs)
        return torch.relu(outputs + residual)


class TemporalHealthTCNModel(nn.Module):
    """Future upgrade skeleton for real time-series health data.

    Input shape: [batch_size, seq_len, feature_dim]
    This class is intentionally instantiable in v1, but is not trained until
    true sequential wearable data is available.
    """

    def __init__(self, feature_dim: int, hidden_dim: int = 64) -> None:
        super().__init__()
        self.feature_dim = feature_dim
        self.temporal_stack = nn.Sequential(
            TemporalConvBlock(feature_dim, 32, kernel_size=3, dilation=1),
            TemporalConvBlock(32, 32, kernel_size=3, dilation=2),
            TemporalConvBlock(32, 64, kernel_size=3, dilation=4),
        )
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.fc = nn.Sequential(
            nn.Linear(64, hidden_dim),
            nn.ReLU(),
        )
        self.hr_alert_head = nn.Linear(hidden_dim, 1)
        self.spo2_alert_head = nn.Linear(hidden_dim, 1)
        self.bp_alert_head = nn.Linear(hidden_dim, 1)
        self.temp_alert_head = nn.Linear(hidden_dim, 1)
        self.risk_score_head = nn.Linear(hidden_dim, 1)

    def forward(self, sequence: Tensor) -> dict[str, Tensor]:
        if sequence.dim() != 3:
            raise ValueError("Expected input with shape [batch_size, seq_len, feature_dim]")
        x = sequence.transpose(1, 2)
        x = self.temporal_stack(x)
        x = self.pool(x).squeeze(-1)
        hidden = self.fc(x)
        return {
            "hr_alert": self.hr_alert_head(hidden),
            "spo2_alert": self.spo2_alert_head(hidden),
            "bp_alert": self.bp_alert_head(hidden),
            "temp_alert": self.temp_alert_head(hidden),
            "risk_score": self.risk_score_head(hidden),
        }
