# 主系统视频桥接对接说明

本文档说明“独立视觉服务”和“本项目主系统”之间的对接方式、接口约定、运行配置、联调步骤与本次实测结果。

适用场景：

- 独立视觉服务负责 RTSP 拉流、画面分析、跌倒识别、事件截图与告警触发
- 本项目作为主系统，负责接收视觉结果、提升为平台告警、供前端和移动端展示
- 主系统也可以反向轮询视觉服务的健康状态、视频源和最新结构化识别结果

## 1. 角色划分

本仓库当前涉及两个不同角色，请联调时不要混淆：

- 独立视觉服务：对外暴露 `/healthz`、`/status`、`/stream/*`、`/webrtc/offer`、`/integration/results/{camera_id}/latest`、`/alerting/*` 等接口
- 本项目主系统：对外暴露 `/api/v1/video-bridge/*`、`/api/v1/alarms/*`、`/api/v1/camera/*` 等接口

一句话理解：

- 视觉服务负责“看”和“判”
- 主系统负责“收”、“转”、“告警入库”和“对业务侧提供统一结果”

## 2. 当前主系统接口

主系统后端默认监听 `0.0.0.0:8000`，公共健康检查接口为：

```text
GET /healthz
```

视频桥接相关接口统一挂在：

```text
/api/v1/video-bridge
```

当前主系统已实现的关键接口如下。

### 2.1 主系统主动轮询视觉服务

```text
GET   /api/v1/video-bridge/status
GET   /api/v1/video-bridge/runtime-config
PATCH /api/v1/video-bridge/runtime-config
POST  /api/v1/video-bridge/vision/poll-once
GET   /api/v1/video-bridge/vision/health
GET   /api/v1/video-bridge/vision/source?camera_id=camera_01
GET   /api/v1/video-bridge/vision/latest?camera_id=camera_01
POST  /api/v1/video-bridge/vision/probe
POST  /api/v1/video-bridge/vision/switch-host
```

这组接口用于：

- 配置主系统当前指向哪个视觉服务
- 检查视觉服务健康状态
- 拉取视觉服务的视频源信息
- 拉取视觉服务的最新结构化识别结果
- 手动触发一次轮询验证

### 2.2 视觉服务主动推送跌倒事件到主系统

```text
POST /api/v1/video-bridge/fall-events
```

这个接口用于让独立视觉服务在确认跌倒后，直接把结构化事件推送给主系统。主系统收到后会：

- 做来源鉴权
- 做桥接去重
- 注入目标老人、家属、设备上下文
- 转成主系统告警
- 返回告警受理结果

### 2.3 主系统告警结果查询

如果要从主系统侧检查是否已经成功生成平台告警，可结合以下接口使用：

```text
GET /api/v1/alarms
GET /api/v1/alarms/queue
GET /api/v1/alarms/queue/snapshot
```

## 3. 独立视觉服务接口约定

联调时，主系统默认认为“独立视觉服务”对外提供以下能力。

### 3.1 基础健康与状态

```text
GET /healthz
GET /status?camera_id=camera_01
```

### 3.2 视频流与当前视频源

```text
POST /stream/start
POST /stream/stop
GET  /stream/source?camera_id=camera_01
GET  /stream/latest-frame.jpg?camera_id=camera_01
POST /webrtc/offer
```

### 3.3 主系统轮询所依赖的结果接口

```text
GET /integration/results/{camera_id}/latest
```

这是主系统反向轮询时最关键的一个接口。主系统会从该接口拉取最新结构化识别结果，并按阈值和状态决定是否提升为正式告警。

### 3.4 视觉服务本地告警上报能力

```text
GET  /alerting/status
POST /alerting/endpoint
POST /alerting/simulation/send-once
POST /alerting/simulation/start
POST /alerting/simulation/stop
GET  /fall-events/snapshots/{filename}
```

这组接口不属于主系统仓库本身，但在联调时很重要，因为它们通常用于：

- 把视觉服务的上报目标地址切到主系统
- 发送一条模拟跌倒告警做验收
- 连续发送模拟告警压测桥接链路
- 查看事件截图是否可回溯

## 4. 主系统轮询视觉服务的接口契约

当主系统启用轮询时，会按下面顺序访问视觉服务：

1. `GET {base_url}/healthz`
2. `GET {base_url}/stream/source?camera_id={camera_id}`
3. `GET {base_url}/integration/results/{camera_id}/latest`

当前实现位于：

- [backend/services/video_bridge_service.py](/abs/path/d:/health_original/health1/backend/services/video_bridge_service.py:379)
- [backend/api/video_bridge_api.py](/abs/path/d:/health_original/health1/backend/api/video_bridge_api.py:34)

