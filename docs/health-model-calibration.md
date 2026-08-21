# Health Model Calibration Notes

Last updated: 2026-03-21

## Scope

This document explains the current local health-model calibration used by the Health Model Engineer (`HM-*`) track.

It covers:

- health-score calibration
- realtime anomaly threshold behavior
- intelligent anomaly scoring intent
- transformer-style temporal assessment
- sustained anomaly escalation
- report-input integration
- community priority ordering rules
- regression expectations

It does not define public API fields. Public response shape remains governed by `docs/agent-collaboration-contract.md`.

## Design goals

The current local model chain is optimized for:

- explainability
- deterministic behavior
- stable regression coverage
- safe operator-facing prioritization

The current implementation intentionally favors readable rules over opaque learned behavior.

## Health score model

Implementation:

- `ai/health_score_model.py`

The health score is a bounded `0-100` score with a configured floor.

Current calibration uses two sources of penalty:

1. Personal-baseline drift
2. Absolute vital-sign risk

### Why combine baseline drift with absolute penalties

Using only personal baseline drift is not stable enough for local deployment. A device with persistently poor blood oxygen or fever can gradually shift its baseline and look falsely "normal."

To prevent that failure mode, the score now combines:

- relative deviation from the rolling personal baseline
- absolute penalties for clearly abnormal values

### Absolute-penalty intent

Current absolute penalties intentionally react to:

- low blood oxygen
- fever or hypothermia
- tachycardia or marked bradycardia
- hypertension or hypotension
- low battery
- SOS state

This means:

- a stable healthy device keeps a high score
- a persistently abnormal device still carries a material score penalty
- SOS still forces the score close to the configured floor

## Realtime anomaly detector

Implementation:

- `ai/anomaly_detector.py`

The realtime detector has two layers:

1. Hard-threshold critical alarms
2. Sliding-window Z-Score drift warning

### Hard-threshold behavior

Critical alarms are raised immediately for:

- SOS
- critical heart rate
- critical temperature
- critical blood oxygen
- critical blood pressure

### Z-Score calibration

The realtime Z-Score path now compares the current sample against the prior window before appending the new point into history.

This avoids a demo-style failure where the current outlier dilutes its own anomaly score by first entering the comparison window.

A minimum absolute delta is also required per metric before a Z-Score warning is emitted. This reduces noisy warnings on tiny changes.

When historical variance is zero but the new sample exceeds the minimum delta, the detector still emits a warning-grade anomaly score instead of silently returning zero.

## Intelligent anomaly scorer

Implementation:

- `ai/anomaly_detector.py`

The intelligent scorer is now a deterministic local scoring layer built around:

- pretrained profile means/stds
- per-device adapters
- a single-head temporal attention model
- a drift score
- a compatibility `reconstruction_score` field backed by the temporal-attention score

Its purpose is not to replace hard-threshold safety rules.

Its purpose is to explain and score hidden drift when the device is worsening without yet crossing all critical thresholds.

### Transformer-style temporal assessment

The current temporal model is a deterministic Transformer-style attention scorer.

Current input contract:

- input window: `6` samples
- features:
  - `heart_rate`
  - `temperature`
  - `blood_oxygen`
  - `systolic`

Current output contract:

- `health_score`
- `anomaly_probability`
- `score`
- `drift_score`
- `reconstruction_score`

Compatibility note:

- public/API fields remain unchanged
- `reconstruction_score` is kept as the existing field name for compatibility, but it is now backed by the temporal-attention score rather than an autoencoder reconstruction metric

### Why this is still explainable

The temporal model is deterministic and does not rely on runtime training.

It uses:

- temporal attention over the input window
- explicit feature weights
- absolute-risk penalties for clinically important ranges
- readable dominant-feature explanations

This preserves local explainability while making the time-series path more coherent than a pure pointwise rule set.

## Sustained anomaly escalation

Implementation:

- `ai/anomaly_detector.py`

Intelligent anomaly alarms no longer depend on a single high-scoring point alone.

The current rule requires:

- sustained duration
- multiple abnormal inference points
- sufficient anomaly probability
- sufficient anomaly score

This is intentional so that:

- brief jitter does not become an alarm
- sustained worsening does become an alarm
- hard-threshold realtime alarms still remain available for immediately dangerous points

Current escalation principle:

- `持续时间 + 异常程度，不依赖单点抖动`

Clarified in plain language:

- `持续时间 + 异常程度，不依赖单点抖动`

## Report-input integration

Implementation:

- `agent/langgraph_health_agent.py`
- `agent/model_interfaces.py`

Transformer-derived anomaly signals are now injected into report generation as internal model signals.

Current integration points:

- report retrieval query
- report prompt context
- fallback report summary
- report `key_findings`
- report `recommendations`

Current normalized internal evidence version:

- `hm_report_v2`

Current evidence sections include:

- input window definition
- latest / average health score evidence
- normalized `risk_level`
- normalized `risk_flags`
- anomaly stage:
  - `normal`
  - `abnormal`
  - `sustained_abnormal`
  - `alarm`
- sustained-abnormality status
- trend evidence
- key evidence lines
- normalized summary inputs
- normalized key findings
- normalized recommendations

Current sustained-abnormality evidence is derived from both:

- direct model payloads when present
- deterministic report-side replay over the same sample window

This keeps report evidence stable even when the formal report path is called outside the live alarm-emission moment.

Important compatibility rule:

- no new public report fields were added
- existing report schema stays stable
- Transformer information is expressed through the existing `summary`, `key_findings`, and `recommendations` fields

## Community priority ordering

Implementation:

- `agent/analysis_service.py`

Community prioritization is intentionally deterministic.

Current sort priority is:

1. Risk level
2. Highest-severity risk flag
3. Health score
4. Number of active risk flags

This prevents same-level high-risk cases from being sorted only by health score.

Examples of flags that should outrank generic same-level cases:

- `sos_active`
- `blood_oxygen_critical`
- other `*_critical` flags

## Recommendation generation

Implementation:

- `agent/analysis_service.py`

Recommendations remain rule-based and are derived from:

- current risk flags
- simple trend direction
- device battery state

This is intentional so operators can trace each recommendation back to visible evidence.

## Regression expectations

Current regression coverage is expected to lock the following behaviors:

- health score drops under persistent abnormal oxygen even if the rolling baseline has shifted
- SOS and critical vital signs drive materially lower scores than stable samples
- realtime anomaly warnings can fire from a stable prior window when a clear outlier arrives
- the Transformer-style scorer keeps a stable window/feature/output contract
- intelligent alarms require sustained abnormality rather than a single spike
- the reproducible demo scenario progresses from normal to alarm in the intended order
- report generation can consume Transformer model signals without changing the public report schema
- community priority ordering favors hard-risk flags over generic score-only ordering
- representative abnormal trends produce matching follow-up recommendations

## Change protocol

If future HM work changes:

- health-analysis semantics
- ranking logic
- recommendation basis

then update in the same task:

1. implementation
2. regression tests
3. this calibration note

If future HM work changes public response fields, stop and coordinate with `AG`, `FE`, and `TE` before merging because that crosses the documented interface boundary.
