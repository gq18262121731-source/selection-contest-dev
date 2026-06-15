# Camera Source Audit Report

## 1. Executive Summary

This audit reviewed camera source governance across code, runtime configuration, and interface exposure in the current repository state.

Overall conclusion:

- Camera Source Of Truth is documented, but not yet fully established in implementation.
- Family / Community / Pose / Fall are not yet provably unified on one effective source.
- The requested Vision Service requirement file `interface_requirements_2026-06-15.md` was not found in the scanned workspace, so interface compliance could only be partially assessed from substitute integration documents.
- Batch 3 side-path integration should remain `No-Go` until truth hierarchy, consumer alignment, and runtime verification are made explicit.

Short answers:

1. Is Camera Source Of Truth established?
   No. The intended hierarchy exists in docs, but the primary truth file is missing and active code paths still rely on `.env`, runtime config, and registry state.
2. Are Family / Community / Pose / Fall unified?
   Not yet. Camera runtime and backend selection logic are partially unified, but frontend and algorithm consumers are not all wired through one proven path.
3. Does Vision Service interface design follow Truth Hierarchy?
   Partially in design, not proven in current runtime implementation.
4. Is Batch 3 side-path integration allowed?
   Not yet.
5. What must be completed before Batch 3?
   Define truth file lifecycle, align registry/env/runtime precedence, add a read-only audit command, and prove runtime-to-status-to-frontend consistency with a live startup validation.

Audit scope notes:

- This was a read-only audit.
- No code, config, RTSP, frontend, mobile, `main.py`, `dependencies.py`, or `config.py` changes were made.
- Live read-only HTTP probes to `http://127.0.0.1:8000` and `http://127.0.0.1:8090` timed out during this audit, so runtime conclusions are based on repository state plus existing logs and docs.

## 2. Source Inventory

| Source | Location | Type | Used By | Runtime Relevant | Deprecated |
| --- | --- | --- | --- | --- | --- |
| Canonical truth file | `data/camera_source_of_truth.json` | Intended canonical truth | `external_camera_bridge_service.py`, policy docs | Yes | No |
| Runtime external config | `camera_runtime_external/camera_live_config.runtime.json` | Active runtime fallback | `camera_source_registry.py`, `external_camera_bridge_service.py`, runtime scripts | Yes | No |
| Runtime bootstrap config | `camera_runtime_external/camera_live_config.json` | Runtime bootstrap/default config | `camera_source_registry.py`, `external_camera_bridge_service.py`, runtime scripts | Yes | No |
| Registry state | `data/camera_registry.json` | Active selection and override state | `camera_source_registry.py`, `camera_source_api.py`, `camera_setup_config_service.py` | Yes | No |
| Environment camera settings | `.env` and `Settings` camera fields | Legacy and operator-editable source | `camera_source_registry.py`, `camera_setup_config_service.py`, `camera_service.py` | Yes | No |
| Runtime truth overrides | `camera_truth_overrides` inside `camera_registry.json` | Bridge override layer | `camera_source_registry.py`, `camera_setup_config_service.py` | Yes | No |
| Runtime health API | `camera_runtime_external/camera_runtime/web.py` | Runtime-exposed status source | `camera_service.py`, `external_camera_bridge_service.py` | Yes | No |
| Bridge truth/config API | `backend/api/target_user_api.py` `/external-camera/*` | Backend-exposed camera truth/config view | External camera bridge consumers | Yes | No |
| Camera source registry API | `backend/api/camera_source_api.py` | Backend-exposed source inventory and selection | Frontend or future operators | Yes | No |
| Legacy camera API | `backend/api/camera_api.py` | Active backend camera status and streams | Frontend camera consumers | Yes | No |
| Historical docs and recovery notes | `docs/system_startup_and_recovery_manual.md`, `docs/camera-source-layer.md`, `camera_runtime_external/*.md` | Operational reference | Humans, scripts | Indirect | Yes |
| Video Bridge integration docs | `docs/main-system-video-bridge-integration.md`, `docs/remote-video-bridge-integration-guide-10.12.14.9.md` | Interface design reference | Video Bridge planning | Indirect | No |

Observed repository state:

- `data/camera_source_of_truth.json`: missing
- `data/camera_registry.json`: missing
- `camera_runtime_external/camera_live_config.runtime.json`: present
- `camera_runtime_external/camera_live_config.json`: present
- Current runtime config points to host `192.168.8.252`, RTSP port `10554`, transport `tcp`, stream `av0_1`, viewer `127.0.0.1:8090`

