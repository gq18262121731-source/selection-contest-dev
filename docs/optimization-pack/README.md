# Core Optimization Pack

## Purpose

This branch contains a compressed optimization pack for the `410health` project.

The goal is to let other team members:

1. Start from the original repository state.
2. Pull only the core optimization branch.
3. Reuse the attached AI prompt to finish rollout, validation, and local deployment quickly.

This branch intentionally excludes local-only artifacts such as:

- `.env`
- databases under `data/`
- logs
- `node_modules`
- Python cache files

## What is included

### 1. SOS real-time alarm optimization

- Community and family sides both receive SOS through real-time websocket delivery.
- Alarm delivery is filtered by session/device visibility.
- Alarm metadata is enriched with elder / device / family context.
- The backend now returns `triggered_alarm_ids` from `/api/v1/health/ingest`.
- Alarm timing fields are attached for observability:
  - `receive_ts`
  - `alarm_emit_ts`
  - `ws_send_ts`
  - `ack_ts`

### 2. Community report optimization

- Community report uses a fixed structured output path.
- Structured attachments are emitted first.
- Answer text is streamed.
- A report skeleton is rendered immediately on the frontend.

### 3. Frontend runtime cleanup

- Alarm runtime is centralized into a single global source.
- Community-side duplicated alarm websocket state is removed.
- Family-side alarm state reuses the same alarm runtime.

## Core modified files

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

## Expected result after applying this branch

### SOS

- Community-side SOS popup latency should be sub-second in normal local-network conditions.
- Family-side SOS popup should also arrive through websocket rather than page polling.
- Popup content should include:
  - elder name
  - device name
  - trigger type
  - device MAC
  - trigger time

### Community report

- Clicking `生成社区报告` should immediately show a report skeleton.
- Structured report attachments should appear before the final full text.
- The answer should stream progressively instead of appearing all at once.

## Suggested rollout method for teammates

### Option A: teammates use Git directly

1. `git fetch origin`
2. `git checkout feature/core-optimization-pack`
3. Ask an AI coding agent to use `docs/optimization-pack/AI_PROMPT.md`

### Option B: teammates already have an unpacked local copy without Git history

1. Download this branch as a zip.
2. Copy only the files listed above into their local project.
3. Ask an AI coding agent to use `docs/optimization-pack/AI_PROMPT.md`

## Validation checklist

- Backend imports successfully.
- Frontend typecheck passes.
- `http://127.0.0.1:8000/healthz` returns OK.
- `http://127.0.0.1:5173` opens successfully.
- Community and family accounts both receive SOS popup.
- Community report shows skeleton first, then structured content, then streamed text.
