# Robot Task Contract

本文档冻结 `health_new` 与 `go2-gateway` 之间的机器人任务契约。主系统负责告警决策、任务持久化、回调接收、状态展示和结果融合；`go2-gateway` 负责 Go2 执行能力，不把 Unitree SDK 暴露给主系统。

## 状态枚举

任务状态：

- `QUEUED`：主系统已创建任务，等待网关接收或执行。
- `RUNNING`：网关已接收任务，机器人正在执行。
- `COMPLETED`：任务完成并产生最终结果。
- `FAILED`：任务执行失败。
- `CANCELLED`：任务已取消。
- `BLOCKED`：任务因网关、机器人或能力前置条件不可用而阻塞。

任务步骤：

- `RECEIVED`：主系统收到跌倒事件并创建机器人任务。
- `PREFLIGHT`：机器人或网关执行前置检查。
- `MOVING`：机器人前往目标区域。
- `ARRIVED`：机器人到达目标区域。
- `CAMERA_CHECK`：机器人现场取证。
- `VOICE_PROMPT`：机器人语音询问。
- `WAITING_RESPONSE`：等待老人回应。
- `REPORTING`：回传最终结果并融合告警。

任务结果：

- `SAFE`：老人有回应，但主系统不自动解除跌倒告警。
- `NEED_HELP`：机器人现场确认老人需要帮助。
- `NO_RESPONSE`：机器人询问无回应。
- `UNKNOWN`：结果未知或证据不足。

## ID 定义

- `source_event_id`：camera-service 跌倒事件 ID，优先对应 `incident_id`。
- `external_task_id`：`health_new` 生成的机器人任务 ID，也是 `robot_tasks.task_id`。
- `gateway_task_id`：`go2-gateway` 内部任务 ID。
- `trace_id`：全链路追踪 ID。
- `callback_id`：单次回调唯一 ID。
- `sequence`：同一 Go2 任务内单调递增序号。

`health_new` 调用 `go2-gateway` 时，必须把本地 `task_id` 作为 `external_task_id` 发送，同时发送 `source_event_id` 和 `trace_id`。`go2-gateway` 回调时优先携带 `external_task_id`，也可以携带 `gateway_task_id` 或 `source_event_id` 兜底对账。

## 主系统到 go2-gateway

```http
POST /api/robot/events/fall
Content-Type: application/json
```

最小请求体：

```json
{
  "event": "fall_detected",
  "elder_id": "elder-001",
  "location": "bedroom",
  "confidence": 0.93,
  "source_event_id": "fall_event_001",
  "external_task_id": "robot_task_001",
  "trace_id": "trace_001",
  "camera_id": "camera_01",
  "metadata": {
    "alarm_id": "alarm_001",
    "source": "vision_service"
  }
}
```

## go2-gateway 回调主系统

阶段状态：

```http
POST /api/v1/robot/callbacks/task-status
Content-Type: application/json
```

```json
{
  "callback_id": "cb_001",
  "sequence": 4,
  "task_id": "go2_task_001",
  "external_task_id": "robot_task_001",
  "source_event_id": "fall_event_001",
  "trace_id": "trace_001",
  "status": "RUNNING",
  "step": "MOVING",
  "message": "机器人正在前往客厅",
  "occurred_at": "2026-07-21T10:31:06+08:00"
}
```

最终结果：

```http
POST /api/v1/robot/callbacks/task-result
Content-Type: application/json
```

```json
{
  "callback_id": "cb_result_001",
  "sequence": 10,
  "task_id": "go2_task_001",
  "external_task_id": "robot_task_001",
  "source_event_id": "fall_event_001",
  "trace_id": "trace_001",
  "status": "COMPLETED",
  "step": "REPORTING",
  "outcome": "NEED_HELP",
  "message": "机器人现场确认老人需要帮助",
  "observation": {
    "snapshot_url": "/api/tasks/go2_task_001/evidence/arrival.jpg",
    "camera_available": true,
    "voice_available": true,
    "response_type": "NEED_HELP",
    "transcript": "我摔倒了，暂时起不来"
  },
  "robot": {
    "robot_id": "go2_001",
    "battery": 76
  },
  "occurred_at": "2026-07-21T10:31:19+08:00"
}
```

## 幂等与乱序规则

1. `source_event_id` 在 `robot_tasks` 中唯一，同一跌倒事件重复到达只能返回原任务。
2. `callback_id` 唯一，重复回调安全返回，不重复写时间线。
3. `sequence <= last_sequence` 的回调只写入幂等确认，不覆盖较新任务状态。
4. 网关不可用、超时或机器人未就绪时仍保留任务，状态为 `BLOCKED`，原跌倒告警继续存在。
5. `SAFE` 不能自动关闭或删除跌倒告警；`NEED_HELP` 与 `NO_RESPONSE` 应升级或保持 `CRITICAL`。