主系统把视觉服务返回的 `latest` 结果转换为自身统一结构后，会根据以下信息判断是否需要提升为告警：

- `state`
- `status`
- `fall_detected`
- `fall_score` 或 `fall_prob`

如果满足跌倒候选条件，主系统会进一步：

- 依据 `incident_id` 或 `camera_id + track_id` 做短窗口去重
- 写入主系统告警队列
- 将结果暴露给前端与移动端

## 5. 视觉服务推送到主系统的接口契约

视觉服务主动上报跌倒事件时，请调用：

```text
POST /api/v1/video-bridge/fall-events
```

请求头支持两种鉴权方式，满足任一种即可：

- 请求来源 IP 与当前已配置的视觉服务 `base_url` 主机一致
- 请求头 `X-Vision-Service-Token` 与主系统当前运行配置中的 `push_token` 一致

当前实现位于：

- [backend/api/video_bridge_api.py](/abs/path/d:/health_original/health1/backend/api/video_bridge_api.py:118)
- [backend/services/video_bridge_service.py](/abs/path/d:/health_original/health1/backend/services/video_bridge_service.py:143)

推荐请求体字段如下：

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
  "risk": "high",
  "fall_detected": true,
  "fall_prob": 0.94,
  "fall_score": 0.94,
  "track_id": "target-001",
  "incident_id": "fall-camera_01-20260609-001",
  "bbox": [318.0, 244.0, 712.0, 981.0],
  "snapshot_url": "http://vision-host:8000/fall-events/snapshots/fall-001.jpg",
  "timestamp": "2026-06-09T10:15:30Z",
  "demo": false,
  "scores": {
    "detector": 0.94,
    "posture": 0.91,
    "hybrid": 0.94
  },
  "injury": {
    "level": "I3",
    "reason": "vision_service_push"
  },
  "metadata": {
    "source_camera_name": "room-a",
    "operator": "vision-runtime"
  }
}
```

主系统成功受理后，返回体中通常至少包含：

- `ok`
- `accepted`
- `pushed`
- `alarm_id`
- `alarm_type`
- `camera_id`
- `stream_name`
- `risk`
- `fall_prob`
- `triggered_at`

## 6. 主系统运行配置

主系统当前桥接配置既可以通过环境变量初始化，也可以通过运行时接口修改。

### 6.1 默认环境变量

相关配置定义见：

- [backend/config.py](/abs/path/d:/health_original/health1/backend/config.py:176)

关键项如下：

```env
VISION_SERVICE_BASE_URL=http://127.0.0.1:8090
VISION_SERVICE_CAMERA_ID=camera_01
VISION_SERVICE_POLL_ENABLED=false
VISION_SERVICE_POLL_HZ=2.0
VISION_SERVICE_TIMEOUT_SECONDS=2.5
VISION_SERVICE_PUSH_TOKEN=
FALL_DETECTION_TARGET_DEVICE_MAC=CAMERA-192.168.8.254
FALL_DETECTION_TARGET_ELDER_ID=
FALL_DETECTION_TARGET_FAMILY_IDS=
FALL_DETECTION_MIN_ALERT_SCORE=0.0
```

### 6.2 运行时修改

可通过以下接口动态修改主系统当前桥接配置：

```text
PATCH /api/v1/video-bridge/runtime-config
```

请求示例：

```json
{
  "base_url": "http://10.12.14.29:8000",
  "camera_id": "camera_01",
  "poll_enabled": true,
  "poll_hz": 2.0,
  "timeout_seconds": 2.5,
  "push_token": "",
  "target_device_mac": "CAMERA-10.12.14.29",
  "target_elder_id": "elder_demo_01",
  "target_family_ids": ["family01", "family02"]
}
```

查询当前配置：

```text
GET /api/v1/video-bridge/runtime-config
```

手动拉一次视觉服务验证配置是否正确：

```text
POST /api/v1/video-bridge/vision/poll-once
```

## 7. 联调推荐步骤

建议按下面顺序做端到端联调。

### 7.1 先确认视觉服务可用

至少验证下面几个地址：

```text
GET http://<vision-host>:8000/healthz
GET http://<vision-host>:8000/status?camera_id=camera_01
GET http://<vision-host>:8000/stream/source?camera_id=camera_01
GET http://<vision-host>:8000/integration/results/camera_01/latest
```

### 7.2 再确认主系统可用

至少验证：

```text
GET http://<main-host>:8000/healthz
GET http://<main-host>:8000/api/v1/video-bridge/status
```

### 7.3 配置主系统指向视觉服务

调用：

```text
PATCH http://<main-host>:8000/api/v1/video-bridge/runtime-config
```

把 `base_url` 改为视觉服务实际可达地址。

### 7.4 做两类验收

验收一：主系统轮询视觉服务

- 触发 `POST /api/v1/video-bridge/vision/poll-once`
- 检查返回中的 `vision_service.health`、`vision_service.source`、`accepted`

验收二：视觉服务主动推送跌倒事件

- 让视觉服务把告警上报地址设置为 `http://<main-host>:8000/api/v1/video-bridge/fall-events`
- 发送一条模拟跌倒告警
- 检查主系统返回是否包含 `accepted=true`、`pushed=true`、`alarm_id`

