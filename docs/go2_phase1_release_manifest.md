# Go2 一期发布清单

> 发布候选：`go2-phase1-v0.1.0-rc.1`
>
> 发布范围：社区端视频监看、本机视频启动、随行遥控器协同
>
> 稳定性定位：演示和阶段性交付候选，不是最终生产稳定版

## 1. 版本对应关系

```yaml
release: go2-phase1-v0.1.0-rc.1

community_repository:
  url: https://github.com/gq18262121731-source/selection-contest-dev
  branch: codex/go2-robot-follow-phase1
  source_commit: f8d6323696c3c6b006f1c05950c95b329d9a76f1

video_bridge_source:
  repository_status: unversioned-local-source
  release_blocker: true
  approved_start_script: start_sta_wireless.ps1
  approved_start_script_sha256: 4D783EECECC1805B67307D17F389CB54DE65C1CF288110D934792E4533AE3603
  note: 无线视频源当前不在 Git 仓库中，不能由本清单提供可复现的仓库 commit

launcher:
  version: 1.1.0
  configuration_version: 2
  protocol: go2bridge
  supported_actions:
    - start
    - status

status_api:
  api_version: "1"
  service_id: go2-wireless-camera
  health_url: http://127.0.0.1:8093/status
  stream_url: http://127.0.0.1:8093/stream.mjpg

tested_environment:
  community_backend: http://127.0.0.1:8000
  community_frontend: http://127.0.0.1:5173
  video_bridge: http://127.0.0.1:8093
  robot_ip: 192.168.8.248
  connection_mode: STA-L / Wi-Fi
  video: 1280x720, approximately 8-9 FPS
  audio: disabled
```

## 2. 社区端交付内容

- 左侧主导航新增“机器狗跟随”，路由为 `#/robot-follow`；
- 当前页面显示 Go2 MJPEG 第一视角；
- `/status` 健康轮询、结构化错误说明、手动重连和后台自动恢复；
- “启动本机视频服务”通过 `go2bridge://start` 调用本机启动器；
- 启动成功后在当前页面重新建立 `/stream.mjpg`，不打开额外预览页；
- “开始跟随 / 停止跟随”只更新页面会话记录，实际操作由随行遥控器完成；
- 页面重新加载后，网页跟随记录恢复为未确认；
- 标准操作流程位于页面顶部，覆盖视频、环境和遥控器三步确认。

实现入口见 [RobotFollowPage.vue](../frontend/vue-dashboard/src/views/RobotFollowPage.vue)，验收证据见 [机器狗跟随验收记录](robot_follow_validation.md)。

## 3. 本机启动器交付内容

启动器位于 [tools/go2-video-bridge-launcher](../tools/go2-video-bridge-launcher/README.md)，安装到当前用户目录并注册：

```text
HKCU\Software\Classes\go2bridge
```

部署时必须显式传入已经审核的 `start_sta_wireless.ps1`。安装器不会写死开发电脑盘符，也不会自动搜索、下载或替换脚本。配置文件记录绝对路径、SHA-256、服务身份和接口版本；运行时只允许固定的 `start`、`status` 动作。

当前批准脚本的 SHA-256 仅用于识别本次现场测试文件。脚本内容发生任何变化后，必须重新审核、更新清单并重新安装启动器。

## 4. 已完成验收

- 机器狗模块定向测试、定向 ESLint 和生产构建通过；
- 本机协议 URI 白名单、脚本哈希和重复启动边界通过；
- 一次连续 15 分钟播放测试通过；
- 运行期间 WebRTC 异常、停帧和连接失败后的自动恢复通过；
- 一轮严格 Go2 关机—开机自动恢复通过，过程中页面和三个本机服务未重启；
- 桌面和窄屏布局、视频错误提示与当前页面恢复行为已验证。

## 5. 发布限制与阻塞项

### 5.1 无线视频源尚未版本化

无线视频桥接项目当前是本机目录，不是 Git 仓库，因此本次 GitHub 分支只发布社区端与启动器代码。要达到可复现发布，必须将无线视频项目建立为独立仓库或纳入正式制品管理，并为本清单补充固定 commit 或制品摘要。

### 5.2 仍待补测

- 第二轮严格 Go2 冷启动重复性；
- 从网络恢复到连接、首帧和页面就绪的分阶段时延；
- Wi-Fi 主动断开；
- 多客户端压力；
- 安全监护场景允许的最大停帧阈值。

### 5.3 仓库既有质量基线

全项目 TypeScript 和 ESLint 仍有与本次文件无关的既有错误，详情见验收记录。不得通过关闭规则或降低检查级别制造通过结果。

## 6. 明确不包含的能力

- 网页直接控制机器狗站立、移动或停止；
- 自动巡检任务、路线、SLAM、路径规划和避障；
- 自动返航与回充；
- 公网 RTMP、HLS、HTTP-FLV 或 WebRTC 分发；
- 音频传输；
- 本机代理端口 `8094`。

## 7. 发布与冻结规则

本候选版本冻结后，只接受崩溃或白屏、视频无法连接或恢复、启动器安全边界、安装卸载、提示语义和验收文档真实性相关修复。其他能力进入后续 Issue，不并入本次候选分支。
