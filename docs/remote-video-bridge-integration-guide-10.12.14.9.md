# 远端服务器联调说明文档：`10.12.14.9` 与本机 `CHINAMI-0ONSGG4` 的跌倒告警接入协作说明

## 摘要
本文档用于发给远端服务器 `10.12.14.9` 的工程师，说明当前主系统所在电脑的网络信息、服务状态、现有接入能力、已经完成的验证、当前实际阻塞点，以及远端工程师需要配合确认和执行的检查项。

当前主系统已经具备“接收跌倒模拟事件 -> 进入正式告警链路 -> 通过 `/ws/alarms` 下发”的能力，且本机已验证通过。

目前唯一未打通的是：**远端服务器 `10.12.14.9` 与本机之间的真实网络/端口联通，导致轮询超时，且尚未观察到远端主动推送到达本机。**

## 1. 本机信息

### 1.1 本机身份
- 主机名：`CHINAMI-0ONSGG4`
- 当前主系统项目目录：`D:\410health-main`

### 1.2 本机网络信息
- 主业务网卡：`以太网 2`
- 本机 IPv4：`172.18.33.66`
- 子网掩码：`255.255.255.0`
- 默认网关：`172.18.33.1`
- WSL 虚拟网卡：`172.22.144.1`

说明：
- WSL 网卡不是业务联调网卡，请忽略。
- 当前主系统的后端和前端都跑在 Windows 主机网络栈上，不在 WSL 内。

### 1.3 本机到远端的已测网络结果
从本机到远端 `10.12.14.9:8000` 的测试结果如下：

#### `Test-NetConnection 10.12.14.9 -Port 8000`
- `SourceAddress = 172.18.33.66`
- `NetRoute (NextHop) = 172.18.33.1`
- `PingSucceeded = False`
- `TcpTestSucceeded = False`

#### `tracert -d 10.12.14.9`
- 第 1 跳：`10.10.0.1`
- 第 2 跳：`172.31.0.22`
- 第 3 跳：`172.31.0.14`
- 第 4 跳：超时

结论：
- 当前本机与 `10.12.14.9` **没有建立可用 TCP 通路**
- 本机 `172.18.33.66/24` 与远端 `10.12.14.9` 不在同一网段
- 本机不是直接二层可达，而是通过 `172.18.33.1` / 上游路由尝试访问

## 2. 本机服务状态

### 2.1 后端服务
- 后端监听地址：`0.0.0.0:8000`
- 健康检查接口：`GET /healthz`
- 当前本机后端是可用的

本机可用性验证：
- `http://127.0.0.1:8000/healthz` 返回正常

### 2.2 防火墙状态
- Windows 防火墙已添加入站规则：
  - 规则名：`410health Backend 8000`
  - 状态：`Enabled=True`
  - 方向：`Inbound`
  - 动作：`Allow`

结论：
- 如果远端网络能够到达本机，则本机 `8000/TCP` 不会被 Windows 防火墙拦住

### 2.3 前端状态
- Web 前端地址：`http://127.0.0.1:5173`
- 后端 API 地址：`http://127.0.0.1:8000/api/v1`
- 前端已对齐到本机后端 `8000`

说明：
- 之前存在前端默认连 `8001` 的问题，当前已修正到 `8000`
- Flutter 端默认服务器端口也已从 `8001` 收敛到 `8000`

## 3. 当前主系统已具备的接入能力

### 3.1 两种接入模式都已具备
主系统当前已经支持两种对接方式：

1. **主动推送模式**
   - 远端服务器主动调用：
     `POST /api/v1/video-bridge/fall-events`

2. **轮询模式**
   - 主系统主动访问远端：
     - `GET /healthz`
     - `GET /stream/source?camera_id=...`
     - `GET /integration/results/{camera_id}/latest`

### 3.2 当前运行时联调配置
当前主系统 `video-bridge` 运行时配置如下：
- `base_url = http://10.12.14.9:8000`
- `camera_id = camera_01`
- `poll_enabled = true`
- `poll_hz = 2.0`
- `timeout_seconds = 2.5`
- `push_token` 已配置
- `target_device_mac = CAMERA-10.12.14.9`
- `target_elder_id = elder01_01`
- `target_family_ids = ["family01"]`

### 3.3 家属端权限目标已配置完成
当前系统已将来自该外部视觉源的跌倒事件默认绑定到：
- 老人：`elder01_01`
- 家属：`family01`

这意味着：
- 网页端应能看到告警
- Flutter 家属端在使用 `family01` 账号时应命中显示条件

## 4. 已完成的本机验证（证明主系统接收链路是通的）

