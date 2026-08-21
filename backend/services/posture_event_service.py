from __future__ import annotations

import time
from collections import deque
from typing import Any


class PostureEventService:
    """Lightweight posture event classifier over target-only pose results."""

    def __init__(self) -> None:
        self._history: dict[str, deque[dict[str, Any]]] = {}
        self._history_size = 20

    def analyze(self, *, session_id: str, pose_result: dict[str, Any] | None, target_matched: bool) -> dict[str, Any] | None:
        now_ms = int(time.time() * 1000)
        if not target_matched:
            self._history.pop(session_id, None)
            return None

        history = self._history.setdefault(session_id, deque(maxlen=self._history_size))
        pose = (pose_result or {}).get("pose") or {}
        posture = pose.get("posture") or {}
        label = str(posture.get("label") or "unknown")
        confidence = float(posture.get("confidence") or 0.0)
        angle = posture.get("torso_angle_deg")
        features = posture.get("features") if isinstance(posture.get("features"), dict) else {}
        anchor_x = features.get("anchor_x") if isinstance(features, dict) else None
        anchor_y = features.get("anchor_y") if isinstance(features, dict) else None
        shoulder_span = float(features.get("shoulder_span") or 1.0) if isinstance(features, dict) else 1.0
        history.append(
            {
                "ts_ms": now_ms,
                "label": label,
                "confidence": confidence,
                "angle": angle,
                "anchor_x": anchor_x,
                "anchor_y": anchor_y,
                "shoulder_span": max(1.0, shoulder_span),
            }
        )

        labels = [item["label"] for item in history]
        recent = list(history)[-12:]
        event_type = "normal"
        level = "normal"
        reasons: list[str] = []

        if label == "fall_like" and confidence >= 0.72:
            event_type = "fall_fast"
            level = "critical"
            reasons.append("FAST_TORSO_DROP")
        elif label == "slumped" and confidence >= 0.65:
            event_type = "collapse_or_slump"
            level = "warning"
            reasons.append("SLUMPED_POSTURE")
        elif label == "leaning" and confidence >= 0.55:
            event_type = "abnormal_lean"
            level = "attention"
            reasons.append("TORSO_LEAN")
        elif label == "hand_to_chest_or_abdomen" and confidence >= 0.6:
            event_type = "hand_to_chest_or_abdomen"
            level = "warning"
            reasons.append("HAND_NEAR_CHEST_OR_ABDOMEN")

        # slow-fall/slump trend: torso angle grows high over several recent windows
        valid_angles = [float(item["angle"]) for item in recent if item.get("angle") is not None]
        if len(valid_angles) >= 5:
            avg_angle = sum(valid_angles[-5:]) / min(5, len(valid_angles))
            if 48 <= avg_angle < 68 and labels[-1] in {"leaning", "slumped"}:
                event_type = "fall_slow"
                level = "danger"
                confidence = max(confidence, min(0.88, avg_angle / 90.0))
                reasons.append("SUSTAINED_TORSO_ANGLE")

        # Stillness uses actual target anchor movement, not only repeated labels.
        still_window = list(history)[-14:]
        anchor_points = [
            item
            for item in still_window
            if item.get("anchor_x") is not None and item.get("anchor_y") is not None
        ]
        static_motion = None
        if len(anchor_points) >= 8:
            xs = [float(item["anchor_x"]) for item in anchor_points]
            ys = [float(item["anchor_y"]) for item in anchor_points]
            scale = max(1.0, sum(float(item.get("shoulder_span") or 1.0) for item in anchor_points) / len(anchor_points))
            static_motion = ((max(xs) - min(xs)) + (max(ys) - min(ys))) / scale
        if (
            static_motion is not None
            and static_motion <= 0.18
            and labels[-1] in {"upright", "slumped"}
            and len(still_window) >= 10
            and event_type == "normal"
        ):
            event_type = "abnormal_stillness"
            level = "attention"
            confidence = max(confidence, 0.58)
            reasons.append("LONG_STATIC_POSTURE")

        return {
            "type": event_type,
            "level": level,
            "confidence": round(confidence, 4),
            "source_pose": label,
            "reasons": reasons,
            "metrics": {
                "torso_angle_deg": angle,
                "static_motion": round(static_motion, 4) if static_motion is not None else None,
                "history_frames": len(history),
            },
            "timestamp_ms": now_ms,
        }
