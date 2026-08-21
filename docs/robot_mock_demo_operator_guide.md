# 机器人 Mock 比赛演示操作手册

> 冻结版本：Step 4.4（2026-07-23）  
> 本手册只适用于 Mock 演示。它不证明真实 Go2、ROS2、Nav2、SLAM、L1 点云或真实音频已经可用。

## 1. 环境要求

- Windows，普通用户权限即可。
- `health` Python 环境可用；脚本会优先使用 `%USERPROFILE%\.conda\envs\health\python.exe`。
- `frontend/vue-dashboard/node_modules` 已按现有 lockfile 安装。
- 默认端口：Gateway `8090`、后端 `8000`、前端 `5173`；视频桥 `8093` 可选。
- 机器人保持关机。不要连接或填写机器人 IP。
- 演示库固定为 `data/robot_mock_demo.db`，正式 `data/app.db` 不参与。

## 2. 标准启动

在 `D:\health_new` 执行：

```powershell
.\scripts\start_robot_mock_demo.ps1
.\scripts\check_robot_mock_demo.ps1
```

启动顺序已冻结为：

1. go2-gateway Mock；
2. 初始化 Gateway Mock 地图；
3. 初始化专用演示 SQLite；
4. health_new 后端；
5. Vue 前端；
6. 可选 8093 视频桥（本脚本不会启动）。

如默认端口已被其他进程占用，不要结束未知进程。使用备用端口：

```powershell
.\scripts\start_robot_mock_demo.ps1 `
  -GatewayPort 18090 -BackendPort 18000 -FrontendPort 15173
```

脚本会拒绝占用端口、非 Mock 响应、`real_motion_enabled=true`、非回环 Gateway 地址和残留的未完成 demo 任务。进程、日志和数据库哈希记录在：

```text
artifacts/robot_mock_acceptance/runtime/process-manifest.json
artifacts/robot_mock_acceptance/logs/
```

## 3. 账号与角色

- 使用系统已有社区管理员账号登录，不在本文保存密码。
- 机器人状态、导航、应急处置需要管理员权限。
- 浏览器自动化使用仅存在于测试上下文的 `robot-demo-admin` 身份，不会写入正式账号数据。

## 4. 演示前检查

运行 `check_robot_mock_demo.ps1`，确认：

- `provider=mock`；
- `real_motion_enabled=false`；
- Gateway 和主系统均使用回环地址；
- active map 为 `map_mock_0001`；
- home、observation、3 个 patrol 点和巡逻路线存在；
- 七项安全联锁均通过；
- 正式 `app.db` SHA-256 与启动前一致；
- 8093 未启动时只影响视频画面，不影响 Mock 导航主线。

页面入口：

```text
#/robot-status
#/robot-navigation
#/robot-emergency?incidentId=...
#/robot-follow
```

## 5. 建图与巡逻演示

本阶段地图和点云均为 Mock。推荐使用预置 active map，不在比赛现场重新建图。

1. 打开机器人状态页，讲解 Mock 标识、控制权和七项联锁。
2. 打开导航页，确认 `map_mock_0001`。
3. 指出待命区、老人活动区观察点和三个巡逻点。
4. 选择 `robot-demo-patrol-route` 并启动巡逻。
5. 确认任务进入 `navigating`。
6. 执行人工接管，确认进入 `paused_manual / MANUAL`。
7. 释放人工控制，确认仍为 `paused_manual / NONE`，不会自动继续。
8. 点击继续，再次执行安全检查。
9. Mock 场景完成后，依次展示到达、返航和 `completed`。
10. 展示 timeline、navigation events 与 SQLite 持久化记录。

## 6. 跌倒应急演示

1. 由跌倒告警入口进入应急详情页。
2. 展示区域 `elderly_activity_area` 到 observation 点的映射。
3. 派发机器人，确认 `navigating`。
4. 执行“模拟到达并开始询问”，状态按顺序经过：
   `arrived → voice_prompting → waiting_response`。
5. 说明播报、ASR、TTS 均为 Mock，不存在真实音频。
6. 选择响应分支。

### safe_response

1. 选择“我没事”；
2. 确认进入 `waiting_admin_confirmation`，系统不自动解除；
3. 管理员点击“我已知晓”；
4. 再次确认七项联锁；
5. 点击解除并返航；
6. 执行 Mock 返航完成；
7. 确认 `completed / resolved`。

### need_help / no_response / uncertain

- 页面显示人工处置要求；
- 机器人保持原地；
- 不显示返航按钮；
- `resolve-and-return` 必须被拒绝；
- 告警不自动解除。

## 7. 联锁阻断展示

可依次选择：

- `localization_invalid`
- `map_not_loaded`
- `emergency_stop_active`
- `robot_offline`
- `path_not_plannable`
- `manual_takeover`

页面必须显示“机器人无法出动，请人工处置”和机器可读 `blocked_by`，不得提供绕过按钮。

## 8. 自动验收

先启动独立 Mock 栈，再执行：

```powershell
cd D:\health_new\frontend\vue-dashboard
npm run qa:robot-mock-full
```

脚本会覆盖巡逻、接管、四类应急、安全阻断、多页面、重连和清理。证据保存到：

```text
D:\health_new\artifacts\robot_mock_acceptance\
```

## 9. 正常停止与恢复

```powershell
cd D:\health_new
.\scripts\stop_robot_mock_demo.ps1
```

停止脚本只结束当前 manifest 记录且启动时间匹配的进程。不要直接批量结束 Python 或 Node。

需要重置专用演示库时：

```powershell
python .\scripts\cleanup_robot_mock_demo.py `
  --database .\data\robot_mock_demo.db --all-demo
python .\scripts\seed_robot_mock_demo.py `
  --database .\data\robot_mock_demo.db --map-id map_mock_0001
