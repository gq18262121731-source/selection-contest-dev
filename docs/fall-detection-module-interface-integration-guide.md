# 跌倒检测模块接口与对接说明

## 1. 文档目的

本文档用于说明当前主系统与外部 Vision Service / 跌倒检测模块之间的接口契约、调用方式、字段要求、鉴权方式、返回语义，以及推荐的联调步骤。

本文档面向两类接入方：

- 外部 Vision Service / 视频系统开发者
- 主系统集成与联调人员

当前架构边界已经明确：

- 主系统是 Vision Service Consumer
- 主系统不是 RTSP Owner
- 主系统不是 Camera Runtime Owner
- 主系统不是 Vision Pipeline Owner

因此：

- RTSP、拉流、YOLO、Pose、Fall 判断、WebRTC 由 Vision Service 负责
- 主系统只负责消费状态、接收结果、提升为业务告警

## 2. 对接总览

当前主系统支持两条与跌倒检测模块相关的链路：

### 2.1 只读状态消费链路

```text
Vision Service
-> VisionServiceClient
-> Main System API
-> /api/v1/vision/*
```

用途：

- 主系统读取 Vision Service 健康状态
- 主系统读取摄像头状态
- 主系统读取视频源信息
- 主系统读取最新结构化识别结果

### 2.2 确认跌倒事件上报链路

```text
Vision Service / Fall Detection Module
-> POST /api/v1/video-bridge/fall-events
-> 主系统告警队列 / 活动告警 / WebSocket 广播
```

用途：

- 当外部跌倒检测模块已经确认跌倒后，主动推送事件给主系统
- 主系统将该事件提升为平台告警

## 3. 主系统已提供接口

### 3.1 基础健康检查

```http
GET /healthz
```

用途：

- 检查主系统后端是否存活
- 用于局域网可达性验证

成功响应示例：

```json
{
  "status": "ok",
  "app": "AIoT Elder Care Monitoring System"
}
```

---

### 3.2 只读 Vision API

统一前缀：

```text
/api/v1/vision
```

接口列表：

```http
GET /api/v1/vision/health
GET /api/v1/vision/status
GET /api/v1/vision/source
GET /api/v1/vision/results/latest
```

说明：

- 这组接口只读
- 不提供 POST / PUT / DELETE
- 主系统内部统一通过 `VisionServiceClient` 访问外部 Vision Service
- 不读取 RTSP
- 不读取 `camera_registry.json`
- 不读取 `camera_live_config.runtime.json`

---

### 3.3 Video Bridge / 跌倒事件接口

统一前缀：

```text
/api/v1/video-bridge
```

当前与跌倒模块最相关的接口如下：

```http
GET   /api/v1/video-bridge/status
GET   /api/v1/video-bridge/runtime-config
PATCH /api/v1/video-bridge/runtime-config
POST  /api/v1/video-bridge/vision/poll-once
GET   /api/v1/video-bridge/vision/health
GET   /api/v1/video-bridge/vision/source
GET   /api/v1/video-bridge/vision/latest
POST  /api/v1/video-bridge/fall-events
```

其中真正用于“确认跌倒上报”的核心接口是：

```http
POST /api/v1/video-bridge/fall-events
```

## 4. Vision Service 需要提供的接口

为了让主系统完成只读状态消费，Vision Service 至少应提供以下接口：

```http
GET /healthz
GET /status?camera_id=camera_01
GET /stream/source?camera_id=camera_01
GET /integration/results/{camera_id}/latest
```

建议还提供：

```http
GET /stream/latest-frame.jpg?camera_id=camera_01
WS  /ws/results
```

## 5. 只读 Vision API 详细说明

## 5.1 GET /api/v1/vision/health

主系统内部调用：

```text
VisionServiceClient.get_health()
-> GET {VISION_SERVICE_BASE_URL}/healthz
```

请求示例：

```http
GET /api/v1/vision/health
```

成功响应示例：

```json
{
  "status": "ok",
  "reason": null,
  "vision_service": {
    "ok": true,
    "status": "ok",
    "reason": null,
    "endpoint": "/healthz",
    "method": "GET",
    "url": "http://192.168.8.254:8000/healthz",
    "camera_id": null,
    "status_code": 200,
    "elapsed_ms": 15,
    "data": {
      "status": "ok"
    },
    "error": null
  }
}
```

