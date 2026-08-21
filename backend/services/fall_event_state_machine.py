from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FallEventStateMachineConfig:
    window_frames: int = 9
    fall_confirm_frames: int = 3
    fall_hold_frames: int = 12
    suspected_confirm_frames: int = 2
    fallen_confirm_frames: int = 6
    recovery_confirm_frames: int = 12
    fall_score_threshold: float = 0.72
    suspected_score_threshold: float = 0.42
    detector_fall_threshold: float = 0.35
    posture_risk_threshold: float = 0.65
    hold_fall_score_threshold: float = 0.58
    hold_risk_score_threshold: float = 0.36
    warning_duration_s: float = 0.7
    danger_duration_s: float = 1.2
    critical_duration_s: float = 3.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "window_frames": self.window_frames,
            "fall_confirm_frames": self.fall_confirm_frames,
            "fall_hold_frames": self.fall_hold_frames,
            "suspected_confirm_frames": self.suspected_confirm_frames,
            "fallen_confirm_frames": self.fallen_confirm_frames,
            "recovery_confirm_frames": self.recovery_confirm_frames,
            "fall_score_threshold": self.fall_score_threshold,
            "suspected_score_threshold": self.suspected_score_threshold,
            "detector_fall_threshold": self.detector_fall_threshold,
            "posture_risk_threshold": self.posture_risk_threshold,
            "hold_fall_score_threshold": self.hold_fall_score_threshold,
            "hold_risk_score_threshold": self.hold_risk_score_threshold,
            "warning_duration_s": self.warning_duration_s,
            "danger_duration_s": self.danger_duration_s,
            "critical_duration_s": self.critical_duration_s,
        }


