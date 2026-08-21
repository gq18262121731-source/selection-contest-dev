# Health Model Demo Scenarios

Last updated: 2026-03-21

## Purpose

This file defines reproducible health-model demo scenarios for the `HM-*` track.

The current primary scenario is designed to prove the intended flow:

`正常 -> 异常 -> 持续异常 -> 报警`

It is meant for:

- regression coverage
- operator demo rehearsal
- threshold review
- cross-role handoff

## Scenario 1: Sustained Anomaly Escalation

Implementation source:

- `ai/data_generator.py`
- method: `build_sustained_anomaly_demo_scenario(...)`

Model assumptions used by this scenario:

- input window: `6`
- step size: `10` minutes
- features:
  - `heart_rate`
  - `temperature`
  - `blood_oxygen`
  - `systolic`
- output scores:
  - `health_score`
  - `anomaly_probability`
  - `score`
  - `drift_score`
  - `reconstruction_score`

Alarm rule exercised by this scenario:

- sustained duration: `30` minutes
- minimum abnormal points: `4`
- trigger principle: `持续时间 + 异常程度，不依赖单点抖动`

### Phase layout

1. `normal`
   - index range: `0-5`
   - purpose: build a stable temporal baseline

2. `anomaly`
   - index range: `6`
   - purpose: produce the first clear deviation without immediate alarm

3. `sustained_anomaly`
   - index range: `7-8`
   - purpose: keep the deviation active long enough to accumulate sustained-risk evidence

4. `alarm`
   - index range: `9`
   - purpose: cross the duration-plus-severity rule and emit an intelligent alarm

### Expected behavior

- No intelligent alarm during `normal`
- No intelligent alarm during the first `anomaly` point
- `sustained_anomaly` should show elevated intelligent scores but still not alarm yet
- The first intelligent alarm should appear in the `alarm` phase
- Hard realtime critical alarms should not be the reason this scenario alarms

## Usage

Recommended verification path:

1. Build the scenario from `SyntheticHealthDataGenerator`
2. Feed the samples in timestamp order
3. Run intelligent inference per point
4. Apply sustained-anomaly alarm logic
5. Assert that the first intelligent alarm appears only in the `alarm` phase

Current regression coverage:

- `tests/test_alarm_service.py`
