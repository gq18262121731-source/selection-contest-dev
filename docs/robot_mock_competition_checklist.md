# 机器人 Mock 比赛演示检查表

> 适用基线：`robot-mock-demo-v1` 之后的比赛收口版本。
> 固定边界：`provider=mock`、`real_motion_enabled=false`。
> 统一口径：当前为模拟导航环境，真实机器人运动控制已禁用。

## 演示前 30 分钟

- [ ] Go2 保持关机，不连接真实设备地址。
- [ ] 端口 `8090/8000/5173` 可用；如被占用，改用明确的备用端口，不结束未知进程。
- [ ] 执行 `.\scripts\start_robot_mock_demo.ps1`。
- [ ] 执行 `.\scripts\check_robot_mock_demo.ps1`。
- [ ] 检查 `provider=mock`、`real_motion_enabled=false`、`robot_ip_contact_allowed=false`。
- [ ] 确认使用 `data/robot_mock_demo.db`，正式 `data/app.db` 哈希未变化。
- [ ] 确认 `map_mock_0001` 为当前地图。
- [ ] 确认“机器人待命点”“活动区观察点”和三个巡逻点存在。
- [ ] 确认“日常巡查路线”存在且顺序正确。
- [ ] 确认 `camera_01` 与 `elderly_activity_area` 的文字映射可用。
- [ ] 打开机器人状态、建图巡航、应急处置和机器人跟随四页。
- [ ] 确认三个机器人主页面均显示统一模拟环境提示。
- [ ] 确认 Go2 视频桥状态；不可用时准备采用状态与地图替代讲解。
- [ ] 清理旧浏览器标签页，强制刷新一次，避免旧前端缓存。
- [ ] 保持比赛网络稳定；Mock 栈只使用回环地址，不依赖外网。
- [ ] 可选执行 45 分钟长稳测试：`.\scripts\robot_mock_soak_test.ps1`。

## 演示前 5 分钟

- [ ] 使用已有社区管理员账号登录，不在文档或屏幕上展示密码。
- [ ] 机器人状态页能显示网络、网关、DDS、LiDAR、定位、地图和急停。
- [ ] 建图巡航页能显示二维地图与模拟三维点云。
- [ ] “日常巡查路线”已载入，当前没有未完成演示任务。
- [ ] 全局跌倒告警弹窗能出现，且“进入应急处置”不会确认告警。
- [ ] `safe_response` 主线数据可创建。
- [ ] `localization_invalid` 与 `map_not_loaded` 两个备用阻断场景可用。
- [ ] 将 Mock scenario 恢复为 `robot_ready`。
- [ ] 关闭开发者工具和无关窗口，浏览器缩放恢复 100%。

## 演示中

### 固定操作顺序

1. 机器人状态：展示模拟边界、状态摘要、安全联锁和视频小窗。
2. 建图巡航：展示地图与点位，启动巡逻，申请接管，释放控制权，显式继续，完成返航。
3. 跌倒应急：触发告警，进入详情，派发，模拟到达与询问，选择“我没事”，管理员确认，返回待命区，完成闭环。

### 讲解提醒

- [ ] 强调事件驱动、任务闭环、安全联锁和人机协同。
- [ ] `mapping_prerequisites_ready` 只解释为“具备后续验证前置条件”。
- [ ] 释放遥控器后明确说明“不会自动恢复”。
- [ ] `safe_response` 只表示老人明确回应，仍需管理员确认。
- [ ] 视频或点云不可用时，继续展示 REST/WebSocket 状态、二维地图、时间线与持久化。

### 禁止点击或宣称

- [ ] 不输入真实机器人 IP，不访问真实设备 8090。
- [ ] 不切换真实 Provider，不启用运动。
- [ ] 不绕过安全联锁。
- [ ] 不声称已接入真实 ROS2、Nav2、SLAM、L1 点云或真实音频。
- [ ] 不把模拟点云描述为现场雷达精度。

### 备用切换

- [ ] 主线失败时切换到 `need_help`、`no_response` 或 `uncertain`，说明机器人保持原地并升级人工处置。
- [ ] 导航失败时切换到 `localization_invalid` 或 `map_not_loaded`，说明安全联锁阻止出动。
- [ ] 视频不可用时使用二维地图、状态页和应急时间线继续。
- [ ] WebSocket 断线时以 REST 当前快照为准，并等待有限退避重连。

## 演示后

- [ ] 执行 `.\scripts\stop_robot_mock_demo.ps1`，只停止 manifest 记录的进程。
- [ ] 如需重置，使用 `cleanup_robot_mock_demo.py` 清理动态演示数据并重新 seed。
- [ ] 保存本轮 `artifacts/robot_mock_acceptance` 和 `artifacts/robot_mock_soak` 日志摘要。
- [ ] 不把日志、截图、临时数据库或构建产物加入提交。
- [ ] 不删除或覆盖 `data/app.db`、正式健康数据和正式告警。
- [ ] 不移动 `robot-mock-demo-v1` 标签。

## 快速命令

```powershell
cd D:\health_new
.\scripts\start_robot_mock_demo.ps1
.\scripts\check_robot_mock_demo.ps1
.\scripts\robot_mock_soak_test.ps1 -DurationMinutes 45
.\scripts\stop_robot_mock_demo.ps1
```