class FallEventStateMachine:
    """Turn frame-level fall model outputs into stable event-level states.

    The detector/classifier stack is frame-based, so video output can flicker.
    This state machine upgrades raw frame statuses into an event lifecycle:
    normal -> suspected -> falling -> fallen -> recovery -> normal.
    """

    def __init__(self, config: FallEventStateMachineConfig | None = None) -> None:
        self.config = config or FallEventStateMachineConfig()
        self._window: deque[dict[str, Any]] = deque(maxlen=max(3, self.config.window_frames))
        self._fall_hold_remaining = 0
        self._current_state = "normal"
        self._state_frames = 0
        self._low_risk_frames = 0
        self._frame_counter = -1
        self._event_id = 0
        self._event_start_frame: int | None = None
        self._event_start_s: float | None = None
        self._event_max_score = 0.0

    @property
    def current_state(self) -> str:
        return self._current_state

    def reset(self) -> None:
        self._window.clear()
        self._fall_hold_remaining = 0
        self._current_state = "normal"
        self._state_frames = 0
        self._low_risk_frames = 0
        self._frame_counter = -1
        self._event_id = 0
        self._event_start_frame = None
        self._event_start_s = None
        self._event_max_score = 0.0

    def apply(
        self,
        result: dict[str, Any],
        *,
        frame_index: int | None = None,
        time_s: float | None = None,
        fps: float | None = None,
    ) -> dict[str, Any]:
        self._frame_counter = frame_index if frame_index is not None else self._frame_counter + 1
        frame_number = self._frame_counter
        current_time_s = time_s if time_s is not None else self._infer_time_s(frame_number, fps)
        raw_status = str(result.get("status") or "unknown")
        fall_score = self._float(result.get("fall_score"))
        scores = result.get("scores") if isinstance(result.get("scores"), dict) else {}
        posture_score = self._float(scores.get("posture"))
        detector_score = self._float(scores.get("detector"))
        prone_score = self._float(scores.get("prone"))
        heuristic_score = self._float(scores.get("heuristic"))
        self._window.append(
            {
                "status": raw_status,
                "fall_score": fall_score,
                "posture_score": posture_score,
                "detector_score": detector_score,
                "prone_score": prone_score,
                "heuristic_score": heuristic_score,
            }
        )

        fall_votes = sum(1 for item in self._window if self._is_fall_vote(item))
        risk_votes = sum(1 for item in self._window if self._is_risk_vote(item))
        max_recent_score = max((self._float(item.get("fall_score")) for item in self._window), default=fall_score)
        max_detector_score = max((self._float(item.get("detector_score")) for item in self._window), default=detector_score)
        max_posture_score = max((self._float(item.get("posture_score")) for item in self._window), default=posture_score)

        previous_state = self._current_state
        state = self._resolve_event_state(
            fall_votes=fall_votes,
            risk_votes=risk_votes,
            max_recent_score=max_recent_score,
        )
        if state != previous_state:
            self._state_frames = 1
            if state in {"suspected", "falling", "fallen"} and previous_state == "normal":
                self._event_id += 1
                self._event_start_frame = frame_number
                self._event_start_s = current_time_s
                self._event_max_score = max_recent_score
        else:
            self._state_frames += 1

        self._current_state = state
        if state in {"suspected", "falling", "fallen", "recovery"}:
            if self._event_start_frame is None:
                self._event_id += 1
                self._event_start_frame = frame_number
                self._event_start_s = current_time_s
            self._event_max_score = max(self._event_max_score, max_recent_score)
        else:
            self._event_start_frame = None
            self._event_start_s = None
            self._event_max_score = 0.0

        event_duration_s = self._event_duration_s(current_time_s)
        public_status = self._public_status(state)
        alarm = self._build_alarm(state=state, event_duration_s=event_duration_s, max_score=self._event_max_score)

        payload = {**result}
        payload["raw_status"] = raw_status
        payload["status"] = public_status
        payload["event_state"] = state
        payload["fall_detected"] = state in {"falling", "fallen"}
        payload["alarm"] = alarm
        payload["event"] = {
            "id": self._event_id if state != "normal" else None,
            "state": state,
            "start_frame": self._event_start_frame,
            "start_s": round(self._event_start_s, 3) if self._event_start_s is not None else None,
            "duration_s": round(event_duration_s, 3),
            "max_fall_score": round(self._event_max_score, 4),
        }
        payload["temporal_smoothing"] = {
            "enabled": True,
            "previous_state": previous_state,
            "state": state,
            "public_status": public_status,
            "state_frames": self._state_frames,
            "low_risk_frames": self._low_risk_frames,
            "window_frames": self._window.maxlen,
            "observed_window_frames": len(self._window),
            "fall_votes": fall_votes,
            "risk_votes": risk_votes,
            "max_recent_fall_score": round(max_recent_score, 4),
            "max_recent_detector_score": round(max_detector_score, 4),
            "max_recent_posture_score": round(max_posture_score, 4),
            "fall_hold_remaining": self._fall_hold_remaining,
            "config": self.as_dict(),
        }
        return payload

    def _resolve_event_state(self, *, fall_votes: int, risk_votes: int, max_recent_score: float) -> str:
        strong_fall = fall_votes >= max(1, self.config.fall_confirm_frames)
        risky = risk_votes >= max(1, self.config.suspected_confirm_frames)
        weak_risk = risk_votes >= 1 or max_recent_score >= self.config.hold_risk_score_threshold
        if weak_risk:
            self._low_risk_frames = 0
        else:
            self._low_risk_frames += 1

        state = self._current_state
        if state == "normal":
            self._fall_hold_remaining = 0
            if strong_fall:
                self._fall_hold_remaining = max(0, self.config.fall_hold_frames)
                return "falling"
            if risky:
                return "suspected"
            return "normal"

        if state == "suspected":
            if strong_fall:
                self._fall_hold_remaining = max(0, self.config.fall_hold_frames)
                return "falling"
            if risky:
                return "suspected"
            return "normal" if self._low_risk_frames >= self.config.recovery_confirm_frames else "suspected"

        if state == "falling":
            if strong_fall:
                self._fall_hold_remaining = max(0, self.config.fall_hold_frames)
                if self._state_frames + 1 >= self.config.fallen_confirm_frames:
                    return "fallen"
                return "falling"
            if self._fall_hold_remaining > 0 and weak_risk:
                self._fall_hold_remaining -= 1
                return "falling" if max_recent_score >= self.config.hold_fall_score_threshold else "suspected"
            return "recovery" if self._low_risk_frames >= self.config.recovery_confirm_frames else "falling"

        if state == "fallen":
            if strong_fall or weak_risk:
                self._fall_hold_remaining = max(self._fall_hold_remaining, max(0, self.config.fall_hold_frames // 2))
                return "fallen"
            return "recovery" if self._low_risk_frames >= self.config.recovery_confirm_frames else "fallen"

        if state == "recovery":
            if strong_fall:
                self._fall_hold_remaining = max(0, self.config.fall_hold_frames)
                return "falling"
            if risky:
                return "suspected"
            return "normal" if self._low_risk_frames >= self.config.recovery_confirm_frames else "recovery"

        return "normal"

    def _event_duration_s(self, current_time_s: float) -> float:
        if self._event_start_s is None or self._current_state == "normal":
            return 0.0
        return max(0.0, current_time_s - self._event_start_s)

    def _build_alarm(self, *, state: str, event_duration_s: float, max_score: float) -> dict[str, Any]:
        if state in {"falling", "fallen"}:
            if event_duration_s >= self.config.critical_duration_s or max_score >= 0.88:
                level = "critical"
            elif event_duration_s >= self.config.danger_duration_s:
                level = "danger"
            else:
                level = "warning"
        elif state in {"suspected", "recovery"}:
            level = "warning" if event_duration_s >= self.config.warning_duration_s else "watch"
        else:
            level = "normal"
        return {
            "level": level,
            "should_alert": level in {"danger", "critical"},
            "reason": state,
            "event_duration_s": round(event_duration_s, 3),
            "max_fall_score": round(max_score, 4),
        }

    @staticmethod
    def _public_status(state: str) -> str:
        if state in {"falling", "fallen"}:
            return "fall"
        if state in {"suspected", "recovery"}:
            return "suspected"
        return "normal"

    @staticmethod
    def _infer_time_s(frame_number: int, fps: float | None) -> float:
        if fps and fps > 0:
            return frame_number / fps
        return float(frame_number)

    def as_dict(self) -> dict[str, Any]:
        return self.config.as_dict()

    def _is_fall_vote(self, item: dict[str, Any]) -> bool:
        return (
            str(item.get("status")) == "fall"
            or self._float(item.get("fall_score")) >= self.config.fall_score_threshold
            or self._float(item.get("detector_score")) >= self.config.detector_fall_threshold
        )

    def _is_risk_vote(self, item: dict[str, Any]) -> bool:
        return (
            self._is_fall_vote(item)
            or str(item.get("status")) == "suspected"
            or self._float(item.get("fall_score")) >= self.config.suspected_score_threshold
            or self._float(item.get("posture_score")) >= self.config.posture_risk_threshold
            or self._float(item.get("prone_score")) >= 0.35
            or self._float(item.get("heuristic_score")) >= 0.42
        )

    @staticmethod
    def _float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
