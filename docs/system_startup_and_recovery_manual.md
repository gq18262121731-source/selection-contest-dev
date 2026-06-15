# 系统启动与恢复运维手册

本文面向第一次接手项目的人，目标是按现场运维流程完成摄像头恢复、视频服务启动、主系统启动、Flutter 家属端验证、视频联调和跌倒告警验证。

本文只引用当前仓库能确认的目录、接口和启动入口。凡是现场 IP、摄像头密码、Conda 环境是否已安装等无法从仓库稳定确认的信息，都放在文末“需要补充的信息”中。

## 0. 现场原则

1. 先确认摄像头物理在线，再启动软件服务。
2. 两个后端不能同时占用 `8000` 端口：`D:\ai_helth-main` 主系统默认用 `8000`，`D:\vision_service` 独立测试文档也默认用 `8000`。完整联调时应让主系统占用 `8000`，视频服务改用空闲端口，例如 `8101`。
3. 不要把真实摄像头密码写入文档、截图或提交记录。现场以 `.env`、摄像头 App、VLC 验证结果为准。
4. `video_bridge` 当前是主系统内的状态遥测桥，不负责拉 RTSP、不负责生成视频流、不直接创建告警。跌倒告警仍走主系统已有告警链路。

## 第一部分：系统架构说明

### 数据链路

```text
摄像头
↓
vision_service
↓
video_bridge
↓
ai_helth-main
↓
Vue
↓
Flutter
```

### 模块说明

| 模块 | 作用 | 所在目录 | 启动顺序 | 依赖关系 |
| --- | --- | --- | --- | --- |
| 摄像头 | 提供 RTSP 主码流、子码流、可选 ONVIF/音频。当前主系统 `.env` 指向 `CAMERA_IP=192.168.8.253`、`CAMERA_RTSP_PORT=554`、主路径 `/tcp/av0_0`、分析路径 `/tcp/av0_1`；`camera_runtime_external` 运行时配置里还有 `192.168.8.249:554`；历史视频服务文档也出现过 `192.168.8.254:10554`。这些只能作为候选，现场必须以实际探测/VLC 为准。 | 物理设备，无代码目录；说明资料在 `D:\ai_helth-main\摄像头说明书` 和 `D:\ai_helth-main\camera_runtime_external` | 第 1 步 | 需要供电、同一局域网、正确 IP、RTSP 端口、账号密码 |
| `vision_service` | 独立视频识别服务：RTSP 拉流、双流显示/分析、YOLO 检测、跟踪、姿态/行为/时序分析、WebRTC 演示页、WS 结果、可选推送到主系统 `video_bridge`。 | `D:\vision_service` | 第 2 步。完整联调时建议主系统后端先启动，或接受 `video_bridge_publish_failed` 后续自动恢复。 | 依赖摄像头 RTSP、Conda 环境 `torchgpu`，可选依赖 `identity_service` 的 `identity310` 环境 |
| `video_bridge` | 主系统预留的独立视频服务接入口，接收 `vision_service` 推送的结构化状态、FPS、目标框、风险和跌倒状态。 | `D:\ai_helth-main\backend\api\video_bridge_api.py`、`backend\services\video_bridge_service.py`、`backend\models\video_bridge_model.py` | 随主系统后端启动 | 依赖主系统后端在线；`vision_service` 需要设置 `VIDEO_BRIDGE_ENABLED=true` 和 `VIDEO_BRIDGE_URL=http://127.0.0.1:8000/api/v1/video-bridge/analysis` |
| `ai_helth-main` 后端 | 主业务后端：认证、健康数据、告警、摄像头代理、视频桥状态、Flutter/Vue API。默认监听 `0.0.0.0:8000`。 | `D:\ai_helth-main` | 第 3 步或在 `vision_service` 前启动 | 依赖 Conda 环境 `health`；Redis 用于本地开发基础服务；摄像头、告警、模型功能按 `.env` 启用 |
| Vue PC 端 | PC 大屏/调试界面，包含 `视频接入口` 页面，读取 `GET /api/v1/video-bridge/status`。 | `D:\ai_helth-main\frontend\vue-dashboard` | 后端启动后 | 依赖主系统后端 API，默认 Vite 端口 `5173` |
| Flutter 家属端 | 家属端 App。真机必须连接主系统后端 `http://<PC-LAN-IP>:8000`，不能填前端端口。家庭摄像头页会读取 `video_bridge/status`，并用现有 WebSocket image-frame 播放表面展示视频。 | `D:\ai_helth-main\mobile\flutter_app` | 后端启动并且手机能访问 PC 后 | 依赖主系统后端、同一局域网、Windows 防火墙放行 `8000` |