### 7.5 最后到主系统业务侧核验

建议继续确认：

- `GET /api/v1/alarms`
- `GET /api/v1/alarms/queue`
- 前端或移动端的告警展示是否同步刷新

## 8. 2026-06-09 实测记录

以下结果为 2026-06-09 当前这台视觉服务机器上的最新联调记录，应优先作为当前状态参考。

### 8.1 独立视觉服务状态

- 后端当前正在运行
- 本机 `http://127.0.0.1:8000/healthz` 返回 `{"status":"ok"}`
- 当前机器 IP 为 `192.168.8.253`
- 视觉服务接口文档已提交到 GitHub 私有仓库：
  `https://github.com/kangzhouyang/69-service-/blob/main/docs/vision_service_api_reference_2026-06-09.md`
- 对应最新提交为 `8112888`：`Add vision service API reference`
- 主系统侧后续可直接基于仓库文档联调，不再依赖本机 `D:\Program\vision_service\...` 路径
- 本地验证结果：`python -m unittest tests.test_alerting_manual_send` 已通过
- 本地工作区状态已整理为干净

现场已确认的视觉服务接口包括：

- `GET /healthz`
- `GET /status?camera_id=camera_01`
- `POST /stream/start`
- `POST /stream/stop`
- `GET /stream/source?camera_id=camera_01`
- `GET /stream/latest-frame.jpg?camera_id=camera_01`
- `POST /webrtc/offer`
- `GET /integration/results/{camera_id}/latest`
- `GET /alerting/status`
- `POST /alerting/endpoint`
- `POST /alerting/simulation/send-once`
- `POST /alerting/simulation/start`
- `POST /alerting/simulation/stop`
- `GET /fall-events/snapshots/{filename}`

### 8.2 主系统联通验证结果

当前主系统联通尝试失败，尚未完成端到端打通。

本次尝试过的目标包括：

- 旧配置地址 `192.168.1.100:8090`
- 当前运行时目标 `http://172.18.33.66:8000/api/v1/video-bridge/fall-events`

当前结果：

- 旧配置地址 `192.168.1.100:8090` 超时
- 当前目标 `172.18.33.66:8000` 超时
- 通过本地模拟告警接口向 `http://172.18.33.66:8000/api/v1/video-bridge/fall-events` 发送测试请求失败
- 返回结果如下：

```json
{
  "ok": false,
  "target_url": "http://172.18.33.66:8000/api/v1/video-bridge/fall-events",
  "status_code": null,
  "error": "Connection to 172.18.33.66 timed out. (connect timeout=2.5)"
}
```

这说明当前问题发生在“建立 TCP 连接”阶段，尚未到达主系统应用层，也就还没有进入 `/api/v1/video-bridge/fall-events` 的业务处理逻辑。

补充一版视频系统侧的最新复测口径：

- 本地后端正常：`GET /healthz` 返回 `ok`
- 当前目标仍为：`http://172.18.33.66:8000/api/v1/video-bridge/fall-events`
- TCP 连接测试失败：`172.18.33.66:8000 connect timeout`
- 主系统状态接口超时：`/api/v1/video-bridge/status` timeout
- 发送模拟告警失败：`Connection to 172.18.33.66 timed out. (connect timeout=2.5)`

因此当前结论保持不变：

- 现在还不能连接到主系统
- 问题仍停留在网络 TCP 连接阶段
- 还没有进入 `token`、`payload`、接口字段或业务逻辑校验

### 8.3 当前网络观察

从当前机器路由与现场校验结果看：

- 默认网关为 `192.168.8.1`
- 现场校验的 WLAN IPv4 为 `192.168.8.253`
- 当前可见本地网段为 `192.168.8.0/24`
- 还存在一条 `172.30.64.0/20` 的本地虚拟网段
- 未看到指向 `172.18.0.0/16` 的直连路由

