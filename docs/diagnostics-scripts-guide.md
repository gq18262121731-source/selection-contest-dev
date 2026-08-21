# 诊断脚本使用指南

本文档说明当前项目中诊断脚本的功能、位置、运行环境和常用命令。

## 运行环境

诊断脚本使用独立 Conda 环境：

```powershell
health-diagnostics
```

Python 解释器位置：

```text
C:\Users\YANG\.conda\envs\health-diagnostics\python.exe
```

在 PyCharm 中配置解释器时选择上述路径。也可以在终端中直接使用：

```powershell
conda run -n health-diagnostics python <脚本路径>
```

项目主后端仍使用原来的业务环境：

```powershell
health
```

后端默认地址：

```text
http://127.0.0.1:8000
```

## PyCharm 自动配置脚本

| 脚本 | 位置 | 功能 | 环境 |
| --- | --- | --- | --- |
| PyCharm 诊断配置脚本 | `scripts/diagnostics/setup_pycharm_diagnostics.ps1` | 检查 `health-diagnostics` 环境、写入 PyCharm Run Configurations、打开 PyCharm、可选运行冒烟测试 | PowerShell + Conda |
| PyCharm 终端一键诊断 | `scripts/diagnostics/run_pycharm_diagnostics.ps1` | 在 PyCharm Terminal 中连续运行后端、健康评分、摄像头、微调、RTSP、视频流监听诊断 | PowerShell + `health-diagnostics` |

