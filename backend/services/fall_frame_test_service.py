from __future__ import annotations

import logging
import time
from pathlib import Path
from threading import RLock
from typing import Any

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from backend.config import Settings


logger = logging.getLogger(__name__)


class FallFrameTestService:
    """Single-frame fall detector for browser camera testing.

    This is intentionally lightweight and deterministic so it can be reused by:
    - single-frame validation endpoints
    - target-user fall gating bridge
    - future real-time browser camera pages
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = RLock()
        self._loaded = False
        self._load_error: str | None = None
        self._detector: YOLO | None = None
        self._posture: YOLO | None = None
        self._device: str | int = "cpu"
        self._half = False
        self._model_root = Path(settings.fall_detection_model_root)
        self._detector_path = self._model_root / "weights" / "yolo_fall_detector_v1.pt"
        self._posture_path = self._model_root / "runs" / "yolo_posture_person_binary_cls_v1" / "weights" / "best.pt"

    def status(self) -> dict[str, Any]:
        return {
            "loaded": self._loaded,
            "load_error": self._load_error,
            "detector_path": str(self._detector_path),
            "posture_path": str(self._posture_path),
            "device": self._device,
            "half": self._half,
        }

    def warmup(self, *, imgsz: int = 416, posture_imgsz: int = 256) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            self._ensure_loaded()
            dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            dummy_crop = np.zeros((256, 128, 3), dtype=np.uint8)
            self._detect_objects(dummy_frame, imgsz=imgsz, posture_imgsz=posture_imgsz)
            self._classify_posture(dummy_crop, imgsz=posture_imgsz)
            return {
                "ok": True,
                "imgsz": imgsz,
                "posture_imgsz": posture_imgsz,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "model": self.status(),
            }
        except Exception as exc:
            self._load_error = f"{exc.__class__.__name__}: {exc}"
            return {
                "ok": False,
                "error": self._load_error,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "model": self.status(),
            }

    def detect(
        self,
        image_bytes: bytes,
        *,
        include_annotated_image: bool = True,
        imgsz: int = 640,
        posture_imgsz: int = 384,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            self._ensure_loaded()
            frame = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                return self._error_payload("INVALID_IMAGE", started)
            return self.detect_frame(
                frame,
                include_annotated_image=include_annotated_image,
                started=started,
                imgsz=imgsz,
                posture_imgsz=posture_imgsz,
            )
        except Exception as exc:
            logger.exception("fall frame detect failed: %s", exc)
            self._load_error = f"{exc.__class__.__name__}: {exc}"
            return self._error_payload(self._load_error, started)

    def detect_frame(
        self,
        frame: np.ndarray,
        *,
        include_annotated_image: bool = True,
        started: float | None = None,
        imgsz: int = 640,
        posture_imgsz: int = 384,
    ) -> dict[str, Any]:
        started_at = started if started is not None else time.perf_counter()
        try:
            self._ensure_loaded()
            if frame is None or frame.size == 0:
                return self._error_payload("INVALID_IMAGE", started_at)

            detections = self._detect_objects(frame, imgsz=imgsz, posture_imgsz=posture_imgsz)
            scores = self._score(detections)
            status = self._resolve_status(scores)
            payload = {
                "ok": True,
                "status": status,
                "fall_detected": status == "fall",
                "fall_score": scores["fall"],
                "scores": scores,
                "detections": detections,
                "alert": self._build_alert(status=status, scores=scores),
                "annotated_image_b64": "",
                "annotated_image_mime": "",
                "latency_ms": int((time.perf_counter() - started_at) * 1000),
                "frame": {"width": frame.shape[1], "height": frame.shape[0]},
                "model": self.status(),
            }
            return payload
        except Exception as exc:
            logger.exception("fall frame detect_frame failed: %s", exc)
            self._load_error = f"{exc.__class__.__name__}: {exc}"
            return self._error_payload(self._load_error, started_at)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            if not self._detector_path.exists():
                raise FileNotFoundError(self._detector_path)
            if not self._posture_path.exists():
                raise FileNotFoundError(self._posture_path)

            use_cuda = torch.cuda.is_available()
            self._device = 0 if use_cuda else "cpu"
            self._half = use_cuda
            self._detector = YOLO(str(self._detector_path))
            self._posture = YOLO(str(self._posture_path))
            self._loaded = True
            self._load_error = None

    def _detect_objects(self, frame: np.ndarray, *, imgsz: int, posture_imgsz: int) -> list[dict[str, Any]]:
        assert self._detector is not None
        with torch.inference_mode():
            result = self._detector.predict(
                frame,
                verbose=False,
                imgsz=imgsz,
                conf=0.2,
                iou=0.45,
                device=self._device,
                half=self._half,
            )[0]
        if result.boxes is None or len(result.boxes) == 0:
            return []

        names = result.names if hasattr(result, "names") else self._detector.names
        boxes = result.boxes.xyxy.detach().cpu().numpy()
        confs = result.boxes.conf.detach().cpu().numpy()
        classes = result.boxes.cls.detach().cpu().numpy().astype(int)
        frame_h, frame_w = frame.shape[:2]
        items: list[dict[str, Any]] = []
        for box, conf, cls_idx in zip(boxes, confs, classes):
            x1, y1, x2, y2 = [float(v) for v in box]
            x1 = max(0.0, min(float(frame_w - 1), x1))
            y1 = max(0.0, min(float(frame_h - 1), y1))
            x2 = max(0.0, min(float(frame_w - 1), x2))
            y2 = max(0.0, min(float(frame_h - 1), y2))
            if x2 <= x1 or y2 <= y1:
                continue
            label = str(names.get(int(cls_idx), cls_idx)).lower()
            crop = frame[int(y1):int(y2), int(x1):int(x2)]
            posture = self._classify_posture(crop, imgsz=posture_imgsz)
            width = max(1.0, x2 - x1)
            height = max(1.0, y2 - y1)
            items.append(
                {
                    "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                    "label": label,
                    "confidence": round(float(conf), 4),
                    "aspect": round(float(width / height), 4),
                    "area_ratio": round(float((width * height) / max(1.0, frame_w * frame_h)), 5),
                    "posture_label": posture["label"],
                    "posture_score": posture["score"],
                }
            )
        items.sort(key=lambda item: float(item["confidence"]), reverse=True)
        return items[:8]

    def _classify_posture(self, crop: np.ndarray, *, imgsz: int = 384) -> dict[str, Any]:
        assert self._posture is not None
        if crop.size == 0:
            return {"label": "unknown", "score": 0.0}
        with torch.inference_mode():
            result = self._posture.predict(
                crop,
                verbose=False,
                imgsz=imgsz,
                device=self._device,
                half=self._half,
            )[0]
        probs = result.probs
        if probs is None:
            return {"label": "unknown", "score": 0.0}
        names = self._posture.names
        top1 = int(probs.top1)
        label = str(names.get(top1, top1)).lower()
        values = probs.data.detach().cpu().numpy()
        score = float(values[top1]) if len(values) > top1 else 0.0
        if label == "safe":
            risk_index = next((idx for idx, name in names.items() if str(name).lower() == "risk"), None)
            if risk_index is not None and len(values) > int(risk_index):
                score = float(values[int(risk_index)])
        return {"label": label, "score": round(score, 4)}

    @staticmethod
    def _score(detections: list[dict[str, Any]]) -> dict[str, float]:
        detector = 0.0
        posture = 0.0
        heuristic = 0.0
        prone = 0.0
        for item in detections:
            label = str(item["label"]).lower()
            conf = float(item["confidence"])
            aspect = float(item["aspect"])
            area_ratio = float(item["area_ratio"])
            posture = max(posture, float(item.get("posture_score") or 0.0))
            if label in {"fall", "fallen"}:
                detector = max(detector, conf)
            elif label == "lying":
                prone = max(prone, conf * 0.72)
            if area_ratio >= 0.015 and aspect >= 1.45:
                heuristic = max(heuristic, min(0.70, 0.30 + (aspect - 1.45) * 0.22))
        fall = max(detector, prone, posture * 0.78, heuristic)
        return {
            "fall": round(max(0.0, min(1.0, fall)), 4),
            "detector": round(max(0.0, min(1.0, detector)), 4),
            "posture": round(max(0.0, min(1.0, posture)), 4),
            "heuristic": round(max(0.0, min(1.0, heuristic)), 4),
            "prone": round(max(0.0, min(1.0, prone)), 4),
        }

    @staticmethod
    def _resolve_status(scores: dict[str, float]) -> str:
        if scores["detector"] >= 0.35 or scores["fall"] >= 0.72:
            return "fall"
        if scores["fall"] >= 0.42 or scores["prone"] >= 0.35 or scores["heuristic"] >= 0.42:
            return "suspected"
        return "normal"

    @staticmethod
    def _build_alert(*, status: str, scores: dict[str, float]) -> dict[str, Any]:
        if status == "fall":
            if scores["fall"] >= 0.88:
                return {
                    "level": "critical",
                    "title": "高危跌倒",
                    "banner": "立即处理",
                    "message": "模型高度确信当前目标用户发生跌倒。",
                    "recommended_action": "立即人工确认并优先处理。",
                }
            return {
                "level": "danger",
                "title": "明显跌倒",
                "banner": "紧急关注",
                "message": "当前目标用户与跌倒特征高度接近。",
                "recommended_action": "马上人工复核。",
            }
        if status == "suspected":
            return {
                "level": "warning",
                "title": "疑似跌倒",
                "banner": "尽快复核",
                "message": "当前目标用户出现较强异常姿态或倒地线索。",
                "recommended_action": "继续观察并尽快确认。",
            }
        return {
            "level": "normal",
            "title": "状态正常",
            "banner": "正常",
            "message": "当前目标用户未见明确跌倒线索。",
            "recommended_action": "继续实时检测。",
        }

    @staticmethod
    def _error_payload(message: str, started: float) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "model_unavailable",
            "fall_detected": False,
            "fall_score": 0.0,
            "scores": {"fall": 0.0, "detector": 0.0, "posture": 0.0, "heuristic": 0.0, "prone": 0.0},
            "detections": [],
            "alert": {
                "level": "model_unavailable",
                "title": "检测异常",
                "banner": "模型异常",
                "message": message,
                "recommended_action": "请检查跌倒检测模型服务。",
            },
            "annotated_image_b64": "",
            "annotated_image_mime": "",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "frame": None,
            "error": message,
            "model": {},
        }