### 4.1 本机主动推送验证已成功
我已在本机手动向后端发送一条模拟跌倒事件，结果如下：
- 调用接口：`POST /api/v1/video-bridge/fall-events`
- 携带有效 token
- 返回结果：
  - HTTP `200`
  - `alarm_id = 43474609-ad66-4df7-970a-c41b17cd4313`
  - `alarm_type = fall_injury_risk`

### 4.2 告警已成功进入正式链路
本机验证事件已经成功：
- 生成正式告警
- 进入 `/api/v1/alarms` 活跃告警列表
- 进入 `/ws/alarms` 实时推送队列
- 带有完整 `elder_id = elder01_01`
- 带有完整 `family_ids = ["family01"]`
- `presentation.show_immediate_popup = true`

### 4.3 当前状态页证据
当前 `GET /api/v1/video-bridge/status` 可见：
- `bridge_state = unknown`
- `camera_count = 0`
- `latest = null`
- `vision_service.enabled = true`
- `vision_service.last_error = Connection to 10.12.14.9:8000 timed out`
- `vision_service.last_promoted_at = 2026-06-09T02:54:43.409134+00:00`
- `vision_service.last_promoted_key = incident:remote-sim-incident-1`

说明：
- 主系统已经进入“真实远端接入模式”
- 当前最新一次真正成功的提升事件仍然是本机模拟推送，不是远端 `10.12.14.9` 发来的新事件

## 5. 当前真正的问题

### 5.1 轮询模式失败点
主系统主动调用：
- `POST /api/v1/video-bridge/vision/poll-once`

得到结果：
- `ok = false`
- `last_ok_at = null`
- `last_error = HTTPConnectionPool(host='10.12.14.9', port=8000)... timed out`
- `last_suppression_reason = poll_failed`

结论：
**轮询失败不是因为代码不支持，而是因为本机连不上 `10.12.14.9:8000`。**

### 5.2 主动推送模式当前未观察到远端新请求
截至目前，本机没有观察到来自 `10.12.14.9` 的新事件进入系统。

当前告警列表中只有之前本机手动推送验证成功的那一条事件，没有新的：
- `alarm_id`
- `incident_id`
- `last_promoted_at`

结论：
**当前无法证明远端服务器的主动推送已经真正到达本机。**

## 6. 远端工程师需要确认的内容

### 6.1 网络层确认
请远端工程师优先确认：
- `10.12.14.9` 是否允许访问 `172.18.33.66`
- 两端之间是否存在 VLAN / ACL / 防火墙 / VPN / 静态路由限制
- `10.12.14.9` 到 `172.18.33.66:8000` 是否可达
- 如果有防火墙，请放行：
  - 目标：`172.18.33.66`
  - 端口：`8000/TCP`

### 6.2 远端服务监听确认
请确认远端服务器上到底是哪一种情况：
1. 在 `8000` 暴露 HTTP 服务
2. 在 `8001` 暴露 HTTP 服务
3. 实际端口不是 `8000/8001`，而是其他端口

如果实际监听端口不是 `8000`，请直接回复真实端口，我这边会同步修改主系统 `base_url`。

### 6.3 远端服务接口确认（轮询模式）
若希望走轮询模式，请远端至少实现并确认以下接口：
- `GET /healthz`
- `GET /stream/source?camera_id=camera_01`
- `GET /integration/results/camera_01/latest`

推荐 `latest` 返回最小字段：
- `camera_id`
- `event_type`
- `state`
- `fall_detected`
- `fall_score` / `fall_prob`
- `track_id`
- `incident_id`
- `snapshot_url`

### 6.4 远端主动推送确认（推送模式）
若希望走主动推送模式，请远端主动调用本机：
- URL：
  `http://172.18.33.66:8000/api/v1/video-bridge/fall-events`
- Header：
  `X-Vision-Service-Token: bridge-token-410health`

#### 6.4.1 远端连续联调的正确发法
为避免第二次请求因为重复事件被服务端按设计拒绝，请远端在“连续联调模式”下遵守以下规则：

- 每次请求**必须更新**：
  - `incident_id`
  - `track_id`
  - `timestamp`
  - `snapshot_url` 或 `snapshot_path`（若截图有更新）
  - `fall_score` / `fall_prob`（若分数有更新）
- 可以固定不变：
  - `camera_id = camera_01`
  - `stream_name = analysis`
  - `source = vision_service`
  - `event_type = fall_confirmed`
  - `state = confirmed_fall`
  - `status = confirmed_fall`
  - `service_state = running`
  - `severity = L3`
  - `risk = high`
  - `risk_level = high`
  - `fall_detected = true`
- 不得复用：
  - 同一个 `incident_id`
  - 同一个 `camera_id + track_id`

推荐联调命名规范：

```text
incident_id = remote-sim-<UTC毫秒时间>-<短随机串>
track_id = remote-track-<UTC毫秒时间>-<短随机串>
```

