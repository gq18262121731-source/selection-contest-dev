# Care Companion Agent V1.0 Contract

## 1. Purpose

The Care Companion Agent is an independent, elder-facing embodied-companion
decision service. It is separate from:

- the health-analysis agent used by family and community clients;
- the fall-alarm and robot emergency workflow;
- the Go2 navigation and execution gateway.

V1.0 demonstrates this closed decision loop:

```text
elder request
  -> fixed intent classification
  -> real read-only health context
  -> Mock weather and location
  -> allow-listed action plan
  -> deterministic safety decision
  -> natural-language reply
```

V1.0 never invokes the Go2 gateway and never executes an external action.

## 2. API

### Address

```http
POST /api/v1/robot-agent/dialogue
Content-Type: application/json
```

### Request fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `elder_id` | string | yes | Elder whose bound health context may be read. |
| `text` | string | yes | Transcribed or typed elder utterance. |
| `device_mac` | string/null | no | Optional bound-device selector. A device bound to another elder is rejected. |
| `location_hint` | string/null | no | Demo location label. The provider remains Mock in V1.0. |
| `demo_weather` | enum | no | `sunny`, `rain`, `windy`, `hot`, or `cold`; used by Mock and QWeather failure fallback. |
| `use_llm` | boolean | no | Use Qwen intent classification when configured; default `true`. Rules are the fallback. |

Example:

```json
{
  "elder_id": "elder-001",
  "device_mac": "53:57:08:00:00:01",
  "text": "小狗，我们出去走走吧",
  "location_hint": "住宅附近",
  "demo_weather": "sunny",
  "use_llm": true
}
```

### Response fields

| Field | Description |
|---|---|
| `agent` | Always `care_companion`. |
| `version` | Contract version, currently `1.0`. |
| `decision` | Fixed intent, confidence, and classifier source. |
| `reply` | Elder-facing Simplified Chinese response. |
| `context` | Health, environment, location, and non-motion robot context used by the decision. |
| `action_plan` | Allow-listed plan. `enabled` is always `false` in V1.0. |
| `safety` | Deterministic `allowed` or `blocked` result and stable code. |

Example:

```json
{
  "agent": "care_companion",
  "version": "1.0",
  "decision": {
    "intent": "walk_request",
    "confidence": 0.94,
    "source": "rule",
    "model": null
  },
  "reply": "今天天气和当前状态适合适量活动，我已经准备好陪伴计划。不过真实运动模式还没有开启，目前只展示计划，建议您慢慢走、不要太累。",
  "context": {
    "elder_id": "elder-001",
    "elder_name": "李奶奶",
    "generated_at": "2026-07-29T09:00:00+00:00",
    "health": {
      "risk_level": "low",
      "health_score": 86,
      "recent_fall": false,
      "sos": false,
      "today_steps": 2500,
      "data_freshness": "fresh",
      "device_mac": "53:57:08:00:00:01"
    },
    "environment": {
      "weather": "sunny",
      "temperature": 22,
      "humidity": 50,
      "wind_level": 2,
      "description": "晴",
      "suggestion": "天气晴朗，温度舒适，适合适量活动。",
      "provider": "mock",
      "source": "mock"
    },
    "location": {
      "city": "南京",
      "area": "住宅附近",
      "address": "住宅附近",
      "provider": "mock"
    },
    "robot": {
      "online": true,
      "motion_enabled": false,
      "provider": "mock"
    }
  },
  "action_plan": {
    "type": "prepare_follow",
    "parameters": {
      "duration_seconds": 1800,
      "distance_limit_meters": 5
    },
    "enabled": false,
    "execution": "not_executed"
  },
  "safety": {
    "status": "blocked",
    "code": "MOTION_DISABLED",
    "reason": "真实运动模式未开启，当前只展示动作计划。"
  }
}
```

## 3. Fixed intent contract

- `chat`
- `walk_request`
- `weather_query`
- `health_check`
- `companionship`
- `emergency`

The LLM cannot introduce a new intent. Invalid or unavailable LLM output
degrades to deterministic rules. Emergency keywords are handled by rules before
the LLM call.

## 4. Fixed action-plan contract

- `none`
- `suggest_walk`
- `prepare_follow`
- `call_family`
- `request_help`