### 当前边界

- `D:\vision_service` 的 `/demo` 使用 WebRTC 播放视频并叠加 overlay，是视频服务自身联调入口。
- Flutter 当前不使用 WebRTC 插件，远程视频是 WebSocket 图片帧播放。桥接记录如果没有可用 `stream_url`，Flutter 会回退到主系统 `/ws/camera/processed`。
- 主系统 `video_bridge` 状态更新成功，不等于 Flutter 一定播放到了 `vision_service` 的 WebRTC 画面。要分别验证“视频服务画面”和“主系统/Flutter 状态同步”。

## 第二部分：摄像头恢复流程

适用场景：摄像头断电、摄像头重启、移动 WiFi 改变、IP 改变。

### 1. 确认摄像头在线

先看物理状态：

- 电源适配器接好，说明书中曾确认过部分设备要求 `DC12V 2A`。
- 网线接路由器 LAN 口或设备已接入同一 Wi-Fi。
- 路由器、摄像头网口指示灯正常。
- 电脑和摄像头在同一局域网，优先用同一路由器，不建议一台接移动热点、一台接家庭 Wi-Fi。

再看 Windows 网络：

```powershell
ipconfig
arp -a
Get-NetAdapter
```

如果使用仓库里的外部摄像头运行时工具，可先运行链路探测：

```powershell
cd D:\ai_helth-main
powershell -ExecutionPolicy Bypass -File .\camera_runtime_external\camera_link_probe.ps1
```

这个脚本会检查有线网卡状态，并扫描常见 IP 的 `80`、`554`、`10554`、`10080` 端口。若输出“wired adapter has no physical link”，先处理供电/网线/PoE/路由器，不要继续查密码。

### 2. 获取新的 IP

按推荐顺序获取：

1. 路由器后台的 DHCP 客户端列表：按设备名、MAC 地址、摄像头厂商名查找。
2. 摄像头厂家 App 或设备搜索助手：仓库历史文档提到过 `Eye4` 和 `设备搜索助手v3.0`。
3. Windows 邻居表：

```powershell
arp -a
Get-NetNeighbor -AddressFamily IPv4
```

4. 已知网段端口探测。主项目诊断脚本可直接探测候选 RTSP：

```powershell
cd D:\ai_helth-main
conda run -n health-diagnostics python .\scripts\diagnostics\probe_rtsp_matrix.py --hosts 192.168.8.253 192.168.8.254 --ports 554 10554 --username admin --password <现场密码> --timeout 2
```

如果 `health-diagnostics` 环境不存在，可先用 PowerShell 判断端口是否开：

```powershell
Test-NetConnection 192.168.8.253 -Port 554
Test-NetConnection 192.168.8.253 -Port 10554
```

### 3. 确认 RTSP 地址

RTSP 格式：

```text
rtsp://<账号>:<密码>@<摄像头IP>:<RTSP端口><码流路径>
```

当前仓库里存在多处摄像头配置，说明现场 IP 曾经变化过。主系统后端 `.env` 能确认的当前候选是：

```text
CAMERA_IP=192.168.8.253
CAMERA_USER=admin
CAMERA_SOURCE_MODE=rtsp
CAMERA_RTSP_PORT=554
CAMERA_RTSP_PATH=/tcp/av0_0
CAMERA_STREAM_RTSP_PATH=/tcp/av0_1
CAMERA_AUDIO_RTSP_PATH=/tcp/av0_1
```

外部摄像头 runtime 配置 `D:\ai_helth-main\camera_runtime_external\camera_live_config.runtime.json` 当前候选是：

```text
host=192.168.8.249
rtsp_port=554
transport=tcp
stream=av0_1
viewer=http://127.0.0.1:8090/viewer
```

`D:\vision_service` 的 `.env.example` 和 phase5 文档使用过另一套历史基线：

```text
main:     rtsp://admin:***@192.168.8.254:10554/tcp/av0_0
analysis: rtsp://admin:***@192.168.8.254:10554/tcp/av0_1
```

