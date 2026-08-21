# 机器人 Mock 演示故障降级手册

| 现象 | 判断 | 处理步骤 | 可继续演示 | 替代内容 |
|---|---|---|---|---|
| go2-gateway 未启动 | 8090/备用端口无响应 | 运行启动脚本；检查 `go2-gateway-mock.stderr.log`；不得切换 real | 否 | 展示冻结合同与验收截图 |
| health_new 后端未启动 | `/api/v1/robot/navigation/state` 无响应 | 检查后端日志和专用数据库；重新运行启动脚本 | 否 | 展示 REST/WS 证据摘要 |
| 前端无法连接 | 页面空白或 API 网络错误 | 检查 Vite 端口、`VITE_API_BASE`、浏览器缓存；不得改生产配置 | 可 | 用 REST 证据讲解 |
| WebSocket 断线 | 页面显示重连 | 保持页面打开；确认 REST 已恢复；等待退避重连 | 可 | 以 REST 当前快照为准 |
| 点云不可用 | Three.js 无帧或重连 | 确认 `/ws/robot/point-cloud`；刷新导航页；不要接入真实 L1 | 可 | 展示二维地图和已保存截图 |
| 视频桥不可用 | 8093 显示不可用 | 不启动真实相机；说明视频为可选独立桥 | 可 | 使用状态、地图和应急数据 |
| 无 active map | `MAP_NOT_LOADED` | 停止栈，用 `--all-demo` 清理后重新启动并 seed | 否 | 展示联锁阻断场景 |
| 无 home 点 | `HOME_POINT_NOT_FOUND` | 重新 seed；确认 `robot-demo-home` | 可演示非返航分支 | 展示 need_help/no_response |
| 无 observation 点 | 区域映射失败 | 重新 seed；确认 metadata `area_id=elderly_activity_area` | 否 | 展示巡逻链路 |
| 联锁 blocked | 有明确 `blocked_by` | 按错误码检查场景；恢复 `robot_ready`；不得绕过 | 可 | 将其作为安全设计展示 |
| Mock scenario 未复位 | 后续任务持续失败或自动分支 | POST `mock/scenario=robot_ready` 或安全重启栈 | 可 | 展示场景隔离机制 |
| 数据重复 | 幂等冲突或旧任务存在 | 运行默认 cleanup 清动态 demo；保留固定地图后重试 | 可 | 展示幂等保护 |
| 页面 404 | hash 路径错误 | 使用 `#/robot-status`、`#/robot-navigation`、`#/robot-emergency?incidentId=...` | 可 | 从主导航重新进入 |
| 浏览器缓存异常 | 旧资源或旧 API 地址 | 强制刷新；关闭旧标签；确认当前 Vite 端口 | 可 | 使用无痕窗口 |
| 端口被占用 | 启动脚本拒绝 | 不结束未知进程；显式选择 18090/18000/15173 等备用端口 | 可 | 无 |
| 服务重启后页面未恢复 | WebSocket 未重新连接 | 先确认 REST；等待重连；必要时刷新页面 | 可 | 展示重启前后 SQLite 证据 |
| 清理脚本拒绝数据库 | 路径不是 `robot_mock_demo.db` 或指向 `app.db` | 修正为专用 demo 路径；不得绕过保护 | 可 | 保留现状，不执行清理 |

## 常用检查

```powershell
cd D:\health_new
.\scripts\check_robot_mock_demo.ps1
Get-Content .\artifacts\robot_mock_acceptance\logs\go2-gateway-mock.stderr.log -Tail 80
Get-Content .\artifacts\robot_mock_acceptance\logs\health-new-backend.stderr.log -Tail 80
Get-Content .\artifacts\robot_mock_acceptance\logs\vue-dashboard.stderr.log -Tail 80
```

## 恢复原则