The action planner cannot return SDK methods, arbitrary commands, routes, or
gateway payloads. In V1.0:

- `enabled` is always `false`;
- `execution` is always `not_executed`;
- no Go2 gateway method is referenced by the companion service.

## 5. Health context

Health context is read from the current care directory, bound device, latest
runtime health sample, and current alarm service. It does not call the health
agent and does not copy health-agent prompts.

The context reports:

- current rule-compatible risk level;
- latest health score and steps when present;
- whether an SOS is active;
- whether a fall alarm occurred in the last 24 hours;
- whether the latest sample is fresh, stale, or missing.

Missing or stale data blocks a `prepare_follow` plan.

## 6. Weather providers

`WEATHER_PROVIDER=mock` remains the default and requires no external service.

To use QWeather Weather Now:

```env
WEATHER_PROVIDER=qweather
QWEATHER_API_KEY=replace-with-api-key
QWEATHER_API_HOST=replace-with-account-host.qweatherapi.com
QWEATHER_LOCATION=118.80,32.06
QWEATHER_TIMEOUT_SECONDS=3
```

`QWEATHER_API_HOST` must be the account-specific HTTPS API Host shown in the
QWeather console. The provider does not accept the retired public
`devapi.qweather.com` host or arbitrary hosts.

`QWEATHER_LOCATION` accepts either a QWeather LocationID or
`longitude,latitude`. Coordinates are normalized to two decimal places before
calling:

```http
GET /v7/weather/now
X-QW-Api-Key: ...
```

The provider converts QWeather `now.text`, `now.temp`, `now.windScale`, and
`now.humidity` into `RobotCompanionEnvironmentContext`. Raw QWeather response
fields are not passed to the Agent or Safety Guard.

If configuration is incomplete, the HTTP request fails, the HTTP status is not
successful, or QWeather returns a non-`200` API code, the current request falls
back to `MockWeatherProvider`. The returned `provider` and `source` then remain
`mock`.

## 7. Safety codes

Important stable codes include:

- `ADVISORY_ONLY`
- `HUMAN_CONFIRMATION_REQUIRED`
- `SOS_ACTIVE`
- `RECENT_FALL`
- `HEALTH_RISK_HIGH`
- `HEALTH_DATA_MISSING`
- `HEALTH_DATA_STALE`
- `WEATHER_RAIN`
- `WEATHER_STRONG_WIND`
- `WEATHER_HIGH_TEMPERATURE`
- `WEATHER_LOW_TEMPERATURE`
- `LOCATION_UNAVAILABLE`
- `ROBOT_OFFLINE`
- `MOTION_DISABLED`
- `EXECUTION_DISABLED`

The guard checks health and environment before the V1.0 motion-disabled gate so
the demonstration can show why an activity is unsuitable.

## 8. Errors

- `404 ELDER_NOT_FOUND`: `elder_id` is not present in the current care directory.
- `409 DEVICE_NOT_BOUND_TO_ELDER`: the requested device is not bound to the elder.
- `422`: request validation failed.

No error path creates a robot task or invokes the Go2 gateway.

## 9. Compatibility and impact

This is a new additive API.

- No existing request field is changed.
- No existing response field is changed.
- No field is deleted.
- No database schema is changed.
- No Go2 gateway contract is changed.
- No health-agent prompt or route is changed.
- No fall, emergency, navigation, or robot task behavior is changed.
- Existing frontend clients are unaffected until they explicitly call this API.
- `environment.description` and `environment.source` are additive fields.
- `environment.provider` now accepts `qweather` in addition to `mock`.

## 10. Future execution boundary

Real Go2 integration requires a separate reviewed task that adds:

1. a frozen Go2 `follow_elder` gateway contract;
2. real robot capability discovery;
3. elder or operator confirmation;
4. navigation preflight and control-owner checks;
5. idempotency, cancellation, timeout, and emergency-stop semantics;
6. updated API documentation and hardware acceptance tests.

The V1.0 companion endpoint must not be treated as authorization for those
changes.

## 11. Test command

```powershell
python -m pytest tests/test_robot_companion_agent.py -q
python -m pytest tests/test_qweather_provider.py -q
```
