from __future__ import annotations
IAN
from statistics import mean

from backend.models.health_model import HealthSample


class HealthDataAnalysisService:
    """Provides deterministic health analytics for the agent tools."""

    def summarize_device(self, samples: list[HealthSample]) -> dict[str, object]:
        if not samples:
            return {
                "sample_count": 0,
                "risk_level": "unknown",
                "risk_flags": ["no_recent_data"],
                "message": "暂无可分析的健康数据。",
            }

        ordered = sorted(samples, key=lambda item: item.timestamp)
        latest = ordered[-1]

        heart_rates = [item.heart_rate for item in ordered]
        temperatures = [item.temperature for item in ordered]
        blood_oxygen_values = [item.blood_oxygen for item in ordered]
        systolic_values, diastolic_values = self._blood_pressure_values(ordered)

        return {
            "device_mac": latest.device_mac,
            "sample_count": len(ordered),
            "window": {
                "start": ordered[0].timestamp.isoformat(),
                "end": latest.timestamp.isoformat(),
                "duration_minutes": round(
                    max((latest.timestamp - ordered[0].timestamp).total_seconds(), 0.0) / 60.0,
                    1,
                ),
            },
            "latest": {
                "heart_rate": latest.heart_rate,
                "temperature": latest.temperature,
                "blood_oxygen": latest.blood_oxygen,
                "blood_pressure": latest.blood_pressure,
                "battery": latest.battery,
                "sos_flag": latest.sos_flag,
                "health_score": latest.health_score,
            },
            "averages": {
                "heart_rate": round(mean(heart_rates), 2),
                "temperature": round(mean(temperatures), 2),
                "blood_oxygen": round(mean(blood_oxygen_values), 2),
                "blood_pressure_systolic": round(mean(systolic_values), 2),
                "blood_pressure_diastolic": round(mean(diastolic_values), 2),
            },
            "ranges": {
                "heart_rate": {"min": min(heart_rates), "max": max(heart_rates)},
                "temperature": {"min": min(temperatures), "max": max(temperatures)},
                "blood_oxygen": {"min": min(blood_oxygen_values), "max": max(blood_oxygen_values)},
                "blood_pressure_systolic": {"min": min(systolic_values), "max": max(systolic_values)},
                "blood_pressure_diastolic": {"min": min(diastolic_values), "max": max(diastolic_values)},
            },
            "trend": {
                "heart_rate": self._trend_label(heart_rates, threshold=3.0),
                "temperature": self._trend_label(temperatures, threshold=0.2),
                "blood_oxygen": self._trend_label(blood_oxygen_values, threshold=1.0),
                "blood_pressure_systolic": self._trend_label(systolic_values, threshold=3.0),
                "blood_pressure_diastolic": self._trend_label(diastolic_values, threshold=3.0),
            },
            "risk_level": self._risk_level(latest),
            "risk_flags": self._risk_flags(latest),
        }

    def metric_trend(self, samples: list[HealthSample], metric: str) -> dict[str, object]:
        metric_key = metric.lower().strip()
        if not samples:
            return {
                "metric": metric_key,
                "sample_count": 0,
                "status": "no_data",
                "message": "暂无可分析的健康数据。",
            }

        ordered = sorted(samples, key=lambda item: item.timestamp)
        systolic_values, diastolic_values = self._blood_pressure_values(ordered)
        series_map: dict[str, tuple[list[float], float]] = {
            "heart_rate": ([item.heart_rate for item in ordered], 3.0),
            "temperature": ([item.temperature for item in ordered], 0.2),
            "blood_oxygen": ([item.blood_oxygen for item in ordered], 1.0),
            "blood_pressure_systolic": (systolic_values, 3.0),
            "blood_pressure_diastolic": (diastolic_values, 3.0),
        }

        values, threshold = series_map.get(metric_key, ([], 0.0))
        if not values:
            return {
                "metric": metric_key,
                "sample_count": len(ordered),
                "status": "unsupported_metric",
                "supported_metrics": sorted(series_map.keys()),
            }

        return {
            "metric": metric_key,
            "sample_count": len(ordered),
            "current": round(values[-1], 3),
            "baseline": round(values[0], 3),
            "delta": round(values[-1] - values[0], 3),
            "average": round(mean(values), 3),
            "trend": self._trend_label(values, threshold=threshold),
        }

    def summarize_community(self, samples: list[HealthSample]) -> dict[str, object]:
        if not samples:
            return {
                "device_count": 0,
                "risk_distribution": {"low": 0, "medium": 0, "high": 0},
                "message": "暂无社区实时快照数据。",
            }

        levels: dict[str, list[str]] = {"low": [], "medium": [], "high": []}
        for sample in samples:
            levels[self._risk_level(sample)].append(sample.device_mac)

        heart_rates = [item.heart_rate for item in samples]
        temperatures = [item.temperature for item in samples]
        blood_oxygen_values = [item.blood_oxygen for item in samples]

        return {
            "device_count": len(samples),
            "risk_distribution": {level: len(devices) for level, devices in levels.items()},
            "risk_devices": levels,
            "community_averages": {
                "heart_rate": round(mean(heart_rates), 2),
                "temperature": round(mean(temperatures), 2),
                "blood_oxygen": round(mean(blood_oxygen_values), 2),
            },
        }

    @staticmethod
    def _blood_pressure_values(samples: list[HealthSample]) -> tuple[list[int], list[int]]:
        systolic_values: list[int] = []
        diastolic_values: list[int] = []
        for sample in samples:
            systolic, diastolic = sample.blood_pressure_pair
            systolic_values.append(systolic)
            diastolic_values.append(diastolic)
        return systolic_values, diastolic_values

    @staticmethod
    def _trend_label(values: list[float], threshold: float) -> str:
        if len(values) < 2:
            return "insufficient_data"
        delta = values[-1] - values[0]
        if abs(delta) <= threshold:
            return "stable"
        if delta > 0:
            return "rising"
        return "falling"

    def _risk_flags(self, sample: HealthSample) -> list[str]:
        flags: list[str] = []
        systolic, diastolic = sample.blood_pressure_pair

        if sample.sos_flag:
            flags.append("sos_active")

        if sample.heart_rate > 180 or sample.heart_rate < 40:
            flags.append("heart_rate_critical")
        elif sample.heart_rate > 110 or sample.heart_rate < 50:
            flags.append("heart_rate_warning")

        if sample.temperature > 38.5 or sample.temperature < 35.0:
            flags.append("temperature_critical")
        elif sample.temperature > 38.0:
            flags.append("temperature_warning")

        if sample.blood_oxygen < 90:
            flags.append("blood_oxygen_critical")
        elif sample.blood_oxygen < 93:
            flags.append("blood_oxygen_warning")

        if systolic > 180 or diastolic > 120 or systolic < 90 or diastolic < 60:
            flags.append("blood_pressure_critical")
        elif systolic > 160 or diastolic > 100:
            flags.append("blood_pressure_warning")

        return flags or ["within_expected_range"]

    def _risk_level(self, sample: HealthSample) -> str:
        flags = self._risk_flags(sample)
        high_risk_prefix = (
            "sos_",
            "heart_rate_critical",
            "temperature_critical",
            "blood_oxygen_critical",
            "blood_pressure_critical",
        )
        if any(flag.startswith(high_risk_prefix) for flag in flags):
            return "high"
        if any(flag.endswith("_warning") for flag in flags):
            return "medium"
        return "low"
def health_score(self,sample:HealthSample):
        score = 100
        systolic, diastolic = sample.blood_pressure_pair

        if sample.sos_flag:
            score -= 50

        if sample.heart_rate > 180 or sample.heart_rate < 40:
            score -= 30
        elif sample.heart_rate > 110 or sample.heart_rate < 50:
            score -= 15

        if sample.temperature > 38.5 or sample.temperature < 35.0:
            score -= 30
        elif sample.temperature > 38.0:
            score -= 15

        if sample.blood_oxygen < 90:
            score -= 30
        elif sample.blood_oxygen < 93:
            score -= 15

        if systolic > 180 or diastolic > 120 or systolic < 90 or diastolic < 60:
            score -= 30
        elif systolic > 160 or diastolic > 100:
            score -= 15

        return max(score, 0)