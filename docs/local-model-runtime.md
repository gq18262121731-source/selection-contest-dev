# Local Model Runtime

Last updated: 2026-03-21

## Supported runtime

The supported agent runtime is offline-only and LAN-friendly.

- No cloud LLM is required.
- No cloud embedding or rerank API is required.
- Retrieval uses deterministic local keyword matching against `docs/knowledge-base/`.
- Local inference runs through Ollama.
- The local knowledge base supports both short advice and structured report generation.

## Approved local models

Only these local models are approved in the supported runtime:

- `qwen3:1.7b`
- `deepseek-r1:1.5b`

## Routing policy

Configured in `backend/config.py` and enforced in `agent/langgraph_health_agent.py`.

- Default routing mode: `task_router`
- Default local model: `qwen3:1.7b`
- Reasoning-oriented local model: `deepseek-r1:1.5b`
- Dedicated report routing mode: `fixed`
- Dedicated report model: `deepseek-r1:1.5b`

### Current behavior

- Device/family-style analysis defaults to `qwen3:1.7b`
- Community summary, prioritization, and explanation tasks route to `deepseek-r1:1.5b`
- Formal health-report generation uses the dedicated report route instead of the ordinary dialogue route
- Dialogue output limits apply only to the ordinary dialogue path
- Formal report generation does not reuse the dialogue output cap
- Ordinary dialogue now uses an internal health-event layer before final role-specific wording
- The internal dialogue path now separates:
  - health-model evidence layer
  - internal health-event layer
  - action-label layer
  - role-expression layer for elder / family / community
- If routing mode is set to `single`, all local tasks use `local_default_model`

## Verification points

- `tests/test_offline_model_runtime.py`
- `tests/test_prompt_kb_integrity.py`
- `tests/test_chat_api.py`

These tests verify:

- offline-only capability reporting
- approved model coverage
- local routing behavior
- prompt readability
- KB readability and retrieval sanity
- report-oriented prompt and knowledge-base support
- dedicated report-model routing
- health-model-evidence-driven report generation
- internal health-event-driven multi-role dialogue
