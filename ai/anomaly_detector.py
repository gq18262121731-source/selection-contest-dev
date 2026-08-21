from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import exp, sqrt
from statistics import mean, pstdev

from backend.models.alarm_model import AlarmLayer, AlarmPriority, AlarmRecord, AlarmType
from backend.models.health_model import HealthSample

try:
    import torch
    from torch import nn
except ImportError:
    torch = None
    nn = None

try:
    from sklearn.cluster import DBSCAN
except ImportError:
    DBSCAN = None


@dataclass(slots=True)
class FeatureWindow:
    heart_rates: deque[int]
    temperatures: deque[float]
    spo2_values: deque[int]
    systolic_values: deque[int]
    diastolic_values: deque[int]


@dataclass(slots=True)
class SequenceProfile:
    feature_means: list[float]
    feature_stds: list[float]


@dataclass(slots=True)
class LatentSequenceAssessment:
    temporal_score: float
    health_score: float
    anomaly_probability: float
    attention_weights: list[float]
    feature_contributions: dict[str, float]
    dominant_features: list[str]


@dataclass(slots=True)
class SustainedAnomalyState:
    started_at: datetime
    latest_at: datetime
    hit_count: int
    mean_probability: float
    peak_probability: float
    peak_score: float
    alarm_emitted: bool = False


@dataclass(slots=True)
class SustainedAnomalyStatus:
    duration_minutes: float
    hit_count: int
    mean_probability: float
    peak_probability: float
    peak_score: float
    alarm_ready: bool
    alarm_emitted: bool


@dataclass(slots=True)
class IntelligentAnomalyResult:
    probability: float
    score: float
    drift_score: float
    reconstruction_score: float
    reason: str
    attention_weights: list[float] = field(default_factory=list)
    feature_contributions: dict[str, float] = field(default_factory=dict)
    health_score: float | None = None
    sustained_minutes: float = 0.0
    alarm_ready: bool = False


@dataclass(slots=True)
class CommunitySummary:
    clusters: dict[str, list[str]]
    trend: dict[str, int]
    risk_heatmap: list[dict[str, object]]