1. 先确认 `provider=mock`、`real_motion_enabled=false`。
2. 只恢复本轮 manifest 管理的进程。
3. 只清理带 `robot-demo-` 标识的动态记录。
4. 不修改正式 `app.db`、用户健康数据或正式告警。
5. 不因演示故障临时开启真实 SDK、DDS、ROS2、运动、音频或设备 IP。

## 比赛现场命令化降级

先在 `D:\health_new` 读取当前端口：

```powershell
$manifest = Get-Content `
  .\artifacts\robot_mock_acceptance\runtime\process-manifest.json `
  -Raw -Encoding UTF8 | ConvertFrom-Json
$backend = $manifest.backend_base_url
$gateway = $manifest.gateway_base_url
```

### 1. 页面能打开但 REST 返回 404

- 现象：页面框架正常，状态卡显示 404 或空数据。
- 检查命令：

```powershell
Invoke-WebRequest "$backend/api/v1/robot/navigation/state" -UseBasicParsing
```

- 处理步骤：确认地址包含 `/api/v1`；强制刷新；从主导航重新进入，不手工拼接非冻结路径。
- 可否继续：可以。若状态接口正常，以刷新后的页面继续；否则转为截图与合同讲解。
- 替代讲解：展示冻结 REST 路径、Mock 合同和既有验收摘要。

### 2. WebSocket 连接失败

- 现象：页面显示“正在重连”或“已断开”，实时事件不更新。
- 检查命令：

```powershell
Invoke-WebRequest "$backend/api/v1/robot/navigation/state" -UseBasicParsing
Get-Content .\artifacts\robot_mock_acceptance\logs\health-new-backend.stderr.log -Tail 80
```

- 处理步骤：先确认 REST 正常；保持页面打开等待有限退避；仍未恢复时刷新当前页。
- 可否继续：可以，REST 快照是当前状态依据。
- 替代讲解：说明 WebSocket 负责增量事件，当前降级到 REST 快照，不影响持久化记录。

### 3. 点云 unavailable、stale 或非法帧

- 现象：模拟三维点云显示不可用、过期或数据格式错误。
- 检查命令：

```powershell
Invoke-WebRequest "$backend/api/v1/robot/navigation/state" -UseBasicParsing
Get-Content .\artifacts\robot_mock_acceptance\logs\health-new-backend.stderr.log -Tail 80
```

- 处理步骤：点击“重连点云”；刷新建图巡航页；不要切换真实 L1 数据源。
- 可否继续：可以。
- 替代讲解：展示二维地图、点位、路线和安全联锁；明确三维点云本来就是模拟可视化。

### 4. 视频桥 unavailable

- 现象：机器人现场画面显示不可用，但页面其他卡片正常。
- 检查命令：

```powershell
Test-NetConnection 127.0.0.1 -Port 8093
```

- 处理步骤：保持页面运行；不启动真实相机或机器人；仅在已准备好的独立 Mock 视频桥存在时恢复它。
- 可否继续：可以。
- 替代讲解：使用机器人状态、二维地图、时间线和应急文字记录。

### 5. active map 丢失

- 现象：地图卡显示“尚未激活地图”，点位和巡逻按钮禁用。
- 检查命令：

```powershell
Invoke-RestMethod "$backend/api/v1/robot/navigation/maps/active"
```

- 处理步骤：停止当前演示栈；仅对 `data/robot_mock_demo.db` 执行 cleanup 与 seed；重新启动并检查。
- 可否继续：不能继续巡逻主线，可以切换安全阻断演示。
- 替代讲解：展示 `MAP_NOT_LOADED` 如何阻止任务启动。

### 6. observation 点丢失

- 现象：跌倒事件存在，但无法映射活动区观察点。
- 检查命令：

```powershell
Invoke-RestMethod "$backend/api/v1/robot/navigation/points?map_id=map_mock_0001" |
  ConvertTo-Json -Depth 8
```

