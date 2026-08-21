from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from backend.models.device_model import DeviceIngestMode, DeviceRecord
from backend.models.health_model import HealthSample, IngestionSource


@dataclass(slots=True)
class DevicePersona:
    mac_address: str
    display_name: str
    apartment: str
    scenario_profile: str
    heart_rate_base: int
    temperature_base: float
    blood_oxygen_base: int
    systolic_base: int
    diastolic_base: int
    battery: int


@dataclass(slots=True)
class DeviceRuntimeState:
    last_generated_at: datetime
    last_step_reset_date: date
    daily_steps: int
    step_fraction: float
    activity_phase: str
    heart_rate_value: float
    blood_oxygen_value: float
    systolic_value: float
    diastolic_value: float
    temperature_value: float
    heart_rate_drift: float
    spo2_drift: float
    bp_drift: float
    temperature_drift: float
    battery_level: int
    next_heart_rate_update_at: datetime
    next_spo2_update_at: datetime
    next_bp_update_at: datetime
    next_temperature_update_at: datetime
    rng: random.Random = field(repr=False)


@dataclass(slots=True)
class ScenarioPhase:
    name: str
    start_index: int
    end_index: int
    description: str


@dataclass(slots=True)
class HealthDemoScenario:
    name: str
    device_mac: str
    step_minutes: int
    model_window: int
    feature_names: list[str]
    output_scores: list[str]
    alarm_rule: dict[str, object]
    phases: list[ScenarioPhase]
    samples: list[HealthSample]


DEMO_TIMEZONE = ZoneInfo("Asia/Shanghai")
DEMO_MOCK_SUBJECTS = [
    ("李四", "1-102"),
    ("王五", "1-103"),
    ("赵六", "2-101"),
    ("孙七", "2-102"),
    ("孙八", "2-103"),
    ("周九", "3-101"),
    ("吴十", "3-102"),
    ("郑十一", "3-103"),
    ("卫十二", "4-101"),
    ("韩十三", "4-102"),
]


