# Go2 本机视频启动器

本工具为社区端 `#/robot-follow` 页面注册当前用户级 Windows 自定义协议：

```text
go2bridge://start
```

协议处理器只接受固定的 `start` 和只读 `status` 动作，不接受额外路径、查询参数、可执行文件路径、命令行或脚本参数。`start` 会调用安装时记录的固定 `start_sta_wireless.ps1`，并传入 `-NoOpenBrowser`，因此不会打开额外预览页。

## 安装

在普通 PowerShell 中执行，不需要管理员权限：

```powershell
cd <社区端仓库路径>\tools\go2-video-bridge-launcher
.\Install-Go2VideoBridgeLauncher.ps1 `
  -BridgeStartScript "<无线视频项目路径>\wireless_collector\start_sta_wireless.ps1"
```

`BridgeStartScript` 是必填参数。安装器不会使用开发电脑的默认目录，也不会搜索或下载脚本；部署人员必须指向已审核的无线视频项目脚本。安装后，启动器只使用配置中记录的绝对路径和 SHA-256。

安装内容：

- 启动器：`%LOCALAPPDATA%\Go2VideoBridgeLauncher`
- 配置：启动器目录内的 `launcher.config.json`
- 日志：`%LOCALAPPDATA%\Go2VideoBridgeLauncher\logs`
- 协议：`HKCU\Software\Classes\go2bridge`

安装程序会记录启动脚本的 SHA-256。脚本更新后必须重新运行安装程序，否则启动器会以退出码 `21` 拒绝执行。若脚本已具有有效 Authenticode 签名，安装程序会自动要求后续运行继续保持有效签名。

安装后浏览器首次调用协议时，通常会提示是否打开外部应用。允许后，社区端会继续轮询 `http://127.0.0.1:8093/status`；当 `data.hasFrame=true` 时，当前页面自动重载 MJPEG 画面。

## 卸载

```powershell
.\Uninstall-Go2VideoBridgeLauncher.ps1
```

卸载会删除当前用户的协议注册和 `%LOCALAPPDATA%\Go2VideoBridgeLauncher` 安装目录，不会删除无线视频项目或 Go2 密钥。

## 安全边界

- URI 必须精确匹配 `go2bridge://start` 或 `go2bridge://status`。
- 配置目标文件名必须是 `start_sta_wireless.ps1`。
- 启动动作使用当前用户命名互斥锁，避免并发启动。
- `8093` 已监听时还会校验 `/status` 的 `serviceId` 和 `apiVersion`；未知程序占用端口时返回退出码 `30`。
- 启动前校验固定脚本路径、SHA-256，以及安装时启用的 Authenticode 要求。
- 健康检查复用无线视频服务的只读 `/status`，不新增常驻代理。
- 启动视频桥接不代表机器狗已连接，也不代表自动跟随已启动。

## 退出码

| 退出码 | 含义 |
| ---: | --- |
| `0` | 启动请求已接受，或状态检查正常 |
| `2` | URI 不在固定白名单 |
| `3` | 视频服务离线 |
| `10` | 服务已运行，或另一个启动请求正在处理 |
| `20` | 启动脚本不存在 |
| `21` | 启动脚本哈希不匹配 |
| `22` | 启动脚本签名无效 |
| `30` | `8093` 被未知服务占用 |
| `40` | PowerShell 启动失败 |
| `50` | 启动器配置错误或版本不兼容 |

## 验证

视频服务运行时执行：

```powershell
.\Test-Go2VideoBridgeLauncher.ps1
```

测试会验证非法 URI 拒绝、配置与脚本哈希，以及连续十次启动不会产生新的视频服务进程。