---

## 5.2 GET /api/v1/vision/status

主系统内部调用：

```text
VisionServiceClient.get_status(camera_id)
-> GET {VISION_SERVICE_BASE_URL}/status?camera_id={camera_id}
```

请求示例：

```http
GET /api/v1/vision/status?camera_id=camera_01
```

成功响应示例：

```json
{
  "status": "ok",
  "reason": null,
  "camera_id": "camera_01",
  "vision_service": {
    "ok": true,
    "status": "ok",
    "reason": null,
    "endpoint": "/status",
    "method": "GET",
    "url": "http://192.168.8.254:8000/status?camera_id=camera_01",
    "camera_id": "camera_01",
    "status_code": 200,
    "elapsed_ms": 22,
    "data": {
      "service_status": "running",
      "camera_id": "camera_01",
      "stream_state": "connected",
      "frame_age_ms": 83
    },
    "error": null
  }
}
```

---

## 5.3 GET /api/v1/vision/source

主系统内部调用：

```text
VisionServiceClient.get_stream_source(camera_id)
-> GET {VISION_SERVICE_BASE_URL}/stream/source?camera_id={camera_id}
```

请求示例：

```http
GET /api/v1/vision/source?camera_id=camera_01
```

---

## 5.4 GET /api/v1/vision/results/latest

主系统内部调用：

```text
VisionServiceClient.get_latest_result(camera_id)
-> GET {VISION_SERVICE_BASE_URL}/integration/results/{camera_id}/latest
```

请求示例：

```http
GET /api/v1/vision/results/latest?camera_id=camera_01
```

此接口建议由 Vision Service 返回最新一帧或最新一次分析结果的结构化数据，例如：

- `camera_id`
- `stream_name`
- `service_state`
- `camera_lost`
- `capture_stale`
- `frame_age_ms`
- `fall_state`
- `risk`
- `fall_prob`
- `track_id`
- `snapshot_url`
- `timestamp`
- `metadata`

## 6. 只读 Vision API 的错误与降级语义

主系统 `/api/v1/vision/*` 的约定是“尽量结构化返回”，避免直接抛 500。

### 6.1 Vision Service 超时

如果 Vision Service 超时，主系统返回：

```json
{
  "status": "unavailable",
  "reason": "timeout",
  "vision_service": {
    "ok": false,
    "status": "unavailable",
    "reason": "timeout"
  }
}
```

HTTP 状态码仍为：

```text
200
```

### 6.2 Vision Service 连接失败

如果主系统无法连接 Vision Service，返回：

```json
{
  "status": "unavailable",
  "reason": "connection_error"
}
```

### 6.3 Vision Service 返回 4xx / 5xx

如果外部 Vision Service 返回非 2xx，例如 `503`，主系统返回：

```json
{
  "status": "degraded",
  "reason": "http_error",
  "vision_service": {
    "status": "degraded",
    "status_code": 503
  }
}
```

## 7. 跌倒检测模块主动上报接口

## 7.1 推荐用途

推荐外部跌倒检测模块在“已经确认跌倒”后调用：

```http
POST /api/v1/video-bridge/fall-events
```

不建议：

- 将每一帧检测都推给该接口
- 将“怀疑跌倒”直接当作平台告警推送

推荐只在以下场景推送：

- `confirmed_fall`
- `fallen`
- `needs_assistance`
- `emergency`

## 7.2 接口地址

主系统 LAN 地址示例：

```text
http://192.168.8.253:8000/api/v1/video-bridge/fall-events
```

## 7.3 鉴权规则

该接口支持以下两种授权方式，满足任意一种即可：

### 方式 A：来源 IP 匹配

如果请求来源 IP 与当前 Video Bridge 运行时配置中的 `base_url` 主机一致，则允许通过。

例如：

- 当前主系统配置的 `base_url = http://192.168.8.254:8000`
- 那么来自 `192.168.8.254` 的请求会被视为可信来源

### 方式 B：Header Token 匹配

请求头中携带：

```http
X-Vision-Service-Token: <push_token>
```

