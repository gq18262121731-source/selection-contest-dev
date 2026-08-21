from __future__ import annotations

from pathlib import Path

import torch
from torch import Tensor, nn


class StaticHealthMultiTaskModel(nn.Module):
    """Lightweight MLP multi-task model for static health scoring."""

    def __init__(self, input_dim: int) -> None:
        super().__init__()
        self.input_dim = input_dim
        self.backbone = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(64, 32),
            nn.ReLU(),
        )
        self.hr_alert_head = nn.Linear(32, 1)
        self.spo2_alert_head = nn.Linear(32, 1)
        self.bp_alert_head = nn.Linear(32, 1)
        self.temp_alert_head = nn.Linear(32, 1)
        self.risk_score_head = nn.Linear(32, 1)

    def forward(self, features: Tensor) -> dict[str, Tensor]:
        hidden = self.backbone(features)
        return {
            "hr_alert": self.hr_alert_head(hidden),
            "spo2_alert": self.spo2_alert_head(hidden),
            "bp_alert": self.bp_alert_head(hidden),
            "temp_alert": self.temp_alert_head(hidden),
            "risk_score": self.risk_score_head(hidden),
        }

    def save(self, path: str | Path) -> None:
        """Save model checkpoint to disk."""

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        torch.save({"input_dim": self.input_dim, "state_dict": self.state_dict()}, target)

    @classmethod
    def load(cls, path: str | Path, map_location: str | torch.device = "cpu") -> "StaticHealthMultiTaskModel":
        """Load model checkpoint from disk."""

        checkpoint = torch.load(Path(path), map_location=map_location)
        model = cls(input_dim=int(checkpoint["input_dim"]))
        model.load_state_dict(checkpoint["state_dict"])
        target_device = map_location if isinstance(map_location, torch.device) else torch.device(str(map_location))
        model.to(target_device)
        model.eval()
        return model