`D:\ai_helth-main\docs\camera-current-source-of-truth.md` 要求优先读取 `data/camera_source_of_truth.json`，但当前仓库没有该文件。因此现场恢复时不要只看任意一个历史配置。先确认新 IP 和端口，再测试：

```text
主码流：rtsp://admin:<现场密码>@<IP>:<端口>/tcp/av0_0
子码流：rtsp://admin:<现场密码>@<IP>:<端口>/tcp/av0_1
```

视频服务推荐双流用途：

- `/tcp/av0_0`：主码流，用于 WebRTC 高清显示。
- `/tcp/av0_1`：子码流，用于 AI 分析。

### 4. 确认账号密码

优先来源：

1. 摄像头厂家 App 中当前设置的本地密码、明文密码、RTSP 密码或 ONVIF 密码。
2. 主系统本机 `.env` 中的 `CAMERA_USER`、`CAMERA_PASSWORD`，只限现场查看，不要复制到文档。
3. 如果设备已恢复出厂，用厂家 App 重新绑定并设置新密码，然后再验证 RTSP。

注意：

- 不要从 SN 反推密码。
- 不要把旧文档里的历史默认密码当作当前密码。
- 若 RTSP 返回 `401` 或 `403`，优先怀疑密码或认证方式，而不是模型服务。

### 5. VLC 验证方法

1. 打开 VLC。
2. 选择 `媒体` -> `打开网络串流`。
3. 输入主码流地址，例如：

```text
rtsp://admin:<现场密码>@192.168.8.253:554/tcp/av0_0
```

4. 能看到实时画面后，再测试子码流：

```text
rtsp://admin:<现场密码>@192.168.8.253:554/tcp/av0_1
```

5. 如果 VLC 弹出账号密码框，可以改用不带密码的地址：

```text
rtsp://192.168.8.253:554/tcp/av0_0
```

然后在弹窗里输入账号密码。

### 6. 常见错误处理

| 现象 | 常见原因 | 处理 |
| --- | --- | --- |
| `ping` 不通，端口也不通 | IP 变了、摄像头未上电、路由器隔离、电脑不在同网段 | 回到路由器 DHCP、厂家 App、`camera_link_probe.ps1` 找新 IP |
| `Test-NetConnection` 端口不通 | RTSP 端口不是当前端口，历史上出现过 `554` 和 `10554` | 同时测试 `554`、`10554`，不要自动混用到配置里，验证后只保留一个 |
| VLC 提示认证失败 | 密码错误、没有开启明文/RTSP 密码 | 在 App 里重新设置本地/RTSP 密码，再测 VLC |
| VLC 黑屏但不报错 | 路径错、码流未启用、摄像头刚重启还没出帧 | 分别测 `/tcp/av0_0`、`/tcp/av0_1`，等待 30 秒后重试 |
| 主码流能看，子码流不能看 | 子码流关闭或路径不同 | 先让系统使用能通的流，再在 App/ONVIF 工具里检查子码流 |
| 局域网 RTSP 偶发不通 | 代理/TUN/VPN 接管了局域网连接 | 临时关闭 Clash/TUN/VPN，确认 Windows 路由表 |

### 摄像头恢复检查清单

- [ ] 摄像头供电正常，网口或 Wi-Fi 已连接。
- [ ] 电脑和摄像头处于同一局域网。
- [ ] 已通过路由器、App、`arp -a` 或探测脚本确认当前 IP。
- [ ] 已确认 RTSP 端口，当前只使用一个明确端口。
- [ ] 已确认账号密码来源，未把真实密码写入文档。
- [ ] VLC 能打开主码流。
- [ ] VLC 能打开子码流，或已记录子码流不可用的事实。
- [ ] 主系统 `.env` 与视频服务启动环境中的 IP、端口、路径一致。

## 第三部分：视频服务启动

目录：`D:\vision_service`

### 1. 激活环境

视频服务 README 推荐 GPU 环境：

```powershell
cd D:\vision_service
conda activate torchgpu
```

如果不用交互式激活，也可用：

```powershell
cd D:\vision_service
conda run -n torchgpu python -c "import sys; print(sys.executable)"
```

