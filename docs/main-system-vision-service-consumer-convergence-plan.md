# Main System Vision Service Consumer Convergence Plan

## 1. 当前结论

- 当前仓库是主系统，不是摄像头系统。
- 主系统不应继续拥有 RTSP 真相。
- RTSP、拉流、检测、WebRTC、实时结果生成，属于摄像头系统 / Vision Service。
- 主系统只保存服务消费侧真相。
- 旧本地摄像头路径可以短期保留为兼容 / 调试 fallback，但不能继续作为未来架构中心。

换句话说：

```text
主系统未来的中心
不是 RTSP
而是 Vision Service API Contract
```

## 2. 新职责边界

### 主系统负责

- 保存 Vision Service 的服务地址
- 保存默认 `camera_id`
- 读取 Vision Service 状态
- 展示摄像头系统运行状态
- 接收或查询视觉分析结果
- 后续按需接收告警或事件
- 将视觉结果与老人、房间、社区业务对象关联

### 摄像头系统 / Vision Service 负责

- RTSP 真相
- 摄像头连接
- 拉流
- 解码
- WebRTC
- 最新帧
- YOLO / Pose / Tracking
- Fall 判断
- 视觉分析结果生成
- 摄像头运行状态输出

## 3. 重新定义 Camera Truth

主系统中的 camera truth 不再是：

- `rtsp_url`
- `rtsp_host`
- `rtsp_port`
- `stream_path`

而应改为：

- `vision_service_base_url`
- `identity_service_base_url`
- `default_camera_id`
- `source_owner = vision_service`
- optional auth / token
- optional service profile

建议示例：

```json
{
  "source_owner": "vision_service",
  "vision_service_base_url": "http://127.0.0.1:8000",
  "identity_service_base_url": "http://127.0.0.1:8100",
  "default_camera_id": "camera_01",
  "mode": "external_vision_service",
  "auth": {
    "type": "none"
  }
}
```

这意味着：

```text
主系统的 truth
不再是 RTSP truth
而是 service endpoint truth
```

## 4. 旧模式遗留降级

当前主系统中的旧模式遗留包括：

- `.env` 中的 RTSP 字段
- `camera_registry.json`
- `camera_live_config.runtime.json`
- `camera_runtime_external/*`
- `backend/services/camera_source_registry.py`
- `backend/services/camera_service.py`
- `backend/api/camera_api.py`
- `backend/api/camera_source_api.py`

这些路径可以暂时保留，但定位必须降级为：

- compatibility fallback
- local debug fallback
- legacy camera runtime
- not future architecture center

治理原则：

- 不再把这些路径视为未来主架构中心
- 不再围绕它们继续扩展主系统职责
- 仅在兼容、排障、调试、本地演示场景下保留有限价值

## 5. Vision Service 接口契约

根据摄像头端接口文档，主系统未来应优先消费：

- `GET /healthz`
- `GET /status`
- `GET /stream/source`
- `GET /stream/latest-frame.jpg`
- `WS /ws/results`
- `GET /integration/results/{camera_id}/latest`

身份服务优先消费：

- `GET /healthz`
- `POST /identity/enroll`
- `POST /identity/match`
- `GET /identity/list`
- `DELETE /identity/{person_id}`

第一阶段边界：

- 主系统当前第一阶段只做只读状态消费，不做控制类接口集成。

控制类接口如：

- `POST /stream/start`
- `POST /stream/switch-host`
- `POST /stream/stop`
- `POST /alerting/*`
- `POST /identity/enroll`

暂不作为第三批最小目标。

## 6. 推荐收敛路线

### P0：明确主系统只消费 Vision Service

不再把主系统作为 camera runtime owner。

### P1：重定义主系统 camera truth

从 RTSP truth 改为 service endpoint truth。

### P2：新增单一适配层

建议未来新增：

`backend/services/vision_service_client.py`

统一访问：

- `/healthz`
- `/status`
- `/stream/source`
- `/integration/results/{camera_id}/latest`
- `/ws/results`

### P3：新增主系统只读接口

建议未来新增：

- `GET /api/v1/vision/health`
- `GET /api/v1/vision/status`
- `GET /api/v1/vision/source`
- `GET /api/v1/vision/results/latest`

第一阶段只读透传或轻量标准化。

### P4：前端只展示状态

前端只展示：

- Vision Service 是否在线
- `camera_id`
- `stream_state`
- `frame_age_ms`
- detection loaded
- pose / fall / pipeline 状态

不接 RTSP。  
不控制摄像头。  
不触发现有告警链路。

### P5：再评估深度集成

只读链路稳定后，再评估：

- Fall 事件接入
- Video Bridge 去留
- 告警联动
- 身份服务接入
- 移动端展示

## 7. 第三批最小目标重定义

第三批不再定义为：

- 接新 fall 链路
- 接 Video Bridge
- 改 `main.py` 大量代码
- 接告警链路

第三批应重新定义为：

```text
主系统以只读方式消费外部 Vision Service 状态
```

最小完成标准：

- 主系统能读取 Vision Service `/healthz`
- 主系统能读取 Vision Service `/status`
- 主系统能读取默认 `camera_id` 的 `/stream/source`
- 主系统能读取最新 vision result
- 主系统能在 Vision Service 不可用时明确显示 `unavailable` / `timeout` / `stale`
- 不改变现有业务行为
- 不影响现有告警链路
- 不影响移动端主入口

## 8. Go / No-Go 条件

### Go 条件

- 摄像头系统接口文档已确认
- Vision Service 可访问
- 主系统服务级 truth 已定义
- 只读 client 能独立验证
- 不需要修改现有 fall 主链路
- 不需要接 RTSP

### No-Go 条件

- 需要主系统继续维护 RTSP
- 需要主系统直接启动摄像头流
- 需要改动现有告警主链路
- 需要替换现有 fall 链路
- 需要大面积修改 `main.py` / `dependencies.py` / `config.py`
- Vision Service 接口尚未稳定

## 9. 决策摘要

当前问题不再是“统一主系统内的 RTSP 配置”，而是“让主系统从旧摄像头内置模式收敛为外部 Vision Service 消费者模式”。

主系统未来的中心不应该是：

```text
RTSP
```

而应该是：

```text
Vision Service API Contract
```

阶段性结论：

- 主系统应停止继续扩张内置摄像头职责
- 主系统应收敛为外部 Vision Service 的只读消费者
- 第三批最小目标应聚焦于状态消费，而不是检测、告警或 RTSP 控制
- 在只读链路稳定之前，不进入更深的 fall / Video Bridge / alarm 集成
