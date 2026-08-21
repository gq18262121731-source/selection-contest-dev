# 机器人状态与 Mock 建图巡航前端契约

- 合同版本：`1.0.0`
- 冻结日期：`2026-07-22`
- 状态：Step 2 冻结，供 Step 3 及后续实现使用
- 适用项目：`health_new`

## 1. 目标与边界

本合同冻结社区管理员端“机器人状态”和“建图巡航”页面的路由、数据来源、接口语义及 Mock 标识。它不是现有功能完成声明。

第一阶段的硬约束如下：

```text
navigation_provider = mock
mapping_provider = mock
point_cloud_provider = mock
audio_provider = mock
manual_takeover_provider = mock
real_motion_enabled = false
```

本阶段不接入 ROS2、Nav2、SLAM Toolbox、真实 L1 点云、真实 Go2 音频或真实运动接口。现有只读 LiDAR 合同及 `mappingPrerequisitesReady` 语义保持不变；该字段不得被前端解释为“可以建图”或“可以导航”。

## 2. 现有代码基线

本合同基于以下真实代码约束冻结：

- 前端为 Vue 3、Vite、TypeScript、自定义 Hash Routing，当前未使用 Vue Router。
- 当前路由集中在 `src/composables/useHashRouting.ts`、`src/App.vue` 和 `src/components/layout/PrimaryNav.vue`。
- `RobotTaskCenterPage.vue` 是新页面的主要视觉与状态展示参考。
- `RobotFollowPage.vue` 及 `useGo2VideoBridge.ts` 已提供 8093 Go2 视频桥接逻辑。
- 浏览器现有机器人业务请求经 `health_new` 后端转发到 `go2-gateway:8090`；新接口沿用该边界。
- 当前 `GET /api/v1/robot/status` 已返回 `{ok, gateway, task_center}`，该结构不得破坏。
- 当前实时机器人事件复用 `/ws/alarms`；尚无独立机器人状态或导航 WebSocket。

## 3. 系统调用边界

```text
Vue 页面
  ├─ REST /api/v1/robot/** ──> health_new 后端 ──> go2-gateway
  ├─ WS /ws/robot/status ───> health_new 后端（Step 4 待实现）
  ├─ WS /ws/robot/navigation > health_new 后端（Step 4 待实现）
  ├─ WS /ws/robot/point-cloud > health_new 后端 Mock 代理（Step 4 待实现）
  ├─ WS /ws/alarms ─────────> 现有告警通道
  └─ 8093 视频桥 ───────────> 仅复用现有 Go2 视频链路
```

禁止浏览器直接访问 `go2-gateway:8090`。8093 仅用于现有 Go2 视频状态和 MJPEG 流，不承载机器人控制。

## 4. 页面与权限

### 4.1 机器人状态页

- Hash：`#/robot-status`
- 建议文件：`src/views/RobotStatusPage.vue`
- 权限：仅 `community`、`admin`
- 视觉参考：`src/views/RobotTaskCenterPage.vue`

页面必须展示：网关、网络、DDS、机器人在线状态、LiDAR 诊断摘要、电量、急停、定位、地图、当前控制权、当前任务、机器可读错误码和更新时间。

LiDAR 展示必须保留 `unknown/null` 语义，并明确区分：探测失败、话题未发现、零样本、样本过期和样本稳定。不得将“DDS 无状态样本”显示成“雷达不存在”。

### 4.2 建图巡航页

- Hash：`#/robot-navigation`
- 建议文件：`src/views/RobotNavigationPage.vue`
- 权限：仅 `community`、`admin`
- 视觉参考：`RobotTaskCenterPage.vue`；视频复用 `RobotFollowPage.vue` 的桥接能力

页面第一阶段可展示 Mock 建图、Mock 二维栅格地图、Mock 点位、Mock 巡逻路线、Mock 点云和 Mock 控制权接管。所有相关控件旁必须持续可见地标识“模拟数据/Mock”，不得只在帮助文本中说明。

网页不提供前进、后退、转向或速度控制按钮。所谓“遥控接管”仅模拟控制权从 `NAVIGATION` 切换为 `MANUAL`，不发送方向或速度指令。

### 4.3 应急详情页的路由占位

- Hash：`#/robot-emergency?incidentId=<incident_id>`
- 建议文件：`src/views/RobotEmergencyPage.vue`
- 不设置永久侧边栏入口；仅从告警弹窗或任务中心进入

该页面的完整语义见 `robot_emergency_workflow_contract.md`。

## 5. 能力状态模型

所有尚未验证的真实能力使用以下枚举，不允许使用含糊布尔值冒充可用：

```text
mock
unavailable
not_verified
blocked
ready
```

