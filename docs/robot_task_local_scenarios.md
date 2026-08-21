# Robot Task Local Scenarios

本文档用于在没有真实 Go2 的情况下，验证 `health_new` 机器人任务闭环。默认主系统地址为 `http://127.0.0.1:8000`。

## 启动命令

后端：

```powershell
python run.py
```

前端：

```powershell
cd frontend/vue-dashboard
npm run dev
```

如需启用开发模拟接口：

```powershell
$env:ROBOT_SIMULATION_ENABLED="true"
python run.py
```

## 创建跌倒事件

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/video-bridge/fall-events `
  -H "Content-Type: application/json" `
  -d "{\"camera_id\":\"camera_01\",\"stream_name\":\"primary\",\"source\":\"vision_service\",\"event_type\":\"fall_confirmed\",\"state\":\"confirmed_fall\",\"status\":\"confirmed_fall\",\"risk\":\"critical\",\"risk_level\":\"critical\",\"fall_detected\":true,\"fall_prob\":0.93,\"fall_score\":0.93,\"track_id\":\"track_001\",\"incident_id\":\"fall_event_local_001\",\"snapshot_url\":\"http://127.0.0.1:8090/fall-events/snapshots/example.jpg\",\"metadata\":{\"elder_id\":\"elder-001\",\"elder_name\":\"张三\",\"location\":\"客厅\"}}"
```

查询任务：

```powershell
curl http://127.0.0.1:8000/api/v1/robot/tasks
```

## 场景 1：SAFE

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/robot/tasks/<task_id>/simulate-response `
  -H "Content-Type: application/json" `
  -d "{\"response_type\":\"SAFE\",\"transcript\":\"我没事，可以自己起来\"}"
```

预期：任务 `COMPLETED`，结果 `SAFE`；跌倒告警保留，不自动解除。

## 场景 2：NEED_HELP

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/robot/tasks/<task_id>/simulate-response `
  -H "Content-Type: application/json" `
  -d "{\"response_type\":\"NEED_HELP\",\"transcript\":\"我摔倒了，起不来\"}"
```

预期：任务 `COMPLETED`，结果 `NEED_HELP`；告警保持或升级为 `CRITICAL`，metadata 保存 transcript 和融合摘要。

## 场景 3：NO_RESPONSE

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/robot/tasks/<task_id>/simulate-response `
  -H "Content-Type: application/json" `
  -d "{\"response_type\":\"NO_RESPONSE\",\"transcript\":\"\"}"
```

预期：任务 `COMPLETED`，结果 `NO_RESPONSE`；告警升级为 `CRITICAL`，建议人工立即核实。

## 场景 4：ROBOT_BLOCKED

使用 Fake Gateway 返回：

```json
{
  "ok": true,
  "data": {
    "success": false,
    "error_code": "DDS_NOT_READY",
    "message": "robot motion stack is not ready"
  }
}
```

预期：任务 `BLOCKED`，`error_code=DDS_NOT_READY`；原跌倒告警继续存在。

## 场景 5：GATEWAY_UNAVAILABLE

停止 go2-gateway 或将 `ROBOT_GATEWAY_BASE_URL` 指向未监听端口。

预期：任务仍创建，状态 `BLOCKED`，`error_code=ROBOT_GATEWAY_UNAVAILABLE` 或 `ROBOT_GATEWAY_TIMEOUT`；原跌倒告警继续推送。

## 场景 6：DUPLICATE_EVENT

重复发送相同 `incident_id/source_event_id` 的跌倒事件。

预期：`robot_tasks.source_event_id` 唯一，主系统只保留一个机器人任务，第二次返回原任务摘要，不再次调度 Go2。

## 前端验证

打开：

```text
http://127.0.0.1:5173/#/robot-tasks
```

刷新页面后，任务、时间线和观测结果应从 REST 接口恢复；WebSocket 不可用时仍能通过“刷新”按钮查询持久化状态。

