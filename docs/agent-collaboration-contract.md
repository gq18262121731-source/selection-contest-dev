# Frontend Backend Agent Collaboration Contract

Last updated: 2026-03-21

## Purpose

This document is the shared contract for multiple agents working on the formal registration, relation binding, device ownership, and agent-analysis presentation flow.

Use this file as the single source of truth when:

- frontend agents build or adjust UI flows
- backend agents add or change APIs
- test agents add regression coverage
- docs agents update process or status descriptions

If code and this file disagree, update one of them immediately in the same task.

## Current scope

This contract covers:

- elder registration
- family registration
- elder-family relation binding
- device registration
- device bind, unbind, rebind
- device delete and re-registration
- write permission rules
- family agent analysis flow
- community agent analysis flow
- device time-range health report generation
- agent frontend-backend collaboration boundaries

This contract does not cover:

- alarm workflow state transitions
- health data ingestion internals
- mobile app-specific UI behavior

For BLE gateway HTTP ingest internals, use:

- `docs/ble-gateway-http-contract.md`

## Shared business rules

### Identity and permission

- This contract distinguishes:
  - public self-service registration
  - management writes for relation and device ownership
- Unauthenticated callers may use only the public self-service registration APIs documented in this file.
- Logged-in `family` users can perform the management write operations covered by this contract.
- Logged-in `community` users can perform the management write operations covered by this contract.
- Logged-in `admin` users can perform the management write operations covered by this contract.
- Logged-in `elder` users cannot perform the management write operations covered by this contract.
- Invalid or expired sessions must be treated as unauthenticated.
- Backend is the authority for write permission enforcement.
- Frontend must not infer write permission from agent output, cached UI state, or role labels alone.
- Distinguish clearly between:
  - API capability
  - current UI exposure
- Current backend/API capability allows management writes for `family`, `community`, and `admin`.
- Current frontend product flow may still expose relation-ledger pages only to community-side operators; that does not change the backend permission contract by itself.

### User rules

- `elder`, `family`, and `community` are formal registered user roles.
- Phone numbers must be unique across formal users.
- `family` and `community` may also carry a `login_username`.
- `login_username`, when present, must be unique across formal users that support it.
- Family relation binding must connect exactly one `elder` and one `family`.
- Duplicate elder-family relations are not allowed.
- Relation role validation is strict:
  - `elder_user_id` must resolve to role `elder`
  - `family_user_id` must resolve to role `family`

### Device rules

- Device MAC must match canonical format: `AA:BB:CC:DD:EE:FF`.
- Device MAC must match configured allowed prefixes.
- MAC validation applies consistently to register, bind, unbind, and rebind requests.
- Public self-service registration creates accounts only.
- Device binding is a management write action in the current product/API policy.
- Public self-service registration does not auto-bind devices as part of the registration API itself.
- Logged-in `family`, `community`, and `admin` users may still call the management write device APIs when the UI or another client exposes that capability.
- Device-cardinality policy:
  - one elder may have multiple bound devices
  - but only one bound device per device model / `device_name`
- `CareDirectory.elders[*].device_mac` remains the earliest bound device for backward compatibility.
- `CareDirectory.elders[*].device_macs` is the complete bound-device list and must be treated as authoritative when multi-device support matters.
- A newly registered device without `user_id` starts as:
  - `user_id = null`
  - `status = offline`
  - `bind_status = unbound`
- A newly registered device with valid `user_id` starts as:
  - `user_id = <elder_id>`
  - `status = offline`
  - `bind_status = bound`
- A device can only be bound to an `elder`.
- Registering with an invalid `user_id` must fail without leaving a partial device record behind.
- Register-with-bind must preserve operator audit context in bind history.
- Deleting a device removes the device record and its bind history.
- After deletion, the same MAC must be registered again before it can be bound again.
- Formal gateway ingest rule for unregistered devices:
  - do not auto-register
  - do not write normal health/alarm state
  - quarantine the report for later operator/device-registration follow-up

### Agent collaboration rules

