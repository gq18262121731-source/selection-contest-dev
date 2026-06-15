# Camera Source Of Truth Consolidation Plan

## Goal

Define a single camera configuration truth source for the current project before any Batch 3 integration work begins.

This document is a governance plan, not a code change plan. Its purpose is to answer four questions:

1. How many camera configuration sources currently exist?
2. Which one is the truth source?
3. Which modules must obey it?
4. How do we verify the system has actually converged?

## Why This Matters

At the current stage, the migration work has already separated low-risk content migration from high-risk system integration.

The next highest-value and lowest-risk task is not to connect new fall modules or wire Video Bridge into the main chain. It is to remove ambiguity around camera configuration.

If camera truth is not unified first, the following areas can drift apart:

- RTSP access
- family camera view
- community camera view
- pose detection
- fall detection
- external camera runtime
- Video Bridge placeholder and future bridge consumers

This creates the exact class of problems that are hardest to debug later:

- historical IPs overriding runtime state
- one module using `.env`, another using runtime JSON, another using hardcoded recovery notes
- diagnostics claiming the source is valid while runtime capture is already stale

## Current Phase Position

This plan starts after the following verified checkpoints:

- `9109511`: Batch 1 document/config migration
- `b0222fd`: Batch 2 scripts/independent modules migration
- `2915260`: Batch 2 script entry safety fixes
- `4ab8e50`: Batch 3 integration decision checklist
- `temp69-batch2-verified`: stable rollback tag

At this point:

- low-risk high-value content has already been migrated
- main wiring has not been touched
- repository state is stable and rollback-safe

## Current Source Inventory

The repository currently references multiple camera-related sources.

### A. Intended Truth Source

Documented in [camera-current-source-of-truth.md](/d:/health_original/health1/docs/camera-current-source-of-truth.md):

- canonical truth file: `data/camera_source_of_truth.json`
- runtime fallback: `camera_runtime_external/camera_live_config.runtime.json`

This is the correct intended direction.

### B. Runtime Configuration Files

Observed references:

- `camera_runtime_external/camera_live_config.runtime.json`
- `camera_runtime_external/camera_live_config.json`

Observed in:

- `backend/services/camera_source_registry.py`
- `backend/services/external_camera_bridge_service.py`
- `camera_runtime_external/camera_runtime_start.ps1`
- `camera_runtime_external/run_camera_live_server.ps1`

These appear to be active runtime-side sources.

### C. Backend Truth/Bridge Logic

Observed references:

- `backend/services/external_camera_bridge_service.py`
- `backend/api/target_user_api.py`

This suggests the backend already has a partial abstraction for exposing camera truth, but convergence across the whole system is not yet proven.

### D. Historical Documentation and Recovery Notes

Observed references:

- `docs/system_startup_and_recovery_manual.md`
- `docs/camera-source-layer.md`
- older runtime owner path notes such as `D:\Program\health(5-12)\camera_runtime_external`

These are useful operational references, but they must not be treated as runtime truth.

### E. `.env` / Camera2 Family of Settings

From [camera-source-layer.md](/d:/health_original/health1/docs/camera-source-layer.md), `camera2` can fall back to runtime config if `CAMERA2_*` is not configured.

This means `.env` remains a possible upstream source for some modules and must be explicitly governed, not left implicit.

## Planned Truth Hierarchy

The project should converge on the following source hierarchy:

1. `data/camera_source_of_truth.json`
2. `camera_runtime_external/camera_live_config.runtime.json`
3. runtime bootstrap / probe refresh path
4. degraded snapshot fallback only after runtime failure is explicit

This hierarchy matches the existing truth document and should remain the official contract.

## Source Of Truth Policy

### Policy 1

Historical IPs in old notes are not truth.

They may be useful as troubleshooting evidence, but they must never override current runtime state.

### Policy 2

`data/camera_source_of_truth.json` is the primary truth source.

If it exists, all camera-consuming modules should treat it as authoritative.

### Policy 3

`camera_runtime_external/camera_live_config.runtime.json` is an operational fallback, not the long-term canonical truth.

