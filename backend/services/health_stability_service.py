from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any, Callable, Mapping

from backend.config import Settings, get_settings
from backend.ml.preprocess import validate_inference_record
from backend.ml.rule_engine import RISK_ORDER, HardThresholdResult, HealthRuleEngine


EventValue = float | bool | dict[str, float]


@dataclass(frozen=True, slots=True)
class EventRule:
    """Debounce and aggregation rule for a single abnormal event type."""

    event_type: str
    min_points: int
    min_duration_seconds: int
    immediate: bool
    enter_condition: Callable[[Mapping[str, Any]], bool]
    exit_condition: Callable[[Mapping[str, Any]], bool]
    value_extractor: Callable[[Mapping[str, Any]], EventValue]
    severity_resolver: Callable[[Mapping[str, Any]], str]
    trigger_reason: Callable[[Mapping[str, Any]], str]
    peak_selector: Callable[[EventValue | None, EventValue], EventValue]


@dataclass(slots=True)
class BufferedPoint:
    """Single buffered measurement used for stabilization and event aggregation."""

    timestamp: datetime
    vitals: dict[str, Any]


@dataclass(slots=True)
class EventState:
    """Mutable per-device event state."""

    event_type: str
    status: str = "inactive"
    start_time: datetime | None = None
    active_since: datetime | None = None
    last_seen_time: datetime | None = None
    peak_value: EventValue | None = None
    latest_value: EventValue | None = None
    sample_count: int = 0
    severity: str = "attention"
    trigger_reason: str = ""

    def reset(self) -> None:
        self.status = "inactive"
        self.start_time = None
        self.active_since = None
        self.last_seen_time = None
        self.peak_value = None
        self.latest_value = None
        self.sample_count = 0
        self.severity = "attention"
        self.trigger_reason = ""


@dataclass(slots=True)
class DeviceStabilityState:
    """Stateful recent history for a single device."""

    history: deque[BufferedPoint] = field(default_factory=deque)
    events: dict[str, EventState] = field(default_factory=dict)
    last_output_score: float | None = None


@dataclass(slots=True)
class StabilitySnapshot:
    """Output of the stabilization layer before model inference."""

    stability_mode: str
    raw_vitals: dict[str, Any]
    stabilized_vitals: dict[str, Any]
    active_events: list[dict[str, Any]]
    raw_hard_threshold: HardThresholdResult
    severe_hard_threshold: HardThresholdResult
    raw_abnormal_tags: list[str]