class RealtimeAnomalyDetector:
    """Realtime detector with hard rules and sliding-window dynamic Z-Score."""

    def __init__(self, window_size: int = 30, zscore_threshold: float = 2.4) -> None:
        self._window_size = window_size
        self._zscore_threshold = zscore_threshold
        self._windows: dict[str, FeatureWindow] = defaultdict(
            lambda: FeatureWindow(
                heart_rates=deque(maxlen=self._window_size),
                temperatures=deque(maxlen=self._window_size),
                spo2_values=deque(maxlen=self._window_size),
                systolic_values=deque(maxlen=self._window_size),
                diastolic_values=deque(maxlen=self._window_size),
            )
        )

    def evaluate(self, sample: HealthSample) -> list[AlarmRecord]:
        return self._evaluate_with_rules(sample)

    def _evaluate_with_rules(self, sample: HealthSample) -> list[AlarmRecord]:
        alarms: list[AlarmRecord] = []
        if sample.sos_flag:
            trigger = self._resolve_sos_trigger(sample.sos_value, sample.sos_trigger)
            alarms.append(
                AlarmRecord(
                    device_mac=sample.device_mac,
                    alarm_type=AlarmType.SOS,
                    alarm_level=AlarmPriority.SOS,
                    alarm_layer=AlarmLayer.REALTIME,
                    message=(
                        "检测到手环长按 SOS 求助，请立即联系值守人员并安排现场核查。"
                        if trigger == "long_press"
                        else "检测到手环双击 SOS 求助，请立即联系值守人员并安排现场核查。"
                        if trigger == "double_click"
                        else "检测到手环紧急 SOS 求助，请立即联系值守人员并安排现场核查。"
                    ),
                    anomaly_probability=1.0,
                    metadata={
                        "event": "sos_broadcast",
                        "sos_value": sample.sos_value,
                        "sos_trigger": trigger,
                        "packet_type": sample.packet_type,
                        "is_real_device": sample.source.value == "serial",
                    },
                )
            )
            sample = sample.model_copy(update={"sos_flag": False})

        # SOS 广播包是“告警信号包”，不是完整生命体征包。
        # 不要再对其做心率/体温/血氧阈值判断，避免 0 值触发假报警。
        is_sos_signal_packet = (
            sample.packet_type == "broadcast"
            and sample.source.value == "serial"
            and sample.heart_rate == 0
            and sample.blood_oxygen == 0
            and sample.temperature == 0
        )
        if is_sos_signal_packet:
            return alarms
        systolic, diastolic = sample.blood_pressure_pair or (None, None)

        if sample.sos_flag:
            alarms.append(
                AlarmRecord(
                    device_mac=sample.device_mac,
                    alarm_type=AlarmType.SOS,
                    alarm_level=AlarmPriority.SOS,
                    alarm_layer=AlarmLayer.REALTIME,
                    message="检测到 SOS 信号，请立即联系家属并安排现场核查。",
                    anomaly_probability=1.0,
                    metadata={"event": "sos_broadcast"},
                )
            )

        if sample.heart_rate > 180 or sample.heart_rate < 40:
            alarms.append(
                AlarmRecord(
                    device_mac=sample.device_mac,
                    alarm_type=AlarmType.VITAL_CRITICAL,
                    alarm_level=AlarmPriority.CRITICAL,
                    alarm_layer=AlarmLayer.REALTIME,
                    message=f"心率异常：{sample.heart_rate} bpm。",
                    anomaly_probability=0.98,
                    metadata={"metric": "heart_rate", "value": sample.heart_rate},
                )
            )

        if sample.temperature > 38.5 or sample.temperature < 35.0:
            alarms.append(
                AlarmRecord(
                    device_mac=sample.device_mac,
                    alarm_type=AlarmType.VITAL_CRITICAL,
                    alarm_level=AlarmPriority.CRITICAL,
                    alarm_layer=AlarmLayer.REALTIME,
                    message=f"体温异常：{sample.temperature:.1f}℃。",
                    anomaly_probability=0.97,
                    metadata={"metric": "temperature", "value": sample.temperature},
                )
            )

        if sample.blood_oxygen < 90:
            alarms.append(
                AlarmRecord(
                    device_mac=sample.device_mac,
                    alarm_type=AlarmType.VITAL_CRITICAL,
                    alarm_level=AlarmPriority.CRITICAL,
                    alarm_layer=AlarmLayer.REALTIME,
                    message=f"血氧偏低：{sample.blood_oxygen}%。",
                    anomaly_probability=0.99,
                    metadata={"metric": "blood_oxygen", "value": sample.blood_oxygen},
                )
            )

        if systolic is not None and diastolic is not None:
            if systolic > 180 or diastolic > 120 or systolic < 90 or diastolic < 60:
                alarms.append(
                    AlarmRecord(
                        device_mac=sample.device_mac,
                        alarm_type=AlarmType.VITAL_CRITICAL,
                        alarm_level=AlarmPriority.CRITICAL,
                        alarm_layer=AlarmLayer.REALTIME,
                        message=f"血压异常：{systolic}/{diastolic} mmHg。",
                        anomaly_probability=0.96,
                        metadata={
                            "metric": "blood_pressure",
                            "systolic": systolic,
                            "diastolic": diastolic,
                        },
                    )
                )

        window = self._windows[sample.device_mac]
        hr_z = self._safe_zscore(list(window.heart_rates), sample.heart_rate, min_delta=8.0)
        temp_z = self._safe_zscore(list(window.temperatures), sample.temperature, min_delta=0.4)
        spo2_z = self._safe_zscore(list(window.spo2_values), sample.blood_oxygen, min_delta=3.0)
        bp_z = (
            self._safe_zscore(list(window.systolic_values), float(systolic), min_delta=10.0)
            if systolic is not None
            else 0.0
        )
        sample.anomaly_score = round(max(hr_z, temp_z, spo2_z, bp_z), 3)

        if sample.anomaly_score >= self._zscore_threshold and not alarms:
            alarms.append(
                AlarmRecord(
                    device_mac=sample.device_mac,
                    alarm_type=AlarmType.ZSCORE_WARNING,
                    alarm_level=AlarmPriority.WARNING,
                    alarm_layer=AlarmLayer.REALTIME,
                    message="实时动态 Z-Score 检测到生命体征漂移，建议缩短复测间隔。",
                    anomaly_probability=min(0.95, round(sample.anomaly_score / 4, 3)),
                    metadata={"zscore": sample.anomaly_score},
                )
            )

        self._append_window(window, sample, systolic=systolic, diastolic=diastolic)
        return alarms

    @staticmethod
    def _resolve_sos_trigger(sos_value: int | None, current_trigger: str | None) -> str | None:
        if current_trigger:
            return current_trigger
        if sos_value is None:
            return None
        if sos_value & 0x02:
            return "long_press"
        if sos_value & 0x01:
            return "double_click"
        return None

    @staticmethod
    def _append_window(
        window: FeatureWindow,
        sample: HealthSample,
        *,
        systolic: int | None,
        diastolic: int | None,
    ) -> None:
        window.heart_rates.append(sample.heart_rate)
        window.temperatures.append(sample.temperature)
        window.spo2_values.append(sample.blood_oxygen)
        if systolic is not None:
            window.systolic_values.append(systolic)
        if diastolic is not None:
            window.diastolic_values.append(diastolic)

    @staticmethod
    def _safe_zscore(values: list[float], current_value: float | None, *, min_delta: float = 0.0) -> float:
        if current_value is None or len(values) < 5:
            return 0.0
        baseline_mean = mean(values)
        delta = abs(current_value - baseline_mean)
        if delta < min_delta:
            return 0.0
        sigma = pstdev(values)
        if sigma == 0:
            return round(max(delta / max(min_delta, 1.0), 3.0), 3)
        return abs((current_value - baseline_mean) / sigma)