并与主系统运行时配置中的 `push_token` 一致。

## 7.4 请求头

推荐请求头：

```http
Content-Type: application/json
X-Vision-Service-Token: vision-bridge-20260609
```

如果你采用 IP 白名单方式，可不传 token；但在跨机器部署时，仍建议保留 token。

## 7.5 请求体字段定义

请求模型名：

```text
VideoBridgeFallEventRequest
```

字段说明如下：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `camera_id` | string | 是 | 摄像头 ID，建议固定且稳定 |
| `stream_name` | string | 否 | 流名称，默认 `primary` |
| `source` | string | 否 | 来源系统名称，默认 `vision_service` |
| `event_type` | string | 否 | 事件类型，建议 `fall_confirmed` |
| `state` | string | 否 | 状态，建议 `confirmed_fall` |
| `status` | string | 否 | 状态别名，可与 `state` 一致 |
| `service_state` | string | 否 | 服务状态，如 `running` |
| `severity` | string | 否 | 严重级别，例如 `L3` |
| `risk` | string | 否 | 风险级别：`low` / `medium` / `high` / `critical` |
| `risk_level` | string | 否 | 风险级别别名 |
| `fall_detected` | bool | 否 | 是否检测到跌倒，默认 `true` |
| `fall_prob` | float | 否 | 跌倒概率，0.0 到 1.0 |
| `fall_score` | float | 否 | 跌倒评分，0.0 到 1.0 |
| `track_id` | string | 否 | 跟踪 ID |
| `incident_id` | string | 否 | 事件 ID，强烈建议传，便于去重 |
| `bbox` | float[4] | 否 | `[x1, y1, x2, y2]` |
| `target` | object/string | 否 | 目标信息，可扩展 |
| `snapshot_url` | string | 否 | 截图 URL |
| `snapshot_path` | string | 否 | 截图路径 |
| `timestamp` | datetime | 否 | 事件时间，默认当前 UTC |
| `demo` | bool | 否 | 是否为演示/模拟事件 |
| `scores` | object | 否 | 多模型评分 |
| `injury` | object | 否 | 伤害评估信息 |
| `metadata` | object | 否 | 扩展字段 |

## 7.6 推荐请求体示例

```json
{
  "camera_id": "camera_01",
  "stream_name": "primary",
  "source": "vision_service",
  "event_type": "fall_confirmed",
  "state": "confirmed_fall",
  "status": "confirmed_fall",
  "service_state": "running",
  "severity": "L3",
  "risk": "critical",
  "risk_level": "critical",
  "fall_detected": true,
  "fall_prob": 0.91,
  "fall_score": 0.91,
  "track_id": "track-20260616-001",
  "incident_id": "vision-fall-camera_01-20260616-001",
  "bbox": [80.0, 60.0, 380.0, 330.0],
  "snapshot_url": "http://192.168.8.254:8000/fall-events/snapshots/fall-001.jpg",
  "timestamp": "2026-06-16T09:37:49Z",
  "demo": false,
  "scores": {
    "detector": 0.91,
    "posture": 0.91,
    "hybrid": 0.91
  },
  "injury": {
    "level": "I3",
    "reason": "vision_service_push",
    "down_seconds": 4.2
  },
  "metadata": {
    "trigger": "vision_service_alert_simulator",
    "provider": "simulator",
    "source_camera_name": "room-a"
  }
}
```

## 7.7 成功响应示例

```json
{
  "ok": true,
  "accepted": true,
  "pushed": true,
  "alarm_id": "b675959f-b75d-4b7d-b8db-41117b636710",
  "alarm_type": "video_fall",
  "alarm": {
    "id": "b675959f-b75d-4b7d-b8db-41117b636710",
    "device_mac": "AA:50:96:02:93:12",
    "alarm_type": "video_fall",
    "alarm_level": 2,
    "alarm_layer": "intelligent",
    "message": "视频跌倒告警 | camera=camera_01 | state=confirmed_fall | score=0.91",
    "acknowledged": false,
    "anomaly_probability": 0.91,
    "metadata": {
      "incident_id": "vision-fall-camera_01-20260616-001",
      "camera_id": "camera_01",
      "stream_name": "primary"
    }
  },
  "camera_id": "camera_01",
  "stream_name": "primary",
  "risk": "critical",
  "fall_prob": 0.91,
  "triggered_at": "2026-06-16T09:37:49Z",
  "elder_id": "elder_demo_01",
  "elder_name": ""
}
```

