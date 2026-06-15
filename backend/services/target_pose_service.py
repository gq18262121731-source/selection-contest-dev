from __future__ import annotations

import time
from collections import deque
from pathlib import Path
from threading import RLock
from typing import Any

import numpy as np
import torch
from ultralytics import YOLO


COCO_SKELETON = [
    {"from": 0, "to": 1, "part": "head"},
    {"from": 0, "to": 2, "part": "head"},
    {"from": 1, "to": 3, "part": "head"},
    {"from": 2, "to": 4, "part": "head"},
    {"from": 5, "to": 6, "part": "torso"},
    {"from": 5, "to": 7, "part": "left_arm"},
    {"from": 7, "to": 9, "part": "left_arm"},
    {"from": 6, "to": 8, "part": "right_arm"},
    {"from": 8, "to": 10, "part": "right_arm"},
    {"from": 5, "to": 11, "part": "torso"},
    {"from": 6, "to": 12, "part": "torso"},
    {"from": 11, "to": 12, "part": "torso"},
    {"from": 11, "to": 13, "part": "left_leg"},
    {"from": 13, "to": 15, "part": "left_leg"},
    {"from": 12, "to": 14, "part": "right_leg"},
    {"from": 14, "to": 16, "part": "right_leg"},
]


POSE_POINT_NAMES = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]


