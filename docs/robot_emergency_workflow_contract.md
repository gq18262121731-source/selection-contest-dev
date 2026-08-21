# 跌倒事件机器人应急处置契约

- 合同版本：`1.0.0`
- 冻结日期：`2026-07-22`
- 状态：Step 2 冻结，供 Step 3 及后续实现使用
- 适用项目：`health_new`，并约束与 `camera-service`、`go2-gateway` 的协作

## 1. 目标

本合同冻结 `fall_confirmed` 进入 health_new 后的告警、区域映射、机器人任务、Mock 导航、Mock 音频对话、人工确认和升级处置流程。

第一阶段仅证明业务闭环和状态可观测性，不证明真实机器人能够到达现场：

```text
navigation_provider = mock
audio_input_provider = mock
audio_output_provider = mock
manual_takeover_provider = mock
real_motion_enabled = false
```

## 2. 职责边界

### camera-service

负责确认跌倒并上报事件、`incident_id`、`camera_id`、可选 `area_id` 和可选 `area_name`。不得选择机器人点位、提供地图坐标、创建机器人任务或调用机器人接口。

### health_new

负责事件接收与幂等、告警创建、区域到观察点映射、应急记录、机器人任务创建、调用 go2-gateway、持久化、WebSocket 推送、移动端告警和结构化对话判断。

### go2-gateway

负责第一阶段 Mock 安全联锁、Mock 执行状态、控制权状态机、Mock 导航/返航及回调。不得调用真实运动、真实点云、真实 Go2 音频、ROS2 或 Nav2。

## 3. 摄像头事件入口

health_new 当前真实入口为：

```http
POST /api/v1/video-bridge/fall-events
```

camera-service 若以基础 URL 配置 `/api/v1`，配置中可能仅显示 `/video-bridge/fall-events`；线上的最终请求路径必须以上述完整路径为准。

输入保持现有字段兼容，并允许新增两个顶层可选字段：

```json
{
  "event_type": "fall_confirmed",
  "incident_id": "incident_20260722_001",
  "camera_id": "camera_01",
  "timestamp": "2026-07-22T10:00:00+08:00",
  "risk_level": "high",
  "fall_prob": 0.96,
  "track_id": "track_12",
  "bbox": [100, 120, 320, 520],
  "area_id": "elderly_activity_area",
  "area_name": "养老活动区"
}
```

`area_id`、`area_name` 缺失不得导致旧事件被拒绝。health_new 当前请求模型允许额外字段，Step 3 应把这两个字段提升为显式可选字段并做长度校验，同时保持 `extra="allow"` 的旧版本兼容性。

## 4. 事件幂等与区域映射

- `incident_id` 是首选事件幂等键；缺失时继续使用现有事件接收逻辑生成或回退标识。
- 重复事件可更新已有告警证据，但不得重复创建应急任务。
- health_new 是区域映射的唯一责任方。
- 映射输入优先级为：显式 `area_id`，再使用 health_new 已有的 `camera_id/location` 配置回退。
- camera-service 提供的 `area_name` 仅用于显示，不作为机器人调度键。

映射的业务形态：

```json
{
  "camera_id": "camera_01",
  "area_id": "elderly_activity_area",
  "observation_point_id": "fall_observation_point",
  "home_point_id": "robot_home"
}
```

如果区域或点位不能解析：

1. 告警仍须创建并推送；
2. 机器人待处置任务仍须保留；
3. 任务标记为 `BLOCKED`，错误码为 `AREA_MAPPING_NOT_FOUND` 或 `OBSERVATION_POINT_NOT_FOUND`；
4. 不自动猜测坐标，不自动重试运动；
5. 页面提示“机器人无法出动，请人工处置”。

## 5. 标准流程

```text
camera-service 上报 fall_confirmed
→ health_new 幂等接收
→ 创建/关联高优先级告警
→ 根据 area_id 或 camera_id 解析观察点
→ 创建应急任务和关联记录
→ 请求 go2-gateway 执行安全联锁
→ Mock 导航到观察点
→ Mock TTS 播放询问状态
→ Mock ASR 提供文本或超时
→ health_new 进行结构化对话判断
→ safe_response / need_help / no_response / uncertain
→ 人工确认返航或升级人工处置
```

即使网关离线、联锁失败或区域映射失败，告警创建也不得回滚。

## 6. 状态兼容

health_new 现有 `RobotTask` 使用：