可选身份服务在 `D:\vision_service\identity_service`，phase5 脚本使用 `identity310` 环境和 `8100` 端口。只有启用 `ENABLE_IDENTITY_BINDING=true` 时才需要重点检查。

### 2. 启动命令

#### 独立视频服务测试

适合只验证 `vision_service` 自身，不启动主系统：

```powershell
cd D:\vision_service
conda activate torchgpu
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000/demo
```

#### 与主系统完整联调

完整联调时主系统后端要使用 `8000`，所以视频服务应改用 `8101` 或其他空闲端口。下面示例只展示现场需要理解的关键变量，密码和 IP 要按现场替换：

```powershell
cd D:\vision_service
conda activate torchgpu

$env:ENABLE_DUAL_STREAM="true"
$env:MAIN_STREAM_URL="rtsp://admin:<现场密码>@<摄像头IP>:<RTSP端口>/tcp/av0_0"
$env:ANALYSIS_STREAM_URL="rtsp://admin:<现场密码>@<摄像头IP>:<RTSP端口>/tcp/av0_1"
$env:DEFAULT_RTSP_URL=$env:ANALYSIS_STREAM_URL

$env:CAPTURE_BACKEND="subprocess_opencv"
$env:MAIN_CAPTURE_BACKEND="subprocess_opencv"
$env:ANALYSIS_CAPTURE_BACKEND="subprocess_opencv"

$env:ENABLE_TRACKING="true"
$env:ENABLE_POSE="true"
$env:POSE_PROVIDER="yolo"
$env:ENABLE_BEHAVIOR="true"
$env:ENABLE_TEMPORAL="true"

$env:VIDEO_BRIDGE_ENABLED="true"
$env:VIDEO_BRIDGE_URL="http://127.0.0.1:8000/api/v1/video-bridge/analysis"
$env:VIDEO_BRIDGE_FPS="1"

python -m uvicorn app.main:app --host 127.0.0.1 --port 8101
```

打开：

```text
http://127.0.0.1:8101/demo?v=phase5-dual
```

如果主系统后端还没启动，视频服务日志可能出现 `video_bridge_publish_failed`。这不影响先看视频服务画面，主系统启动后下一次推送应恢复。

### 3. 必须检查的接口

#### `/healthz`

```powershell
Invoke-RestMethod http://127.0.0.1:8101/healthz
```

期望：

```json
{"status":"ok"}
```

#### `/status`

```powershell
Invoke-RestMethod "http://127.0.0.1:8101/status?camera_id=camera_01" | ConvertTo-Json -Depth 8
```

重点看：

- `service_status=running`
- `main_stream.stream_state=connected`
- `analysis_stream.stream_state=connected`
- `main_stream.frame_age_ms`、`analysis_stream.frame_age_ms` 持续低于几秒级阈值
- `main_stream.capture_fps`、`analysis_stream.capture_fps` 大于 `0`
- `pipeline.result_publish_fps` 大于 `0`，有人体画面时更有意义
- `diagnostics.camera_lost=false`
- `diagnostics.capture_stale=false`

#### WebRTC

用浏览器打开视频服务 demo：

```text
http://127.0.0.1:8101/demo?v=phase5-dual
```

期望：

- 页面中的 WebRTC 状态变为 `connected`。
- 能看到实时画面。
- 打开页面时 `/status.streaming.webrtc_clients` 大于 `0`。

#### WS

demo 页面会连接：

```text
WS /ws/results?camera_id=camera_01
```

期望：

- 页面中的 WS 状态变为 `connected`。
- 页面中 `ws_fps` 或结果 JSON 持续更新。
- 打开页面时 `/status.streaming.ws_clients` 大于 `0`。

也可用拉取接口确认最近 AI 结果：

```powershell
Invoke-RestMethod http://127.0.0.1:8101/integration/results/latest | ConvertTo-Json -Depth 8
```

有人体画面且检测已运行时，期望 `has_result=true`。

#### Overlay

在 demo 页面观察：

- 目标框或骨架出现在画面上。
- `overlay_fps` 大于 `0`。
- 快速移动时可有轻微滞后，但不应长期无框、无骨架、无状态。

### 视频服务启动成功判定标准