## 3. Truth Hierarchy Verification

Expected hierarchy from [camera-current-source-of-truth.md](/d:/health_original/health1/docs/camera-current-source-of-truth.md):

1. `data/camera_source_of_truth.json`
2. `camera_runtime_external/camera_live_config.runtime.json`
3. runtime bootstrap / probe
4. snapshot fallback after runtime failure is explicit

Observed implementation behavior:

- `external_camera_bridge_service.py` knows about the intended truth file and merges it with runtime config.
- `camera_source_registry.py` does not read `data/camera_source_of_truth.json`.
- `camera_source_registry.py` builds active sources from:
  - `data/camera_registry.json`
  - runtime config files
  - `.env` camera and camera2 settings
- `camera_setup_config_service.py` persists operator changes back into `.env` and also writes registry-backed `camera_truth_overrides`.
- `camera_source_registry.active_source()` prefers `camera2`, then `camera1`, then local when no explicit registry selection exists.

Assessment:

- The documented hierarchy is not the active global hierarchy.
- The implemented hierarchy is currently closer to:

```text
registry active selection
-> camera_truth_overrides in registry
-> .env camera2 / camera1 settings
-> camera_runtime_external/camera_live_config.runtime.json
-> camera_runtime_external/camera_live_config.json
-> local fallback
```

- This means the project still has competing authority layers.
- The primary truth file is missing, so the documented top layer is not in force.

Hierarchy verdict:

- `Fail` for full conformance to the intended truth hierarchy
- `Partial` for bridge-local truth handling

## 4. Consumer Mapping Matrix

| Consumer | Camera Source | RTSP Source | Camera ID Source | Alignment Status |
| --- | --- | --- | --- | --- |
| `camera_source_registry` | registry + `.env` + runtime config | runtime config or `.env` | registry active selection, fallback `camera2/camera1/local` | Misaligned with documented primary truth file |
| `camera_service` | `Settings` provided by registry or caller | `Settings.camera_*` or runtime HTTP health path | caller-provided settings | Partially aligned, depends on upstream settings integrity |
| `camera_stream_hub` | `CameraService(settings)` | `CameraService.stream_rtsp_urls()` or runtime MJPEG path | inherited from injected settings | Partially aligned |
| `camera_audio_hub` | `CameraService(settings)` | `CameraService.build_audio_rtsp_url()` and fallbacks | inherited from injected settings | Partially aligned |
| `camera_setup_config_service` | `.env` plus registry truth overrides | `.env` and registry override sync | not source-of-truth driven | Misaligned, can create parallel truth |
| `external_camera_bridge_service` | truth file merged with runtime config | runtime config and probe candidates | defaults to `camera2` | Locally aligned, globally bypassed by registry stack |
| `target_user_fall_service` | no direct camera source lookup | consumes uploaded image bytes only | external caller/session | Not a source owner |
| `camera_api` | active source from registry | `CameraService(get_camera_source_settings("active"))` | registry active camera | Aligned to registry, not to canonical truth file |
| `camera_source_api` | registry per camera | per-camera `CameraService` settings | registry camera IDs | Aligned to registry, not to canonical truth file |
| `target_user_api` external camera endpoints | bridge truth + runtime config | bridge runtime config and probe path | bridge `camera2` default | Split between bridge-local truth and registry-driven rest of system |
| Family frontend | no direct camera-source endpoint reference found in current scanned frontend pages | not proven | not proven | Unknown / not provably unified |
| Community frontend | no direct camera-source endpoint reference found in current scanned frontend pages | not proven | not proven | Unknown / not provably unified |
| Pose debug frontend | legacy component named in docs but not active in scanned current frontend route/view usage | not proven | not proven | Unknown |
| Fall debug frontend | no current direct camera-source consumer identified in scanned frontend views | not proven | not proven | Unknown |
| Video Bridge placeholder | `video_bridge` status payload, default snapshot fallback `/api/v1/camera/processed-snapshot` | indirect | `camera_id` from bridge status/runtime config | Isolated placeholder, not a unified truth consumer |
| Vision Service `/status` design | intended external status source | external runtime/vision service | `camera_id` query or payload | Design present, repo runtime mismatch remains |
| Vision Service `/stream/source` design | intended external source endpoint | external runtime/vision service | `camera_id` | Design present, current local runtime does not expose it |
| Vision Service `/integration/results/{camera_id}/latest` design | intended external result endpoint | n/a | `camera_id` path | Design present, not implemented by local camera runtime |