## 8. 主系统如何处理跌倒推送

主系统收到 `POST /api/v1/video-bridge/fall-events` 后，会执行以下步骤：

1. 校验来源 IP 或 `X-Vision-Service-Token`
2. 规范化事件结构
3. 注入目标业务上下文
4. 进行短窗口去重
5. 生成平台告警
6. 写入活动告警与告警队列
7. 通过 WebSocket 广播告警变化

## 8.1 去重规则

主系统会优先使用以下键做桥接去重：

- `incident_id`
- 若没有 `incident_id`，则可能退化到 `camera_id + track_id` 等组合

因此强烈建议外部跌倒模块始终传递稳定的 `incident_id`。

如果同一事件重复发送，主系统可能返回：

```http
409
```

响应：

```json
{
  "detail": "VIDEO_BRIDGE_FALL_EVENT_NOT_CREATED"
}
```

这通常表示：

- 已被去重
- 本次未再次生成新告警

## 8.2 告警等级映射

当前主系统内部规则：

- 如果 `fall_score >= 0.82`，提升为高优先级视频跌倒告警
- 或者 `risk in {"high", "critical"}`，也会提升为高优先级告警
- 否则可能降为较低级别告警

因此建议外部模块在确认跌倒时：

- `risk` 使用 `high` 或 `critical`
- `fall_score` 使用可信的高分值，例如 `0.85+`

## 8.3 目标业务上下文

主系统会将事件映射到平台内部的目标设备 / 老人 / 家属上下文。

相关运行时配置包括：

- `target_device_mac`
- `target_elder_id`
- `target_family_ids`

这些可通过以下接口查看或修改：

```http
GET   /api/v1/video-bridge/runtime-config
PATCH /api/v1/video-bridge/runtime-config
```

## 9. 推荐对接方式

## 9.1 最小只读集成

如果当前只需要“让主系统知道视频系统在线且能读到结果”，推荐先完成：

1. Vision Service 提供：
   - `GET /healthz`
   - `GET /status`
   - `GET /stream/source`
   - `GET /integration/results/{camera_id}/latest`
2. 主系统配置：
   - `VISION_SERVICE_BASE_URL`
   - `VISION_SERVICE_CAMERA_ID`
3. 用主系统接口验证：
   - `GET /api/v1/vision/health`
   - `GET /api/v1/vision/status`
   - `GET /api/v1/vision/source`
   - `GET /api/v1/vision/results/latest`

## 9.2 确认跌倒告警集成

如果要让跌倒检测模块真正触发主系统告警，推荐按以下步骤：

1. 保证主系统可从视频系统机器访问：
   - `GET http://<main-host>:8000/healthz`
2. 在主系统设置运行时配置：
   - `base_url = http://<vision-host>:8000`
   - `camera_id = camera_01`
   - `push_token = <约定 token>`
   - `target_device_mac`
   - `target_elder_id`
   - `target_family_ids`
3. 外部跌倒模块在确认跌倒后调用：
   - `POST http://<main-host>:8000/api/v1/video-bridge/fall-events`
4. 主系统检查：
   - `GET /api/v1/alarms?active_only=true`
   - `GET /api/v1/alarms/queue`

## 10. 调用示例

## 10.1 curl：读取主系统只读 Vision 状态

```bash
curl http://127.0.0.1:8000/api/v1/vision/health
curl http://127.0.0.1:8000/api/v1/vision/status
curl "http://127.0.0.1:8000/api/v1/vision/source?camera_id=camera_01"
curl "http://127.0.0.1:8000/api/v1/vision/results/latest?camera_id=camera_01"
```

## 10.2 curl：推送确认跌倒事件

