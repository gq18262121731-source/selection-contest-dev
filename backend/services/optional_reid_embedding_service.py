from __future__ import annotations

import os
import sys
from pathlib import Path
from threading import RLock
from typing import Any

import cv2
import numpy as np
import torch


class OptionalReidEmbeddingService:
    """Optional OSNet-style body ReID extractor.

    The service is deliberately opt-in. It does not install packages, download
    weights, or mutate the project environment. When disabled or unavailable it
    returns ``None`` and the caller can keep using the lightweight local
    appearance embedding.
    """

    def __init__(self) -> None:
        self._enabled = os.getenv("TARGET_REID_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
        self._source_dir = Path(
            os.getenv("TARGET_REID_SOURCE_DIR", r"D:\Program\github_KaiyangZhou_deep-person-reid")
        )
        weights_value = os.getenv("TARGET_REID_WEIGHTS", "").strip()
        self._weights_path = Path(weights_value).expanduser() if weights_value else None
        self._allow_pretrained_download = os.getenv("TARGET_REID_ALLOW_PRETRAINED_DOWNLOAD", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self._model_name = os.getenv("TARGET_REID_MODEL", "osnet_x0_25")
        self._loaded = False
        self._load_error: str | None = None
        self._model: Any | None = None
        self._torchreid: Any | None = None
        self._lock = RLock()
        self._device: str | torch.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self._enabled,
            "loaded": self._loaded,
            "load_error": self._load_error,
            "source_dir": str(self._source_dir),
            "weights_path": str(self._weights_path) if self._weights_path is not None else "",
            "model_name": self._model_name,
            "device": str(self._device),
            "allow_pretrained_download": self._allow_pretrained_download,
        }

    def embed(self, crop: np.ndarray | None) -> list[float] | None:
        if not self._enabled or crop is None or crop.size == 0:
            return None
        try:
            self._ensure_loaded()
            if self._model is None:
                return None
            tensor = self._prepare_crop(crop)
            with torch.inference_mode():
                vector = self._model(tensor).detach().cpu().numpy().reshape(-1).astype(np.float32)
            norm = float(np.linalg.norm(vector))
            if norm <= 1e-6:
                return None
            return (vector / norm).tolist()
        except Exception as exc:
            self._load_error = f"{exc.__class__.__name__}: {exc}"
            return None

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            if self._source_dir.exists() and str(self._source_dir) not in sys.path:
                sys.path.insert(0, str(self._source_dir))
            import torchreid  # type: ignore[import-not-found]

            self._torchreid = torchreid
            self._model = torchreid.models.build_model(
                name=self._model_name,
                num_classes=1000,
                pretrained=self._allow_pretrained_download and not (self._weights_path and self._weights_path.is_file()),
            )
            if self._weights_path is not None and self._weights_path.is_file():
                state = torch.load(str(self._weights_path), map_location="cpu")
                if isinstance(state, dict) and "state_dict" in state:
                    state = state["state_dict"]
                cleaned = {str(k).replace("module.", "", 1): v for k, v in state.items()} if isinstance(state, dict) else state
                self._model.load_state_dict(cleaned, strict=False)
            elif not self._allow_pretrained_download:
                raise RuntimeError("TARGET_REID_WEIGHTS is required unless TARGET_REID_ALLOW_PRETRAINED_DOWNLOAD=1")
            self._model.to(self._device)
            self._model.eval()
            self._loaded = True
            self._load_error = None

    def _prepare_crop(self, crop: np.ndarray) -> torch.Tensor:
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (128, 256), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        mean = np.asarray([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.asarray([0.229, 0.224, 0.225], dtype=np.float32)
        normalized = (resized - mean) / std
        tensor = torch.from_numpy(normalized.transpose(2, 0, 1)).unsqueeze(0).to(self._device)
        return tensor