class TinyLSTMVAE(nn.Module if nn else object):
    """A compact local LSTM-VAE for health time-series reconstruction."""

    def __init__(self, input_size: int = 4, hidden_size: int = 16, latent_size: int = 8) -> None:
        if not nn:
            return
        super().__init__()
        self.encoder = nn.LSTM(input_size=input_size, hidden_size=hidden_size, batch_first=True)
        self.mu_head = nn.Linear(hidden_size, latent_size)
        self.logvar_head = nn.Linear(hidden_size, latent_size)
        self.decoder_seed = nn.Linear(latent_size, hidden_size)
        self.decoder = nn.LSTM(input_size=hidden_size, hidden_size=hidden_size, batch_first=True)
        self.output = nn.Linear(hidden_size, input_size)

    def forward(self, inputs):
        _, (hidden, _) = self.encoder(inputs)
        hidden_state = hidden[-1]
        mu = self.mu_head(hidden_state)
        logvar = self.logvar_head(hidden_state)
        std = torch.exp(0.5 * logvar)
        epsilon = torch.randn_like(std)
        latent = mu + (epsilon * std)
        seed = self.decoder_seed(latent).unsqueeze(1).repeat(1, inputs.shape[1], 1)
        decoded, _ = self.decoder(seed)
        reconstructed = self.output(decoded)
        return reconstructed, mu, logvar