第一阶段导航相关能力必须至少返回：

```json
{
  "provider": "mock",
  "real_motion_enabled": false,
  "mapping": "mock",
  "navigation": "mock",
  "patrol": "mock",
  "return_home": "mock",
  "point_cloud": "mock",
  "audio_input": "mock",
  "audio_output": "mock",
  "manual_takeover": "mock",
  "ros2": "unavailable",
  "nav2": "unavailable",
  "slam_toolbox": "unavailable",
  "real_lidar_point_cloud": "not_verified"
}
```

`ready` 只允许用于已有证据且当前可用的真实能力；第一阶段不得对真实导航能力返回 `ready`。

## 6. HTTP 返回约定

### 6.1 现有状态接口兼容

`GET /api/v1/robot/status` 是现有接口，继续保留：

```json
{
  "ok": true,
  "gateway": {},
  "task_center": {
    "persisted": true,
    "task_count": 0,
    "current_task": null
  }
}
```

Step 3 只能增添可选字段，不得删除、重命名或改变现有字段类型。新状态页的技术诊断使用新增的 `/status/diagnostics`，避免重新定义旧接口。

### 6.2 Step 3 新接口 envelope

除上述兼容接口外，本合同新增接口统一返回：

```json
{
  "success": true,
  "code": "OK",
  "message": "ok",
  "data": {},
  "timestamp": "2026-07-22T10:00:00+08:00"
}
```

- 未就绪、被安全联锁阻止或真实运动关闭属于可预期业务状态，返回 HTTP 200 或 409，并提供稳定 `code`；不得依赖中文 `message` 判断状态。
- 参数错误返回 HTTP 4xx。
- health_new 或网关不可恢复故障返回 HTTP 503。
- 所有写操作必须支持幂等键；具体请求头或字段名留到 Step 3 与现有任务幂等机制统一。

## 7. health_new REST 接口

以下除 `/status` 外均为 Step 3/4 待实现合同。

### 7.1 状态与诊断

```http
GET /api/v1/robot/status
GET /api/v1/robot/status/diagnostics
GET /api/v1/robot/navigation/capabilities
GET /api/v1/robot/navigation/state
```

`/status/diagnostics` 至少返回：

```json
{
  "network_reachable": true,
  "gateway_reachable": true,
  "dds_initialized": true,
  "dds_state_available": false,
  "robot_online": false,
  "motion_ready": false,
  "lidar": {},
  "localization_ready": false,
  "map_loaded": false,
  "emergency_stop_active": false,
  "control_owner": "NONE",
  "current_task_id": null,
  "error_codes": ["UNITREE_DDS_NO_STATE_SAMPLES"],
  "updated_at": "2026-07-22T10:00:00+08:00"
}
```

LiDAR 对象直接适配现有只读 `LidarStatusService` 语义，不复制检测逻辑。

### 7.2 Mock 地图

```http
POST /api/v1/robot/navigation/mapping/start
POST /api/v1/robot/navigation/mapping/stop
POST /api/v1/robot/navigation/maps/preview
POST /api/v1/robot/navigation/maps/save
GET  /api/v1/robot/navigation/maps/active
```

写接口响应必须回显 `provider="mock"`、`real_motion_enabled=false`、Mock 会话或地图标识及当前状态。`maps/save` 只保存 Mock 地图业务记录，不保存、覆盖或加载真实机器人地图。

### 7.3 点位

```http
GET    /api/v1/robot/navigation/points
POST   /api/v1/robot/navigation/points
PUT    /api/v1/robot/navigation/points/{point_id}
DELETE /api/v1/robot/navigation/points/{point_id}
```

点位 DTO：

```json
{
  "point_id": "point_xxx",
  "name": "养老活动区观察点",
  "point_type": "home",
  "x": 1.2,
  "y": 2.4,
  "yaw": 1.57,
  "map_id": "map_mock_default",
  "status": "valid"
}
```

`point_type` 仅允许 `home | observation | patrol`。坐标仅属于 health_new 的 Mock 地图域，不得由 camera-service 上报，也不得转化为真实运动命令。

### 7.4 巡逻路线与任务控制

```http
GET  /api/v1/robot/navigation/routes
POST /api/v1/robot/navigation/routes
GET  /api/v1/robot/navigation/routes/{route_id}
POST /api/v1/robot/navigation/routes/{route_id}/start
POST /api/v1/robot/navigation/tasks/{task_id}/pause
POST /api/v1/robot/navigation/tasks/{task_id}/resume
POST /api/v1/robot/navigation/tasks/{task_id}/stop
```

路线只引用已存在且 `status=valid` 的 Mock 点位 ID。第一版不冻结停留时间。恢复任务前必须重新执行完整安全联锁。