```bash
curl -X POST "http://192.168.8.253:8000/api/v1/video-bridge/fall-events" \
  -H "Content-Type: application/json" \
  -H "X-Vision-Service-Token: vision-bridge-20260609" \
  -d '{
    "camera_id": "camera_01",
    "stream_name": "primary",
    "source": "vision_service",
    "event_type": "fall_confirmed",
    "state": "confirmed_fall",
    "status": "confirmed_fall",
    "service_state": "running",
    "severity": "L3",
    "risk": "critical",
    "fall_detected": true,
    "fall_prob": 0.91,
    "fall_score": 0.91,
    "track_id": "track-001",
    "incident_id": "vision-fall-camera_01-20260616-001",
    "snapshot_url": "http://192.168.8.254:8000/fall-events/snapshots/fall-001.jpg",
    "timestamp": "2026-06-16T09:37:49Z",
    "metadata": {
      "trigger": "vision_service_alert_simulator"
    }
  }'
```

## 10.3 PowerShell：推送确认跌倒事件

```powershell
$body = @{
  camera_id = "camera_01"
  stream_name = "primary"
  source = "vision_service"
  event_type = "fall_confirmed"
  state = "confirmed_fall"
  status = "confirmed_fall"
  service_state = "running"
  severity = "L3"
  risk = "critical"
  fall_detected = $true
  fall_prob = 0.91
  fall_score = 0.91
  track_id = "track-001"
  incident_id = "vision-fall-camera_01-20260616-001"
  snapshot_url = "http://192.168.8.254:8000/fall-events/snapshots/fall-001.jpg"
  timestamp = "2026-06-16T09:37:49Z"
  metadata = @{
    trigger = "vision_service_alert_simulator"
  }
} | ConvertTo-Json -Depth 8

Invoke-RestMethod `
  -Uri "http://192.168.8.253:8000/api/v1/video-bridge/fall-events" `
  -Method POST `
  -Headers @{
    "X-Vision-Service-Token" = "vision-bridge-20260609"
  } `
  -ContentType "application/json" `
  -Body $body
```

## 11. 联调排障建议

## 11.1 先测网络再测业务

先在视频系统机器执行：

```powershell
curl.exe http://192.168.8.253:8000/healthz
```

结果解释：

- 返回 `{"status":"ok",...}`：说明网络通，进入业务联调
- 连接超时：优先检查监听地址和防火墙
- 返回 `403`：说明已到应用层，检查鉴权逻辑

## 11.2 如果跌倒推送超时

优先检查：

- 主系统是否监听 `0.0.0.0:8000`
- 主系统是否能快速返回
- Redis / 队列 / 广播链路是否阻塞

当前系统曾出现过这样的问题：

- 网络是通的
- 路由也命中了
- 但由于 Redis 不可用，告警入队重试拖慢接口返回，导致外部看到 `read timeout=2.5`

因此建议：

- 将外部模块调用超时至少设为 `2.5s ~ 5s`
- 不要把“收到 timeout”直接等同于“主系统没收到”
- 同时检查主系统 `GET /api/v1/alarms?active_only=true`

## 11.3 如果收到 409

说明主系统没有再次创建新告警，常见原因：

- 同一个 `incident_id` 重复发送
- 当前事件已在短窗口内被去重

## 12. 推荐实施顺序

建议按以下顺序完成对接：

1. 先通 `GET /healthz`
2. 再通 Vision Service 的：
   - `/healthz`
   - `/status`
   - `/stream/source`
   - `/integration/results/{camera_id}/latest`
3. 再通主系统只读接口：
   - `/api/v1/vision/health`
   - `/api/v1/vision/status`
   - `/api/v1/vision/source`
   - `/api/v1/vision/results/latest`
4. 最后才接：
   - `POST /api/v1/video-bridge/fall-events`

这样可以避免一开始就把问题混在“网络、鉴权、状态消费、告警转换、前端弹窗”多个层面里。

## 13. 对接结论

对于跌倒检测模块，当前推荐的最小对接契约是：

### 主系统消费你

- `GET /healthz`
- `GET /status?camera_id=camera_01`
- `GET /stream/source?camera_id=camera_01`
- `GET /integration/results/{camera_id}/latest`

### 你上报主系统

- `POST /api/v1/video-bridge/fall-events`

如果你只想做“状态接入”，做到第一组即可。

如果你想做“真实跌倒告警接入”，必须再完成第二组。