```text
status: QUEUED | RUNNING | COMPLETED | FAILED | CANCELLED | BLOCKED
step: RECEIVED | PREFLIGHT | MOVING | ARRIVED | CAMERA_CHECK |
      VOICE_PROMPT | WAITING_RESPONSE | REPORTING
outcome: SAFE | NEED_HELP | NO_RESPONSE | UNKNOWN
```

Step 3 不替换该模型。应急详情需要的细粒度阶段使用独立 `execution_state`：

```text
created
safety_checking
blocked
queued
navigating
paused_manual
paused_admin
arrived
voice_prompting
waiting_response
safe_response
help_requested
no_response
uncertain
waiting_admin_confirmation
returning_home
completed
failed
cancelled
```

`execution_state` 必须映射回现有 `status/step/outcome`，不得出现两个互相矛盾的任务终态。具体映射代码和存储位置留到 Step 3。

## 7. 安全联锁

以下操作必须由 go2-gateway 在每次执行前重新检查：首次 Mock 出发、暂停后继续、人工接管释放后继续、Mock 返航。

```json
{
  "passed": false,
  "checks": {
    "robot_online": true,
    "emergency_stop_clear": true,
    "localization_valid": false,
    "map_loaded": true,
    "path_plannable": false,
    "robot_stationary": true,
    "control_available": true
  },
  "blocked_by": ["LOCALIZATION_INVALID", "PATH_NOT_PLANNABLE"],
  "checked_at": "2026-07-22T10:00:00+08:00"
}
```

第一阶段这些检查由 Mock 场景生成，但返回结构与未来真实实现一致。`passed=true` 只允许推进 Mock 状态机，不得放开真实运动。

## 8. 控制权

统一枚举：

```text
NONE
MANUAL
NAVIGATION
FOLLOW
EMERGENCY_STOP
```

规则：同一时刻只有一个控制者；`EMERGENCY_STOP` 优先级最高；`MANUAL` 高于 `NAVIGATION`。Mock 人工接管将任务置为 `paused_manual` 并保留任务上下文；释放控制权后不得自动继续，管理员必须点击继续并重新执行完整安全联锁。

第一阶段“人工接管”不包含方向、速度、姿态或真实遥控器输入，只模拟所有权变化。

## 9. 对话与处置规则

ASR、TTS 及 Go2 麦克风/扬声器全部为 Mock。health_new 可复用现有 Qwen/DashScope OpenAI 兼容调用方式，但应急对话必须请求：

```json
{
  "response_format": {"type": "json_object"}
}
```

严格校验的结果结构：

```json
{
  "intent": "safe_response",
  "confidence": 0.92,
  "reply_text": "好的，请您先保持原位，工作人员会进一步确认。",
  "recommended_action": "wait_admin_confirmation",
  "conversation_complete": true
}
```

模型允许返回的 `intent` 为 `safe_response | need_help | uncertain`；`no_response` 由 15 秒无有效响应的确定性规则产生。

硬规则优先于模型：

- 明确求助关键词：`need_help`。
- 15 秒无有效响应：`no_response`。
- JSON 非法、超时、低置信度或服务失败：`uncertain`。
- 模型不得解除告警、命令返航、关闭任务或直接调用网关。

分支行为：

| 结果 | 机器人状态 | 告警行为 | 自动返航 |
| --- | --- | --- | --- |
| `safe_response` | 原地等待管理员确认 | 保持未解除 | 禁止 |
| `need_help` | 原地等待人工处置 | 立即升级并推送 | 禁止 |
| `no_response` | 原地等待人工处置 | 立即升级并推送 | 禁止 |
| `uncertain` | 按求助分支处理 | 立即升级并推送 | 禁止 |

只有 `safe_response` 且管理员主动执行“解除告警并返回待命区”时，才可再次联锁并启动 Mock 返航。

## 10. health_new 应急 API

以下接口为 Step 3/4 待实现；均使用 `robot_navigation_frontend_contract.md` 定义的新接口 envelope：

```http
GET  /api/v1/robot/emergency/{incident_id}
POST /api/v1/robot/emergency/{incident_id}/acknowledge
POST /api/v1/robot/emergency/{incident_id}/dispatch
POST /api/v1/robot/emergency/{incident_id}/pause
POST /api/v1/robot/emergency/{incident_id}/resume
POST /api/v1/robot/emergency/{incident_id}/escalate
POST /api/v1/robot/emergency/{incident_id}/resolve-and-return
GET  /api/v1/robot/emergency/{incident_id}/dialogue
GET  /api/v1/robot/tasks/{task_id}/navigation-events
```