class SyntheticHealthDataGenerator:
    """Generates realistic elder-care vital signs for demos, tests and model warm-up."""

    def __init__(self, device_count: int = 10, mac_prefix: str = "53:57:08", seed: int = 42) -> None:
        self._seed = seed
        self._rng = random.Random(seed)
        self._device_count = device_count
        self._mac_prefix = mac_prefix
        self._personas = [self._build_persona(index) for index in range(device_count)]
        self._persona_by_mac = {persona.mac_address: persona for persona in self._personas}
        self._runtime_states: dict[str, DeviceRuntimeState] = {}

    @property
    def personas(self) -> list[DevicePersona]:
        return self._personas

    def build_devices(self) -> list[DeviceRecord]:
        return [
            DeviceRecord(
                mac_address=persona.mac_address,
                device_name="T10-WATCH",
                ingest_mode=DeviceIngestMode.MOCK,
            )
            for persona in self._personas
        ]

    def build_subject_profiles(self) -> list[dict[str, str]]:
        return [
            {
                "elder_id": f"demo-elder-{index + 1:02d}",
                "elder_name": persona.display_name,
                "apartment": persona.apartment,
                "device_mac": persona.mac_address,
                "scenario_profile": persona.scenario_profile,
            }
            for index, persona in enumerate(self._personas)
        ]

    def next_sample(self, now: datetime | None = None) -> HealthSample:
        now = now or datetime.now(timezone.utc)
        persona = self._rng.choice(self._personas)
        return self.sample_for_device(persona.mac_address, now=now)

    def sample_for_device(self, device_mac: str, now: datetime | None = None) -> HealthSample:
        now = now or datetime.now(timezone.utc)
        persona = self._resolve_persona(device_mac)
        state = self._runtime_states.get(persona.mac_address)
        if state is None or now < state.last_generated_at:
            anchor = now - timedelta(hours=6)
            state = self._bootstrap_state(persona, anchor)
            self._runtime_states[persona.mac_address] = state
        self._advance_state(state, persona, now)
        return self._sample_from_state(persona, state, now)

    def build_history(
        self,
        *,
        hours: int = 1,
        step_minutes: int = 10,
    ) -> dict[str, list[HealthSample]]:
        history: dict[str, list[HealthSample]] = {}
        now = datetime.now(timezone.utc)
        total_steps = max(1, int((hours * 60) / step_minutes))
        for persona in self._personas:
            device_samples: list[HealthSample] = []
            state = self._bootstrap_state(persona, now - timedelta(hours=hours, minutes=1))
            for index in range(total_steps + 1):
                point_at = now - timedelta(minutes=step_minutes * (total_steps - index))
                self._advance_state(state, persona, point_at)
                device_samples.append(self._sample_from_state(persona, state, point_at))
            history[persona.mac_address] = device_samples
        return history

    def build_training_sequences(
        self,
        *,
        hours: int = 24,
        step_minutes: int = 10,
    ) -> dict[str, list[list[float]]]:
        sequences: dict[str, list[list[float]]] = {}
        history = self.build_history(hours=hours, step_minutes=step_minutes)
        for device_mac, samples in history.items():
            windows: list[list[float]] = []
            for sample in samples:
                systolic, _ = sample.blood_pressure_pair or (120, 80)
                windows.append(
                    [
                        float(sample.heart_rate),
                        float(sample.temperature),
                        float(sample.blood_oxygen),
                        float(systolic),
                    ]
                )
            sequences[device_mac] = windows
        return sequences

    def build_sustained_anomaly_demo_scenario(
        self,
        *,
        device_mac: str | None = None,
        start: datetime | None = None,
        step_minutes: int = 10,
    ) -> HealthDemoScenario:
        start = start or datetime.now(timezone.utc).replace(second=0, microsecond=0)
        mac_address = device_mac.upper() if device_mac else self._personas[0].mac_address
        vitals = [
            (74, 36.5, 97, 120, 80, "normal"),
            (75, 36.6, 97, 121, 80, "normal"),
            (73, 36.5, 98, 119, 79, "normal"),
            (76, 36.6, 97, 121, 80, "normal"),
            (74, 36.5, 97, 120, 80, "normal"),
            (75, 36.5, 97, 121, 80, "normal"),
            (88, 37.1, 94, 132, 84, "anomaly"),
            (98, 37.6, 92, 146, 90, "sustained_anomaly"),
            (108, 37.8, 91, 152, 94, "sustained_anomaly"),
            (116, 38.0, 90, 160, 96, "alarm"),
        ]
        samples: list[HealthSample] = []
        daily_steps = 1200
        for index, (heart_rate, temperature, blood_oxygen, systolic, diastolic, _) in enumerate(vitals):
            daily_steps += 110 + (index * 35)
            samples.append(
                HealthSample(
                    device_mac=mac_address,
                    timestamp=start + timedelta(minutes=index * step_minutes),
                    heart_rate=heart_rate,
                    temperature=temperature,
                    blood_oxygen=blood_oxygen,
                    blood_pressure=f"{systolic}/{diastolic}",
                    battery=max(42, 76 - index),
                    steps=daily_steps,
                    sos_flag=False,
                    source=IngestionSource.MOCK,
                )
            )

        phases = [
            ScenarioPhase(
                name="normal",
                start_index=0,
                end_index=5,
                description="稳定基线窗口，用于形成时序模型输入背景。",
            ),
            ScenarioPhase(
                name="anomaly",
                start_index=6,
                end_index=6,
                description="第一次明显偏移，但持续时间不足，不应直接报警。",
            ),
            ScenarioPhase(
                name="sustained_anomaly",
                start_index=7,
                end_index=8,
                description="异常持续存在且逐步加重，应进入持续异常状态但尚未报警。",
            ),
            ScenarioPhase(
                name="alarm",
                start_index=9,
                end_index=9,
                description="同时满足持续时间与异常程度阈值，触发智能报警。",
            ),
        ]
        return HealthDemoScenario(
            name="sustained-anomaly-escalation",
            device_mac=mac_address,
            step_minutes=step_minutes,
            model_window=6,
            feature_names=["heart_rate", "temperature", "blood_oxygen", "systolic"],
            output_scores=[
                "health_score",
                "anomaly_probability",
                "score",
                "drift_score",
                "reconstruction_score",
            ],
            alarm_rule={
                "duration_minutes": 30,
                "minimum_points": 4,
                "principle": "持续时间 + 异常程度，不依赖单点抖动",
            },
            phases=phases,
            samples=samples,
        )

    def encode_packet_pair(self, sample: HealthSample) -> tuple[str, str]:
        """Encodes a sample into the demo packet layout used by iot/parser.py."""
        systolic, diastolic = sample.blood_pressure_pair
        flags = 0x01 if sample.sos_flag else 0x00
        event_code = 0x02 if sample.sos_flag else 0x00
        temperature_raw = int(round(sample.temperature * 100))
        merged_payload = bytes(
            [
                sample.heart_rate,
                (temperature_raw >> 8) & 0xFF,
                temperature_raw & 0xFF,
                sample.blood_oxygen,
                systolic,
                diastolic,
                sample.battery,
                flags,
                event_code,
                0x00,
                0x00,
                0x00,
            ]
        )
        header = bytes.fromhex("AA55AA55AA55AA55AA55AA55")
        packet_a = header + bytes.fromhex("1803") + merged_payload[:6]
        packet_b = header + bytes.fromhex("0318") + merged_payload[6:]
        return packet_a.hex().upper(), packet_b.hex().upper()

    def _resolve_persona(self, device_mac: str) -> DevicePersona:
        persona = self._persona_by_mac.get(device_mac.upper())
        if persona is None:
            raise ValueError(f"Unknown device: {device_mac}")
        return persona

    def _bootstrap_state(self, persona: DevicePersona, anchor: datetime) -> DeviceRuntimeState:
        local_anchor = anchor.astimezone(DEMO_TIMEZONE)
        rng = self._seeded_rng(persona.mac_address, int(anchor.timestamp()) // 60)
        activity_phase = self._resolve_activity_phase(persona, local_anchor)
        return DeviceRuntimeState(
            last_generated_at=anchor,
            last_step_reset_date=local_anchor.date(),
            daily_steps=self._initial_steps_for_time(persona, local_anchor),
            step_fraction=0.0,
            activity_phase=activity_phase,
            heart_rate_value=float(persona.heart_rate_base),
            blood_oxygen_value=float(persona.blood_oxygen_base),
            systolic_value=float(persona.systolic_base),
            diastolic_value=float(persona.diastolic_base),
            temperature_value=float(persona.temperature_base),
            heart_rate_drift=0.0,
            spo2_drift=0.0,
            bp_drift=0.0,
            temperature_drift=0.0,
            battery_level=persona.battery,
            next_heart_rate_update_at=anchor,
            next_spo2_update_at=anchor,
            next_bp_update_at=anchor,
            next_temperature_update_at=anchor,
            rng=rng,
        )

    def _advance_state(self, state: DeviceRuntimeState, persona: DevicePersona, target_at: datetime) -> None:
        if target_at <= state.last_generated_at:
            return

        cursor = state.last_generated_at
        while cursor < target_at:
            step_at = min(target_at, cursor + timedelta(minutes=1))
            local_step = step_at.astimezone(DEMO_TIMEZONE)
            if local_step.date() != state.last_step_reset_date:
                state.last_step_reset_date = local_step.date()
                state.daily_steps = 0
                state.step_fraction = 0.0

            state.activity_phase = self._resolve_activity_phase(persona, local_step)
            self._advance_steps(state, persona, local_step, (step_at - cursor).total_seconds())

            while step_at >= state.next_heart_rate_update_at:
                self._refresh_heart_rate(state, persona, state.next_heart_rate_update_at.astimezone(DEMO_TIMEZONE))
                state.next_heart_rate_update_at += timedelta(seconds=state.rng.randint(45, 90))

            while step_at >= state.next_spo2_update_at:
                self._refresh_blood_oxygen(state, persona, state.next_spo2_update_at.astimezone(DEMO_TIMEZONE))
                state.next_spo2_update_at += timedelta(seconds=state.rng.randint(75, 150))

            while step_at >= state.next_bp_update_at:
                self._refresh_blood_pressure(state, persona, state.next_bp_update_at.astimezone(DEMO_TIMEZONE))
                state.next_bp_update_at += timedelta(seconds=state.rng.randint(180, 360))

            while step_at >= state.next_temperature_update_at:
                self._refresh_temperature(state, persona, state.next_temperature_update_at.astimezone(DEMO_TIMEZONE))
                state.next_temperature_update_at += timedelta(seconds=state.rng.randint(300, 600))

            if local_step.minute % 20 == 0 and local_step.second < 30:
                state.battery_level = max(18, state.battery_level - state.rng.choice([0, 0, 0, 1]))

            cursor = step_at

        state.last_generated_at = target_at

    def _advance_steps(
        self,
        state: DeviceRuntimeState,
        persona: DevicePersona,
        local_step: datetime,
        delta_seconds: float,
    ) -> None:
        rate_per_minute = self._step_rate_for_phase(persona, state.activity_phase, local_step)
        state.step_fraction += rate_per_minute * max(delta_seconds, 1.0) / 60.0
        whole_steps = int(state.step_fraction)
        if whole_steps > 0:
            state.daily_steps += whole_steps
            state.step_fraction -= whole_steps

    def _refresh_heart_rate(self, state: DeviceRuntimeState, persona: DevicePersona, local_step: datetime) -> None:
        target = self._target_heart_rate(persona, state.activity_phase, local_step)
        state.heart_rate_drift = self._bounded_walk(state.heart_rate_drift, state.rng, 0.6, 5.0)
        state.heart_rate_value = self._smooth_value(
            current=state.heart_rate_value,
            target=target,
            drift=state.heart_rate_drift,
            noise=state.rng.uniform(-0.35, 0.35),
            weight=0.18,
            minimum=48.0,
            maximum=165.0,
        )

    def _refresh_blood_oxygen(self, state: DeviceRuntimeState, persona: DevicePersona, local_step: datetime) -> None:
        target = self._target_blood_oxygen(persona, state.activity_phase, local_step)
        state.spo2_drift = self._bounded_walk(state.spo2_drift, state.rng, 0.15, 1.0)
        state.blood_oxygen_value = self._smooth_value(
            current=state.blood_oxygen_value,
            target=target,
            drift=state.spo2_drift,
            noise=state.rng.uniform(-0.12, 0.12),
            weight=0.12,
            minimum=84.0,
            maximum=100.0,
        )

    def _refresh_blood_pressure(self, state: DeviceRuntimeState, persona: DevicePersona, local_step: datetime) -> None:
        target_sbp, target_dbp = self._target_blood_pressure(persona, state.activity_phase, local_step)
        state.bp_drift = self._bounded_walk(state.bp_drift, state.rng, 0.45, 4.0)
        state.systolic_value = self._smooth_value(
            current=state.systolic_value,
            target=target_sbp,
            drift=state.bp_drift,
            noise=state.rng.uniform(-0.45, 0.45),
            weight=0.12,
            minimum=95.0,
            maximum=185.0,
        )
        state.diastolic_value = self._smooth_value(
            current=state.diastolic_value,
            target=target_dbp,
            drift=state.bp_drift * 0.45,
            noise=state.rng.uniform(-0.35, 0.35),
            weight=0.10,
            minimum=58.0,
            maximum=120.0,
        )

    def _refresh_temperature(self, state: DeviceRuntimeState, persona: DevicePersona, local_step: datetime) -> None:
        target = self._target_temperature(persona, state.activity_phase, local_step)
        state.temperature_drift = self._bounded_walk(state.temperature_drift, state.rng, 0.008, 0.08)
        state.temperature_value = self._smooth_value(
            current=state.temperature_value,
            target=target,
            drift=state.temperature_drift,
            noise=state.rng.uniform(-0.006, 0.006),
            weight=0.06,
            minimum=35.5,
            maximum=39.2,
        )

    def _sample_from_state(self, persona: DevicePersona, state: DeviceRuntimeState, now: datetime) -> HealthSample:
        sos_value = self._sos_value_for(persona, now.astimezone(DEMO_TIMEZONE))
        systolic = int(round(state.systolic_value))
        diastolic = int(round(state.diastolic_value))
        heart_rate = int(round(state.heart_rate_value))
        blood_oxygen = int(round(state.blood_oxygen_value))
        temperature = round(state.temperature_value, 1)
        return HealthSample(
            device_mac=persona.mac_address,
            timestamp=now,
            heart_rate=max(45, min(165, heart_rate)),
            temperature=max(35.5, min(39.2, temperature)),
            blood_oxygen=max(84, min(100, blood_oxygen)),
            blood_pressure=f"{max(95, min(185, systolic))}/{max(58, min(120, diastolic))}",
            battery=state.battery_level,
            steps=state.daily_steps,
            sos_flag=sos_value > 0,
            sos_value=sos_value or None,
            sos_trigger="long_press" if sos_value == 0x02 else ("double_click" if sos_value == 0x01 else None),
            source=IngestionSource.MOCK,
        )

    def _resolve_activity_phase(self, persona: DevicePersona, local_step: datetime) -> str:
        minute_of_day = local_step.hour * 60 + local_step.minute
        burst_windows = self._burst_windows(persona, local_step)
        for start, end in burst_windows:
            if start <= minute_of_day < end:
                return "walk_burst"
        if 0 <= local_step.hour < 6:
            return "sleep"
        if 6 <= local_step.hour < 9:
            return "wake"
        if 9 <= local_step.hour < 12:
            return "routine"
        if 12 <= local_step.hour < 14:
            return "rest"
        if 14 <= local_step.hour < 18:
            return "afternoon"
        if 18 <= local_step.hour < 21:
            return "evening"
        return "settle"

    def _burst_windows(self, persona: DevicePersona, local_step: datetime) -> list[tuple[int, int]]:
        seed_value = int(persona.mac_address.replace(":", "")[-4:], 16) + local_step.date().toordinal()
        morning_start = 7 * 60 + (seed_value % 35)
        evening_start = 16 * 60 + ((seed_value * 3) % 60)
        return [(morning_start, morning_start + 22), (evening_start, evening_start + 28)]

    def _step_rate_for_phase(self, persona: DevicePersona, phase: str, local_step: datetime) -> float:
        base_rates = {
            "sleep": 0.0,
            "wake": 7.2,
            "routine": 4.2,
            "rest": 1.4,
            "afternoon": 4.8,
            "evening": 3.2,
            "settle": 0.9,
            "walk_burst": 16.0,
        }
        multiplier = {
            "stable_normal": 1.0,
            "chronic_risk": 0.76,
            "escalating_anomaly": 0.62,
            "alert_active": 0.48,
        }[persona.scenario_profile]
        if phase == "walk_burst":
            if persona.scenario_profile == "stable_normal":
                return 20.0
            if persona.scenario_profile == "chronic_risk":
                return 13.0
            if persona.scenario_profile == "escalating_anomaly":
                return 9.5
            return 6.5
        hour_bias = 1.0 + max(0.0, math.sin((local_step.hour / 24) * math.pi * 2)) * 0.12
        return base_rates.get(phase, 0.25) * multiplier * hour_bias

    def _target_heart_rate(self, persona: DevicePersona, phase: str, local_step: datetime) -> float:
        phase_boost = {
            "sleep": -8.0,
            "wake": 2.0,
            "routine": 0.0,
            "rest": -2.0,
            "afternoon": 1.0,
            "evening": 0.0,
            "settle": -3.0,
            "walk_burst": 14.0,
        }[phase]
        circadian = math.sin((local_step.hour / 24) * math.pi * 2) * 4.0
        scenario_offset = {
            "stable_normal": 0.0,
            "chronic_risk": 8.0,
            "escalating_anomaly": 4.0 + self._progression(local_step) * 16.0,
            "alert_active": 13.0,
        }[persona.scenario_profile]
        return persona.heart_rate_base + phase_boost + circadian + scenario_offset

    def _target_blood_oxygen(self, persona: DevicePersona, phase: str, local_step: datetime) -> float:
        phase_shift = -1.0 if phase == "walk_burst" else 0.0
        scenario_offset = {
            "stable_normal": 0.0,
            "chronic_risk": -2.5,
            "escalating_anomaly": -(1.5 + self._progression(local_step) * 4.0),
            "alert_active": -4.0,
        }[persona.scenario_profile]
        return persona.blood_oxygen_base + phase_shift + scenario_offset

    def _target_blood_pressure(self, persona: DevicePersona, phase: str, local_step: datetime) -> tuple[float, float]:
        phase_boost = {
            "sleep": (-4.0, -3.0),
            "wake": (2.0, 1.0),
            "routine": (0.0, 0.0),
            "rest": (-2.0, -1.0),
            "afternoon": (1.0, 0.5),
            "evening": (0.0, 0.0),
            "settle": (-1.0, -1.0),
            "walk_burst": (11.0, 6.0),
        }[phase]
        escalation = self._progression(local_step)
        scenario_offsets = {
            "stable_normal": (0.0, 0.0),
            "chronic_risk": (12.0, 8.0),
            "escalating_anomaly": (8.0 + escalation * 18.0, 4.0 + escalation * 10.0),
            "alert_active": (18.0, 10.0),
        }[persona.scenario_profile]
        return (
            persona.systolic_base + phase_boost[0] + scenario_offsets[0],
            persona.diastolic_base + phase_boost[1] + scenario_offsets[1],
        )

    def _target_temperature(self, persona: DevicePersona, phase: str, local_step: datetime) -> float:
        phase_boost = 0.08 if phase == "walk_burst" else 0.0
        scenario_offset = {
            "stable_normal": 0.0,
            "chronic_risk": 0.2,
            "escalating_anomaly": 0.1 + self._progression(local_step) * 0.7,
            "alert_active": 0.45,
        }[persona.scenario_profile]
        circadian = math.sin(((local_step.hour + local_step.minute / 60) / 24) * math.pi * 2) * 0.08
        return persona.temperature_base + phase_boost + scenario_offset + circadian

    def _progression(self, local_step: datetime) -> float:
        return max(0.0, min(1.0, ((local_step.hour * 60) + local_step.minute - 13 * 60) / (8 * 60)))

    def _sos_value_for(self, persona: DevicePersona, local_step: datetime) -> int:
        if persona.scenario_profile != "alert_active":
            return 0
        minute_of_day = local_step.hour * 60 + local_step.minute
        seed_value = int(persona.mac_address.replace(":", "")[-2:], 16) + local_step.date().toordinal()
        double_click_minute = 11 * 60 + (seed_value % 180)
        long_press_minute = 18 * 60 + ((seed_value * 5) % 120)
        if double_click_minute <= minute_of_day < double_click_minute + 2:
            return 0x01
        if long_press_minute <= minute_of_day < long_press_minute + 2:
            return 0x02
        return 0

    def _initial_steps_for_time(self, persona: DevicePersona, local_anchor: datetime) -> int:
        steps = 0
        midnight = local_anchor.replace(hour=0, minute=0, second=0, microsecond=0)
        cursor = midnight
        while cursor < local_anchor:
            phase = self._resolve_activity_phase(persona, cursor)
            steps += int(self._step_rate_for_phase(persona, phase, cursor))
            cursor += timedelta(minutes=1)
        baseline = {
            "stable_normal": 220,
            "chronic_risk": 160,
            "escalating_anomaly": 120,
            "alert_active": 80,
        }[persona.scenario_profile]
        return steps + baseline

    @staticmethod
    def _smooth_value(
        *,
        current: float,
        target: float,
        drift: float,
        noise: float,
        weight: float,
        minimum: float,
        maximum: float,
    ) -> float:
        next_value = current + (target - current) * weight + drift * 0.12 + noise
        return max(minimum, min(maximum, next_value))

    @staticmethod
    def _bounded_walk(current: float, rng: random.Random, step: float, limit: float) -> float:
        next_value = current + rng.uniform(-step, step)
        return max(-limit, min(limit, next_value))

    def _seeded_rng(self, mac_address: str, salt: int) -> random.Random:
        compact = int(mac_address.replace(":", ""), 16)
        return random.Random(self._seed + compact + salt)

    def _build_persona(self, index: int) -> DevicePersona:
        suffix = f"{index + 1:06X}"
        mac = ":".join([*self._mac_prefix.split(":"), suffix[0:2], suffix[2:4], suffix[4:6]])
        scenario_profile = [
            "stable_normal",
            "stable_normal",
            "stable_normal",
            "chronic_risk",
            "stable_normal",
            "stable_normal",
            "stable_normal",
            "escalating_anomaly",
            "stable_normal",
            "stable_normal",
            "stable_normal",
            "alert_active",
        ][index % 12]
        subject_name, subject_apartment = DEMO_MOCK_SUBJECTS[index % len(DEMO_MOCK_SUBJECTS)]
        display_name = subject_name
        apartment = subject_apartment
        hr_base = self._rng.randint(62, 84)
        temp_base = round(self._rng.uniform(36.2, 36.8), 1)
        spo2_base = self._rng.randint(95, 99)
        systolic_base = self._rng.randint(108, 128)
        diastolic_base = self._rng.randint(68, 82)
        if scenario_profile == "chronic_risk":
            hr_base += 8
            temp_base = round(min(37.2, temp_base + 0.3), 1)
            spo2_base = max(92, spo2_base - 3)
            systolic_base += 12
            diastolic_base += 8
        elif scenario_profile == "escalating_anomaly":
            hr_base += 5
            spo2_base = max(93, spo2_base - 2)
            systolic_base += 8
            diastolic_base += 4
        elif scenario_profile == "alert_active":
            hr_base += 12
            temp_base = round(min(37.4, temp_base + 0.5), 1)
            spo2_base = max(90, spo2_base - 5)
            systolic_base += 18
            diastolic_base += 10
        return DevicePersona(
            mac_address=mac,
            display_name=display_name,
            apartment=apartment,
            scenario_profile=scenario_profile,
            heart_rate_base=hr_base,
            temperature_base=temp_base,
            blood_oxygen_base=spo2_base,
            systolic_base=systolic_base,
            diastolic_base=diastolic_base,
            battery=self._rng.randint(72, 100),
        )