### 7.5 health_new 到 go2-gateway 的适配关系

| health_new 对前端接口 | go2-gateway 上游或处理方 |
| --- | --- |
| `/status/diagnostics` | 聚合现有网关状态、DDS 与只读 LiDAR 状态 |
| `/navigation/capabilities` | `GET /api/navigation/capabilities` |
| `/navigation/state` | `GET /api/navigation/state` |
| `/mapping/start`、`/mapping/stop` | 同名 `/api/navigation/mapping/*` |
| `/maps/preview` | health_new 读取停止建图后返回的 Mock 预览描述，不另启真实建图 |
| `/maps/save`、`/maps/active` | 调用网关 Mock 地图状态；业务元数据由 health_new 负责 |
| `/points/**`、`/routes` 的增删改查 | health_new 业务层，不向网关发送运动命令 |
| `/routes/{route_id}/start` | health_new 解析有效点位后调用 `POST /api/navigation/patrol/start` |
| `/tasks/{task_id}/pause\|resume\|stop` | 同名网关 Mock 任务控制接口 |
| `/emergency/{incident_id}/dispatch` | `POST /api/navigation/emergency/dispatch` |
| `/emergency/{incident_id}/resolve-and-return` | health_new 完成人工确认后调用 `POST /api/navigation/return-home` |
| `/ws/robot/point-cloud` | 代理网关 `WS /ws/navigation/point-cloud` 的有界 Mock 数据 |

health_new 不透传 camera-service 的 `area_id` 作为导航目标；必须先解析成受当前 Mock 地图版本约束的 `target_point_id`。

## 8. WebSocket 契约

页面首次进入先获取 REST 完整快照，再接收增量事件；重连后必须重新拉取快照。

```text
/ws/robot/status          Step 4 待实现，低频状态变化
/ws/robot/navigation      Step 4 待实现，Mock 任务及控制权变化
/ws/robot/point-cloud     Step 4 待实现，独立 Mock 点云流
/ws/alarms                现有通道，继续承载告警和应急事件
```

普通事件结构：

```json
{
  "type": "robot_navigation_updated",
  "sequence": 12,
  "timestamp": "2026-07-22T10:00:00+08:00",
  "data": {}
}
```

前端必须按 `sequence` 忽略同一流中的重复或倒序事件。点云不得通过 `/ws/alarms` 发送，也不得使用高频 REST 轮询替代。

## 9. UI 安全规则

- 所有启动、继续、返航操作都显示最新安全联锁结果。
- `real_motion_enabled=false` 时，不出现“真实执行中”措辞。
- Mock 导航可视化只表示状态机推进，不代表机器人发生物理位移。
- 急停激活时，所有启动和恢复操作禁用。
- `control_owner=MANUAL` 时，导航显示暂停；释放后不得自动继续，必须由管理员点击继续并重新联锁。
- 覆盖 Mock 正式地图前需要二次确认，并提示旧点位失效；具体持久化规则留到 Step 3。

## 10. 错误码最小集合

```text
ROBOT_OFFLINE
DDS_NOT_READY
LIDAR_NOT_READY
LOCALIZATION_INVALID
MAP_NOT_LOADED
MAP_POINTS_INVALID
EMERGENCY_STOP_ACTIVE
PATH_NOT_PLANNABLE
CONTROL_NOT_AVAILABLE
MANUAL_CONTROL_ACTIVE
NAVIGATION_NOT_READY
REAL_MOTION_DISABLED
MOCK_PROVIDER_REQUIRED
```

## 11. 明确禁止

1. 引入 Vue Router 或绕过现有角色权限。
2. 浏览器直接请求 8090。
3. 复制 Go2 视频连接逻辑或把 8093 当作控制通道。
4. 将 `mappingPrerequisitesReady=true` 解释为导航可用。
5. 从页面发送 `/cmd_vel`、速度、姿态或真实目标点。
6. 将 Mock 点位、路径、地图或点云标记为真实数据。
7. 用 `/ws/alarms` 传输点云。
8. 在第一阶段自动重试被安全联锁阻止的运动任务。

## 12. Step 3 待决定

- 新 DTO 的 Pydantic/TypeScript 具体类名与文件拆分。
- Mock 地图、点位、路线的 SQLite 表结构及版本失效策略。
- 幂等键沿用请求字段还是 HTTP Header。
- 三个新增 WebSocket 的连接管理是否扩展现有 `WebSocketManager`。
- Mock 点云帧格式、点数上限、刷新频率和 Three.js 是否获准新增依赖。
- 8093 视频逻辑抽取为共享组件的最小实现方式。

这些事项不得改变本合同冻结的调用方向、Mock 标识和 `real_motion_enabled=false`。