- Agent output is advisory, not an authority override.
- Any hard business restriction must be enforced by backend rules, not only by prompt wording or frontend copy.
- Frontend must not infer write permissions from agent text.
- Frontend must not turn agent output into implicit state changes.
- Agent analysis APIs are read-style advisory APIs and must not mutate registration, relation, device, or alarm state.
- Family agent is scoped to one current elder/device context at a time.
- Community agent is scoped to a multi-device community snapshot at a time.
- If agent output conflicts with explicit backend state, frontend must trust backend state and treat the agent output as stale or advisory.
- If agent output conflicts with explicit alarm, device bind, or relation data already shown on screen, frontend copy must avoid presenting the agent as the source of truth.
- Any new agent role, tool, output field, or display-critical response shape that frontend depends on must be added to this document before or in the same task as the code change.

### Gateway ingest preparation rules

- BLE gateway HTTP ingest should reuse the same parser and downstream ingest path already used by serial/MQTT flows.
- Registered gateway-reported devices should continue through parser -> `ingest_sample(...)`.
- Unregistered gateway-reported devices must be quarantined instead of auto-registered in formal mode.
- Quarantined gateway reports must not:
  - update device online/offline state
  - publish health stream samples
  - trigger alarms
  - emit websocket health/alarm broadcasts
- The detailed receiver transport contract is owned by backend task `BE-013`.
- The device-registration side preparation for that receiver is documented in:
  - `docs/ble-gateway-http-prep.md`

## API contract

Base prefix: `/api/v1`

### Authentication contract

- `POST /auth/login` is the canonical login API for formal and demo-compatible accounts.
- `POST /auth/mock-login` remains available for explicit demo-account login.
- Public self-service registration APIs do not require bearer auth.
- Management write APIs below require `Authorization: Bearer <token>`.
- Management write APIs below are available to logged-in `family`, `community`, and `admin` roles.
- Frontend must explicitly attach the bearer token on every management write call.
- Frontend must not rely on implicit global fetch interception for write authentication.
- Missing bearer token and invalid bearer token are both handled by backend and must surface as authentication failures.

#### Login

- Method: `POST`
- Path: `/auth/login`
- Auth required: no
- Request:

```json
{
  "username": "community_worker_01",
  "password": "123456"
}
```

- Success: `200`
- Response: `LoginResponse`

### Public self-service registration APIs

Current profile-completion support:

- There is no standalone backend `complete profile` or `update profile` API in the current public registration chain.
- The current supported flow is:
  - frontend collects profile fields across one or more steps
  - frontend submits the final complete payload once to the matching `/auth/register/*` endpoint
- So the current `资料完善` step should be treated as a frontend draft/stepper stage, not a separate persisted backend call.
- If later product requirements need resumable or post-registration profile completion, that will require a new backend contract.

#### Register elder (public)

- Method: `POST`
- Path: `/auth/register/elder`
- Auth required: no
- Request:

```json
{
  "name": "Zhang Guilan",
  "phone": "13800138000",
  "password": "123456",
  "age": 78,
  "apartment": "2-301",
  "community_id": "community-haitang"
}
```

- Success: `200`
- Response: `UserRegisterResponse`

#### Register family (public)

- Method: `POST`
- Path: `/auth/register/family`
- Auth required: no
- Request:

```json
{
  "name": "Li Na",
  "phone": "13900139000",
  "password": "123456",
  "relationship": "daughter",
  "community_id": "community-haitang",
  "login_username": "family01"
}
```

- Success: `200`
- Response: `UserRegisterResponse`

#### Register community staff (public)

- Method: `POST`
- Path: `/auth/register/community-staff`
- Auth required: no
- Request:

```json
{
  "name": "Chen Lili",
  "phone": "13700137001",
  "password": "123456",
  "community_id": "community-haitang",
  "login_username": "community_worker_01"
}
```

- Success: `200`
- Response: `UserRegisterResponse`

### Management write APIs

#### Register elder (management)

- Method: `POST`
- Path: `/users/elders/register`
- Auth required: yes
- Request:

```json
{
  "name": "Zhang Guilan",
  "phone": "13800138000",
  "password": "123456",
  "age": 78,
  "apartment": "2-301",
  "community_id": "community-haitang"
}
```

- Success: `200`
- Response: `UserRegisterResponse`

#### Register family (management)

- Method: `POST`
- Path: `/users/families/register`
- Auth required: yes
- Request:

