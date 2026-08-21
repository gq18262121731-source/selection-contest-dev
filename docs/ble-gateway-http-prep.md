# BLE Gateway HTTP Ingest Prep

Last updated: 2026-03-21
Owner: `DR`
Related tasks:

- completed design prep: `DR-006`, `DR-007`
- follow-up implementation: `BE-013`, `BE-014`, `TE-019`, `TE-020`

## Purpose

This document prepares the backend/device-registration side of BLE gateway HTTP ingest before real hardware arrives.

Goal:

- when the gateway hardware arrives, the team should already know:
  - where the HTTP receiver fits
  - how raw payload reaches the parser
  - where accepted data lands
  - what happens to unregistered devices

Non-goal for this round:

- no live hardware test
- no final HTTP contract implementation
- no transport-specific BE implementation beyond design agreement

## Existing ingest chain

Current supported paths already in repo:

- mock push loop
- serial gateway loop
- MQTT gateway loop

Current shared downstream path:

1. gateway adapter obtains raw BLE payload
2. `T10PacketParser.feed(...)` parses it into `HealthSample`
3. backend calls `ingest_sample(sample)`
4. `ingest_sample` merges latest fields, updates device status, publishes stream data, evaluates alarms, and broadcasts websocket updates

Important existing behavior:

- in formal mode, `ingest_sample` requires the device to already exist in the registry
- in mock mode only, missing devices may be auto-created through `ensure_device(...)`

This means BLE gateway HTTP ingest should reuse the same parser and same `ingest_sample(...)` path, not invent a separate health-write path.

## Proposed receiver position

The future HTTP receiver should sit before parser handoff and should behave like the MQTT listener, but over HTTP.

Recommended logical flow:

1. receive HTTP request from BLE gateway
2. decode MessagePack request body
3. normalize top-level gateway metadata
4. iterate `devices[]` entries from the request
5. for each device entry:
   - normalize gateway MAC and device MAC if available
   - extract raw BLE hex payload
   - call parser with the raw payload
6. if parser returns a `HealthSample`, send it through formal device-registration policy checks
7. accepted samples go to `ingest_sample(...)`
8. rejected samples are recorded as gateway rejects/pending-registration evidence
9. return one HTTP response with batch-level summary and per-device outcomes

## Recommended internal handoff objects

To minimize rework, the future HTTP path should conceptually mirror the current MQTT envelope flow.

Suggested internal layers:

- transport layer:
  - HTTP request decoding
  - MessagePack body parsing
- gateway normalization layer:
  - top-level metadata extraction
  - per-device raw payload normalization
- parser layer:
  - `T10PacketParser.feed(...)`
- device-registration policy layer:
  - registered vs unregistered handling
  - accepted vs quarantined routing
- ingest layer:
  - `ingest_sample(...)`

## Data landing plan

### For registered devices

If the device MAC already exists in the formal registry:

- parse payload into `HealthSample`
- pass sample to `ingest_sample(...)`
- data lands in normal runtime destinations:
  - stream service
  - alarm evaluation
  - websocket broadcasts
  - persisted device state updates

No special gateway-only business path should exist for registered devices.

### For unregistered devices

In formal mode, unregistered gateway-reported devices must not be auto-registered.

Required behavior:

- do not create a device automatically
- do not write sample into normal health stream
- do not trigger alarms
- do not broadcast websocket health/alarm events
- do not mutate device online/offline status

Instead, unregistered reports should land in a quarantine/pending-registration sink.

Recommended sink semantics:

- append-only gateway reject/pending-registration record
- keyed by:
  - received time
  - device MAC
  - gateway identity
  - raw payload hash
- includes enough data for later operator review

## Unregistered-device policy

This is the chosen `DR-007` rule for formal HTTP gateway ingest:

- registered device:
  - accept and ingest normally
- unregistered device:
  - reject from health ingest
  - quarantine for registration follow-up
  - keep evidence for operator/device-registration workflows

Rationale:

- avoids silent auto-registration in formal mode
- avoids fake health/alarm state for unknown hardware
- preserves enough evidence to bind/register later
- stays consistent with current formal ingest policy already enforced in backend

## Minimum data required for unregistered-device quarantine

Even before final schema work, these fields should be considered mandatory:

- `received_at`
- `source = "gateway_http"`
- `gateway_message_id` if present
- `gateway_ip` if available from transport
- `gateway_mac` if present in body
- `gateway_uptime_seconds` if present
- `device_mac`
- `raw_ble_payload`
- `raw_payload_hash`
- `parse_status`
- `registration_status = "unregistered"`
- `action_taken = "quarantined"`
- `rssi` if present

Optional but useful:

- parser-derived `packet_type`
- parser-derived `device_uuid`
- parser error message if parsing failed after normalization

## Batch response policy

The future HTTP receiver should support mixed outcomes in one batch.

Recommended response behavior:

- one bad or unregistered device should not fail the whole batch
- return aggregate counts plus per-device result items

Recommended logical outcome categories:

- `accepted`
- `quarantined_unregistered`
- `rejected_invalid_payload`
- `rejected_parse_failed`

Exact field names and transport response shape remain owned by `BE-013`.

## Interaction with existing device rules

Gateway ingest must respect current device-registration rules:

- MAC format/prefix policy
- one elder may have multiple bound devices
- but only one bound device per `device_name`
- delete means device is gone and must be registered again before future ingest is accepted

Practical implication:

- a device deleted from registry must be treated the same as an unregistered device if the gateway keeps reporting it

## Deferred implementation boundaries

### Backend Engineer should implement

- actual HTTP endpoint
- MessagePack decoding
- exact request/response contract
- metadata persistence schema
- operational query surface if needed

### Device Registration Engineer owns

- registered vs unregistered policy
- lifecycle consistency
- how quarantined events relate to later device registration
- how deleted devices are treated when gateway reports continue

### Test Engineer should prepare

- fixture bodies for:
  - registered device accepted
  - unregistered device quarantined
  - malformed payload rejected
  - mixed batch response

## Recommended follow-up tasks

After this prep, the next execution order should be:

1. `BE-013` define the final BLE gateway HTTP contract
2. `BE-014` define metadata retention policy
3. `TE-019` prepare HTTP fixtures and parser-side test plan
4. hardware-dependent integration under `TE-020` only after endpoint exists

## Short rule summary

When BLE gateway HTTP ingest is added:

- registered device reports go through parser -> `ingest_sample(...)`
- unregistered device reports do not auto-register
- unregistered device reports are quarantined with evidence
- mixed batches should return mixed per-device outcomes instead of hard-failing the whole upload
