# AI Rollout Prompt

Use the following prompt with an AI coding agent for teammates who start from the original `410health` project and want to reach the optimized state represented by branch `feature/core-optimization-pack`.

---

You are working on the `410health` project.

## Goal

Bring the local project to the same optimization level as branch `feature/core-optimization-pack`.

## Constraints

- Only keep and apply the core optimization changes.
- Do not introduce local-only artifacts into version control.
- Do not commit:
  - `.env`
  - `data/`
  - `logs/`
  - `node_modules/`
  - cache files
- Prefer minimal, high-signal changes.

## Source of truth

Use the branch `feature/core-optimization-pack` as the source of truth for the following files only:

### Backend

- `agent/langgraph_health_agent.py`
- `backend/api/alarm_api.py`
- `backend/dependencies.py`
- `backend/main.py`
- `backend/services/websocket_manager.py`
- `iot/serial_reader.py`

### Frontend

- `frontend/vue-dashboard/src/api/client.ts`
- `frontend/vue-dashboard/src/components/layout/AppShell.vue`
- `frontend/vue-dashboard/src/components/layout/CommunitySosOverlay.vue`
- `frontend/vue-dashboard/src/composables/useAlarmCenter.ts`
- `frontend/vue-dashboard/src/composables/useCareDirectoryDashboard.ts`
- `frontend/vue-dashboard/src/composables/useCommunityAgentWorkbench.ts`
- `frontend/vue-dashboard/src/composables/useCommunityWorkspace.ts`
- `frontend/vue-dashboard/src/utils/markdown.ts`
- `frontend/vue-dashboard/src/views/CommunityPage.vue`

## Required outcomes

### SOS optimization

1. Community-side SOS must be websocket-driven.
2. Family-side SOS must also be websocket-driven.
3. Alarm websocket must be filtered by session / visible device scope.
4. Alarm metadata must include:
   - `elder_name`
   - `elder_id`
   - `apartment`
   - `family_names`
   - `device_name`
   - `device_status`
5. `/api/v1/health/ingest` must return:
   - `sample`
   - `triggered_alarm_ids`
6. Alarm timing metadata must include:
   - `receive_ts`
   - `alarm_emit_ts`
   - `ws_send_ts`
   - `ack_ts`

### Community report optimization

1. `生成社区报告` must use a fixed structured answer path.
2. The frontend must render a report skeleton immediately after submit.
3. Structured attachments must appear before final full text.
4. Text output must stream progressively.

### Runtime cleanup

1. Alarm runtime must be centralized into a single shared source.
2. Remove duplicated community-side alarm websocket state.
3. Preserve real-time SOS popup behavior for:
   - community
   - family
   - elder if enabled

## Verification steps

After applying the changes, run the following:

1. Backend import verification:
   - `conda run -n health python -c "import backend.main; print('backend_import_ok')"`
2. Frontend typecheck:
   - `npm run typecheck`
3. Start backend and frontend.
4. Verify:
   - `http://127.0.0.1:8000/healthz`
   - `http://127.0.0.1:5173`
5. Simulate SOS through `/api/v1/health/ingest` and measure:
   - community-side websocket receipt time
   - family-side websocket receipt time
6. Trigger `生成社区报告` and measure:
   - first attachment time
   - first text chunk time
   - completed answer time

## Acceptance criteria

- SOS reaches community and family in sub-second local conditions.
- Family popup shows real elder/device information, not only fallback placeholders.
- Community report shows skeleton first, then attachments, then streamed fixed-format text.
- No unrelated files are modified.

## Deliverables

At the end, provide:

1. Final changed file list
2. Validation results
3. Any remaining issues
4. Suggested next optimization steps

---

If the local repo already has these files, reconcile them carefully instead of blindly overwriting unrelated team work.