常用命令：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\diagnostics\setup_pycharm_diagnostics.ps1 -OpenPyCharm -RunSmoke
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\diagnostics\run_pycharm_diagnostics.ps1
```

PyCharm 中已生成的运行配置：

- `Diagnostics Backend Health`
- `Diagnostics Camera Status`
- `Diagnostics Camera Stream Watch`
- `Diagnostics RTSP Matrix`
- `Diagnostics Health Score`
- `Diagnostics Health WebSocket Watch`
- `Diagnostics Model Finetune`

配置文件位置：

```text
.idea/runConfigurations/
```

## 公共工具模块

| 脚本 | 位置 | 功能 | 环境 |
| --- | --- | --- | --- |
| 公共诊断工具 | `scripts/diagnostics/diag_common.py` | 提供 HTTP 请求、WebSocket 监听、MJPEG 帧解析、统一日志、默认参数等公共能力 | `health-diagnostics` |

这个文件通常不单独运行，其他诊断脚本会自动引用它。

## 后端基础诊断

| 脚本 | 位置 | 功能 | 环境 |
| --- | --- | --- | --- |
| 后端健康检查 | `scripts/diagnostics/probe_backend_health.py` | 检查 `/healthz`、`/api/v1/system/info`、`/api/v1/system/demo-data/status` | `health-diagnostics` |
| 后端持续监听 | `scripts/diagnostics/watch_backend_health.py` | 持续轮询后端健康状态，终端滚动输出 OK 或错误 | `health-diagnostics` |

命令：

```powershell
conda run -n health-diagnostics python scripts\diagnostics\probe_backend_health.py --timeout 30
```

```powershell
conda run -n health-diagnostics python scripts\diagnostics\watch_backend_health.py --interval 2
```

## 摄像头与视频流诊断

| 脚本 | 位置 | 功能 | 环境 |
| --- | --- | --- | --- |
| 摄像头状态检查 | `scripts/diagnostics/probe_camera_status.py` | 检查摄像头源、active camera、stream status、音频状态、跌倒检测状态、姿态检测状态、外部摄像头 runtime | `health-diagnostics` |
| 摄像头截图检查 | `scripts/diagnostics/probe_camera_snapshot.py` | 请求当前摄像头截图，保存到 `runtime_logs/diagnostics/` | `health-diagnostics` |
| 视频流持续监听 | `scripts/diagnostics/watch_camera_stream.py` | 持续监听 MJPEG 视频流。如果有画面帧进入，终端会不断输出 frame、bytes、fps | `health-diagnostics` |
| 摄像头 WebSocket 监听 | `scripts/diagnostics/watch_camera_ws.py` | 监听摄像头 WebSocket 通道，输出消息数量、大小和预览 | `health-diagnostics` |
| RTSP 矩阵探测 | `scripts/diagnostics/probe_rtsp_matrix.py` | 直接探测摄像头 IP、RTSP 端口、码流路径和认证是否可达 | `health-diagnostics` |

常用命令：

```powershell
conda run -n health-diagnostics python scripts\diagnostics\probe_camera_status.py --timeout 30
```

```powershell
conda run -n health-diagnostics python scripts\diagnostics\probe_camera_snapshot.py --timeout 15
```

```powershell
conda run -n health-diagnostics python scripts\diagnostics\watch_camera_stream.py --timeout 10
```

```powershell
conda run -n health-diagnostics python scripts\diagnostics\probe_rtsp_matrix.py --timeout 2
```

如果视频流正常，会看到类似输出：

```text
frame=1 frame_bytes=73421 total_bytes=81222 fps=1.00
frame=2 frame_bytes=72880 total_bytes=154102 fps=1.00
```

如果当前摄像头不可达或无帧，会看到连接超时、HTTP 503、没有 JPEG 帧、RTSP OPTIONS 超时等错误。

## 健康数据与告警诊断

| 脚本 | 位置 | 功能 | 环境 |
| --- | --- | --- | --- |
| 健康评分接口检查 | `scripts/diagnostics/probe_health_score.py` | 调用 `/api/v1/health/score` 和 `/api/v1/health/warning/check` | `health-diagnostics` |
| 健康 WebSocket 监听 | `scripts/diagnostics/watch_health_ws.py` | 监听指定设备的实时健康数据 WebSocket | `health-diagnostics` |
| 告警 WebSocket 监听 | `scripts/diagnostics/watch_alarm_ws.py` | 监听 `/ws/alarms` 告警消息 | `health-diagnostics` |

命令：

```powershell
conda run -n health-diagnostics python scripts\diagnostics\probe_health_score.py --timeout 30
```

```powershell
conda run -n health-diagnostics python scripts\diagnostics\watch_health_ws.py --device-mac 53:57:08:00:00:01
```

```powershell
conda run -n health-diagnostics python scripts\diagnostics\watch_alarm_ws.py
```

## 跌倒检测与姿态检测诊断

| 脚本 | 位置 | 功能 | 环境 |
| --- | --- | --- | --- |
| 跌倒检测状态检查 | `scripts/diagnostics/probe_fall_detection.py` | 检查跌倒检测、姿态检测和分析帧状态接口 | `health-diagnostics` |

命令：

```powershell
conda run -n health-diagnostics python scripts\diagnostics\probe_fall_detection.py --timeout 30
```

## 用户、认证、设备与照护目录诊断

| 脚本 | 位置 | 功能 | 环境 |
| --- | --- | --- | --- |
| 认证流程检查 | `scripts/diagnostics/probe_auth_flow.py` | 检查 mock accounts、mock login、`/auth/me` | `health-diagnostics` |
| 设备流程检查 | `scripts/diagnostics/probe_device_flow.py` | 检查设备列表、设备详情、绑定日志 | `health-diagnostics` |
| 照护目录检查 | `scripts/diagnostics/probe_care_directory.py` | 检查 care directory、access profile、community dashboard | `health-diagnostics` |

命令：

```powershell
conda run -n health-diagnostics python scripts\diagnostics\probe_auth_flow.py --timeout 30
```

```powershell
conda run -n health-diagnostics python scripts\diagnostics\probe_device_flow.py --timeout 30
```

```powershell
conda run -n health-diagnostics python scripts\diagnostics\probe_care_directory.py --timeout 30
```

## Agent、大模型、语音与多模态诊断

| 脚本 | 位置 | 功能 | 环境 |
| --- | --- | --- | --- |
| Agent 能力检查 | `scripts/diagnostics/probe_agent.py` | 检查 Agent elder 列表、chat capabilities、MCP tools | `health-diagnostics` |
| Chat 流式输出监听 | `scripts/diagnostics/watch_chat_stream.py` | 调用社区 Agent 流式接口，终端逐行显示事件 | `health-diagnostics` |
| 语音服务检查 | `scripts/diagnostics/probe_voice.py` | 检查 `/api/v1/voice/status` | `health-diagnostics` |
| 多模态服务检查 | `scripts/diagnostics/probe_omni.py` | 检查 `/api/v1/omni/status` | `health-diagnostics` |

命令：

```powershell
conda run -n health-diagnostics python scripts\diagnostics\probe_agent.py --timeout 30
```

```powershell
conda run -n health-diagnostics python scripts\diagnostics\watch_chat_stream.py --timeout 30
```

```powershell
conda run -n health-diagnostics python scripts\diagnostics\probe_voice.py --timeout 30
```

```powershell
conda run -n health-diagnostics python scripts\diagnostics\probe_omni.py --timeout 30
```

## 模型微调诊断

| 脚本 | 位置 | 功能 | 环境 |
| --- | --- | --- | --- |
| 模型微调能力检查 | `scripts/diagnostics/probe_model_finetune.py` | 检查 overview、capabilities、templates、datasets、eval gates、adapters | `health-diagnostics` |

命令：

```powershell
conda run -n health-diagnostics python scripts\diagnostics\probe_model_finetune.py --timeout 30
```

## 全量诊断

| 脚本 | 位置 | 功能 | 环境 |
| --- | --- | --- | --- |
| 全量一次性检查 | `scripts/diagnostics/run_all_diagnostics.ps1` | 依次运行多个 probe 脚本，适合快速自检 | PowerShell + `health-diagnostics` |
| PyCharm 可见诊断 | `scripts/diagnostics/run_pycharm_diagnostics.ps1` | 适合在 PyCharm Terminal 中运行，输出更适合现场查看 | PowerShell + `health-diagnostics` |

命令：

```powershell
conda run -n health-diagnostics powershell -ExecutionPolicy Bypass -File scripts\diagnostics\run_all_diagnostics.ps1 -Timeout 30
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\diagnostics\run_pycharm_diagnostics.ps1
```

## 当前摄像头诊断结论说明

当前脚本已经能够正确运行并暴露真实链路状态。

已验证通过：

- 后端健康检查通过
- 健康评分接口通过
- 摄像头状态接口可访问
- 模型微调接口可访问

当前视频链路问题：

- 后端 MJPEG 接口能打开响应头，但没有 JPEG 帧进入
- RTSP 矩阵探测显示 `192.168.8.248` 和 `192.168.8.253` 的 `554 / 10554` 当前超时
- 摄像头状态显示 active camera 配置存在，但 `online=False`
- external camera runtime 显示 `has_frame=False`

因此，当前视频失败更可能是摄像头 IP、端口、供电、网络可达性或 RTSP 服务状态问题，不是 PyCharm 配置或诊断脚本本身的问题。