```json
{
  "name": "Li Na",
  "phone": "13900139000",
  "password": "123456",
  "relationship": "daughter",
  "community_id": "community-haitang",
  "login_username": "family01"
}
```

- Success: `200`
- Response: `UserRegisterResponse`

#### Register community staff (management)

- Method: `POST`
- Path: `/users/community-staff/register`
- Auth required: yes
- Request:

```json
{
  "name": "Chen Lili",
  "phone": "13700137001",
  "password": "123456",
  "community_id": "community-haitang",
  "login_username": "community_worker_01"
}
```

- Success: `200`
- Response: `UserRegisterResponse`

#### Bind family to elder

- Method: `POST`
- Path: `/relations/family-bind`
- Auth required: yes
- Request:

```json
{
  "elder_user_id": "elder-id",
  "family_user_id": "family-id",
  "relation_type": "daughter",
  "is_primary": true
}
```

- Success: `200`
- Response: `FamilyRelationRecord`

#### Register device

- Method: `POST`
- Path: `/devices/register`
- Auth required: yes
- Request:

```json
{
  "mac_address": "53:57:08:01:00:E1",
  "device_name": "T10-WATCH",
  "user_id": "optional-elder-id"
}
```

- Success: `200`
- Response: `DeviceRecord`

#### Bind device

- Method: `POST`
- Path: `/devices/bind`
- Auth required: yes
- Request:

```json
{
  "mac_address": "53:57:08:01:00:E1",
  "target_user_id": "elder-id",
  "operator_id": "session-user-id"
}
```

- Success: `200`
- Response: `DeviceBindLogRecord`

#### Unbind device

- Method: `POST`
- Path: `/devices/unbind`
- Auth required: yes
- Request:

```json
{
  "mac_address": "53:57:08:01:00:E1",
  "operator_id": "session-user-id",
  "reason": "maintenance"
}
```

- Success: `200`
- Response: `DeviceBindLogRecord`

#### Rebind device

- Method: `POST`
- Path: `/devices/rebind`
- Auth required: yes
- Request:

```json
{
  "mac_address": "53:57:08:01:00:E1",
  "new_user_id": "elder-id",
  "operator_id": "session-user-id",
  "reason": "transfer"
}
```

- Success: `200`
- Response: `DeviceBindLogRecord`

#### Delete device

- Method: `DELETE`
- Path: `/devices/{mac_address}`
- Auth required: yes
- Success: `200`
- Response: deleted `DeviceRecord`

### Read APIs relevant to the flow

- `GET /devices`
- `GET /devices/{mac_address}`
- `GET /devices/{mac_address}/bind-logs`
- `GET /care/directory`
- `GET /care/directory/family/{family_id}`
- `GET /care/access-profile/me`

Current device read-access policy:

- `GET /devices`
- `GET /devices/{mac_address}`
- `GET /devices/{mac_address}/bind-logs`

remain unauthenticated in the current implementation.

If this policy changes in the future, backend, frontend, tests, and this document must be updated in the same task.

#### Access profile / bound-vs-unbound contract

- Method: `GET`
- Path: `/care/access-profile/me`
- Auth required: yes
- Response shape example for a bound family user:

```json
{
  "user_id": "family-user-id",
  "role": "family",
  "community_id": "community-haitang",
  "family_id": "family-user-id",
  "binding_state": "bound",
  "bound_device_macs": [
    "53:57:08:01:00:E1"
  ],
  "related_elder_ids": [
    "elder-user-id"
  ],
  "capabilities": {
    "basic_advice": true,
    "device_metrics": true,
    "health_evaluation": true,
    "health_report": true
  },
  "basic_advice": "当前账号已绑定到有效设备链路，可查看设备指标、评估结果和健康报告摘要。",
  "device_metrics": [
    {
      "device_mac": "53:57:08:01:00:E1",
      "device_name": "T10-WATCH",
      "device_status": "online",
      "bind_status": "bound"
    }
  ],
  "health_evaluations": [
    {
      "device_mac": "53:57:08:01:00:E1",
      "risk_level": "medium",
      "risk_flags": [
        "temperature_warning"
      ],
      "latest_health_score": 74
    }
  ],
  "health_reports": [
    {
      "device_mac": "53:57:08:01:00:E1",
      "risk_level": "medium",
      "sample_count": 24,
      "latest_health_score": 74,
      "recommendations": [
        "建议 15-30 分钟内复测体温。"
      ],
      "notable_events": [
        "体温最高达到 38.1℃。"
      ]
    }
  ]
}
```