Matrix conclusion:

- Backend camera APIs are internally converging around `camera_source_registry`.
- The registry stack itself is not yet converged around the documented canonical truth file.
- Frontend unification for Family / Community / Pose / Fall cannot yet be proven from current wiring.

## 5. Runtime Consistency Assessment

Requested runtime assessment target:

```text
Truth Source
-> Runtime Config
-> Status API
-> Frontend
```

### 5.1 Runtime config layer

Confirmed:

- Runtime config files exist and are populated.
- Runtime config is clearly active in both `camera_source_registry.py` and `external_camera_bridge_service.py`.
- Runtime scripts also treat `camera_live_config.json` and `camera_live_config.runtime.json` as operational inputs.

### 5.2 Runtime status layer

Current local runtime implementation in `camera_runtime_external/camera_runtime/web.py` exposes:

- `GET /health`
- `GET /api/v1/camera/health`
- `GET /snapshot.jpg`
- `GET /api/v1/camera/snapshot`
- `GET /stream.mjpg`
- `GET /api/v1/camera/stream.mjpg`
- `POST /api/v1/camera/stream/switch`
- `POST /api/v1/camera/stop`

Health payload includes:

- `running`
- `source`
- `stream`
- `rtsp_port`
- `has_frame`
- `latest_frame_at`
- `frame_age_seconds`
- `fresh_frame`
- `stale_frame`
- `last_error`
- `reconnect_count`
- `consecutive_failures`
- `current_stream`

This is useful, but it is not the same contract as the requested Vision Service interface set:

- `GET /status`
- `GET /stream/source`
- `GET /healthz`
- `POST /stream/probe`
- `GET /integration/results/{camera_id}/latest`

### 5.3 Backend normalization layer

`camera_service.runtime_health()` already anticipates two possible runtime shapes:

- current runtime health: `/api/v1/camera/health`
- future vision service status: `/status`

It also normalizes a `/status` payload into fields such as:

- `stream_state`
- `frame_age_ms`
- `capture_fps`

This is a good compatibility layer, but it does not mean the local runtime already provides the required design contract.

### 5.4 API exposure layer

Current backend exposure is split:

- `camera_api.py` exposes `/camera/status`, `/camera/stream-status`, `/camera/health`, `/camera/snapshot`
- `camera_source_api.py` exposes per-camera source detail, status, stream, audio, PTZ
- `target_user_api.py` exposes `/external-camera/config`, `/external-camera/health`, `/external-camera/probe`, `/external-camera/bootstrap`

There is no single current API that proves all of the following are derived from the same truth source:

- active camera selection
- RTSP host and path
- runtime freshness
- frontend-visible camera identity

### 5.5 Frontend layer

Observed current frontend state:

- `VideoBridgePage.vue` is a placeholder that reads video bridge status and can fall back to `/api/v1/camera/processed-snapshot`.
- No current direct Family / Community page consumption of camera-source APIs was identified in the scanned active views.
- This means frontend-wide camera truth convergence is not yet demonstrable.

Runtime chain verdict:

- `Truth Source -> Runtime Config`: partial
- `Runtime Config -> Status API`: partial
- `Status API -> Frontend`: not fully proven
- End-to-end consistency: not established

## 6. Conflict Analysis

### High Risk

- Missing primary truth file while docs declare it authoritative
  - `data/camera_source_of_truth.json` is absent
- Competing authority layers
  - `.env`
  - runtime config files
  - registry file
  - registry `camera_truth_overrides`
  - bridge-local truth merge
- `camera_setup_config_service.py` can persist operator edits into `.env` and registry overrides, increasing drift risk
- Current runtime implementation does not match the requested Vision Service endpoint set
- Live localhost health probes timed out during the audit, so runtime state could not be validated online

### Medium Risk

- Historical docs still contain machine-specific paths and historical IP usage habits
- `camera_source_registry.active_source()` contains implicit fallback preference logic that may override operator expectations
- Family / Community / Pose / Fall frontend consumers are not mapped to one observable camera-source contract
- `camera_registry.json` is also missing, so active selection persistence is not currently materialized in repo state

### Low Risk

- Runtime health payload already surfaces stale/fresh frame status explicitly
- `camera_service` already contains a normalization layer for a future `/status`-style vision service
- Video Bridge remains isolated, which reduces blast radius for now

