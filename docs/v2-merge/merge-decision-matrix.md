# V2 Fusion Decision Matrix

## Goal

Merge the current branch, which keeps the mobile-oriented application shell and runtime fixes, with `D:\Program\410health_new\health1`, which adds the upgraded fall-detection model pipeline and showcase scripts.

## Decisions

| Area | V2 source of truth | Decision |
| --- | --- | --- |
| Web dashboard and mobile layout | Current branch | Keep the current Vue application shell, routing, navigation, and mobile optimizations. Add only one new model showcase page. |
| Backend API surface | Current branch plus B fall APIs | Preserve current device, health, camera, target-user, and local-camera endpoints. Add B's external-camera config/probe/discover/refresh and speed-mode fall-detect options. |
| Target-person fall detection | B branch | Use B's target-person fall service, pose sequence service, event state machine, and optional ReID service. Keep ReID disabled by default for stable offline startup. |
| Single-frame fall testing | B branch with local paths | Use B's upgraded frame service, but resolve all model roots from the current project's `.env`. |
| Camera bridge | B branch with local safeguards | Use B's bridge implementation and route blocking camera/model calls through worker threads in FastAPI. |
| Model and training scripts | B branch | Import B's evaluation, import, export, training, tuning, and showcase scripts. Replace hardcoded B-machine paths with current-project paths. |
| Runtime startup | Current branch | Keep fall/pose workers disabled unless explicitly enabled. Add optional target-user vision warmup, disabled by default. |
| Documentation | Combined | Keep historical model reports and add this merge record plus generated diff files under `docs/v2-merge/`. |

## Acceptance Criteria

- Backend imports, tests, and FastAPI startup succeed with default `.env`.
- Frontend type check/build checks pass and dashboard can open.
- `/docs`, `/healthz`, detection model status, target-user status, and external-camera health endpoints respond.
- New model showcase page is reachable from navigation and does not break existing dashboard pages.
- Fall/model scripts expose usable `--help` commands and write outputs under the current project by default.
- Hardware-dependent features fail gracefully when no camera or API key is configured.