- [ ] `/healthz` 返回 `{"status":"ok"}`。
- [ ] `/status` 返回 `service_status=running`。
- [ ] 主码流和分析码流至少一个真实连接；双流场景下两者都应 `connected`。
- [ ] `frame_age_ms` 不持续增长到 stale。
- [ ] `capture_fps` 大于 `0`。
- [ ] demo 页面 WebRTC 连接成功并有实时画面。
- [ ] demo 页面 WS 连接成功，结果或 FPS 持续更新。
- [ ] overlay 有可见目标框/骨架，或现场明确记录“当前画面无人，无法产生目标框”。
- [ ] 完整联调时，主系统 `GET /api/v1/video-bridge/status` 能看到 `metadata.source=vision_service` 或 `service_state=running/degraded`。

## 第四部分：主系统启动

目录：`D:\ai_helth-main`

### 1. 后端启动

主系统固定使用 Conda 环境 `health`，不要用裸 `python`：

```powershell
cd D:\ai_helth-main
conda run -n health powershell -ExecutionPolicy Bypass -File .\scripts\start_server.ps1
```

脚本会监听 `0.0.0.0:8000`，并尝试打印手机应使用的局域网地址。

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
```

期望：

```json
{"status":"ok","app":"AIoT Elder Care Monitoring System"}
```

如果手机要访问，Windows 防火墙需要放行 `8000`：

```powershell
New-NetFirewallRule -DisplayName "AIoT Health Backend" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

### 2. 前端启动

```powershell
cd D:\ai_helth-main
conda run -n health powershell -ExecutionPolicy Bypass -File .\scripts\start_frontend.ps1
```

默认打开：

```text
http://127.0.0.1:5173
```

前端中的 `视频接入口` 页面读取：

```text
GET /api/v1/video-bridge/status
```

### 3. Flutter 调试启动

进入 Flutter 项目：

```powershell
cd D:\ai_helth-main\mobile\flutter_app
flutter pub get
flutter devices
```

调试方式：

```powershell
flutter run
```

如果需要指定设备：

```powershell
flutter run -d <deviceId>
```

真机必须在 App 的“服务器设置”中填写主系统后端：

```text
协议：http
主机：运行主系统后端的 PC 局域网 IP，例如 192.168.8.xxx
端口：8000
```

不要填写：

- `127.0.0.1`
- `localhost`
- 真机上的 `10.0.2.2`
- 前端端口 `5173`、`5182`
- 工具端口 `7860`、`7861`、`8090`

先在手机浏览器打开：

```text
http://<PC-LAN-IP>:8000/healthz
```

浏览器能打开后，再在 App 里点“测试连接”和保存。

### 4. video_bridge 状态检查

主系统接口：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/video-bridge/status | ConvertTo-Json -Depth 8
```

解释：

- `latest.service_state=mock`：主系统桥存在，但还没有收到真实视频服务推送。
- `latest.service_state=running`：视频服务正在推送状态。
- `latest.service_state=degraded`：视频服务可达但摄像头丢失、采集 stale 或其他降级状态。
- `latest.metadata.source=vision_service`：可以确认数据来自 `D:\vision_service` 的桥接发布器。
- `updated_at`、`latest.received_at` 应随推送刷新。

## 第五部分：联调流程

### 联调步骤

1. 启动摄像头。
   - 先完成第二部分检查清单。
   - VLC 能打开 RTSP 后，再进入服务启动。

2. 启动 `vision_service`。
   - 完整联调建议使用 `8101`。
   - 如果要推送到主系统，必须设置 `VIDEO_BRIDGE_ENABLED=true` 和正确 `VIDEO_BRIDGE_URL`。
   - 在 `http://127.0.0.1:8101/demo?v=phase5-dual` 确认 WebRTC、WS、Overlay。

3. 启动 `ai_helth-main`。
   - 后端固定 `8000`。
   - Vue 固定从后端读取 API。
   - 若 `vision_service` 已先启动，观察几秒，等待下一次桥接推送。

4. 检查 bridge。
   - 调主系统 `GET /api/v1/video-bridge/status`。
   - 期望不再是纯 `mock`，并且 `received_at` 刷新。

5. 检查 Flutter。
   - 手机浏览器能打开 `http://<PC-LAN-IP>:8000/healthz`。
   - App 服务器设置测试通过。
   - 家庭摄像头页能进入，处理后视频页显示视频服务状态或主系统处理后视频。

