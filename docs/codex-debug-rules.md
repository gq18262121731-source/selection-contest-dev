# Vibe Coding / Codex 调试规则

## 规则 1：主系统与视频系统地址确认规则

### 适用场景

任何涉及以下内容的任务，都必须先执行本规则，再继续调试：

- 主系统
- Vision Service
- 视频系统
- 跌倒检测
- `/api/v1/vision/*`
- `/integration/results/*`
- 告警联调
- 前端弹窗联调

### 核心原则

不要根据固定 IP 判断系统身份。

`192.168.8.253` 和 `192.168.8.254` 只是当前网络下的临时地址。换 WiFi、换热点、重连后，它们可能互换。

必须通过接口特征确认谁是主系统，谁是 Vision Service。

### 系统身份判定

#### 1. 主系统判定

请求：

```text
GET http://<IP>:8000/healthz
```

如果返回包含：

```json
{
  "app": "AIoT Elder Care Monitoring System"
}
```

则该 `IP:8000` 是主系统。

#### 2. Vision Service 判定

请求：

```text
GET http://<IP>:8000/status
GET http://<IP>:8000/integration/results/camera_01/latest
```

如果返回中包含下列字段特征：

- `camera_id`
- `latest_result`
- `objects`
- `detector`
- `source_fps`
- `analysis_fps`
- `temporal`
- `fall_event_reporter`

则该 `IP:8000` 是 Vision Service。

#### 3. 禁止事项

禁止直接假设：

- `192.168.8.253 = 主系统`
- `192.168.8.254 = Vision Service`

也禁止直接假设：

- `192.168.8.254 = 主系统`
- `192.168.8.253 = Vision Service`

必须先探测接口。

### 联调前必须输出

在继续任何告警、弹窗、事件流排查前，必须先输出一份确认结果：

```text
Main System:
http://<confirmed-main-ip>:8000

Vision Service:
http://<confirmed-vision-ip>:8000

Camera ID:
camera_01

Main healthz result:
...

Vision status result:
...

Vision latest result:
...
```

### 配置规则

- 主系统的 `VISION_SERVICE_BASE_URL` 必须指向“已通过 Vision Service 判定”的地址。
- Flutter / PC 调试窗口中显示的 Vision Service 地址，必须来自主系统 `/api/v1/vision/health` 返回结果，而不是手写 IP。

### 必须立即停止继续调试的情况

当出现以下任一情况时，必须先停下，不允许继续排查 `alarm_type`、`metadata.event`、前端弹窗或告警去重：

1. 主系统 `/api/v1/vision/health` 返回 `timeout`
2. Vision Service `/integration/results/camera_01/latest` 返回 `404`
3. 某 IP 的 `/healthz` 返回 `AIoT Elder Care Monitoring System`，但它被配置成 Vision Service
4. 主系统读取到的是自己，而不是 Vision Service

结论：

先修地址配置，再继续联调。

### 推荐联调顺序

1. 识别主系统地址
2. 识别 Vision Service 地址
3. 修改或确认主系统 `VISION_SERVICE_BASE_URL`
4. 重启主系统
5. 验证 `/api/v1/vision/health`
6. 验证 `/api/v1/vision/results/latest`
7. 再进入 `incident_id -> alarm_id -> popup` 测试

### 一句话规则

先确认“谁是主系统、谁是 Vision Service”，再调试跌倒告警。不要用 IP 猜系统身份。