```

清理脚本拒绝 `data/app.db`。

## 10. 讲解底线

必须明确说“这是完整业务链路的 Mock 验证”。不得声称已完成真实机器人自主导航、真实建图、真实 L1 点云、真实语音或 ROS2/Nav2/SLAM 接入。

## 11. 比赛固定数据

展示名称与稳定 ID 固定如下：

| 类型 | 展示名称 | 稳定 ID / 约束 |
|---|---|---|
| 区域 | 养老活动区 | `elderly_activity_area` |
| 地图 | 养老活动区演示地图 | `map_mock_0001` |
| 待命点 | 机器人待命点 | `robot-demo-home` |
| 观察点 | 活动区观察点 | `robot-demo-observation-elderly-activity` |
| 巡逻点 | 客厅巡逻点 | `robot-demo-patrol-01` |
| 巡逻点 | 走廊巡逻点 | `robot-demo-patrol-02` |
| 巡逻点 | 门口巡逻点 | `robot-demo-patrol-03` |
| 路线 | 日常巡查路线 | `robot-demo-patrol-route` |
| 摄像头 | 摄像头 01 | `camera_01` |

seed 可重复执行；它更新上述固定演示记录，不创建重复主键。cleanup 只处理演示记录并拒绝正式 `data/app.db`。

## 12. 比赛固定操作顺序

### 第一部分：机器人状态

1. 打开 `#/robot-status`。
2. 指出统一提示：“当前为模拟导航环境，真实机器人运动控制已禁用。”
3. 展示网络、网关、DDS、LiDAR、定位、地图、电量与急停。
4. 展示七项安全联锁、更新时间、WebSocket 状态和 Go2 视频小窗。

### 第二部分：建图巡航

1. 打开 `#/robot-navigation`。
2. 展示 active 模拟地图、待命点、观察点、三个巡逻点和“日常巡查路线”。
3. 启动巡逻。
4. 申请遥控接管，确认任务进入暂停。
5. 释放控制权，强调任务不会自动恢复。
6. 点击“继续”，重新经过安全联锁。
7. 展示完成与返航结果。

### 第三部分：跌倒应急

1. 触发 `fall_confirmed` 并展示全局告警。
2. 点击“进入应急处置”；该操作不解除告警。
3. 派发机器人，模拟到达并开始询问。
4. 选择“模拟‘我没事’”。
5. 强调当前仍在等待管理员确认。
6. 点击“管理员确认并返回待命区”。
7. 点击“模拟完成返航”，展示 `completed` 只读终态。

备用分支：老人请求帮助、15 秒内无有效回应、无法可靠判断老人状态、定位无效、地图未加载。

## 13. 长时间稳定性验收

默认运行 45 分钟：

```powershell
cd D:\health_new
.\scripts\robot_mock_soak_test.ps1
```

快速验证可缩短：

```powershell
.\scripts\robot_mock_soak_test.ps1 `
  -DurationMinutes 5 `
  -SampleIntervalSeconds 10 `
  -CycleIntervalSeconds 60 `
  -RestartOwnedStack $false
```

脚本只连接 Mock 回环服务，检查正式数据库哈希，采样浏览器与服务进程内存、WebSocket、点云帧、WebGL、任务数量和 SQLite 状态。只有脚本自行启动的服务才会被停止；证据保存于 `artifacts/robot_mock_soak/<timestamp>/`。

完整比赛前后检查见 `docs/robot_mock_competition_checklist.md`。