6. 检查风险状态同步。
   - 在视频服务有人体画面时，观察 `fall_state`、`risk`、`fall_prob` 是否从 bridge 到 Vue/Flutter 同步。
   - 注意：bridge 风险状态同步不等于主系统已创建跌倒告警。告警要看 `/api/v1/alarms` 和 `/ws/alarms`。

### 联调检查表

- [ ] 摄像头主码流 VLC 可播放。
- [ ] 摄像头子码流 VLC 可播放，或已记录不可用原因。
- [ ] `vision_service /healthz` 正常。
- [ ] `vision_service /status` 显示采集 connected，frame age 不 stale。
- [ ] `vision_service /demo` WebRTC 有画面。
- [ ] `vision_service /demo` WS 有数据。
- [ ] `vision_service /demo` overlay 有目标或合理解释无目标。
- [ ] 主系统 `/healthz` 正常。
- [ ] 主系统 `/api/v1/video-bridge/status` 能返回桥状态。
- [ ] bridge 最新记录不是长期 `mock`，或已确认尚未启用视频服务推送。
- [ ] Vue `视频接入口` 能展示最新 bridge 状态。
- [ ] 手机能访问 `http://<PC-LAN-IP>:8000/healthz`。
- [ ] Flutter 家属端服务器设置测试通过。
- [ ] Flutter 家庭摄像头页能看到画面或明确状态错误。
- [ ] 风险字段 `risk`、`fall_state`、`fall_prob` 能在 Vue/Flutter 侧看到。

## 第六部分：跌倒告警验证

跌倒验证分两类：手动触发和自动检测。

### A. 手动触发

主系统提供开发/演示接口：

```text
POST /api/v1/camera/fall-detection/simulate
```

该接口在 `settings.debug=false` 且 `environment` 不是 `development` 时会返回 `404`，所以只用于本地开发或演示环境。

触发示例：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/camera/fall-detection/simulate `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"scenario":"critical","track_id":"manual-demo"}' |
  ConvertTo-Json -Depth 8
```

触发后检查：

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/alarms?active_only=true" | ConvertTo-Json -Depth 8
```

监听告警 WebSocket：

```powershell
cd D:\ai_helth-main
conda run -n health-diagnostics python .\scripts\diagnostics\watch_alarm_ws.py --duration 30
```

PC 端应检查：

- Vue 最近告警或告警队列出现跌倒相关告警。
- 告警类型包含 `fall_detected` 或 `fall_injury_risk`。
- 处理/确认后，告警从 active 队列消失或变为已确认。

Flutter 家属端应检查：

- App 已登录到能看到目标老人的家属账号。
- 全局告警监听或告警中心出现告警。
- 家庭摄像头页风险提示与告警不冲突。

视频状态应检查：

- 如果 `simulate` 成功但视频无画面，说明告警链路可用但摄像头链路仍需单独处理。
- 如果 bridge 只有 `mock`，手动告警仍可能成功，因为它不依赖 `vision_service`。

### B. 自动检测

自动检测依赖主系统的摄像头/跌倒检测服务，和 `vision_service` 的 bridge 状态不是同一条告警链路。

先确认主系统检测状态：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/camera/detection-models/status | ConvertTo-Json -Depth 8
Invoke-RestMethod http://127.0.0.1:8000/api/v1/camera/fall-detection/status | ConvertTo-Json -Depth 8
```

如果未启用，可通过接口开启：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/camera/detection-models/enabled `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"fall_detection_enabled":true,"pose_detection_enabled":true}' |
  ConvertTo-Json -Depth 8
```