class LSTMVAEHealthEvaluator:
    """LSTM-VAE-first health sequence evaluator with deterministic fallback."""

    def __init__(self, window_size: int = 6) -> None:
        self.window_size = window_size
        self.feature_names = ("heart_rate", "temperature", "blood_oxygen", "systolic")
        self._feature_weights = {
            "heart_rate": 0.24,
            "temperature": 0.22,
            "blood_oxygen": 0.34,
            "systolic": 0.20,
        }
        self._model = TinyLSTMVAE(input_size=len(self.feature_names)) if torch else None
        self._is_trained = False

    def describe(self) -> dict[str, object]:
        return {
            "model_name": "lstm_vae",
            "input_window": self.window_size,
            "feature_names": list(self.feature_names),
            "output_scores": [
                "health_score",
                "anomaly_probability",
                "score",
                "drift_score",
                "reconstruction_score",
            ],
        }

    def warmup(self, sequences: list[list[list[float]]]) -> None:
        if not torch or self._model is None or not sequences:
            return
        training_sequences = sequences[:256]
        if not training_sequences:
            return
        tensor = torch.tensor(training_sequences, dtype=torch.float32)
        optimizer = torch.optim.Adam(self._model.parameters(), lr=0.01)
        self._model.train()
        for _ in range(2):
            optimizer.zero_grad()
            reconstructed, mu, logvar = self._model(tensor)
            reconstruction_loss = torch.mean((tensor - reconstructed) ** 2)
            kl_loss = -0.5 * torch.mean(1 + logvar - mu.pow(2) - logvar.exp())
            loss = reconstruction_loss + (0.05 * kl_loss)
            loss.backward()
            optimizer.step()
        self._model.eval()
        self._is_trained = True

    def assess(
        self,
        windows: list[list[float]],
        *,
        baseline: SequenceProfile,
        global_profile: SequenceProfile,
    ) -> LatentSequenceAssessment:
        selected = windows[-self.window_size :]
        if torch and self._model is not None and self._is_trained:
            return self._assess_with_model(selected, baseline=baseline, global_profile=global_profile)

        return self._assess_with_fallback(selected, baseline=baseline, global_profile=global_profile)

    def _assess_with_model(
        self,
        windows: list[list[float]],
        *,
        baseline: SequenceProfile,
        global_profile: SequenceProfile,
    ) -> LatentSequenceAssessment:
        tensor = torch.tensor([windows], dtype=torch.float32)
        with torch.no_grad():
            reconstructed, _, _ = self._model(tensor)
        reconstructed_windows = reconstructed[0].tolist()
        timestep_errors = [
            mean(abs(value - recon) for value, recon in zip(row, reconstructed_row, strict=True))
            for row, reconstructed_row in zip(windows, reconstructed_windows, strict=True)
        ]
        attention_weights = self._softmax(timestep_errors)
        latest = windows[-1]
        latest_reconstructed = reconstructed_windows[-1]
        feature_contributions = {}
        for index, feature_name in enumerate(self.feature_names):
            reconstruction_gap = abs(latest[index] - latest_reconstructed[index])
            scale = max(baseline.feature_stds[index], global_profile.feature_stds[index], 0.1)
            normalized_gap = reconstruction_gap / scale
            severity = self._severity_vector(latest, baseline=baseline, global_profile=global_profile)[index]
            contribution = (normalized_gap * 0.45) + (severity * self._feature_weights[feature_name])
            feature_contributions[feature_name] = round(contribution, 4)
        temporal_score = round(sum(feature_contributions.values()), 4)
        anomaly_probability = max(0.01, min(0.99, round(temporal_score / 3.0, 4)))
        health_score = round(max(25.0, 100.0 - min(75.0, temporal_score * 17.0)), 2)
        dominant_features = [
            feature
            for feature, contribution in sorted(feature_contributions.items(), key=lambda item: item[1], reverse=True)
            if contribution >= 0.2
        ][:3]
        if temporal_score > 12:
            return self._assess_with_fallback(windows, baseline=baseline, global_profile=global_profile)
        return LatentSequenceAssessment(
            temporal_score=temporal_score,
            health_score=health_score,
            anomaly_probability=anomaly_probability,
            attention_weights=[round(weight, 4) for weight in attention_weights],
            feature_contributions=feature_contributions,
            dominant_features=dominant_features,
        )

    def _assess_with_fallback(
        self,
        windows: list[list[float]],
        *,
        baseline: SequenceProfile,
        global_profile: SequenceProfile,
    ) -> LatentSequenceAssessment:
        severity_vectors = [
            self._severity_vector(vector, baseline=baseline, global_profile=global_profile)
            for vector in windows
        ]
        query = severity_vectors[-1]
        logits: list[float] = []
        total = len(severity_vectors)
        for index, vector in enumerate(severity_vectors):
            similarity = sum(current * previous for current, previous in zip(query, vector, strict=True)) / sqrt(len(query))
            recency_bias = (index / max(total - 1, 1)) * 0.35
            logits.append(similarity + recency_bias)

        attention_weights = self._softmax(logits)
        context = [
            sum(weight * vector[feature_index] for weight, vector in zip(attention_weights, severity_vectors, strict=True))
            for feature_index in range(len(self.feature_names))
        ]
        feature_contributions = {
            feature_name: round(context[index] * self._feature_weights[feature_name], 4)
            for index, feature_name in enumerate(self.feature_names)
        }
        temporal_score = round(sum(feature_contributions.values()), 4)
        anomaly_probability = max(0.01, min(0.99, round(temporal_score / 3.2, 4)))
        health_score = round(max(28.0, 100.0 - min(72.0, temporal_score * 18.0)), 2)
        dominant_features = [
            feature
            for feature, contribution in sorted(feature_contributions.items(), key=lambda item: item[1], reverse=True)
            if contribution >= 0.18
        ][:3]
        return LatentSequenceAssessment(
            temporal_score=temporal_score,
            health_score=health_score,
            anomaly_probability=anomaly_probability,
            attention_weights=[round(weight, 4) for weight in attention_weights],
            feature_contributions=feature_contributions,
            dominant_features=dominant_features,
        )

    def _severity_vector(
        self,
        vector: list[float],
        *,
        baseline: SequenceProfile,
        global_profile: SequenceProfile,
    ) -> list[float]:
        heart_rate, temperature, blood_oxygen, systolic = vector
        values = {
            "heart_rate": heart_rate,
            "temperature": temperature,
            "blood_oxygen": blood_oxygen,
            "systolic": systolic,
        }
        severities: list[float] = []
        for index, feature_name in enumerate(self.feature_names):
            local_mean = baseline.feature_means[index]
            local_std = max(baseline.feature_stds[index], 0.1)
            global_mean = global_profile.feature_means[index]
            global_std = max(global_profile.feature_stds[index], 0.1)
            mixed_z = (abs((values[feature_name] - local_mean) / local_std) * 0.6) + (
                abs((values[feature_name] - global_mean) / global_std) * 0.4
            )
            severities.append(round(mixed_z + self._absolute_feature_penalty(feature_name, values[feature_name]), 4))
        return severities

    @staticmethod
    def _softmax(logits: list[float]) -> list[float]:
        anchor = max(logits)
        exponentials = [exp(item - anchor) for item in logits]
        denominator = sum(exponentials) or 1.0
        return [value / denominator for value in exponentials]

    @staticmethod
    def _absolute_feature_penalty(feature_name: str, value: float) -> float:
        if feature_name == "heart_rate":
            if value >= 130 or value < 45:
                return 1.2
            if value >= 110 or value < 50:
                return 0.8
            if value >= 100:
                return 0.35
            return 0.0

        if feature_name == "temperature":
            if value >= 38.5 or value < 35.0:
                return 1.1
            if value >= 38.0:
                return 0.8
            if value >= 37.5:
                return 0.45
            return 0.0

        if feature_name == "blood_oxygen":
            if value <= 88:
                return 1.6
            if value <= 90:
                return 1.25
            if value <= 93:
                return 0.85
            if value <= 94:
                return 0.45
            return 0.0

        if feature_name == "systolic":
            if value >= 180 or value < 90:
                return 1.1
            if value >= 160:
                return 0.8
            if value >= 140:
                return 0.35
        return 0.0


