# 摄像头源层约定

当前项目保留两套摄像头接入方案，但摄像头本身不再承担业务身份。

## 命名

- `camera1`：默认复用原 `.env` 里的 `CAMERA_*` 配置。当前现场约定 `192.168.8.253` 是 `camera1`。
- `camera2`：优先读取 `CAMERA2_*`，未配置时回退到 `camera_runtime_external/camera_live_config.runtime.json` 或 `camera_live_config.json`。

## 职责边界

摄像头源层只负责：

- 视频状态检测
- 当前截图
- MJPEG/WS 视频流转发
- 声音轨道检测
- 局域网声音监听流
- 对讲能力诊断和后续厂商网关接入预留

摄像头源层不负责：

- 家属端展示布局
- 跌倒检测算法
- 目标老人识别
- 告警策略
- 业务角色绑定

## 后端接口

- `GET /api/v1/camera-sources`
- `GET /api/v1/camera-sources/{camera_id}`
- `GET /api/v1/camera-sources/{camera_id}/status`
- `GET /api/v1/camera-sources/{camera_id}/snapshot`
- `GET /api/v1/camera-sources/{camera_id}/stream.mjpg`
- `GET /api/v1/camera-sources/{camera_id}/stream-status`
- `GET /api/v1/camera-sources/{camera_id}/audio/status`
- `GET /api/v1/camera-sources/{camera_id}/audio/stream-status`
- `GET /api/v1/camera-sources/{camera_id}/talk/status`
- `POST /api/v1/camera-sources/{camera_id}/ptz`

## WebSocket

- `/ws/camera-sources/{camera_id}`
- `/ws/camera-sources/{camera_id}/audio/listen`

## 后续接入方式

前端、跌倒检测、目标老人识别等业务模块以后只传 `camera_id`：

```text
camera1/camera2 -> 摄像头源层 -> 前端或算法按需订阅
```

不要在业务代码里写死 `192.168.8.253` 或 `192.168.8.248` 的业务含义。
