# Camera Current Source Of Truth

This document is the canonical source for the currently selected external/runtime camera chain.

## Owner

- Runtime root: `D:\Program\health(5-12)\camera_runtime_external`
- Truth file: `data/camera_source_of_truth.json`
- Runtime config: `camera_runtime_external/camera_live_config.runtime.json`

## Rules

1. Do not treat historical IPs in old notes as current truth.
2. `camera2` is the runtime-managed network camera source.
3. The family page, community page, fall detection, and pose detection should all converge on the same raw source.
4. If RTSP is unreachable, diagnostics must say so explicitly instead of silently pretending the source is valid.

## Current Verification Fields

- `preferred_host`
- `rtsp_port`
- `transport`
- `stream`
- `verified_at`
- `verified_status`
- `verification_reason`

## Resolution Strategy

1. Read `data/camera_source_of_truth.json`.
2. If absent, fall back to `camera_runtime_external/camera_live_config.runtime.json`.
3. If runtime has no fresh frame, run the automatic external-camera bootstrap/probe path.
4. Only after all runtime candidates fail should the system fall back to degraded snapshot strategies.