结合现场现象，当前更像是以下几类问题之一：

- 主系统 IP 已变化，`172.18.33.66` 不再是当前可达地址
- 主系统服务没有监听 `0.0.0.0:8000`
- 主系统主机或中间网络防火墙拦截了 `8000` 端口
- 视觉服务机器与主系统机器不在可相互路由的网络中

### 8.4 当前建议反馈给主系统工程师

建议主系统侧尽快确认以下事项：

- 主系统当前实际对外 IP 是否仍为 `172.18.33.66`
- 主系统服务是否确实监听在 `0.0.0.0:8000` 或对应业务网卡
- 主系统主机防火墙、安全组或交换网络策略是否允许来自 `192.168.8.253` 的访问
- 两台机器之间是否存在跨网段路由，尤其是 `192.168.8.0/24` 到 `172.18.0.0/16`
- 是否能在主系统机器上直接访问 `http://192.168.8.253:8000/healthz`

建议主系统工程师至少回传以下验证结果：

- `GET http://<main-host>:8000/healthz`
- `GET http://<main-host>:8000/api/v1/video-bridge/status`
- 从主系统机器访问 `http://192.168.8.253:8000/healthz` 的结果
- `netstat` 或等效命令确认 `8000` 端口监听状态

### 8.5 可直接转发给主系统工程师的排障消息模板

下面这段可直接复制给主系统工程师：

```text
当前视觉服务侧状态如下，请主系统侧协助确认网络与监听状态：

1. 视觉服务本机后端正常：
   GET http://127.0.0.1:8000/healthz 返回 {"status":"ok"}

2. 视觉服务本机当前 WLAN IPv4：
   192.168.8.253

3. 当前视觉服务向主系统推送模拟告警的目标地址：
   POST http://172.18.33.66:8000/api/v1/video-bridge/fall-events
   Header: X-Vision-Service-Token: <configured token>

4. 当前失败现象：
   TCP 连接超时，尚未进入主系统应用层。
   错误摘要：
   Connection to 172.18.33.66 timed out. (connect timeout=2.5)

5. 旧地址也不可达：
   http://192.168.1.100:8090/api/v1/video-bridge/status 超时

请主系统侧重点确认：
- 当前主系统真实 IP 是否仍为 172.18.33.66
- 服务是否监听 0.0.0.0:8000，而不是只监听 127.0.0.1:8000
- 防火墙是否放行入站 TCP 8000
- /api/v1/video-bridge/fall-events 是否已挂载
- 视觉服务机器 192.168.8.253 是否能路由到主系统所在网段
- 如主系统 IP 已变化，请提供新的 IP，我们会在控制台“接收服务器 IP”里修改后重试
```

当前判断仍然是：

- 问题停在网络 TCP 连接阶段
- 暂时不是 `token`、`payload` 或接口字段格式问题

### 8.6 当前本机主系统已可接收视频侧推送

在切换为“本机作为主系统接收端”后，当前工作区已完成接收链路打通，结论如下：

- 当前这台主系统机器的真实 WLAN IPv4 为 `192.168.8.254`
- 本机主系统当前监听 `0.0.0.0:8000`
- 主系统健康检查成功：`GET http://127.0.0.1:8000/healthz`
- 视频桥接接收接口可用：`POST /api/v1/video-bridge/fall-events`
- 已通过本机回环请求验证，主系统返回：
  - `ok=true`
  - `accepted=true`
  - `pushed=true`
  - `alarm_type=video_fall`
- 本次回环验证生成的 `alarm_id`：
  - `8164a194-3d07-4f0c-9bd6-36f2de5e462c`
- 该事件已成功进入：
  - `GET /api/v1/alarms`
  - `GET /api/v1/alarms/queue/snapshot`

当前主系统运行时接收配置为：

```text
接收地址: http://192.168.8.254:8000/api/v1/video-bridge/fall-events
Header: X-Vision-Service-Token: vision-bridge-20260609
camera_id: camera_01
target_device_mac: CAMERA-192.168.8.253
target_elder_id: elder_demo_01
target_family_ids: family01
```

补充说明：

- 当前代码已支持将视频侧的 `CAMERA-192.168.8.253` 这类设备标识映射为主系统内部可注册的伪设备标识，同时保留原始 `target_device_mac` 在告警元数据中
- 当前新增验证测试已通过：
  - `python -m pytest tests/test_video_bridge_integration.py -q`

当前仍需现场确认的一点：

- Windows 防火墙入站 `TCP 8000` 是否已放行

