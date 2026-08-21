from __future__ import annotations

from collections import Counter
from statistics import mean

from backend.models.health_model import HealthSample


class HealthDataAnalysisService:
    """Provides deterministic time-window analytics for device and community agents."""

    def sample_risk_flags(self, sample: HealthSample) -> list[str]:
        return self._risk_flags(sample)

    def sample_risk_level(self, sample: HealthSample) -> str:
        return self._risk_level(sample)

    def summarize_device(self, samples: list[HealthSample]) -> dict[str, object]:
        if not samples:
            return {
                "scope": "device",
                "sample_count": 0,
                "risk_level": "unknown",
                "risk_flags": ["no_recent_data"],
                "notable_events": ["暂无最近监测数据，无法完成趋势分析。"],
                "recommendations": [
                    "先检查手环、网关和采集服务是否在线。",
                    "确认设备电量与佩戴状态，再重新观察一段时间。",
                ],
                "message": "暂无可分析的健康数据。",
            }

        ordered = sorted(samples, key=lambda item: item.timestamp)
        latest = ordered[-1]
        heart_rates = [item.heart_rate for item in ordered]
        temperatures = [item.temperature for item in ordered]
        blood_oxygen_values = [item.blood_oxygen for item in ordered]
        systolic_values, diastolic_values = self._blood_pressure_values(ordered)
        health_scores = [item.health_score for item in ordered if item.health_score is not None]
        latest_flags = self._risk_flags(latest)
        flag_counter = self._collect_flag_counts(ordered)
        trend_summary: dict[str, dict[str, object]] = {
            "heart_rate": self._trend_summary(heart_rates, threshold=3.0),
            "temperature": self._trend_summary(temperatures, threshold=0.2),
            "blood_oxygen": self._trend_summary(blood_oxygen_values, threshold=1.0),
            "blood_pressure_systolic": self._trend_summary(systolic_values, threshold=3.0),
            "blood_pressure_diastolic": self._trend_summary(diastolic_values, threshold=3.0),
        }
        if health_scores:
            trend_summary["health_score"] = self._trend_summary(health_scores, threshold=3.0)

        notable_events = self._notable_device_events(
            ordered=ordered,
            latest_flags=latest_flags,
            flag_counter=flag_counter,
        )

        return {
            "scope": "device",
            "device_mac": latest.device_mac,
            "sample_count": len(ordered),
            "window": self._window_summary(ordered),
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
                "health_score": round(mean(health_scores), 2) if health_scores else None,
            },
            "ranges": {
                "heart_rate": {"min": min(heart_rates), "max": max(heart_rates)},
                "temperature": {"min": min(temperatures), "max": max(temperatures)},
                "blood_oxygen": {"min": min(blood_oxygen_values), "max": max(blood_oxygen_values)},
                "blood_pressure_systolic": {"min": min(systolic_values), "max": max(systolic_values)},
                "blood_pressure_diastolic": {"min": min(diastolic_values), "max": max(diastolic_values)},
                "health_score": {
                    "min": min(health_scores) if health_scores else None,
                    "max": max(health_scores) if health_scores else None,
                },
            },
            "trend": trend_summary,
            "data_quality": self._data_quality(ordered),
            "risk_level": self._risk_level(latest),
            "risk_flags": latest_flags,
            "event_counts": dict(flag_counter),
            "notable_events": notable_events,
            "recommendations": self._device_recommendations(
                latest=latest,
                latest_flags=latest_flags,
                trend_summary=trend_summary,
                flag_counter=flag_counter,
            ),
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
            "health_score": ([item.health_score for item in ordered if item.health_score is not None], 3.0),
        }

        values, threshold = series_map.get(metric_key, ([], 0.0))
        if not values:
            return {
                "metric": metric_key,
                "sample_count": len(ordered),
                "status": "unsupported_metric",
                "supported_metrics": sorted(series_map.keys()),
            }

        summary = self._trend_summary(values, threshold=threshold)
        return {
            "metric": metric_key,
            "sample_count": len(ordered),
            "current": round(values[-1], 3),
            "baseline": round(values[0], 3),
            "delta": summary["delta"],
            "average": round(mean(values), 3),
            "trend": summary,
        }

    def summarize_community(self, samples: list[HealthSample]) -> dict[str, object]:
        grouped_samples = {sample.device_mac: [sample] for sample in samples}
        return self.summarize_community_history(grouped_samples)

    def summarize_community_history(
        self,
        device_samples: dict[str, list[HealthSample]],
    ) -> dict[str, object]:
        normalized: dict[str, list[HealthSample]] = {
            device_mac.upper(): sorted(samples, key=lambda item: item.timestamp)
            for device_mac, samples in device_samples.items()
            if samples
        }
        if not normalized:
            return {
                "scope": "community",
                "device_count": 0,
                "risk_distribution": {"low": 0, "medium": 0, "high": 0},
                "priority_devices": [],
                "recommendations": [
                    "社区端当前没有收到有效监测数据。",
                    "先检查网关在线状态、设备电量和时间同步情况。",
                ],
                "message": "暂无社区时间窗监测数据。",
            }

        device_summaries = [self.summarize_device(samples) for samples in normalized.values()]
        latest_samples = [samples[-1] for samples in normalized.values()]
        levels: dict[str, list[str]] = {"low": [], "medium": [], "high": []}
        for summary in device_summaries:
            levels[str(summary["risk_level"])].append(str(summary["device_mac"]))

        heart_rates = [item.heart_rate for item in latest_samples]
        temperatures = [item.temperature for item in latest_samples]
        blood_oxygen_values = [item.blood_oxygen for item in latest_samples]
        health_scores = [item.health_score for item in latest_samples if item.health_score is not None]
        priority_devices = self._community_priority_devices(device_summaries)
        data_gap_devices = [
            str(summary["device_mac"])
            for summary in device_summaries
            if int(summary["data_quality"]["gaps_over_30_minutes"]) > 0
        ]
        attention_summary = {
            "sos_devices": [
                str(summary["device_mac"])
                for summary in device_summaries
                if "sos_active" in summary["risk_flags"]
            ],
            "low_oxygen_devices": [
                str(summary["device_mac"])
                for summary in device_summaries
                if any(str(flag).startswith("blood_oxygen_") for flag in summary["risk_flags"])
            ],
            "fever_devices": [
                str(summary["device_mac"])
                for summary in device_summaries
                if any(str(flag).startswith("temperature_") for flag in summary["risk_flags"])
            ],
            "data_gap_devices": data_gap_devices,
        }

        return {
            "scope": "community",
            "device_count": len(device_summaries),
            "total_samples": sum(int(summary["sample_count"]) for summary in device_summaries),
            "window": self._community_window_summary(normalized),
            "risk_distribution": {level: len(devices) for level, devices in levels.items()},
            "risk_devices": levels,
            "community_averages": {
                "heart_rate": round(mean(heart_rates), 2),
                "temperature": round(mean(temperatures), 2),
                "blood_oxygen": round(mean(blood_oxygen_values), 2),
                "health_score": round(mean(health_scores), 2) if health_scores else None,
            },
            "trend_distribution": self._community_trend_distribution(device_summaries),
            "priority_devices": priority_devices,
            "attention_summary": attention_summary,
            "recommendations": self._community_recommendations(
                risk_distribution={level: len(devices) for level, devices in levels.items()},
                priority_devices=priority_devices,
                data_gap_devices=data_gap_devices,
            ),
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
    def _window_summary(samples: list[HealthSample]) -> dict[str, object]:
        start = samples[0].timestamp
        end = samples[-1].timestamp
        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "duration_minutes": round(max((end - start).total_seconds(), 0.0) / 60.0, 1),
        }

    def _community_window_summary(self, device_samples: dict[str, list[HealthSample]]) -> dict[str, object]:
        all_samples = [sample for samples in device_samples.values() for sample in samples]
        ordered = sorted(all_samples, key=lambda item: item.timestamp)
        return self._window_summary(ordered)

    def _data_quality(self, samples: list[HealthSample]) -> dict[str, object]:
        if len(samples) < 2:
            return {
                "avg_interval_minutes": None,
                "max_gap_minutes": None,
                "gaps_over_30_minutes": 0,
            }

        intervals = [
            max((current.timestamp - previous.timestamp).total_seconds(), 0.0) / 60.0
            for previous, current in zip(samples, samples[1:])
        ]
        return {
            "avg_interval_minutes": round(mean(intervals), 2),
            "max_gap_minutes": round(max(intervals), 2),
            "gaps_over_30_minutes": sum(1 for item in intervals if item > 30.0),
        }

    @staticmethod
    def _trend_summary(values: list[float], threshold: float) -> dict[str, object]:
        if len(values) < 2:
            return {
                "label": "insufficient_data",
                "delta": 0.0,
                "start_average": round(values[0], 3) if values else None,
                "end_average": round(values[-1], 3) if values else None,
            }

        segment = max(2, len(values) // 3)
        start_avg = mean(values[:segment])
        end_avg = mean(values[-segment:])
        delta = end_avg - start_avg
        label = "stable"
        if abs(delta) > threshold:
            label = "rising" if delta > 0 else "falling"
        return {
            "label": label,
            "delta": round(delta, 3),
            "start_average": round(start_avg, 3),
            "end_average": round(end_avg, 3),
        }

    def _collect_flag_counts(self, samples: list[HealthSample]) -> Counter[str]:
        counter: Counter[str] = Counter()
        for sample in samples:
            for flag in self._risk_flags(sample):
                if flag != "within_expected_range":
                    counter[flag] += 1
        return counter

    def _notable_device_events(
        self,
        *,
        ordered: list[HealthSample],
        latest_flags: list[str],
        flag_counter: Counter[str],
    ) -> list[str]:
        latest = ordered[-1]
        events: list[str] = []
        if flag_counter.get("sos_active"):
            events.append(f"时间窗内检测到 {flag_counter['sos_active']} 次 SOS 或持续求助信号。")
        if flag_counter.get("blood_oxygen_critical"):
            events.append(f"最低血氧已降至 {min(item.blood_oxygen for item in ordered)}%，存在明显缺氧风险。")
        if flag_counter.get("temperature_warning") or flag_counter.get("temperature_critical"):
            events.append(
                f"体温最高达到 {max(item.temperature for item in ordered):.1f}℃，需持续关注感染或发热趋势。"
            )
        if flag_counter.get("heart_rate_warning") or flag_counter.get("heart_rate_critical"):
            events.append(
                f"心率区间波动在 {min(item.heart_rate for item in ordered)}-{max(item.heart_rate for item in ordered)} bpm。"
            )
        if flag_counter.get("blood_pressure_warning") or flag_counter.get("blood_pressure_critical"):
            systolic_values, diastolic_values = self._blood_pressure_values(ordered)
            events.append(
                "血压波动明显，"
                f"收缩压范围 {min(systolic_values)}-{max(systolic_values)} mmHg，"
                f"舒张压范围 {min(diastolic_values)}-{max(diastolic_values)} mmHg。"
            )
        if latest_flags == ["within_expected_range"]:
            events.append("最近监测窗口内主要生命体征总体处于预期范围。")
        if latest.health_score is not None and latest.health_score < 65:
            events.append(f"当前健康分为 {latest.health_score}，已低于重点随访阈值。")
        return events[:5]

    def _community_priority_devices(self, device_summaries: list[dict[str, object]]) -> list[dict[str, object]]:
        risk_rank = {"high": 0, "medium": 1, "low": 2, "unknown": 3}
        flag_rank = {
            "sos_active": 0,
            "blood_oxygen_critical": 1,
            "heart_rate_critical": 2,
            "temperature_critical": 3,
            "blood_pressure_critical": 4,
            "blood_oxygen_warning": 5,
            "temperature_warning": 6,
            "blood_pressure_warning": 7,
            "heart_rate_warning": 8,
        }

        def sort_key(summary: dict[str, object]) -> tuple[object, object, object, object]:
            latest = summary.get("latest", {})
            if not isinstance(latest, dict):
                latest = {}
            flags = summary.get("risk_flags", [])
            if not isinstance(flags, list):
                flags = []
            health_score = latest.get("health_score")
            score_value = health_score if isinstance(health_score, (int, float)) else 999
            top_flag_rank = min((flag_rank.get(str(flag), 99) for flag in flags), default=99)
            return (
                risk_rank.get(str(summary.get("risk_level", "unknown")), 3),
                top_flag_rank,
                score_value,
                -len(flags),
            )

        ordered = sorted(device_summaries, key=sort_key)
        priority_devices: list[dict[str, object]] = []
        for summary in ordered[:5]:
            latest = summary.get("latest", {})
            if not isinstance(latest, dict):
                latest = {}
            priority_devices.append(
                {
                    "device_mac": summary.get("device_mac"),
                    "risk_level": summary.get("risk_level"),
                    "risk_flags": summary.get("risk_flags"),
                    "health_score": latest.get("health_score"),
                    "notable_events": list(summary.get("notable_events", []))[:2],
                }
            )
        return priority_devices

    def _community_trend_distribution(
        self,
        device_summaries: list[dict[str, object]],
    ) -> dict[str, dict[str, int]]:
        metrics = (
            "heart_rate",
            "temperature",
            "blood_oxygen",
            "blood_pressure_systolic",
            "blood_pressure_diastolic",
        )
        distribution = {
            metric: {"rising": 0, "stable": 0, "falling": 0, "insufficient_data": 0}
            for metric in metrics
        }
        for summary in device_summaries:
            trend = summary.get("trend", {})
            if not isinstance(trend, dict):
                continue
            for metric in metrics:
                metric_summary = trend.get(metric, {})
                if not isinstance(metric_summary, dict):
                    continue
                label = str(metric_summary.get("label", "insufficient_data"))
                if label not in distribution[metric]:
                    distribution[metric]["insufficient_data"] += 1
                else:
                    distribution[metric][label] += 1
        return distribution

    def _device_recommendations(
        self,
        *,
        latest: HealthSample,
        latest_flags: list[str],
        trend_summary: dict[str, dict[str, object]],
        flag_counter: Counter[str],
    ) -> list[str]:
        recommendations: list[str] = []
        if "sos_active" in latest_flags:
            recommendations.append("立即联系老人或现场值守人员，必要时按 SOS 预案启动上门处置。")
        if any(flag.startswith("blood_oxygen_") for flag in latest_flags):
            recommendations.append("优先复测血氧与呼吸状态，保持端坐位；若持续偏低，应尽快就医。")
        if any(flag.startswith("temperature_") for flag in latest_flags):
            recommendations.append("建议 15-30 分钟内复测体温，结合精神状态与补水情况继续观察。")
        if any(flag.startswith("blood_pressure_") for flag in latest_flags):
            recommendations.append("建议在静坐后重新测量血压，并排查情绪波动、运动后采样等干扰因素。")
        if any(flag.startswith("heart_rate_") for flag in latest_flags):
            recommendations.append("继续观察心率变化与活动情况，若波动持续或伴随不适，应联系医生。")
        if trend_summary["blood_oxygen"]["label"] == "falling":
            recommendations.append("血氧呈下降趋势，建议缩短复测间隔并重点关注呼吸道症状。")
        if trend_summary["temperature"]["label"] == "rising":
            recommendations.append("体温持续走高，建议结合症状记录并准备发热应对预案。")
        if latest.battery <= 20:
            recommendations.append("设备电量偏低，需尽快充电，避免关键时段监测中断。")
        if flag_counter.total() == 0 and not recommendations:
            recommendations.append("当前主要生命体征整体平稳，可保持常规监测与日常随访。")
        return recommendations[:5]

    def _community_recommendations(
        self,
        *,
        risk_distribution: dict[str, int],
        priority_devices: list[dict[str, object]],
        data_gap_devices: list[str],
    ) -> list[str]:
        recommendations: list[str] = []
        if risk_distribution.get("high", 0) > 0:
            focus = ", ".join(str(item["device_mac"]) for item in priority_devices[:3])
            recommendations.append(f"优先处理高风险对象，建议先核查 {focus} 的当前状态与现场响应情况。")
        if risk_distribution.get("medium", 0) > 0:
            recommendations.append("对中风险对象安排分级随访，优先关注血氧下降、发热和心率持续偏高的人群。")
        if data_gap_devices:
            recommendations.append(
                "部分设备存在较长数据间隔，建议排查网关在线状态、佩戴依从性和手环电量。"
            )
        if risk_distribution.get("high", 0) == 0 and risk_distribution.get("medium", 0) == 0:
            recommendations.append("社区整体态势平稳，可维持常规巡检频率并继续关注异常漂移。")
        return recommendations[:4]

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
        elif sample.temperature >= 37.5:
            flags.append("temperature_warning")

        if sample.blood_oxygen < 90:
            flags.append("blood_oxygen_critical")
        elif sample.blood_oxygen < 93:
            flags.append("blood_oxygen_warning")

        if systolic > 180 or diastolic > 120 or systolic < 90 or diastolic < 60:
            flags.append("blood_pressure_critical")
        elif systolic >= 140 or diastolic >= 90:
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