说明：
- 如果第二次请求沿用相同 `incident_id`，服务端返回 `409 VIDEO_BRIDGE_FALL_EVENT_NOT_CREATED` 属于预期去重行为，不是网络故障。
- 如果希望“连续多次模拟告警都要进入正式链路”，请确保每次生成新的唯一事件 ID。

最小请求体建议如下：

```json
{
  "camera_id": "camera_01",
  "stream_name": "analysis",
  "source": "vision_service",
  "event_type": "fall_confirmed",
  "state": "confirmed_fall",
  "status": "confirmed_fall",
  "service_state": "running",
  "severity": "L3",
  "risk": "high",
  "risk_level": "high",
  "fall_detected": true,
  "fall_prob": 0.93,
  "fall_score": 0.93,
  "track_id": "remote-sim-track-1",
  "incident_id": "remote-sim-incident-1",
  "bbox": [120, 80, 260, 360],
  "snapshot_url": "http://10.12.14.9:8000/snapshots/fall-1.jpg",
  "timestamp": "2026-06-09T11:05:00+08:00",
  "metadata": {
    "model_version": "remote-sim-v1"
  }
}
```

## 7. 远端工程师建议执行的验证命令

### 7.1 在 `10.12.14.9` 上验证本机可达
如果远端也是 Windows：

```powershell
Test-NetConnection 172.18.33.66 -Port 8000
```

如果远端是 Linux：

```bash
curl -v http://172.18.33.66:8000/healthz
```

### 7.2 在远端验证本机推送接口
```bash
curl -v -X POST "http://172.18.33.66:8000/api/v1/video-bridge/fall-events" \
  -H "Content-Type: application/json" \
  -H "X-Vision-Service-Token: bridge-token-410health" \
  -d '{
    "camera_id":"camera_01",
    "stream_name":"analysis",
    "source":"vision_service",
    "event_type":"fall_confirmed",
    "state":"confirmed_fall",
    "status":"confirmed_fall",
    "service_state":"running",
    "severity":"L3",
    "risk":"high",
    "risk_level":"high",
    "fall_detected":true,
    "fall_prob":0.93,
    "fall_score":0.93,
    "track_id":"remote-sim-track-1",
    "incident_id":"remote-sim-incident-1",
    "snapshot_url":"http://10.12.14.9:8000/snapshots/fall-1.jpg",
    "timestamp":"2026-06-09T11:05:00+08:00"
  }'
```

预期：
- HTTP `200`
- 返回 `alarm_id`

### 7.3 在远端验证轮询接口本身
请在 `10.12.14.9` 本机自查：

```bash
curl -v http://127.0.0.1:8000/healthz
curl -v "http://127.0.0.1:8000/stream/source?camera_id=camera_01"
curl -v http://127.0.0.1:8000/integration/results/camera_01/latest
```

## 8. 双方联调通过标准

### 8.1 推送模式通过标准
- 远端向本机 `POST /api/v1/video-bridge/fall-events` 返回 `200`
- 本机 `/api/v1/alarms?active_only=true` 出现新告警
- 本机 `/ws/alarms` 能看到新 `alarm_queue`
- 社区网页出现跌倒告警弹窗
- Flutter 家属端使用 `family01` 账号时出现对应弹窗或提示

### 8.2 轮询模式通过标准
- 本机 `POST /api/v1/video-bridge/vision/poll-once` 返回 `ok = true`
- `status.vision_service.last_ok_at` 不再为空
- `status.latest` 不再为空
- 满足跌倒条件时，出现新的 `last_promoted_at`
- 告警进入 `/api/v1/alarms` 和 `/ws/alarms`
- 社区网页和 Flutter 家属端都能看到

## 9. 当前结论
- 主系统本机**已经能接收模拟跌倒事件**
- 主系统本机**已经能生成正式告警并下发 WebSocket**
- 主系统本机**已经准备好接收 `10.12.14.9` 的推送或轮询结果**
- 当前唯一阻塞点是：
  **`10.12.14.9` 与本机 `172.18.33.66:8000` 之间尚未建立成功的网络/HTTP 通路**

## 10. 建议协作顺序
1. 远端先验证能否访问本机 `http://172.18.33.66:8000/healthz`
2. 若可达，先走主动推送模式验证 `POST /api/v1/video-bridge/fall-events`
3. 推送成功后，再补轮询接口
4. 轮询接口可达后，再验证自动升级告警
5. 最终再做网页 + Flutter 双端验收

## 假设
- 远端工程师可以登录 `10.12.14.9`，并检查监听端口、接口实现、防火墙与路由配置
- 本机 `172.18.33.66` 是远端应当访问的正确业务地址
- 当前 `push token` 为：`bridge-token-410health`
- 当前主系统后端使用端口：`8000`