class IntelligentAnomalyScorer:
    """Explainable minutes-level scorer with temporal attention and sustained escalation rules."""

    def __init__(
        self,
        *,
        sequence_length: int = 6,
        inference_interval_minutes: int = 10,
        history_minutes: int = 60,
        alert_threshold: float = 0.68,
        sustained_duration_minutes: int = 30,
        sustained_min_points: int = 4,
        sustained_probability_threshold: float = 0.72,
        sustained_score_threshold: float = 2.6,
    ) -> None:
        self._sequence_length = sequence_length
        self._inference_interval = timedelta(minutes=inference_interval_minutes)
        self._history_minutes = history_minutes
        self._alert_threshold = alert_threshold
        self._sustained_duration = timedelta(minutes=sustained_duration_minutes)
        self._sustained_min_points = sustained_min_points
        self._sustained_probability_threshold = sustained_probability_threshold
        self._sustained_score_threshold = sustained_score_threshold
        self._tracking_probability_threshold = max(0.55, alert_threshold - 0.1)
        self._tracking_score_threshold = max(2.0, sustained_score_threshold - 0.4)
        self._critical_probability_threshold = 0.86
        self._critical_duration = timedelta(minutes=max(sustained_duration_minutes + 10, 40))
        self._tracking_gap = timedelta(minutes=max(inference_interval_minutes * 2, 20))
        self._pretrained_profile = SequenceProfile(
            feature_means=[75.0, 36.5, 97.0, 118.0],
            feature_stds=[8.0, 0.25, 2.0, 12.0],
        )
        self._device_adapters: dict[str, SequenceProfile] = {}
        self._last_inference_at: dict[str, datetime] = {}
        self._sustained_states: dict[str, SustainedAnomalyState] = {}
        self._lstm_vae = LSTMVAEHealthEvaluator(window_size=sequence_length)

    def describe_model(self) -> dict[str, object]:
        description = self._lstm_vae.describe()
        description["alarm_rule"] = {
            "duration_minutes": round(self._sustained_duration.total_seconds() / 60),
            "minimum_points": self._sustained_min_points,
            "probability_threshold": self._sustained_probability_threshold,
            "score_threshold": self._sustained_score_threshold,
            "principle": "持续时间 + 异常程度，不依赖单点抖动",
        }
        return description

    def warmup(self, sequences_by_device: dict[str, list[list[float]]]) -> None:
        all_sequences = [window for windows in sequences_by_device.values() for window in windows]
        if all_sequences:
            self._pretrained_profile = self._build_profile(all_sequences)
        for device_mac, windows in sequences_by_device.items():
            if windows:
                self._device_adapters[device_mac.upper()] = self._build_profile(windows)
        self._lstm_vae.warmup(self._build_training_sequences(sequences_by_device))

    def score_sequence(self, windows: list[list[float]], device_mac: str | None = None) -> float:
        if not windows:
            return 0.0
        result = self._score_windows(windows, device_mac=device_mac)
        return result.score

    def _build_training_sequences(
        self,
        sequences_by_device: dict[str, list[list[float]]],
    ) -> list[list[list[float]]]:
        training_sequences: list[list[list[float]]] = []
        for windows in sequences_by_device.values():
            if len(windows) < self._sequence_length:
                continue
            for index in range(len(windows) - self._sequence_length + 1):
                training_sequences.append(windows[index : index + self._sequence_length])
        return training_sequences

    def should_infer(self, device_mac: str, now: datetime) -> bool:
        last_at = self._last_inference_at.get(device_mac.upper())
        if not last_at:
            return True
        return now - last_at >= self._inference_interval

    def infer_device(
        self,
        device_mac: str,
        samples: list[HealthSample],
        *,
        now: datetime | None = None,
        force: bool = False,
    ) -> IntelligentAnomalyResult | None:
        if len(samples) < self._sequence_length:
            return None

        now = now or samples[-1].timestamp
        history_cutoff = now - timedelta(minutes=self._history_minutes)
        history = [sample for sample in samples if sample.timestamp >= history_cutoff]
        if len(history) < self._sequence_length or (not force and not self.should_infer(device_mac, now)):
            return None

        windows = [self._vectorize(sample) for sample in history[-self._sequence_length :]]
        result = self._score_windows(windows, device_mac=device_mac)
        if not force:
            self._last_inference_at[device_mac.upper()] = now
        self._device_adapters[device_mac.upper()] = self._build_profile(windows)
        return result

    def build_alarm(self, sample: HealthSample, result: IntelligentAnomalyResult) -> AlarmRecord | None:
        status = self._update_sustained_state(sample, result)
        result.sustained_minutes = status.duration_minutes
        result.alarm_ready = status.alarm_ready
        if not status.alarm_ready or status.alarm_emitted:
            return None

        device_mac = sample.device_mac.upper()
        state = self._sustained_states[device_mac]
        state.alarm_emitted = True
        alarm_level = (
            AlarmPriority.CRITICAL
            if status.duration_minutes >= self._critical_duration.total_seconds() / 60
            and status.peak_probability >= self._critical_probability_threshold
            else AlarmPriority.WARNING
        )
        return AlarmRecord(
            device_mac=sample.device_mac,
            alarm_type=AlarmType.INTELLIGENT_ANOMALY,
            alarm_level=alarm_level,
            alarm_layer=AlarmLayer.INTELLIGENT,
            message=(
                f"智能时序评估检测到持续异常，已持续约 {status.duration_minutes:.0f} 分钟，"
                f"平均异常概率 {status.mean_probability:.0%}，建议立即人工复核。"
            ),
            anomaly_probability=min(0.99, round(status.peak_probability, 4)),
            metadata={
                "score": result.score,
                "drift_score": result.drift_score,
                "reconstruction_score": result.reconstruction_score,
                "reason": result.reason,
                "health_score": result.health_score,
                "attention_weights": result.attention_weights,
                "feature_contributions": result.feature_contributions,
                "sustained_minutes": round(status.duration_minutes, 2),
                "consecutive_hits": status.hit_count,
                "mean_probability": round(status.mean_probability, 4),
                "peak_probability": round(status.peak_probability, 4),
                "peak_score": round(status.peak_score, 4),
                "model_window": self._sequence_length,
                "feature_names": list(self._lstm_vae.feature_names),
                "alarm_rule": self.describe_model()["alarm_rule"],
            },
        )

    def _score_windows(self, windows: list[list[float]], device_mac: str | None) -> IntelligentAnomalyResult:
        adapter = self._device_adapters.get(device_mac.upper()) if device_mac else None
        baseline = adapter or self._pretrained_profile
        current = windows[-1]
        assessment = self._lstm_vae.assess(
            windows,
            baseline=baseline,
            global_profile=self._pretrained_profile,
        )

        drift_terms: list[float] = []
        for index, value in enumerate(current):
            baseline_mean = baseline.feature_means[index]
            baseline_std = max(baseline.feature_stds[index], 0.1)
            pretrained_mean = self._pretrained_profile.feature_means[index]
            pretrained_std = max(self._pretrained_profile.feature_stds[index], 0.1)
            local_z = abs((value - baseline_mean) / baseline_std)
            pretrained_z = abs((value - pretrained_mean) / pretrained_std)
            drift_terms.append((local_z * 0.65) + (pretrained_z * 0.35))
        drift_score = round(mean(drift_terms), 4)

        fused_score = round((drift_score * 0.4) + (assessment.temporal_score * 0.6), 4)
        score_probability = max(0.01, min(0.99, fused_score / 4.0))
        probability = max(
            0.01,
            min(
                0.99,
                round((assessment.anomaly_probability * 0.7) + (score_probability * 0.3), 4),
            ),
        )
        reason = self._build_reason(
            windows=windows,
            dominant_features=assessment.dominant_features,
            feature_contributions=assessment.feature_contributions,
        )
        return IntelligentAnomalyResult(
            probability=probability,
            score=fused_score,
            drift_score=drift_score,
            reconstruction_score=assessment.temporal_score,
            reason=reason,
            attention_weights=assessment.attention_weights,
            feature_contributions=assessment.feature_contributions,
            health_score=assessment.health_score,
        )

    def _update_sustained_state(
        self,
        sample: HealthSample,
        result: IntelligentAnomalyResult,
    ) -> SustainedAnomalyStatus:
        device_mac = sample.device_mac.upper()
        tracking_hit = (
            result.probability >= self._tracking_probability_threshold
            and result.score >= self._tracking_score_threshold
        )
        if not tracking_hit:
            self._sustained_states.pop(device_mac, None)
            return SustainedAnomalyStatus(
                duration_minutes=0.0,
                hit_count=0,
                mean_probability=0.0,
                peak_probability=0.0,
                peak_score=0.0,
                alarm_ready=False,
                alarm_emitted=False,
            )

        state = self._sustained_states.get(device_mac)
        if state is None or sample.timestamp - state.latest_at > self._tracking_gap:
            state = SustainedAnomalyState(
                started_at=sample.timestamp,
                latest_at=sample.timestamp,
                hit_count=1,
                mean_probability=result.probability,
                peak_probability=result.probability,
                peak_score=result.score,
            )
            self._sustained_states[device_mac] = state
        else:
            total_probability = (state.mean_probability * state.hit_count) + result.probability
            state.hit_count += 1
            state.latest_at = sample.timestamp
            state.mean_probability = total_probability / state.hit_count
            state.peak_probability = max(state.peak_probability, result.probability)
            state.peak_score = max(state.peak_score, result.score)

        duration_minutes = max((state.latest_at - state.started_at).total_seconds() / 60.0, 0.0)
        alarm_ready = (
            duration_minutes >= self._sustained_duration.total_seconds() / 60.0
            and state.hit_count >= self._sustained_min_points
            and state.mean_probability >= self._sustained_probability_threshold
            and state.peak_score >= self._sustained_score_threshold
        )
        return SustainedAnomalyStatus(
            duration_minutes=duration_minutes,
            hit_count=state.hit_count,
            mean_probability=state.mean_probability,
            peak_probability=state.peak_probability,
            peak_score=state.peak_score,
            alarm_ready=alarm_ready,
            alarm_emitted=state.alarm_emitted,
        )

    @staticmethod
    def _build_reason(
        *,
        windows: list[list[float]],
        dominant_features: list[str],
        feature_contributions: dict[str, float],
    ) -> str:
        latest = windows[-1]
        previous = windows[-2] if len(windows) >= 2 else latest
        heart_rate, temperature, blood_oxygen, systolic = latest
        prev_heart_rate, prev_temperature, prev_blood_oxygen, prev_systolic = previous
        phrases: list[str] = []

        if "blood_oxygen" in dominant_features and blood_oxygen <= prev_blood_oxygen:
            phrases.append("血氧持续偏低并呈下降趋势")
        if "temperature" in dominant_features and temperature >= prev_temperature:
            phrases.append("体温持续上扬")
        if "heart_rate" in dominant_features and heart_rate >= prev_heart_rate:
            phrases.append("心率持续偏高")
        if "systolic" in dominant_features and systolic >= prev_systolic:
            phrases.append("收缩压持续走高")
        if not phrases:
            focus = sorted(feature_contributions.items(), key=lambda item: item[1], reverse=True)[:2]
            phrases = [f"{feature} 时序贡献升高" for feature, _ in focus]
        return "；".join(phrases[:3])

    @staticmethod
    def _build_profile(windows: list[list[float]]) -> SequenceProfile:
        columns = list(zip(*windows))
        means = [mean(column) for column in columns]
        stds = [max(pstdev(column), 0.1) for column in columns]
        return SequenceProfile(feature_means=means, feature_stds=stds)

    @staticmethod
    def _vectorize(sample: HealthSample) -> list[float]:
        systolic, _ = sample.blood_pressure_pair or (120, 80)
        return [
            float(sample.heart_rate),
            float(sample.temperature),
            float(sample.blood_oxygen),
            float(systolic),
        ]