class HealthStabilityService:
    """Stateful signal stabilization and event aggregation for demo-friendly scoring."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.rule_engine = HealthRuleEngine()
        self.window_seconds = self.settings.stabilization_window_seconds
        self.max_points = self.settings.stabilization_max_points
        self.min_points = self.settings.stabilization_min_points
        self.activation_min_points = self.settings.stability_activation_min_abnormal_points
        self.bp_points = self.settings.stabilization_bp_points
        self.recovery_points = self.settings.stability_recovery_points
        self.default_sample_interval_seconds = self.settings.stability_default_sample_interval_seconds
        self.history_cap = max(self.settings.stabilization_history_cap, self.max_points * 3)
        self._device_states: dict[str, DeviceStabilityState] = {}
        self._event_rules = self._build_event_rules()

    def process_point(
        self,
        *,
        device_id: str,
        timestamp: datetime,
        vitals: Mapping[str, Any],
        stateful: bool,
    ) -> StabilitySnapshot:
        """Process a single point, optionally using and updating the live device state."""

        state = self._device_states.setdefault(device_id, DeviceStabilityState()) if stateful else DeviceStabilityState()
        return self._process_state(state=state, timestamp=timestamp, vitals=vitals)

    def process_window(self, window_points: list[Mapping[str, Any]]) -> StabilitySnapshot:
        """Process an entire window statelessly and return the final aggregated snapshot."""

        if not window_points:
            raise ValueError("window_points must not be empty")
        state = DeviceStabilityState()
        ordered_points = list(window_points)
        if any(point.get("timestamp") is not None for point in ordered_points):
            ordered_points.sort(key=lambda item: self._normalize_timestamp(item.get("timestamp"), fallback_index=0))

        snapshot: StabilitySnapshot | None = None
        for index, point in enumerate(ordered_points):
            point_timestamp = self._normalize_timestamp(point.get("timestamp"), fallback_index=index)
            vitals = {key: value for key, value in point.items() if key != "timestamp"}
            snapshot = self._process_state(state=state, timestamp=point_timestamp, vitals=vitals)

        assert snapshot is not None  # pragma: no cover
        return snapshot

    def get_last_score(self, device_id: str) -> float | None:
        """Return the last emitted score for score damping."""

        state = self._device_states.get(device_id)
        if state is None:
            return None
        return state.last_output_score

    def set_last_score(self, device_id: str, score: float) -> None:
        """Store the last emitted score for score damping."""

        state = self._device_states.setdefault(device_id, DeviceStabilityState())
        state.last_output_score = float(score)

    def _process_state(
        self,
        *,
        state: DeviceStabilityState,
        timestamp: datetime,
        vitals: Mapping[str, Any],
    ) -> StabilitySnapshot:
        normalized_timestamp = self._normalize_timestamp(timestamp)
        raw_vitals = self._normalize_vitals(vitals)
        state.history.append(BufferedPoint(timestamp=normalized_timestamp, vitals=raw_vitals))
        self._trim_history(state.history, normalized_timestamp)

        recent_points = self._recent_points(state.history, normalized_timestamp)
        stabilized_vitals = self._stabilize_vitals(raw_vitals, recent_points)
        active_events = self._update_events(
            state=state,
            recent_points=recent_points,
            raw_vitals=raw_vitals,
            stabilized_vitals=stabilized_vitals,
            timestamp=normalized_timestamp,
        )
        raw_hard_threshold = self.rule_engine.evaluate_hard_thresholds(raw_vitals)
        severe_hard_threshold = self._evaluate_severe_hard_thresholds(raw_vitals)
        raw_abnormal_tags = self.rule_engine.generate_abnormal_tags(raw_vitals)
        return StabilitySnapshot(
            stability_mode=self.settings.stability_profile,
            raw_vitals=raw_vitals,
            stabilized_vitals=stabilized_vitals,
            active_events=active_events,
            raw_hard_threshold=raw_hard_threshold,
            severe_hard_threshold=severe_hard_threshold,
            raw_abnormal_tags=raw_abnormal_tags,
        )

    def _normalize_vitals(self, vitals: Mapping[str, Any]) -> dict[str, Any]:
        validated = validate_inference_record(vitals)
        return {
            "heart_rate": float(validated["heart_rate"]),
            "spo2": float(validated["spo2"]),
            "sbp": float(validated["sbp"]),
            "dbp": float(validated["dbp"]),
            "body_temp": float(validated["body_temp"]),
            "fall_detection": bool(validated.get("fall_detection", False)),
            "data_accuracy": float(validated.get("data_accuracy", 100.0)),
        }

    def _normalize_timestamp(self, value: Any, fallback_index: int | None = None) -> datetime:
        if isinstance(value, datetime):
            timestamp = value
        elif isinstance(value, str) and value.strip():
            timestamp = datetime.fromisoformat(value)
        else:
            base = datetime.now(UTC)
            offset = fallback_index or 0
            timestamp = base + timedelta(seconds=offset * self.default_sample_interval_seconds)
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=UTC)
        return timestamp.astimezone(UTC)

    def _trim_history(self, history: deque[BufferedPoint], now: datetime) -> None:
        window_start = now - timedelta(seconds=max(self.window_seconds, self.settings.stability_warning_aggregation_seconds))
        while history and len(history) > self.history_cap:
            history.popleft()
        while history and history[0].timestamp < window_start and len(history) > self.max_points:
            history.popleft()

    def _recent_points(self, history: deque[BufferedPoint], now: datetime) -> list[BufferedPoint]:
        window_start = now - timedelta(seconds=self.window_seconds)
        recent = [point for point in history if point.timestamp >= window_start]
        return recent[-self.history_cap :]

    def _stabilize_vitals(self, raw_vitals: Mapping[str, Any], recent_points: list[BufferedPoint]) -> dict[str, Any]:
        recent = recent_points[-self.max_points :] if recent_points else []
        hr_values = [float(point.vitals["heart_rate"]) for point in recent] or [float(raw_vitals["heart_rate"])]
        spo2_values = [float(point.vitals["spo2"]) for point in recent] or [float(raw_vitals["spo2"])]
        temp_values = [float(point.vitals["body_temp"]) for point in recent] or [float(raw_vitals["body_temp"])]
        bp_window = recent_points[-self.bp_points :] if recent_points else []
        sbp_values = [float(point.vitals["sbp"]) for point in bp_window] or [float(raw_vitals["sbp"])]
        dbp_values = [float(point.vitals["dbp"]) for point in bp_window] or [float(raw_vitals["dbp"])]
        accuracy_values = [float(point.vitals["data_accuracy"]) for point in recent] or [float(raw_vitals["data_accuracy"])]

        stabilized = {
            "heart_rate": round(float(median(hr_values)), 4),
            "spo2": round(float(median(spo2_values)), 4),
            "sbp": round(float(median(sbp_values)), 4),
            "dbp": round(float(median(dbp_values)), 4),
            "body_temp": round(float(median(temp_values)), 4),
            "fall_detection": bool(raw_vitals.get("fall_detection", False)),
            "data_accuracy": round(float(min(accuracy_values)), 4),
        }
        return stabilized

    def _update_events(
        self,
        *,
        state: DeviceStabilityState,
        recent_points: list[BufferedPoint],
        raw_vitals: Mapping[str, Any],
        stabilized_vitals: Mapping[str, Any],
        timestamp: datetime,
    ) -> list[dict[str, Any]]:
        active_events: list[dict[str, Any]] = []
        recent_tail = recent_points[-self.min_points :]

        for rule in self._event_rules:
            event_state = state.events.setdefault(rule.event_type, EventState(event_type=rule.event_type))
            current_raw_abnormal = rule.enter_condition(raw_vitals)
            current_stable_abnormal = rule.enter_condition(stabilized_vitals)
            current_abnormal = current_raw_abnormal or current_stable_abnormal
            recent_abnormal_count = sum(1 for point in recent_tail if rule.enter_condition(point.vitals))
            recent_recovered_count = sum(1 for point in recent_tail if rule.exit_condition(point.vitals))
            abnormal_segment = self._recent_abnormal_segment(recent_points, rule.enter_condition)
            sustained_seconds = self._segment_duration_seconds(abnormal_segment, timestamp) if current_abnormal else 0.0
            activation_ready = current_abnormal and (
                rule.immediate
                or (
                    recent_abnormal_count >= rule.min_points
                    or sustained_seconds >= float(rule.min_duration_seconds)
                )
            )
            stable_recovered = rule.exit_condition(stabilized_vitals)

            if event_state.status == "active":
                should_resolve = False
                if rule.immediate:
                    should_resolve = not any(rule.enter_condition(point.vitals) for point in recent_points)
                else:
                    should_resolve = (not current_abnormal) and (
                        recent_recovered_count >= self.recovery_points or stable_recovered
                    )

                if should_resolve:
                    event_state.status = "resolved"
                    event_state.last_seen_time = timestamp
                    continue

                if current_abnormal or rule.immediate:
                    self._refresh_active_event_state(
                        rule=rule,
                        event_state=event_state,
                        raw_vitals=raw_vitals,
                        stabilized_vitals=stabilized_vitals,
                        timestamp=timestamp,
                    )
                active_events.append(self._serialize_event(event_state, timestamp))
                continue

            if activation_ready:
                event_state.status = "active"
                event_state.active_since = event_state.start_time or (
                    abnormal_segment[0].timestamp if abnormal_segment else timestamp
                )
                event_state.start_time = event_state.active_since
                self._refresh_active_event_state(
                    rule=rule,
                    event_state=event_state,
                    raw_vitals=raw_vitals,
                    stabilized_vitals=stabilized_vitals,
                    timestamp=timestamp,
                )
                active_events.append(self._serialize_event(event_state, timestamp))
                continue

            if current_abnormal:
                event_state.status = "candidate"
                event_state.start_time = event_state.start_time or timestamp
                event_state.last_seen_time = timestamp
                event_state.trigger_reason = rule.trigger_reason(raw_vitals)
            else:
                event_state.reset()

        active_events.sort(key=lambda item: (RISK_ORDER[item["severity"]], item["event_type"]), reverse=True)
        return active_events

    def _refresh_active_event_state(
        self,
        *,
        rule: EventRule,
        event_state: EventState,
        raw_vitals: Mapping[str, Any],
        stabilized_vitals: Mapping[str, Any],
        timestamp: datetime,
    ) -> None:
        value_source = raw_vitals if rule.enter_condition(raw_vitals) else stabilized_vitals
        current_value = rule.value_extractor(value_source)
        event_state.latest_value = current_value
        event_state.peak_value = rule.peak_selector(event_state.peak_value, current_value)
        event_state.last_seen_time = timestamp
        event_state.sample_count += 1
        event_state.severity = rule.severity_resolver(raw_vitals)
        event_state.trigger_reason = rule.trigger_reason(raw_vitals)
        event_state.start_time = event_state.start_time or timestamp
        event_state.active_since = event_state.active_since or event_state.start_time

    def _serialize_event(self, event_state: EventState, now: datetime) -> dict[str, Any]:
        sustained_seconds = 0.0
        if event_state.active_since is not None:
            sustained_seconds = max((now - event_state.active_since).total_seconds(), 0.0)
        return {
            "event_type": event_state.event_type,
            "severity": event_state.severity,
            "status": "active",
            "start_time": event_state.active_since or event_state.start_time or now,
            "last_seen_time": event_state.last_seen_time or now,
            "peak_value": event_state.peak_value,
            "latest_value": event_state.latest_value,
            "sample_count": event_state.sample_count,
            "sustained_seconds": round(sustained_seconds, 2),
            "trigger_reason": event_state.trigger_reason,
        }

    def _recent_abnormal_segment(
        self,
        recent_points: list[BufferedPoint],
        enter_condition: Callable[[Mapping[str, Any]], bool],
    ) -> list[BufferedPoint]:
        segment: list[BufferedPoint] = []
        for point in reversed(recent_points):
            if not enter_condition(point.vitals):
                break
            segment.append(point)
        return list(reversed(segment))

    def _segment_duration_seconds(self, segment: list[BufferedPoint], now: datetime) -> float:
        if not segment:
            return 0.0
        return max((now - segment[0].timestamp).total_seconds(), 0.0)

    def _evaluate_severe_hard_thresholds(self, vitals: Mapping[str, Any]) -> HardThresholdResult:
        reasons: list[str] = []
        heart_rate = float(vitals["heart_rate"])
        spo2 = float(vitals["spo2"])
        sbp = float(vitals["sbp"])
        dbp = float(vitals["dbp"])
        body_temp = float(vitals["body_temp"])
        fall_detection = bool(vitals.get("fall_detection", False))

        if spo2 < 88:
            reasons.append("SpO2 below 88%")
        if heart_rate > 140:
            reasons.append("Heart rate above 140 bpm")
        if heart_rate < 40:
            reasons.append("Heart rate below 40 bpm")
        if sbp >= 180:
            reasons.append("Systolic blood pressure above or equal to 180 mmHg")
        if dbp >= 110:
            reasons.append("Diastolic blood pressure above or equal to 110 mmHg")
        if body_temp >= 39.0:
            reasons.append("Body temperature above or equal to 39.0 C")
        if fall_detection:
            reasons.append("Fall detection triggered")

        if reasons:
            return HardThresholdResult(level="critical", trigger_reasons=reasons)
        return HardThresholdResult(level=None, trigger_reasons=[])

    def _build_event_rules(self) -> list[EventRule]:
        thresholds = self.settings.stability_event_thresholds
        durations = self.settings.stability_event_min_duration_seconds

        def peak_max(previous: EventValue | None, current: EventValue) -> EventValue:
            return current if previous is None else max(float(previous), float(current))

        def peak_min(previous: EventValue | None, current: EventValue) -> EventValue:
            return current if previous is None else min(float(previous), float(current))

        def peak_bp(previous: EventValue | None, current: EventValue) -> EventValue:
            current_bp = {"sbp": float(current["sbp"]), "dbp": float(current["dbp"])}
            if previous is None:
                return current_bp
            return {
                "sbp": max(float(previous["sbp"]), current_bp["sbp"]),
                "dbp": max(float(previous["dbp"]), current_bp["dbp"]),
            }

        def peak_bool(previous: EventValue | None, current: EventValue) -> EventValue:
            return bool(previous) or bool(current)

        return [
            EventRule(
                event_type="tachycardia",
                min_points=self.activation_min_points,
                min_duration_seconds=int(durations["tachycardia"]),
                immediate=False,
                enter_condition=lambda vitals: float(vitals["heart_rate"]) > float(thresholds["tachycardia"]["enter"]),
                exit_condition=lambda vitals: float(vitals["heart_rate"]) < float(thresholds["tachycardia"]["exit"]),
                value_extractor=lambda vitals: float(vitals["heart_rate"]),
                severity_resolver=lambda vitals: self._tachycardia_severity(float(vitals["heart_rate"])),
                trigger_reason=lambda vitals: f"Sustained heart rate above {int(thresholds['tachycardia']['enter'])} bpm",
                peak_selector=peak_max,
            ),
            EventRule(
                event_type="bradycardia",
                min_points=self.activation_min_points,
                min_duration_seconds=int(durations["bradycardia"]),
                immediate=False,
                enter_condition=lambda vitals: float(vitals["heart_rate"]) < float(thresholds["bradycardia"]["enter"]),
                exit_condition=lambda vitals: float(vitals["heart_rate"]) > float(thresholds["bradycardia"]["exit"]),
                value_extractor=lambda vitals: float(vitals["heart_rate"]),
                severity_resolver=lambda vitals: self._bradycardia_severity(float(vitals["heart_rate"])),
                trigger_reason=lambda vitals: f"Sustained heart rate below {int(thresholds['bradycardia']['enter'])} bpm",
                peak_selector=peak_min,
            ),
            EventRule(
                event_type="low_spo2",
                min_points=self.activation_min_points,
                min_duration_seconds=int(durations["low_spo2"]),
                immediate=False,
                enter_condition=lambda vitals: float(vitals["spo2"]) < float(thresholds["low_spo2"]["enter"]),
                exit_condition=lambda vitals: float(vitals["spo2"]) > float(thresholds["low_spo2"]["exit"]),
                value_extractor=lambda vitals: float(vitals["spo2"]),
                severity_resolver=lambda vitals: self._spo2_severity(float(vitals["spo2"])),
                trigger_reason=lambda vitals: f"Sustained SpO2 below {int(thresholds['low_spo2']['enter'])}%",
                peak_selector=peak_min,
            ),
            EventRule(
                event_type="hypertension",
                min_points=self.activation_min_points,
                min_duration_seconds=int(durations["hypertension"]),
                immediate=False,
                enter_condition=lambda vitals: (
                    float(vitals["sbp"]) >= float(thresholds["hypertension"]["sbp_enter"])
                    or float(vitals["dbp"]) >= float(thresholds["hypertension"]["dbp_enter"])
                ),
                exit_condition=lambda vitals: (
                    float(vitals["sbp"]) < float(thresholds["hypertension"]["sbp_exit"])
                    and float(vitals["dbp"]) < float(thresholds["hypertension"]["dbp_exit"])
                ),
                value_extractor=lambda vitals: {"sbp": float(vitals["sbp"]), "dbp": float(vitals["dbp"])},
                severity_resolver=lambda vitals: self._bp_severity(float(vitals["sbp"]), float(vitals["dbp"])),
                trigger_reason=lambda vitals: (
                    f"Sustained blood pressure above {int(thresholds['hypertension']['sbp_enter'])}/"
                    f"{int(thresholds['hypertension']['dbp_enter'])} mmHg"
                ),
                peak_selector=peak_bp,
            ),
            EventRule(
                event_type="fever",
                min_points=self.activation_min_points,
                min_duration_seconds=int(durations["fever"]),
                immediate=False,
                enter_condition=lambda vitals: float(vitals["body_temp"]) >= float(thresholds["fever"]["enter"]),
                exit_condition=lambda vitals: float(vitals["body_temp"]) < float(thresholds["fever"]["exit"]),
                value_extractor=lambda vitals: float(vitals["body_temp"]),
                severity_resolver=lambda vitals: self._temperature_severity(float(vitals["body_temp"])),
                trigger_reason=lambda vitals: f"Sustained body temperature above {thresholds['fever']['enter']:.1f} C",
                peak_selector=peak_max,
            ),
            EventRule(
                event_type="poor_signal_quality",
                min_points=self.activation_min_points,
                min_duration_seconds=int(durations["poor_signal_quality"]),
                immediate=False,
                enter_condition=lambda vitals: float(vitals["data_accuracy"]) < float(thresholds["poor_signal_quality"]["enter"]),
                exit_condition=lambda vitals: float(vitals["data_accuracy"]) > float(thresholds["poor_signal_quality"]["exit"]),
                value_extractor=lambda vitals: float(vitals["data_accuracy"]),
                severity_resolver=lambda vitals: "warning" if float(vitals["data_accuracy"]) < 75 else "attention",
                trigger_reason=lambda vitals: (
                    f"Sustained signal quality below {int(thresholds['poor_signal_quality']['enter'])}%"
                ),
                peak_selector=peak_min,
            ),
            EventRule(
                event_type="fall_detected",
                min_points=1,
                min_duration_seconds=0,
                immediate=True,
                enter_condition=lambda vitals: bool(vitals.get("fall_detection", False)),
                exit_condition=lambda vitals: not bool(vitals.get("fall_detection", False)),
                value_extractor=lambda vitals: bool(vitals.get("fall_detection", False)),
                severity_resolver=lambda vitals: (
                    "critical"
                    if bool(vitals.get("fall_detection", False))
                    and (float(vitals["spo2"]) < 90 or float(vitals["heart_rate"]) > 130)
                    else "warning"
                ),
                trigger_reason=lambda vitals: (
                    "Fall detected with concurrent hypoxia or severe tachycardia"
                    if bool(vitals.get("fall_detection", False))
                    and (float(vitals["spo2"]) < 90 or float(vitals["heart_rate"]) > 130)
                    else "Fall detection triggered"
                ),
                peak_selector=peak_bool,
            ),
        ]

    @staticmethod
    def _tachycardia_severity(heart_rate: float) -> str:
        if heart_rate > 140:
            return "critical"
        if heart_rate > 130:
            return "warning"
        return "attention"

    @staticmethod
    def _bradycardia_severity(heart_rate: float) -> str:
        if heart_rate < 40:
            return "critical"
        if heart_rate < 45:
            return "warning"
        return "attention"

    @staticmethod
    def _spo2_severity(spo2: float) -> str:
        if spo2 < 88:
            return "critical"
        if spo2 < 90:
            return "warning"
        return "attention"

    @staticmethod
    def _bp_severity(sbp: float, dbp: float) -> str:
        if sbp >= 180 or dbp >= 110:
            return "critical"
        if sbp >= 160 or dbp >= 100:
            return "warning"
        return "attention"

    @staticmethod
    def _temperature_severity(body_temp: float) -> str:
        if body_temp >= 39.0:
            return "critical"
        if body_temp >= 38.0:
            return "warning"
        return "attention"