### Agent analysis APIs

These APIs provide explanation and suggestion only. They do not write business state.

Current authentication behavior:

- `POST /chat/analyze` does not require login in the current implementation.
- `POST /chat/analyze/device` does not require login in the current implementation.
- `POST /chat/analyze/community` does not require login in the current implementation.

If this changes in the future, frontend, tests, and this document must be updated in the same task.

#### Analyze single device / family agent

- Method: `POST`
- Path: `/chat/analyze`
- Alias path: `/chat/analyze/device`
- Auth required: no, current behavior
- Request:

```json
{
  "device_mac": "53:57:08:01:00:E1",
  "question": "Please summarize the recent health data and give family-friendly care advice.",
  "role": "family",
  "mode": "local",
  "history_limit": 240,
  "history_minutes": 1440
}
```

- Success: `200`
- Response shape example:

```json
{
  "answer": "Heart rate and oxygen remain mostly stable today. Continue observation and encourage hydration and rest.",
  "references": [
    "elder-care.md"
  ],
  "analysis": {
    "risk_level": "medium",
    "recommendations": [
      "Measure again after 2 hours if discomfort continues.",
      "Keep the elder hydrated and avoid overexertion."
    ],
    "risk_flags": [
      "Short-term heart-rate fluctuation"
    ],
    "notable_events": [
      "Two mild deviations were detected in the last 6 hours."
    ]
  }
}
```

#### Analyze community / community agent

- Method: `POST`
- Path: `/chat/analyze/community`
- Auth required: no, current behavior
- Request:

```json
{
  "question": "Please summarize the current community-wide monitoring picture and suggest handling priorities.",
  "role": "community",
  "mode": "local",
  "history_minutes": 1440,
  "per_device_limit": 240,
  "device_macs": [
    "53:57:08:01:00:E1",
    "53:57:08:01:00:E2"
  ]
}
```

- Success: `200`
- Response shape example:

```json
{
  "answer": "One high-risk device should be reviewed first, while the remaining devices appear stable overall.",
  "references": [
    "community-care.md"
  ],
  "analysis": {
    "device_count": 10,
    "risk_distribution": {
      "high": 1,
      "medium": 3,
      "low": 6
    },
    "priority_devices": [
      {
        "device_mac": "53:57:08:01:00:E1",
        "risk_level": "high",
        "notable_events": [
          "Repeated abnormal readings in the last hour"
        ]
      }
    ],
    "recommendations": [
      "Review the top-risk elder first and confirm the latest reading.",
      "Keep routine observation for the remaining medium-risk group."
    ]
  }
}
```

#### Generate device health report

- Method: `POST`
- Path: `/chat/report/device`
- Auth required: no, current behavior
- Request:

```json
{
  "device_mac": "53:57:08:01:00:E1",
  "start_at": "2026-03-20T00:00:00Z",
  "end_at": "2026-03-21T00:00:00Z",
  "role": "family",
  "mode": "local"
}
```

- Success: `200`
- Response shape example:

```json
{
  "report_type": "device_health_report",
  "device_mac": "53:57:08:01:00:E1",
  "subject_name": "Zhang Guilan",
  "device_name": "T10-WATCH",
  "generated_at": "2026-03-21T08:00:00Z",
  "period": {
    "start_at": "2026-03-20T00:00:00Z",
    "end_at": "2026-03-21T00:00:00Z",
    "duration_minutes": 1440,
    "sample_count": 24
  },
  "summary": "The overall condition in this time window is stable, with short-term fluctuation that still warrants observation.",
  "risk_level": "medium",
  "risk_flags": [
    "Short-term heart-rate fluctuation"
  ],
  "key_findings": [
    "Two mild deviations were detected in the last 6 hours."
  ],
  "recommendations": [
    "Measure again after 2 hours if discomfort continues."
  ],
  "metrics": {
    "heart_rate": {
      "latest": 88,
      "average": 82.3,
      "min": 74,
      "max": 102,
      "trend": "stable"
    }
  },
  "references": [
    "elder-care.md"
  ]
}
```