class CommunityHealthClusterer:
    """Hourly community-level grouping with DBSCAN fallback and trend summary."""

    def classify(self, samples: list[HealthSample]) -> dict[str, list[str]]:
        if not samples:
            return {"healthy": [], "attention": [], "danger": []}

        if DBSCAN and len(samples) >= 3:
            vectors = [
                [sample.heart_rate, sample.temperature, sample.blood_oxygen, (sample.blood_pressure_pair or (120, 80))[0]]
                for sample in samples
            ]
            labels = DBSCAN(eps=8.0, min_samples=2).fit_predict(vectors)
            grouped = {"healthy": [], "attention": [], "danger": []}
            for label, sample in zip(labels, samples, strict=True):
                if self._danger(sample):
                    grouped["danger"].append(sample.device_mac)
                elif label == -1 or self._attention(sample):
                    grouped["attention"].append(sample.device_mac)
                else:
                    grouped["healthy"].append(sample.device_mac)
            return grouped

        grouped = {"healthy": [], "attention": [], "danger": []}
        for sample in samples:
            if self._danger(sample):
                grouped["danger"].append(sample.device_mac)
            elif self._attention(sample):
                grouped["attention"].append(sample.device_mac)
            else:
                grouped["healthy"].append(sample.device_mac)
        return grouped

    def summarize(
        self,
        latest_samples: list[HealthSample],
        history_by_device: dict[str, list[HealthSample]],
    ) -> CommunitySummary:
        clusters = self.classify(latest_samples)
        trend = {
            "healthy": len(clusters["healthy"]),
            "attention": len(clusters["attention"]),
            "danger": len(clusters["danger"]),
        }
        heatmap: list[dict[str, object]] = []
        for sample in latest_samples:
            history = history_by_device.get(sample.device_mac, [])
            previous = history[-2] if len(history) >= 2 else None
            delta_hr = sample.heart_rate - previous.heart_rate if previous else 0
            delta_temp = round(sample.temperature - previous.temperature, 2) if previous else 0.0
            risk = (
                "danger"
                if sample.device_mac in clusters["danger"]
                else "attention"
                if sample.device_mac in clusters["attention"]
                else "healthy"
            )
            heatmap.append(
                {
                    "device_mac": sample.device_mac,
                    "risk": risk,
                    "heart_rate": sample.heart_rate,
                    "temperature": sample.temperature,
                    "blood_oxygen": sample.blood_oxygen,
                    "trend_delta": {"heart_rate": delta_hr, "temperature": delta_temp},
                }
            )
        return CommunitySummary(clusters=clusters, trend=trend, risk_heatmap=heatmap)

    def build_alarm(self, summary: CommunitySummary) -> AlarmRecord | None:
        danger_count = len(summary.clusters["danger"])
        attention_count = len(summary.clusters["attention"])
        total = sum(len(items) for items in summary.clusters.values())
        if total == 0:
            return None

        if danger_count >= 2:
            probability = min(0.99, round((danger_count / total) + 0.35, 2))
            return AlarmRecord(
                device_mac="COMMUNITY",
                alarm_type=AlarmType.COMMUNITY_RISK,
                alarm_level=AlarmPriority.WARNING,
                alarm_layer=AlarmLayer.COMMUNITY,
                message=f"社区宏观层识别到 {danger_count} 台高风险设备聚集，建议启动网格化排查。",
                anomaly_probability=probability,
                metadata={"trend": summary.trend, "risk_heatmap": summary.risk_heatmap[:5]},
            )

        if attention_count / total >= 0.4:
            probability = min(0.9, round((attention_count / total) + 0.2, 2))
            return AlarmRecord(
                device_mac="COMMUNITY",
                alarm_type=AlarmType.COMMUNITY_RISK,
                alarm_level=AlarmPriority.NOTICE,
                alarm_layer=AlarmLayer.COMMUNITY,
                message="社区关注人群占比持续升高，建议安排集中复测与电话随访。",
                anomaly_probability=probability,
                metadata={"trend": summary.trend, "risk_heatmap": summary.risk_heatmap[:5]},
            )

        return None

    @staticmethod
    def _danger(sample: HealthSample) -> bool:
        systolic, diastolic = sample.blood_pressure_pair or (120, 80)
        return (
            sample.sos_flag
            or sample.blood_oxygen < 90
            or sample.heart_rate > 180
            or sample.heart_rate < 40
            or sample.temperature > 38.5
            or sample.temperature < 35.0
            or systolic > 180
            or diastolic > 120
            or systolic < 90
            or diastolic < 60
        )

    @staticmethod
    def _attention(sample: HealthSample) -> bool:
        systolic, diastolic = sample.blood_pressure_pair or (120, 80)
        return (
            sample.heart_rate > 110
            or sample.heart_rate < 50
            or sample.temperature > 37.6
            or sample.blood_oxygen <= 93
            or systolic >= 140
            or diastolic >= 90
        )