It is allowed as fallback because runtime may need a bootstrap source before truth is persisted.

### Policy 4

Modules must report unreachable RTSP explicitly.

No module should silently pretend camera state is healthy when:

- runtime has no fresh frame
- RTSP is stale
- configuration is syntactically present but operationally dead

## Modules That Must Obey The Truth Source

The following areas must converge on the same effective camera source:

### Backend runtime and registry

- `backend/services/camera_source_registry.py`
- `backend/services/external_camera_bridge_service.py`
- `backend/services/camera_service.py`
- `backend/services/camera_stream_hub.py`
- `backend/services/camera_setup_config_service.py`
- `backend/services/camera_audio_hub.py`

### Existing vision chain

- `backend/services/fall_detection_service.py`
- `backend/services/pose_detection_service.py`
- `backend/services/target_user_fall_service.py`

### Existing API surface

- `backend/api/camera_api.py`
- `backend/api/camera_source_api.py`
- any API exposing target-user or camera health state

### Frontend consumers

- family camera pages
- community camera pages
- pose/fall debug views
- any future Video Bridge read-only status page

### Diagnostics and recovery tooling

- runtime startup scripts
- camera probe scripts
- recovery manual steps
- future truth-source verification scripts

## Current Governance Gaps

The following issues are still unresolved:

- The repository contains a canonical truth document, but not yet a proven end-to-end enforcement path.
- Historical operational notes still mention machine-specific paths and recovery habits that can mislead later operators.
- `camera2` fallback behavior exists, but governance around when `.env` is allowed to lead is not yet explicit enough.
- There is not yet a single verification command or script that proves all camera consumers are using the same truth source.
- Video Bridge is intentionally isolated today, but its future consumers must still inherit the same truth-source policy.

## What Must Be Verified Before Batch 3 Wiring

### Verification A: Truth file existence

Confirm whether `data/camera_source_of_truth.json` exists in the active runtime scenario.

If not, document whether the expected boot path is:

- generated at runtime
- copied from bootstrap probe
- manually written during deployment

### Verification B: Runtime fallback behavior

Confirm `camera_live_config.runtime.json` is only used as fallback and not silently overriding truth when truth already exists.

### Verification C: Consumer alignment

Confirm the following all resolve to the same effective source:

- family camera chain
- community camera chain
- pose detection chain
- fall detection chain
- target-user camera-dependent flows

### Verification D: Failure reporting

Confirm stale/unreachable RTSP is surfaced consistently in:

- backend status
- diagnostics
- frontend-visible health or placeholder state

### Verification E: Historical note quarantine

Confirm old documents are treated as operational history, not active runtime truth.

## Recommended Next Actions

### P0

Write a small truth-source audit script that prints:

- whether `data/camera_source_of_truth.json` exists
- whether runtime config exists
- which source each key camera consumer resolves to
- whether RTSP verification is fresh or stale

This should be read-only and must not change business behavior.

### P1

Add a short operator-facing checklist for recovering truth when:

- truth file is missing
- runtime config is stale
- RTSP verification fails

### P2

Normalize documentation so that:

- `camera-current-source-of-truth.md` remains the policy document
- recovery manuals reference that document instead of inventing parallel truth

### P3

Only after the above are complete, begin considering minimal Batch 3 side-path integration.

## Out Of Scope For This Plan

This plan does not authorize:

- replacing the current fall detection chain
- wiring new fall modules into `backend/main.py`
- attaching Video Bridge to RTSP or YOLO
- connecting experimental fall logic to SOS or production alarm paths
- modifying the mobile app main entry

## Success Criteria

This plan is considered complete when:

- the project has one documented truth hierarchy
- all camera-consuming modules are mapped to that hierarchy
- a read-only verification method exists
- stale/unreachable camera state is surfaced explicitly
- historical notes no longer function as accidental competing truth sources

## Decision Summary

Before Batch 3 system integration, the project should first complete Camera Source Of Truth governance.

The intended order is:

1. decide and document camera truth hierarchy
2. verify all critical modules obey it
3. prove stale-state detection is explicit
4. only then evaluate side-path integration of fall experiments or Video Bridge