在当前会话中尝试自动新增防火墙规则时，系统返回 `Access is denied`，因此跨机器访问如果失败，应优先检查这一步。

重要区分：

- `192.168.8.253:8000` 当前是 Vision Service
- `192.168.8.254:8000` 当前才是主系统接收端
- 因此访问 `http://192.168.8.253:8000/api/v1/video-bridge/fall-events` 返回 `404`，说明请求落到了视觉服务，而不是主系统应用

### 8.7 可直接发给视频侧工程师的最终接入说明模板

下面这段可直接复制给视频侧工程师：

```text
主系统接收端现已就绪，请视频侧按下面配置推送跌倒事件：

1. 主系统接收地址：
   POST http://192.168.8.254:8000/api/v1/video-bridge/fall-events

2. 请求头：
   X-Vision-Service-Token: vision-bridge-20260609
   Content-Type: application/json

3. 当前主系统已验证通过：
   - GET http://127.0.0.1:8000/healthz 正常
   - 本机回环推送 /api/v1/video-bridge/fall-events 成功
   - 返回 ok=true, accepted=true, pushed=true
   - 告警已进入主系统 alarms 和 queue

4. 推荐请求体至少包含这些字段：
   {
     "camera_id": "camera_01",
     "stream_name": "primary",
     "source": "vision_service",
     "event_type": "fall_confirmed",
     "state": "confirmed_fall",
     "status": "confirmed_fall",
     "service_state": "running",
     "severity": "L3",
     "risk": "high",
     "fall_detected": true,
     "fall_prob": 0.94,
     "incident_id": "fall-camera_01-001",
     "track_id": "target-001",
     "snapshot_url": "http://<vision-host>:8000/fall-events/snapshots/<filename>.jpg",
     "metadata": {
       "target_device_mac": "CAMERA-192.168.8.253"
     }
   }

5. 当前主系统侧绑定上下文：
   - camera_id: camera_01
   - target_device_mac: CAMERA-192.168.8.253
   - target_elder_id: elder_demo_01
   - target_family_ids: family01

6. 如果视频侧跨机器推送仍失败，请优先检查：
   - 是否能从视频侧机器访问 http://192.168.8.254:8000/healthz
   - 主系统机器 Windows 防火墙是否放行入站 TCP 8000
   - 双方是否处于可互通网段
```

### 8.8 视频侧仓库同步记录

以下记录仅描述视频侧 Vision Service 仓库的同步状态，不代表当前主系统仓库 `D:\health_original\health1` 已同步到相同提交。

```markdown
### 视频侧仓库同步记录

视频侧 Vision Service 仓库已同步主系统桥接目标配置。

- 仓库：`https://github.com/kangzhouyang/69-service-`
- 分支：`main`
- 提交：`fccce1d Update main system bridge target`
- 主系统接收端：`http://192.168.8.254:8000/api/v1/video-bridge/fall-events`
- 视觉服务机器：`192.168.8.253`
- 鉴权头：`X-Vision-Service-Token: <configured token>`
- 联调结果：视觉服务通过 `/alerting/simulation/send-once` 成功推送模拟跌倒事件，主系统返回 `ok=true / accepted=true / pushed=true`
```

## 9. 常见误区

### 9.1 不要把两个 `8000` 端口当成同一个服务

虽然主系统和独立视觉服务都可能监听 `8000`，但它们部署在不同机器上，角色不同，接口也不同。

### 9.2 `/healthz` 成功不代表桥接链路已经完全通

`/healthz` 只能说明单个服务活着，不能说明以下事项已经正确：

- 主系统配置的视觉服务地址正确
- 主系统能拉到 `/integration/results/{camera_id}/latest`
- 视觉服务能把跌倒事件成功推到主系统
- 主系统已成功生成业务告警

### 9.3 优先使用固定 IP，不要只写本机回环地址

`127.0.0.1` 只适合本机自测。跨机器联调时，主系统和视觉服务都应该配置成对方实际可访问的局域网 IP。

### 9.4 先做地址身份确认，再做告警联调

从当前版本开始，凡是涉及主系统、Vision Service、`/api/v1/vision/*`、`/integration/results/*`、跌倒检测、告警联调、前端弹窗联调的任务，都必须先执行：

- [主系统与视频系统地址确认规则](codex-debug-rules.md)

尤其不要直接把 `192.168.8.253` 或 `192.168.8.254` 当成固定身份。必须先通过 `/healthz`、`/status`、`/integration/results/camera_01/latest` 的接口特征确认角色，再决定 `VISION_SERVICE_BASE_URL` 应该指向谁。