class TargetPoseService:
    """Pose estimation on a target-only ROI."""

    def __init__(self, *, model_root: Path) -> None:
        self._lock = RLock()
        self._loaded = False
        self._load_error: str | None = None
        self._model: YOLO | None = None
        self._device: str | int = "cpu"
        self._half = False
        self._pose_path = model_root / "yolo11n-pose.pt"
        self._session_states: dict[str, dict[str, Any]] = {}
        self._max_state_age_ms = 1600

    def status(self) -> dict[str, Any]:
        return {
            "loaded": self._loaded,
            "load_error": self._load_error,
            "pose_path": str(self._pose_path),
            "device": self._device,
            "half": self._half,
        }

    def warmup(self, *, imgsz: int = 384, conf: float = 0.25) -> dict[str, Any]:
        dummy = np.zeros((420, 240, 3), dtype=np.uint8)
        return self.estimate_pose(dummy, imgsz=imgsz, conf=conf)

    def estimate_pose(
        self,
        frame: np.ndarray,
        *,
        bbox: list[int] | None = None,
        imgsz: int = 640,
        conf: float = 0.2,
        session_id: str = "default",
        track_id: int | str | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            self._ensure_loaded()
            if frame is None or frame.size == 0:
                return self._empty_payload("INVALID_IMAGE", started)

            roi = frame
            offset_x = 0
            offset_y = 0
            if bbox is not None:
                x1, y1, x2, y2 = [int(v) for v in bbox]
                h, w = frame.shape[:2]
                x1 = max(0, min(w - 1, x1))
                y1 = max(0, min(h - 1, y1))
                x2 = max(0, min(w, x2))
                y2 = max(0, min(h, y2))
                if x2 > x1 and y2 > y1:
                    roi = frame[y1:y2, x1:x2]
                    offset_x = x1
                    offset_y = y1

            with torch.inference_mode():
                result = self._model.predict(  # type: ignore[union-attr]
                    roi,
                    verbose=False,
                    imgsz=imgsz,
                    conf=conf,
                    device=self._device,
                    half=self._half,
                )[0]
            keypoints = result.keypoints
            if keypoints is None or keypoints.xy is None or len(keypoints.xy) == 0:
                return self._empty_payload("POSE_NOT_FOUND", started)

            xy = keypoints.xy.detach().cpu().numpy()[0]
            conf = keypoints.conf.detach().cpu().numpy()[0] if keypoints.conf is not None else np.zeros((xy.shape[0],), dtype=np.float32)

            points = []
            for idx, ((x, y), score) in enumerate(zip(xy, conf)):
                points.append(
                    {
                        "index": idx,
                        "name": POSE_POINT_NAMES[idx] if idx < len(POSE_POINT_NAMES) else str(idx),
                        "x": round(float(x) + offset_x, 1),
                        "y": round(float(y) + offset_y, 1),
                        "score": round(float(score), 4),
                        "tracked": False,
                        "estimated": False,
                    }
                )
            points = self._smooth_points(session_id=session_id, track_id=track_id, points=points, bbox=bbox)

            connections = []
            for item in COCO_SKELETON:
                a = int(item["from"])
                b = int(item["to"])
                if a < len(points) and b < len(points):
                    connections.append({"from": a, "to": b, "part": item["part"]})

            posture = self._classify_posture(points)
            return {
                "ok": True,
                "pose": {
                    "points": points,
                    "connections": connections,
                    "posture": posture,
                    "quality": self._pose_quality(points),
                },
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "model": self.status(),
            }
        except Exception as exc:
            self._load_error = f"{exc.__class__.__name__}: {exc}"
            return self._empty_payload(self._load_error, started)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            if not self._pose_path.exists():
                raise FileNotFoundError(self._pose_path)
            use_cuda = torch.cuda.is_available()
            self._device = 0 if use_cuda else "cpu"
            self._half = use_cuda
            self._model = YOLO(str(self._pose_path))
            self._loaded = True
            self._load_error = None

    def _smooth_points(
        self,
        *,
        session_id: str,
        track_id: int | str | None,
        points: list[dict[str, Any]],
        bbox: list[int] | None,
    ) -> list[dict[str, Any]]:
        now_ms = int(time.perf_counter() * 1000)
        state_key = f"{session_id}:{track_id if track_id is not None else 'target'}"
        previous = self._session_states.get(state_key)
        if previous and (now_ms - int(previous.get("ts_ms", 0))) > self._max_state_age_ms:
            previous = None

        bbox_diag = 240.0
        if bbox is not None and len(bbox) >= 4:
            box_w = max(1.0, float(bbox[2]) - float(bbox[0]))
            box_h = max(1.0, float(bbox[3]) - float(bbox[1]))
            bbox_diag = max(80.0, float(np.hypot(box_w, box_h)))
        max_jump = bbox_diag * 0.18
        smoothed: list[dict[str, Any]] = []
        prev_points = previous.get("points") if previous else None

        for point in points:
            idx = int(point["index"])
            score = float(point.get("score") or 0.0)
            x = float(point.get("x") or 0.0)
            y = float(point.get("y") or 0.0)
            prev = None
            if isinstance(prev_points, list):
                prev = next((item for item in prev_points if int(item.get("index", -1)) == idx), None)

            estimated = False
            tracked = False
            if prev is not None:
                px = float(prev.get("x") or x)
                py = float(prev.get("y") or y)
                prev_score = float(prev.get("score") or 0.0)
                jump = float(np.hypot(x - px, y - py))
                if score < 0.18 <= prev_score:
                    x, y = px, py
                    score = max(0.12, min(0.32, prev_score * 0.82))
                    estimated = True
                    tracked = True
                elif jump > max_jump and prev_score >= 0.28:
                    blend = 0.72
                    x = px * blend + x * (1.0 - blend)
                    y = py * blend + y * (1.0 - blend)
                    score = min(score, max(0.24, prev_score * 0.92))
                    tracked = True
                elif score >= 0.18:
                    alpha = 0.55 if score >= 0.5 else 0.38
                    x = px * (1.0 - alpha) + x * alpha
                    y = py * (1.0 - alpha) + y * alpha
                    tracked = True

            smoothed.append(
                {
                    **point,
                    "x": round(x, 1),
                    "y": round(y, 1),
                    "score": round(max(0.0, min(1.0, score)), 4),
                    "tracked": tracked,
                    "estimated": estimated,
                }
            )

        history = deque(maxlen=6)
        if previous and isinstance(previous.get("history"), deque):
            history = previous["history"]
        history.append(smoothed)
        self._session_states[state_key] = {
            "ts_ms": now_ms,
            "points": smoothed,
            "history": history,
        }
        return smoothed

    @staticmethod
    def _pose_quality(points: list[dict[str, Any]]) -> dict[str, Any]:
        if not points:
            return {"visible_points": 0, "mean_score": 0.0, "estimated_points": 0}
        scores = [float(item.get("score") or 0.0) for item in points]
        return {
            "visible_points": sum(1 for score in scores if score >= 0.2),
            "mean_score": round(sum(scores) / max(1, len(scores)), 4),
            "estimated_points": sum(1 for item in points if item.get("estimated")),
        }

    @staticmethod
    def _classify_posture(points: list[dict[str, Any]]) -> dict[str, Any]:
        def pt(idx: int):
            if idx >= len(points):
                return None
            p = points[idx]
            if float(p["score"]) < 0.2:
                return None
            return np.array([float(p["x"]), float(p["y"])], dtype=np.float32)

        left_shoulder = pt(5)
        right_shoulder = pt(6)
        left_hip = pt(11)
        right_hip = pt(12)
        nose = pt(0)
        left_wrist = pt(9)
        right_wrist = pt(10)

        if left_shoulder is None or right_shoulder is None:
            return {
                "label": "unknown",
                "severity": "normal",
                "confidence": 0.0,
                "torso_angle_deg": None,
                "features": {},
            }

        shoulder_mid = (left_shoulder + right_shoulder) * 0.5
        hip_mid = (left_hip + right_hip) * 0.5 if left_hip is not None and right_hip is not None else None
        anchor = hip_mid if hip_mid is not None else shoulder_mid

        angle = None
        if hip_mid is not None:
            torso = shoulder_mid - hip_mid
            torso_norm = max(float(np.linalg.norm(torso)), 1e-6)
            vertical = np.array([0.0, -1.0], dtype=np.float32)
            cosine = float(np.dot(torso / torso_norm, vertical))
            angle = float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))

        label = "upright"
        severity = "normal"
        confidence = 0.0

        hand_to_chest = False
        hand_to_abdomen = False
        shoulder_span = float(np.linalg.norm(left_shoulder - right_shoulder))
        if shoulder_span > 1e-6:
            chest_threshold = shoulder_span * 0.75
            abdomen_threshold = shoulder_span * 0.9
            if left_wrist is not None:
                if float(np.linalg.norm(left_wrist - shoulder_mid)) <= chest_threshold:
                    hand_to_chest = True
                if hip_mid is not None and float(np.linalg.norm(left_wrist - hip_mid)) <= abdomen_threshold:
                    hand_to_abdomen = True
            if right_wrist is not None:
                if float(np.linalg.norm(right_wrist - shoulder_mid)) <= chest_threshold:
                    hand_to_chest = True
                if hip_mid is not None and float(np.linalg.norm(right_wrist - hip_mid)) <= abdomen_threshold:
                    hand_to_abdomen = True

        if hand_to_chest or hand_to_abdomen:
            label = "hand_to_chest_or_abdomen"
            severity = "warning"
            confidence = 0.7
        elif angle is not None:
            confidence = max(0.0, min(1.0, angle / 90.0))
            if angle >= 68:
                label = "fall_like"
                severity = "danger"
            elif angle >= 42:
                label = "leaning"
                severity = "warning"
            elif nose is not None and hip_mid is not None and nose[1] > hip_mid[1]:
                label = "slumped"
                severity = "warning"
                confidence = max(confidence, 0.65)
        elif nose is not None and nose[1] > shoulder_mid[1] + max(shoulder_span * 0.15, 10.0):
            label = "slumped"
            severity = "warning"
            confidence = 0.6
        else:
            label = "upright"
            severity = "normal"
            confidence = 0.45

        return {
            "label": label,
            "severity": severity,
            "confidence": round(confidence, 4),
            "torso_angle_deg": round(angle, 2) if angle is not None else None,
            "features": {
                "hand_to_chest": hand_to_chest,
                "hand_to_abdomen": hand_to_abdomen,
                "hips_visible": hip_mid is not None,
                "anchor_x": round(float(anchor[0]), 2),
                "anchor_y": round(float(anchor[1]), 2),
                "shoulder_span": round(float(shoulder_span), 2),
            },
        }

    def _empty_payload(self, error: str, started: float) -> dict[str, Any]:
        return {
            "ok": False,
            "error": error,
            "pose": {
                "points": [],
                "connections": [],
                "posture": {
                    "label": "unknown",
                    "severity": "normal",
                    "confidence": 0.0,
                },
            },
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "model": self.status(),
        }
