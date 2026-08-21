# BLE Gateway HTTP Contract

Last updated: 2026-03-21

## Scope

This document defines the backend contract for a future BLE gateway HTTP receiver.

It exists outside `docs/agent-collaboration-contract.md` because that contract explicitly does not cover health-ingestion internals.

## Decision Summary

- Transport: HTTP
- Body encoding: MessagePack, not JSON
- Preferred content type: `application/msgpack`
- Compatible content type: `application/x-msgpack`
- Receiver path: `POST /api/v1/gateway/ble-http-ingest`
- Parser handoff basis: gateway frame bytes from `devices[]`

## Request Contract

### Headers

- `Content-Type: application/msgpack`
- `X-Gateway-Mac: <gateway-mac>` is optional convenience metadata
- `X-Message-Id: <message-id>` is optional convenience metadata

### Top-level MessagePack object

The request body is a MessagePack map with this shape:

```text
{
  "protocol_version": 1,
  "message_id": "uuid-or-sequence-string",
  "gateway_mac": "AA:BB:CC:DD:EE:FF",
  "gateway_ip": "optional-ip-string",
  "uploaded_at": "2026-03-21T10:00:00Z",
  "uptime_ms": 1234567,
  "devices": [ ... ]
}
```

### Required top-level fields

- `protocol_version`
- `message_id`
- `gateway_mac`
- `devices`

### Optional top-level fields

- `gateway_ip`
- `uploaded_at`
- `uptime_ms`

## `devices[]` Contract

Each item in `devices[]` is a MessagePack map.

### Required field

- `frame_bytes`

`frame_bytes` must be a MessagePack `bin` value, not a hex string and not base64 text.

### Optional mirror fields

- `device_mac`
- `data_type`
- `rssi`
- `ble_payload_bytes`

These optional fields may be included by the gateway for debugging or producer-side visibility, but the backend treats `frame_bytes` as the source of truth.

## `frame_bytes` Semantics

`frame_bytes` is the full gateway frame for one observed BLE device record.

Byte layout:

1. byte 0: `data_type`
2. bytes 1-6: BLE MAC
3. byte 7: RSSI
4. bytes 8..n: raw BLE payload

In compact notation:

```text
frame_bytes = data_type(1 byte) + ble_mac(6 bytes) + rssi(1 byte) + ble_payload(n bytes)
```

The backend derives:

- `data_type`
- `device_mac`
- `rssi`
- `ble_payload_bytes`

from `frame_bytes`, and then passes:

- `device_mac`
- `ble_payload_bytes`

into the existing T10 parser path.

## BLE Payload Interpretation

`ble_payload_bytes` is the raw BLE payload segment after stripping the 8-byte gateway prefix.

It is interpreted using the existing parser rules:

- broadcast packet
- response A packet
- response B packet
- merged response AB behavior

The parser contract is therefore:

```text
gateway frame -> strip gateway prefix -> device_mac + ble_payload_bytes -> T10PacketParser.feed(...)
```

## Response Contract

### Success

- HTTP status: `202 Accepted`

Response body:

```json
{
  "accepted": true,
  "message_id": "uuid-or-sequence-string",
  "received_device_count": 4,
  "parsed_sample_count": 3,
  "ignored_device_count": 1
}
```

### Client errors

- `400` unsupported or malformed MessagePack payload
- `400` missing required top-level fields
- `400` empty `devices`
- `422` invalid `gateway_mac` format when present

### Operational behavior

- The endpoint is ingest-oriented and should not block on frontend-style rendering needs.
- It may accept a request even if some `devices[]` items are ignored.
- Per-device parse failures should be counted and logged, not necessarily fail the whole request.

## Metadata Retention Policy

### Request-level metadata retained

- `received_at` on the backend
- request source IP
- `gateway_mac`
- `message_id`
- `uploaded_at` if provided
- `uptime_ms` if provided
- `device_count`

### Per-device metadata retained in ingest/audit logs

- derived `device_mac`
- derived `data_type`
- derived `rssi`
- parse outcome

### Metadata not promoted into public health APIs by default

The following should not automatically appear in:

- `/health/realtime/*`
- `/health/trend/*`
- `/care/access-profile/me`
- `/chat/report/device`

unless a later contract explicitly adds them:

- source IP
- `gateway_mac`
- `message_id`
- `uptime_ms`
- raw `frame_bytes`

### Current storage policy

- retain gateway/request metadata in receiver-side audit logs or ingest tables
- keep `HealthSample` focused on health and parser-derived fields
- keep report and dashboard contracts free of transport-layer gateway metadata unless explicitly requested later

## Report API Decision

Frontend should use the existing dedicated report endpoint:

- `POST /api/v1/chat/report/device`

Frontend should not overload:

- `POST /api/v1/chat/analyze`
- `POST /api/v1/chat/analyze/device`

for time-range report generation.

Reason:

- analyze endpoints are advisory summary endpoints
- report generation has a richer, stable structured contract
- keeping report generation separate reduces frontend branching and contract ambiguity