### Agent response contract

- `answer` is the primary natural-language conclusion for direct display.
- `references` is an ordered list of source or knowledge identifiers suitable for lightweight display.
- `analysis` is structured supplemental data for cards, chips, lists, or ranked items.
- The public agent response shape is:
  - `answer`
  - `analysis`
  - `references`

Frontend agents may display `analysis` fields only when they exist. They must tolerate missing fields.

Current scope-specific analysis fields:

- family or single-device analysis may include:
  - `risk_level`
  - `risk_flags`
  - `recommendations`
  - `notable_events`
- community analysis may include:
  - `device_count`
  - `risk_distribution`
  - `priority_devices`
  - `recommendations`

### Device health report contract

- Frontend report views should call `POST /chat/report/device`.
- Frontend should not overload `/chat/analyze` or `/chat/analyze/device` to simulate a time-range report contract.
- Public device report shape is:
  - `report_type`
  - `device_mac`
  - `subject_name`
  - `device_name`
  - `generated_at`
  - `period`
  - `summary`
  - `risk_level`
  - `risk_flags`
  - `key_findings`
  - `recommendations`
  - `metrics`
  - `references`
- Report output must not expose:
  - prompt text
  - tool traces
  - orchestration metadata
  - internal model fields
- Frontend should be able to render the report without reconstructing hidden business meaning from raw model text.

Backend must not expose prompt text, tool traces, model traces, or orchestration metadata in the public response.

### Agent role contract

- `role=family` is the canonical role for single-device or family-agent calls.
- `role=community` is the canonical role for community summary calls.
- Frontend must not silently swap `family` and `community`.
- If future roles are introduced, they must be added here and to request-model validation in the same change.

## Error contract

### Authentication and permission

- `401 AUTH_REQUIRED`
- `401 INVALID_SESSION`
- `403 FORBIDDEN`

### User registration errors

- `409 PHONE_ALREADY_EXISTS`
- `409 LOGIN_USERNAME_ALREADY_EXISTS`
- `400 INVALID_LOGIN_USERNAME`

### Relation write errors

- `404 USER_NOT_FOUND`
- `400 INVALID_USER_ROLE`
- `409 RELATION_ALREADY_EXISTS`

### Device write errors

- `409 DEVICE_ALREADY_EXISTS`
- `404 DEVICE_NOT_FOUND`
- `404 USER_NOT_FOUND`
- `400 INVALID_BIND_TARGET_ROLE`
- `409 TARGET_USER_ALREADY_HAS_DEVICE_OF_SAME_MODEL`
- `409 DEVICE_ALREADY_BOUND`
- `409 DEVICE_ALREADY_BOUND_TO_TARGET`
- `400 DEVICE_NOT_BOUND`

### Request model validation

These are currently emitted by FastAPI or Pydantic as `422`.

- `INVALID_MAC_ADDRESS`
- `INVALID_MAC_PREFIX`

Frontend agents should not assume these two will be wrapped as `400`.
This validation contract applies to all device write request models, not only device registration.

### Agent analysis request errors

These are also currently emitted by FastAPI or Pydantic as `422` when request shape or field constraints fail.

- invalid `mode`
- invalid `role`
- `question` shorter than minimum length
- `history_limit` out of range
- `history_minutes` out of range
- `per_device_limit` out of range

Frontend agents must treat these as request-construction bugs or operator-input validation gaps, not as business-state failures.

## Canonical frontend behavior

### Relation ledger page

The intended operator flow is:

1. Register elder
2. Register family
3. Bind elder-family relation
4. Register device and optionally bind immediately
5. Bind, unbind, rebind, or delete an existing device

This page is a community or admin operator surface.
This is a statement about current UI exposure, not backend permission capability.
`elder` users must not be treated as having relation-ledger write access.
`family` users may still have backend/API write capability even if this specific page remains community-facing in the current frontend.

### Delete behavior

After deleting a device:

- the device should disappear from device lists
- direct bind attempts must fail with `DEVICE_NOT_FOUND`
- the operator must register the device again before binding
- device bind-history views must be refreshed
- frontend should not keep showing deleted-device history as if it were still current state

