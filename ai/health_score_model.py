from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from statistics import mean

from backend.models.health_model import HealthSample


@dataclass(slots=True)
class PersonalBaseline:
    heart_rate: float
    temperature: float
    blood_oxygen: float
    battery: float


class BaselineTracker:
    """Maintains a rolling personal baseline for each elder device."""

    def __init__(self, max_samples: int = 180) -> None:
        self._history: dict[str, deque[HealthSample]] = defaultdict(lambda: deque(maxlen=max_samples))

    def observe(self, sample: HealthSample) -> PersonalBaseline:
        history = self._history[sample.device_mac]
        history.append(sample)
        return PersonalBaseline(
            heart_rate=mean(entry.heart_rate for entry in history),
            temperature=mean(entry.temperature for entry in history),
            blood_oxygen=mean(entry.blood_oxygen for entry in history),
            battery=mean(entry.battery for entry in history),
        )


class HealthScoreService:
    """Explainable 0-100 scoring model tuned for local elder-care monitoring."""

    def __init__(self, floor: int = 35) -> None:
        self._floor = floor

    def score(self, sample: HealthSample, baseline: PersonalBaseline) -> int:
        penalty = 0.0
        penalty += min(abs(sample.heart_rate - baseline.heart_rate) * 0.32, 16)
        penalty += min(abs(sample.temperature - baseline.temperature) * 14, 14)
        penalty += min(abs(sample.blood_oxygen - baseline.blood_oxygen) * 2.0, 16)
        penalty += min(abs(sample.battery - baseline.battery) * 0.12, 6)
        penalty += self._absolute_vital_penalty(sample)
        penalty += (100 - sample.battery) * 0.03
        if sample.sos_flag:
            penalty += 35
        if sample.ambient_temperature is not None and sample.surface_temperature is not None:
            penalty += min(abs(sample.surface_temperature - sample.ambient_temperature) * 0.2, 6)
        return max(self._floor, min(100, round(100 - penalty)))

    def _absolute_vital_penalty(self, sample: HealthSample) -> float:
        penalty = 0.0

        if sample.blood_oxygen < 88:
            penalty += 24
        elif sample.blood_oxygen <= 90:
            penalty += 18
        elif sample.blood_oxygen < 93:
            penalty += 10
        elif sample.blood_oxygen < 95:
            penalty += 4

        if sample.temperature >= 39.0 or sample.temperature < 35.0:
            penalty += 20
        elif sample.temperature >= 38.5:
            penalty += 14
        elif sample.temperature >= 37.5:
            penalty += 6

        if sample.heart_rate >= 130 or sample.heart_rate < 45:
            penalty += 18
        elif sample.heart_rate >= 110 or sample.heart_rate < 50:
            penalty += 10
        elif sample.heart_rate >= 100:
            penalty += 4

        blood_pressure = sample.blood_pressure_pair
        if blood_pressure is not None:
            systolic, diastolic = blood_pressure
            if systolic >= 180 or diastolic >= 120 or systolic < 90 or diastolic < 60:
                penalty += 18
            elif systolic >= 160 or diastolic >= 100:
                penalty += 10
            elif systolic >= 140 or diastolic >= 90:
                penalty += 4

        if sample.battery <= 10:
            penalty += 8
        elif sample.battery <= 20:
            penalty += 4

        return penalty