再确认视频状态：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/camera/stream-status | ConvertTo-Json -Depth 8
Invoke-RestMethod http://127.0.0.1:8000/api/v1/camera/processed-overlay/status | ConvertTo-Json -Depth 8
```

自动检测验收：

- PC 端：处理后视频有画面，姿态/跌倒 overlay 有状态，告警队列能出现或更新。
- Flutter 家属端：家庭摄像头页有画面，风险状态可读，告警中心收到告警。
- 视频状态：`/api/v1/camera/stream-status` 不应长期 `last_error`，处理后 overlay 不应长期无可绘制数据，bridge 若启用应持续刷新。

## 第七部分：故障排查

### 情况 1：摄像头断电

现象：

- VLC 断流。
- `vision_service /status` 中 `camera_lost=true`、`capture_stale=true` 或 `stream_state=stale/reconnecting`。
- 主系统 `/api/v1/camera/status` 显示离线。

原因：

- 电源断开、适配器不匹配、PoE/网线断开、摄像头重启中。

检查步骤：

1. 看摄像头电源灯、网口灯。
2. 路由器 DHCP 列表是否还有该设备。
3. `Test-NetConnection <IP> -Port <RTSP端口>`。
4. VLC 重连主码流。

解决方案：

- 恢复供电，等待 30 到 60 秒。
- 若 IP 变了，按第二部分重新获取 IP，并更新主系统 `.env` 和 `vision_service` 启动变量。
- 重启 `vision_service` 或调用 `/stream/start` 重新拉流。

### 情况 2：RTSP 不通

现象：

- VLC 无法播放。
- `probe_rtsp_matrix.py` 全部失败。
- `vision_service` 日志出现 open failed、timeout 或 no frame。

原因：

- IP、端口、路径、账号密码不对。
- 摄像头未启用 RTSP。
- 代理/TUN/VPN 干扰局域网。

检查步骤：

1. 确认当前 IP，不看历史 IP。
2. 同时测试 `554` 和 `10554`。
3. 分别测试 `/tcp/av0_0` 和 `/tcp/av0_1`。
4. 用厂家 App 确认密码。
5. 临时关闭 Clash/TUN/VPN。

解决方案：

- 以 VLC 能播放的地址为唯一标准。
- 更新 `.env` 与 `vision_service` 环境变量。
- 必要时恢复出厂并重新设置明文/RTSP 密码。

### 情况 3：WebRTC 黑屏

现象：

- `vision_service /healthz` 正常。
- demo 页面 WebRTC 显示 connected 或 connecting，但画面黑屏。
- WS 可能仍有结果。

原因：

- 主显示流 stale，分析流仍在跑。
- WebRTC 使用的 display source 无新帧。
- 摄像头主码流不可用，只有子码流可用。

检查步骤：

1. 查看 `vision_service /status` 的 `main_stream`、`analysis_stream`。
2. 看 `display_source_current` 是否切到 `analysis`。
3. 用 VLC 单独打开主码流 `/tcp/av0_0`。
4. 刷新 demo 页面或重新点击 Start/Connect。

解决方案：

- 如果主码流坏但子码流可用，临时让主/分析都使用可用流。
- 重启 `vision_service`。
- 现场稳定后再恢复双流：主码流显示，子码流 AI。

### 情况 4：WS 无数据

现象：

- demo 页面 WS 未连接或 `ws_fps=0`。
- `/integration/results/latest` 返回 `has_result=false`。
- `/status.streaming.ws_clients=0` 或 `pipeline.result_publish_fps=0`。

原因：

- demo 没连接到正确服务端口。
- `camera_id` 不一致。
- 检测/发布 worker 未运行。
- 画面无人体，尚未生成检测结果。

检查步骤：

1. 确认打开的是 `http://127.0.0.1:8101/demo`，不是主系统 `8000`。
2. 确认 camera id 是 `camera_01`。
3. 查 `/status` 中 `detection`、`tracking`、`pipeline`。
4. 确保画面中有人体。

解决方案：

- 重新 `/stream/start`。
- 重启视频服务。
- 检查 `DETECTION_ENABLED`、`ENABLE_TRACKING`、`RESULT_PUBLISH_FPS`。

### 情况 5：video_bridge 无更新

现象：

- 主系统 `GET /api/v1/video-bridge/status` 一直显示 `latest.service_state=mock`。
- `updated_at` 不刷新。
- Vue 视频接入口只显示占位状态。

原因：

- `vision_service` 未启用 `VIDEO_BRIDGE_ENABLED`。
- `VIDEO_BRIDGE_URL` 指错端口。
- 主系统后端没启动。
- 两个服务争抢 `8000`，导致请求打到错误进程。

检查步骤：

1. 确认主系统后端在 `8000`：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
```

2. 确认视频服务在 `8101` 或其他非 `8000` 端口：

```powershell
Invoke-RestMethod http://127.0.0.1:8101/healthz
```

3. 查看 `vision_service` 启动窗口是否有 `video_bridge_publish_ok` 或 `video_bridge_publish_failed`。
4. 手动向主系统推送一次测试 payload，确认桥接口本身可用：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/video-bridge/analysis `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"camera_id":"manual-check","service_state":"running","fall_state":"normal","risk":"low"}'
```

解决方案：

- 主系统固定 `8000`。
- 视频服务改为 `8101`。
- 设置 `VIDEO_BRIDGE_URL=http://127.0.0.1:8000/api/v1/video-bridge/analysis`。
- 重启视频服务。