现有接口继续保留：

```http
GET  /api/v1/robot/tasks/{task_id}
GET  /api/v1/robot/tasks/{task_id}/timeline
POST /api/v1/robot/tasks/{task_id}/cancel
POST /api/v1/robot/tasks/{task_id}/simulate-response
```

`acknowledge` 只记录管理员已看到，不解除告警、不停止任务、不触发返航。`dispatch` 在自动派发失败或被策略关闭时用于显式重试；不得绕过安全联锁。

`resolve-and-return` 的最小前置条件：

```text
intent = safe_response
execution_state = waiting_admin_confirmation
robot_stationary = true
robot_online = true（Mock 场景中的状态）
emergency_stop_clear = true
localization_valid = true（Mock）
map_loaded = true（Mock）
path_plannable = true（Mock）
control_available = true
real_motion_enabled = false
```

## 11. 告警与实时同步

继续复用现有 `/ws/alarms` 和现有 Web/Flutter 告警框架，不新建第二套应急通知通道。

告警增量元数据至少允许：

```json
{
  "incident_id": "incident_20260722_001",
  "robot_task_id": "task_xxx",
  "area_id": "elderly_activity_area",
  "area_name": "养老活动区",
  "robot_execution_state": "navigating",
  "robot_position_label": "前往观察点",
  "dialogue_intent": null,
  "asr_text": null,
  "provider": "mock",
  "real_motion_enabled": false
}
```

Web 管理端弹窗按钮：

- “进入应急处置”：进入 `#/robot-emergency?incidentId=...`。
- “我已知晓”：仅确认并关闭当前弹窗。

Flutter 继续使用 REST 初始快照、`/ws/alarms`、Provider 和 `GlobalAlarmListener`。`need_help`、`no_response`、`uncertain` 均触发高优先级弹窗；不得重写告警框架。

## 12. 应急详情页内容

页面仅显示事件文字摘要、Go2 现有视频、Mock 导航进度、控制权变化、对话记录和操作按钮。

页面不得显示固定摄像头视频或固定摄像头快照，避免扩大敏感影像暴露。Go2 视频继续复用 8093 链路，并明确它不属于 Mock 导航控制通道。

## 13. 错误码最小集合

```text
AREA_MAPPING_NOT_FOUND
OBSERVATION_POINT_NOT_FOUND
ROBOT_OFFLINE
EMERGENCY_STOP_ACTIVE
LOCALIZATION_INVALID
MAP_NOT_LOADED
PATH_NOT_PLANNABLE
CONTROL_NOT_AVAILABLE
MANUAL_CONTROL_ACTIVE
NAVIGATION_NOT_READY
AUDIO_INPUT_NOT_VERIFIED
AUDIO_OUTPUT_NOT_VERIFIED
ASR_NOT_CONFIGURED
TTS_NOT_CONFIGURED
DIALOGUE_MODEL_FAILED
NO_RESPONSE
SAFE_RESPONSE_REQUIRES_ADMIN
REAL_MOTION_DISABLED
```

## 14. 明确禁止

1. camera-service 指定点位、坐标或机器人命令。
2. health_new 前端直连 8090。
3. 安全联锁失败后自动重试运动。
4. 模型输出直接改变告警终态或机器人控制权。
5. `safe_response` 自动解除告警或自动返航。
6. 求助、无响应或不确定时自动返航。
7. 第一阶段调用真实 Go2 运动、真实 ASR/TTS、真实麦克风或扬声器。
8. 以 Mock 到达状态声称机器人已物理到达现场。

## 15. Step 3 待决定

- 区域映射和应急记录是复用现有表的 JSON 字段还是新增表；任何数据库变更须在 Step 3 单独确认。
- 细粒度 `execution_state` 的存储位置及与现有状态的完整映射表。
- 自动派发开关、失败后的人工重试幂等键和超时策略。
- Qwen 调用是否在第一阶段启用真实服务，或先提供确定性 Mock 对话 Provider。
- 告警元数据在 Web 与 Flutter 模型中的具体可选字段定义。
- Mock ASR 场景切换入口与审计记录格式。

这些细节不得改变“health_new 决策和建任务、go2-gateway Mock 执行、camera-service 只感知”的边界。