- 处理步骤：确认 `robot-demo-observation-elderly-activity` 及 `metadata.area_id=elderly_activity_area`；必要时重新 seed。
- 可否继续：不能继续应急派发，可以继续状态与巡逻演示。
- 替代讲解：说明主系统负责区域到观察点映射，映射缺失时不会猜测机器人坐标。

### 7. home 点丢失

- 现象：安全回应完成，但返回待命区按钮禁用并显示 `HOME_POINT_NOT_FOUND`。
- 检查命令：

```powershell
Invoke-RestMethod "$backend/api/v1/robot/navigation/points?map_id=map_mock_0001" |
  ConvertTo-Json -Depth 8
```

- 处理步骤：确认 `robot-demo-home`；必要时重新 seed；不绕过返航前置条件。
- 可否继续：可以展示应急到管理员确认，不能演示返航完成。
- 替代讲解：把它作为“缺少安全目标时禁止返航”的设计证据。

### 8. Mock scenario 未复位

- 现象：后续任务持续按上一阻断或对话分支执行。
- 检查命令：

```powershell
Invoke-RestMethod "$gateway/api/navigation/state" | ConvertTo-Json -Depth 8
```

- 处理步骤：通过现有 Mock 场景接口恢复 `robot_ready`；再执行 `check_robot_mock_demo.ps1`。
- 可否继续：复位成功后可以。
- 替代讲解：展示场景隔离与可重复测试设计。

### 9. 前端缓存旧数据

- 现象：按钮或文案与当前版本不一致，API 地址仍指向旧端口。
- 检查命令：

```powershell
Invoke-WebRequest $manifest.frontend_base_url -UseBasicParsing
```

- 处理步骤：强制刷新；关闭旧标签页；使用无痕窗口；确认当前 manifest 的前端端口。
- 可否继续：可以。
- 替代讲解：直接展示 REST 数据和已保存截图。

### 10. 后端状态 stale

- 现象：页面更新时间长时间不变，WebSocket 重连后仍显示旧任务。
- 检查命令：

```powershell
Invoke-RestMethod "$backend/api/v1/robot/navigation/state" | ConvertTo-Json -Depth 8
Get-Content .\artifacts\robot_mock_acceptance\logs\health-new-backend.stderr.log -Tail 80
```

- 处理步骤：比较 REST 的 `updated_at`；若 REST 新鲜则刷新页面；若 REST 同样过期，只重启 manifest 管理的 Mock 栈。
- 可否继续：REST 新鲜时可以；否则切换静态证据。
- 替代讲解：展示 SQLite 重启恢复的既有验收结果。

### 11. SQLite locked

- 现象：后端日志出现 `database is locked`，写操作失败或长时间等待。
- 检查命令：

```powershell
Select-String `
  .\artifacts\robot_mock_acceptance\logs\*.log `
  -Pattern "database is locked|SQLite.*locked"
```

- 处理步骤：停止本轮 Mock 栈；确认没有第二套演示进程占用专用数据库；不要删除数据库；重新启动后执行检查。
- 可否继续：锁未解除前不继续写操作，可展示只读截图。
- 替代讲解：展示冻结验收报告中的持久化与重启证据。

### 12. 多个演示任务未清理

- 现象：任务中心出现多条旧任务，当前任务选择混乱。
- 检查命令：

```powershell
Invoke-RestMethod "$backend/api/v1/robot/tasks?limit=500" |
  ConvertTo-Json -Depth 6
```

- 处理步骤：执行正常停止；仅对 `data/robot_mock_demo.db` 运行默认 cleanup；重新 seed；再启动。
- 可否继续：清理完成后可以。
- 替代讲解：如现场不宜重启，切换状态页和已有完成任务时间线。

## 禁止的现场恢复方式

- 不执行 `taskkill /F /IM python.exe` 或批量结束 Node。
- 不删除 `data/app.db`、正式告警或健康数据。
- 不修改 `.env`、真实设备地址或冻结接口。
- 不为了恢复页面而启用真实运动、DDS、ROS2、Nav2、SLAM 或音频。