### 情况 6：Flutter 无画面

现象：

- App 能打开，但家庭摄像头页一直等待、黑屏或连接失败。
- 服务器设置测试失败。
- PC 浏览器正常但手机不正常。

原因：

- 真机填了 `127.0.0.1`、`localhost`、`10.0.2.2` 或前端端口。
- PC 防火墙拦截 `8000`。
- 手机和 PC 不在同一局域网。
- bridge 提供的 `stream_url` 不是 Flutter 当前支持的 WebSocket image-frame 流。
- 主系统 `/ws/camera/processed` 没有帧。

检查步骤：

1. 手机浏览器打开 `http://<PC-LAN-IP>:8000/healthz`。
2. App 服务器设置填写 `<PC-LAN-IP>` 和 `8000`。
3. PC 调：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/video-bridge/status | ConvertTo-Json -Depth 8
Invoke-RestMethod http://127.0.0.1:8000/api/v1/camera/stream-status | ConvertTo-Json -Depth 8
```

4. 切换 Flutter 家庭摄像头页的原视频/处理后视频。

解决方案：

- 后端使用 `scripts\start_server.ps1`，确保监听 `0.0.0.0:8000`。
- 放行 Windows 防火墙 `8000`。
- 手机和 PC 接同一 Wi-Fi。
- 若 bridge 只有风险状态无可播放流，先使用主系统现有 `/ws/camera/processed` 或原视频验证画面。

### 情况 7：跌倒告警未出现

现象：

- 视频或 bridge 显示高风险，但 `/api/v1/alarms?active_only=true` 没有跌倒告警。
- Flutter 没有弹出告警。
- `/ws/alarms` 无新消息。

原因：

- `video_bridge` 当前只同步状态，不直接创建告警。
- 主系统跌倒检测未启用。
- `simulate` 接口在非开发环境被关闭。
- 告警被已确认冷却窗口抑制。
- 家属账号没有绑定目标老人或 `FALL_DETECTION_TARGET_FAMILY_IDS` 配置不匹配。

检查步骤：

1. 手动触发 `POST /api/v1/camera/fall-detection/simulate`。
2. 查 active 告警：

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/alarms?active_only=true" | ConvertTo-Json -Depth 8
```

3. 监听 `/ws/alarms`。
4. 查检测状态：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/camera/fall-detection/status | ConvertTo-Json -Depth 8
```

5. 检查 `.env` 中 `FALL_DETECTION_TARGET_DEVICE_MAC`、`FALL_DETECTION_TARGET_ELDER_ID`、`FALL_DETECTION_TARGET_FAMILY_IDS`。

解决方案：

- 用 `simulate` 先验证告警链路。
- 开启主系统跌倒/姿态检测。
- 确认当前登录的 Flutter 家属账号能看到目标老人。
- 若刚确认过跌倒告警，等待跌倒 ack 冷却结束后再测。

## 需要补充的信息

以下信息当前无法从仓库稳定确认，交接时需要现场补齐：

- 摄像头当前真实 IP、RTSP 端口、主/子码流路径的最终值；当前仓库候选值存在 `192.168.8.253:554`、`192.168.8.249:554`、历史 `192.168.8.254:10554`。
- `data/camera_source_of_truth.json` 当前缺失，需现场生成或明确替代来源。
- 摄像头当前密码的安全保存位置，文档中不要明文记录。
- `D:\vision_service` 当前没有 `.env` 文件，需确认是否使用 PowerShell 环境变量启动，或补一份不含真实密码的 `.env`。
- `torchgpu`、`identity310`、`health`、`health-diagnostics` 这几个 Conda 环境是否都已在现场机器安装。
- Flutter 真机设备 ID、Android/iOS 调试授权状态。
- 若希望 Flutter 直接播放 `vision_service` 的视频，需要明确未来桥接输出的 `stream_type` 和 `stream_url`，因为当前 Flutter 远程播放器是 WebSocket image-frame，不是 WebRTC。