## 7. Failure Handling Assessment

Desired behavior:

- RTSP failure should surface as `stale`, `disconnected`, or `reconnecting`
- No layer should silently pretend camera state is healthy

Observed design quality:

- `camera_runtime_external/camera_runtime/web.py` explicitly exposes:
  - `fresh_frame`
  - `stale_frame`
  - `last_error`
  - `reconnect_count`
  - `consecutive_failures`
- `external_camera_bridge_service.health()` classifies unavailable or stale states into bridge-level status
- `camera_service.check_status()` can use runtime health when runtime-managed source is active
- `camera_api.py` exposes `runtime_health` via `/camera/health`
- Existing runtime logs show repeated RTSP unreachable warnings for `192.168.8.252:10554`, which indicates failure is at least logged explicitly

Observed gaps:

- No proof that Family / Community frontend surfaces these failure states consistently
- No single audited endpoint shows normalized `cameras[].stream_state`, `cameras[].frame_age_ms`, and `diagnostics.capture_stale` from the current local runtime
- The requested official interface file was not found, so failure-field compliance could not be fully checked against the named baseline

Failure path verdict:

- Runtime layer: strong
- Backend layer: moderate
- Frontend layer: unproven
- End-to-end failure transparency: incomplete

## 8. Risk Ranking

| Rank | Issue | Severity |
| --- | --- | --- |
| R1 | Canonical truth file is documented but absent | High |
| R2 | Registry, `.env`, runtime config, and bridge-local truth all compete | High |
| R3 | Current runtime API shape differs from requested Vision Service contract | High |
| R4 | Family / Community / Pose / Fall are not all provably consuming one source contract | High |
| R5 | Official `interface_requirements_2026-06-15.md` file not found in scanned workspace | Medium |
| R6 | Active registry file also absent, limiting persistence certainty | Medium |
| R7 | Historical docs still contain path and IP baggage that can mislead operators | Medium |
| R8 | Failure semantics exist but are not proven end-to-end in UI | Medium |

## 9. Recommended Actions

Recommended actions before any Batch 3 side-path integration:

1. Materialize the truth-file lifecycle.
   Decide exactly when `data/camera_source_of_truth.json` is created, who writes it, and which modules must read it first.
2. Freeze and document precedence.
   Explicitly define whether `.env`, registry overrides, runtime config, and truth file are authoritative, fallback, or deprecated.
3. Add a read-only truth audit command.
   It should print:
   - truth file presence
   - runtime config presence
   - registry presence
   - active camera source
   - effective RTSP host, port, path
   - runtime freshness
   - mismatch warnings
4. Obtain or restore the official interface baseline.
   Add `interface_requirements_2026-06-15.md` to the repository or link it from an authoritative location.
5. Run a live startup validation.
   Verify backend and runtime are online, then capture:
   - `/camera/health`
   - `/camera-sources/active`
   - runtime health endpoint
   - any future `/status` or `/stream/source` vision endpoints
6. Map frontend camera consumers explicitly.
   Identify whether Family, Community, Pose Debug, and Fall Debug use:
   - `/camera/*`
   - `/camera-sources/*`
   - Video Bridge data
   - some unrelated local state
7. Quarantine historical notes.
   Keep them as operational history only, not active truth candidates.

## 10. Go / No-Go Recommendation

Recommendation: `No-Go` for Batch 3 side-path integration at the current audit point.

Reasons:

- The documented primary truth source is not present.
- Active backend camera selection still depends on multiple competing layers.
- Full Family / Community / Pose / Fall convergence is not yet proven.
- Current local runtime API does not yet match the requested Vision Service contract.
- Live localhost runtime and backend endpoints were unavailable during this audit, so startup-level consistency was not demonstrated.

Go conditions for reconsideration:

- `data/camera_source_of_truth.json` exists or its lifecycle is explicitly defined
- registry/env/runtime precedence is locked and documented
- all critical camera consumers are mapped to the same effective source
- runtime freshness and stale-state semantics are observable through one stable status path
- the official interface requirements document is available and matched against implementation
- a live read-only validation run proves:
  - backend starts
  - runtime starts
  - camera status is coherent
  - failure states are explicit

Final recommendation:

- Do not enter Batch 3 side-path integration yet.
- Complete Camera Source Of Truth governance first.
- Treat the current state as a stable decision checkpoint, not an integration-ready state.