Frontend copy should communicate this clearly.

### Family agent behavior

- Family agent UI must be anchored to the currently selected elder or device context.
- Family home or user-facing health views must use `GET /care/access-profile/me` as the source of truth for:
  - `binding_state`
  - whether realtime metrics may be shown
  - whether health evaluation may be shown
  - whether health report summaries may be shown
- Family agent UI may show:
  - natural-language answer
  - risk flags
  - notable events
  - recommendations
  - lightweight references
- Family agent UI must not imply that the agent changed a device, relation, or registration record.
- Family agent UI should present the answer as interpretation plus next-step guidance.
- If no current device is selected, frontend should block submit and show a clear operator hint.
- If `binding_state = unbound`, frontend should show only `basic_advice` and avoid presenting realtime metrics, health evaluations, or health reports as available.

### Community agent behavior

- Community agent UI must be anchored to the current visible community scope or selected device set.
- Community agent UI may show:
  - natural-language shift summary
  - risk distribution
  - priority device list
  - dispatch recommendations
  - lightweight references
- Community agent UI must not imply that priority order is a backend workflow state.
- Community agent UI should present ranked items as recommended handling order, not a persisted queue unless backed by a separate queue API.

### Frontend fallback behavior for agent outputs

- If `answer` exists but `analysis` is empty, frontend should still render the answer.
- If `analysis` exists but some fields are missing, frontend should render only available sections.
- If the request fails, frontend should show a clear failure message and keep existing business-state cards stable.
- Frontend should not clear core health, relation, device, or alarm data just because an agent request fails.

### Multi-agent expansion rule

- Any future multi-agent orchestration must still expose a stable frontend contract.
- Frontend should consume one normalized response shape even if backend internally runs multiple sub-agents.
- Backend may change internal orchestration without frontend changes only if this public contract remains stable.
- If orchestration introduces new display-critical fields, this document, response models, and tests must be updated together.

## Agent ownership guidance

### Backend agent owns

- route definitions
- permission enforcement
- request and response models
- service-layer state transitions
- error-code consistency
- agent request validation
- normalized agent response shape
- ensuring agent APIs remain non-mutating unless explicitly redesigned and documented

### Frontend agent owns

- form flow
- request wiring
- success and error messaging
- explicit bearer-token propagation for all write requests
- operator affordances for delete and re-register
- family agent presentation
- community agent presentation
- graceful handling of partial `analysis` payloads
- ensuring advisory agent output is visually distinct from hard business state

### Test agent owns

- API regression coverage
- permission-matrix coverage
- state-transition coverage
- delete and re-registration coverage
- agent request-validation coverage
- agent response-shape coverage
- regression coverage for frontend assumptions about optional analysis fields

### Docs agent owns

- updating this contract
- updating user-facing flow docs
- updating status summaries when behavior changes
- documenting new agent roles, output fields, authentication changes, and collaboration rules

## Change protocol

When any agent changes this flow, it must update all relevant items together:

1. code
2. regression tests
3. this document

For agent-related changes, `code` includes both backend response construction and frontend rendering assumptions.

When changing agent behavior, also verify all of the following in the same task:

1. request model and response shape
2. frontend rendering logic for missing or new fields
3. regression tests or lightweight repro coverage
4. this document

If a planned behavior is not implemented yet, mark it explicitly as `planned` instead of describing it as current behavior.

## Quick checklist for agents

Before finishing a task in this area, verify:

- management write APIs still require login
- `family`, `community`, and `admin` sessions can perform management writes
- `elder` sessions cannot perform management writes
- public self-service registration routes remain consistent with the documented contract
- invalid registration does not leave partial device state
- MAC validation behavior is unchanged or documented
- delete requires re-registration before rebind
- frontend still sends bearer token for all write calls
- frontend or tests use `GET /care/access-profile/me` instead of guessing bound vs unbound state from partial UI state
- tests or lightweight repro scripts cover the changed path
- agent APIs remain non-mutating
- frontend does not treat agent output as persisted business state
- any new agent field is documented before frontend depends on it
- any authentication change for agent-analysis APIs is documented before rollout
