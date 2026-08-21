# 摄像头接入与二次开发完整交接文档

更新时间：2026-05-05  
整理目录：`D:\Program\camear_new`

本文档整合了目前为止围绕这台摄像头的全部对话、截图、说明书、远程地址、浏览器后台线索、本地探测结果和目录内工具清单，目标是让后续接手的工作人员不需要翻聊天记录，也能快速理解现状并继续推进。

---

## 1. 当前任务目标

当前目标不是单纯“看视频”，而是把这台摄像头作为硬件设备接入系统，后续支持：

1. 实时预览
2. 主辅码流访问
3. 截图
4. 录像/回放
5. HLS / RTMP / WebRTC 等流媒体能力
6. ONVIF / RTSP 标准协议接入
7. 后续 AI 检测 / 跌倒检测 / 事件联动

---

## 2. 已确认的设备身份

### 2.1 品牌与型号

根据机身标签、说明书长图和官方产品页，设备属于：

```text
xstrive / 迅思维科技
XSWCAM-WB4MP
4MP 网络摄像机
```

### 2.2 设备类别判断

这台设备属于：

```text
网络摄像机
```

不是：

- 4G 摄像机
- 电池摄像机
- 可视门铃

判断依据：

1. 型号是 `XSWCAM-WB4MP`
2. 标签上 `WIFI` 被勾选
3. 说明书长图写明支持 `WIFI / 有线`
4. 说明书长图写明支持 `RTSP / ONVIF`

### 2.3 已看到的功能线索

从本地设备详情页确认：

- 远程管理地址
- 高清码流
- 辅码流
- 通道 1 / 通道 2
- 本地录像开关
- HLS 开关
- RTMP 推流开关
- 高级配置
- 配置设备 IP
- 重置设备

这说明设备能力明显不只是“预览”，而是完整的网络视频设备平台。

---

## 3. 目前已掌握的关键地址

### 3.1 设备 SN / UID

扫码获得设备唯一标识：

```text
841d5d8b0ac6604c1fd0945eed876459
```

注意：这是设备 SN / UID，不是密码。

### 3.2 远程控制地址

用户已确认以下地址来自设备详情页：

```text
http://841d5d8b0ac6604c1fd0945eed876459.cloud.xstrive.com:9502/
http://841d5d8b0ac6604c1fd0945eed876459.cloud.xstrive.com:9502/cloud
```

### 3.3 连通性验证结果

本地验证结果：

1. 两个地址都返回同一个前端页面
2. 页面标题为：

```text
配置后台
```

3. 域名解析结果：

```text
841d5d8b0ac6604c1fd0945eed876459.cloud.xstrive.com
-> 45.120.100.178
```

4. `9502/tcp` 端口可达

说明：

```text
设备远程 Web 管理后台已经存在，且浏览器可以访问。
```

---

## 4. 官方文档与来源

### 4.1 用户提供的远程文档

用户给出的官方/厂商文档入口：

```text
http://182.44.40.174:19999/web/#/p/7e7292846bde0256970377bd8eeefb0d
http://docs.xvipcloud.com/web/#/p/c8b25dcd9be8536bc1607c85fbe66251
```

说明：

1. 第一份是 4MP 摄像头电子版说明书
2. 第二份是 WiFi 摄像头配网说明

### 4.2 已抽取到的本地说明书线索

当前目录中的 `说明书长图.png` 已经提取出以下关键内容：

- 类型：4MP 网络摄像头
- 编码：`H.264 / H.265`
- 最大分辨率：`2560x1440`
- 最大帧率：`25FPS`
- 协议：`ONVIF / GB28181 / TCP/IP / DHCP / DNS / NTP / RTSP / RTMP`
- 有线口：`RJ45 10M/100M`
- 供电：`DC12V 2A`
- 音频输入输出：支持
- 支持本地客户端
- 支持移动侦测
- 支持网络访问
- 支持本地升级
- 支持本地录像与远程录像回放

### 4.3 快启 PDF 抽取结果

本地文件：

`D:\Program\camear_new\tools\VStarcam_C_series_quick_start.pdf`

从 PDF 中提取到的重点：

1. App 名称为：

```text
Eye4
```

2. 首次使用建议：

- 手机连接 `2.4GHz WiFi`
- 摄像头放在路由器 2 米内

3. 复位方式：

```text
按住 Reset 约 5 秒
听到 "Reset completed"
```

4. App 添加路径：

- 扫二维码
- 或 `Others -> IP Camera -> Wireless installation`

5. 文档明确提示：

```text
如果连接失败，请尝试用网线方式添加
```

---

## 5. App 侧已确认的情况

### 5.1 App 类型

目前判断厂商 App 是：

```text
Eye4
```

### 5.2 App 中正确的设备类型选择

用户提供截图显示 “其他添加方式” 中存在：

- 网络摄像机
- 4G 摄像机
- 电池摄像机
- 可视门铃

根据型号与说明书，正确选择应为：

```text
网络摄像机
```

### 5.3 App 中更合适的添加方式

用户截图中“添加摄像机”页提供了：

- 新声波
- 扫描二维码
- 无线配置
- 网线连接
- 手动添加
- AP 模式添加

当前最推荐路径：

```text
网络摄像机 -> 网线连接
```

原因：

1. 当前设备带有网口
2. 当前用户已在尝试有线方式
3. `手动添加` 需要 UID + 密码
4. `AP 模式添加` 适合设备热点模式
5. `无线配置` 更适合复位后的 WiFi 首配

---

## 6. 浏览器后台已侦察到的能力

从设备远程管理后台前端脚本中，已经确认后台模块包含：

- `dashboard`
- `playback`
- `vodFile`
- `system/password`
- `system/netTools`
- `system/obs`
- `system/draw`
- `system/ai`
- `system/args`
- `system/graphics`
- `system/face`
- `system/faceInfo`
- `system/snap`
- `system/car`
- `system/fileList`
- `system/remSerial`
- `system/customCmd`
- `system/gps`
- `system/update`
- `system/recovery`
- `system/reset`
- `system/reboot`
- `system/restart`
- `system/startPush`
- `system/interfaceAuth`
- `system/webrtc`
- `system/decode`
- `system/timezone`
- `system/config`
- `system/users`

这表明设备具备如下潜在能力：

1. 实时视频与回放
2. 系统密码管理
3. 网络工具与网络配置
4. OSD / Draw / ROI / 图形配置
5. AI 相关开关或页面
6. 人脸 / 车辆 / 抓拍类能力
7. 用户管理
8. 固件升级 / 恢复 / 重置 / 重启
9. WebRTC
10. 启动推流
11. 接口认证

目前这些能力只完成了只读侦察，没有实际点击修改。

---

## 7. 本地网络与物理链路现状

### 7.1 电脑侧网卡状态

多次检测结果一致：

```text
以太网 / Realtek Gaming GbE Family Controller
Status: Disconnected
```

### 7.2 结论

这意味着：

```text
电脑当前没有和摄像头建立有效物理以太网链路
```

所以目前无法完成：

1. 本地网线侧发现摄像头
2. 读取局域网 IP
3. 本地 RTSP / ONVIF 验证
4. 局域网直接抓流

### 7.3 已确认的原因线索

说明书长图明确写明：

```text
供电：DC12V 2A
```

因此高概率问题是：

1. 只插了网线，没单独供电
2. 网线插法不对
3. 需要 PoE 但未使用 PoE 设备
4. 摄像头当前未正常启动

### 7.4 当前最大阻塞

当前不是“协议搞不清”，而是：

```text
设备本地侧还没真正上电并建立链路
```

---

## 8. 关于账号密码的当前判断

用户当前口述：

```text
账号密码都是 admin
```

但这只能算“待验证线索”，不能直接当作最终结论。

原因：

这类设备通常至少存在三类认证：

1. Eye4 App 账号密码
2. 设备浏览器后台账号密码
3. RTSP / ONVIF 明文密码

它们可能：

- 用户名都像 `admin`
- 但密码不一定相同

目前已经明确的安全边界：

1. 不能从 SN 反推密码
2. 不能做密码破解
3. 只能通过合法的登录、恢复出厂、明文密码设置来推进

### 8.1 已有的常见默认凭据线索

资料中曾出现过的常见组合：

```text
账号：admin
候选默认密码：888888
```

但不能保证当前设备仍使用默认密码。

---

## 9. 二次开发当前已经足够提出的要求

目前已经足以让工作人员开始做：

1. 设备类型判断
2. 接入方案设计
3. 后台功能清点
4. 流媒体接入路线选择
5. 后续系统对接评估

### 9.1 已经足够提出的技术方向

可以要求工作人员评估并推进：

1. RTSP 直连方案
2. ONVIF 接入方案
3. HLS 页面播放方案
4. RTMP 推流到服务器方案
5. WebRTC 低延迟预览方案
6. 后续 AI 检测/跌倒检测方案

---

## 10. 还缺哪些关键信息

虽然已经能提需求，但要真正打通接入，仍缺下面这些关键情报：

### 10.1 必须补齐

1. 浏览器后台是否真的能用 `admin / admin` 登录
2. 设备局域网本地 IP
3. RTSP 是否可用
4. ONVIF 是否可用
5. HLS / RTMP / WebRTC 的真实可用地址或启用状态
6. 通道 1 / 通道 2 的具体含义

### 10.2 最好补齐

1. 后台首页截图
2. 网络设置截图
3. 用户管理/密码页截图
4. 码流设置截图
5. HLS / RTMP / WebRTC 页截图
6. AI / 抓拍 / 回放页截图
7. 固件版本信息

---

## 11. 推荐的后续操作顺序

### 11.1 现场优先级最高的动作

1. 给摄像头接 `12V 2A` 独立供电
2. 把摄像头接到路由器 LAN
3. 电脑与手机也接入同一路由器
4. 再尝试 Eye4 中：

```text
网络摄像机 -> 网线连接
```

### 11.2 如果 App 还不行

执行恢复出厂：

1. 上电约 30 秒
2. 用针按住 `Reset` 约 5 秒
3. 听到 `Reset completed`
4. 再次在 Eye4 中重新添加

### 11.3 登录后台后优先查看的页面

只读采集，不修改：

1. 设备信息
2. 网络设置
3. 用户/密码
4. 主码流/辅码流
5. HLS / RTMP / WebRTC
6. AI / Snap / Playback

---

## 12. 当前目录内容清单

当前工作目录：

`D:\Program\camear_new`

### 12.1 摄像头相关文档与脚本

1. [CAMERA_BEGINNER_GUIDE.md](D:/Program/camear_new/CAMERA_BEGINNER_GUIDE.md:1)
   - 面向初学者的摄像头基础使用与二开指南

2. [CAMERA_RECOVERY_AND_HANDOFF.md](D:/Program/camear_new/CAMERA_RECOVERY_AND_HANDOFF.md:1)
   - 恢复、复位、交接说明，强调物理链路与合法恢复路径

3. [camera_probe_xstrive.py](D:/Program/camear_new/camera_probe_xstrive.py:1)
   - RTSP 摄像头探测脚本
   - 支持主辅码流、端口检测、截图输出

4. [camera_link_probe.ps1](D:/Program/camear_new/camera_link_probe.ps1:1)
   - Windows 下的链路/候选 IP/端口检测脚本
   - 当前已验证能准确提示“有线网卡无物理链路”

5. [run_camera_probe_ai.ps1](D:/Program/camear_new/run_camera_probe_ai.ps1:1)
   - 用本机已有的 `AI` / `health` conda 环境来运行探测脚本

6. [camera_set_wired_ip.ps1](D:/Program/camear_new/camera_set_wired_ip.ps1:1)
   - 一键切换有线网卡到静态 IP 或 DHCP

7. `说明书长图.png`
   - 4MP 网络摄像头说明书长图截图
   - 已从中提取出协议、供电、编码等关键信息

### 12.2 厂商工具与资料目录

#### `tools`

路径：`D:\Program\camear_new\tools`

内容：

1. `VStarcam_C_series_quick_start.pdf`
   - 快速开始说明书 PDF
   - 已提取出 `Eye4`、`Reset completed`、网线添加等关键信息

2. `odm-v2.2.250r.msi`
   - ONVIF Device Manager 安装包
   - 后续可用于验证 ONVIF

3. `vlc-3.0.23-win64.exe`
   - VLC 安装包
   - 后续可用于验证 RTSP/HLS

4. `python_libs`
   - 本地补充的 Python 依赖目录
   - 已成功放入 `pypdf`

#### `设备搜索助手v3.0`

路径：`D:\Program\camear_new\设备搜索助手v3.0`

内容：

1. `CameraConfig.exe`
   - 厂商提供的设备搜索/配置工具

2. `config.ini`
3. `dualserver.ini`
4. `CameraConfig.url`
5. `test.log`
   - 日志中已确认它只在 Wi-Fi 网卡上空转，没有发现有线侧设备

### 12.3 当前目录中的其他文件

以下文件不是本轮摄像头工作核心材料，而是原有数据文件：

- `README.md`
- `single_turn_public_zh_medical.jsonl`
- `single_turn_monitoring_focus_zh_medical.jsonl`
- `multi_turn_public_zh_medical.jsonl`
- `multi_turn_monitoring_focus_zh_medical.jsonl`

这些文件是医疗数据集，不属于摄像头配置主线。

---

## 13. 给工作人员的最简交接话术

```text
我现在有一台 xstrive / 迅思维 XSWCAM-WB4MP 4MP 网络摄像机。

已经确认：
1. 设备支持 RTSP / ONVIF / RTMP / HLS / WebRTC
2. 远程配置后台可访问
3. 后台存在系统配置、用户、网络、码流、AI、回放、抓拍、推流等模块
4. 本地 App 已看到高清码流、辅码流、通道1/2、HLS、RTMP、高级配置、配置设备IP、重置设备
5. 当前本地最大阻塞是设备网线侧没有和电脑建立物理链路

请你优先帮我完成：
1. 验证后台账号密码
2. 确认局域网 IP
3. 验证 RTSP 和 ONVIF
4. 确认 HLS / RTMP / WebRTC 的真实接入方式
5. 基于这些能力设计并实现项目接入
```

---

## 14. 当前状态总结

### 2026-05-07 最新突破

在 2026-05-07 的进一步联调中，已经确认：

1. 摄像头真实局域网 IP 不是此前探测到的 `192.168.8.254`，而是后台首页显示的：

```text
192.168.8.248
```

2. 经过 RTSP 矩阵测试，最终成功可用的访问方式为：

```text
rtsp://admin:admin@192.168.8.248:554/tcp/av0_1
rtsp://admin:admin@192.168.8.248:554/tcp/av0_0
```

3. 以下组合已明确失败：

- `192.168.8.248:10554`
- `admin / 888888`
- `admin / 123456`
- `admin / 000000`

4. 已在本机实现一个本地实时预览服务：

```text
http://127.0.0.1:8090/viewer
```

该服务不依赖 App 播放页，也不依赖设备控制台中的播放页面，而是：

```text
摄像头 RTSP -> 本机 Python 服务 -> 本地浏览器 MJPEG 实时预览
```

5. 健康检查结果通过：

- `/health` 返回 `running=true`
- `has_frame=true`
- `frame_count > 0`
- `last_error = null`

6. 截图接口通过：

```text
http://127.0.0.1:8090/snapshot.jpg
```

返回 `200 OK`，说明服务已真正取到实时帧。

### 这意味着什么

这意味着当前主目标已经达成：

```text
已经可以不通过控制台或 App，直接在本机浏览器中查看摄像头实时画面。
```

### 已新增的本地实时预览文件

1. [camera_live_server.py](D:/Program/camear_new/camera_live_server.py:1)
   - RTSP -> 本地 MJPEG 浏览器预览服务

2. [run_camera_live_server.ps1](D:/Program/camear_new/run_camera_live_server.ps1:1)
   - 一键启动本地实时预览服务

3. [camera_matrix_probe.py](D:/Program/camear_new/camera_matrix_probe.py:1)
   - 批量验证用户/密码/端口/主辅码流/UDP/TCP 的 RTSP 矩阵探测脚本

4. [camera_scan_subnet.ps1](D:/Program/camear_new/camera_scan_subnet.ps1:1)
   - 对指定网段做受控端口扫描，用于发现摄像头 IP

5. [camera_runtime_start.ps1](D:/Program/camear_new/camera_runtime_start.ps1:1)
   - 单实例启动脚本，负责停止旧实例、生成运行时配置并启动主服务

6. [camera_runtime_stop.ps1](D:/Program/camear_new/camera_runtime_stop.ps1:1)
   - 停止当前运行时

7. [camera_runtime_status.ps1](D:/Program/camear_new/camera_runtime_status.ps1:1)
   - 查看当前运行状态和健康检查结果

### 当前最推荐的开发入口

在当前阶段，最适合开发和后续系统接入的入口已经明确为：

```text
RTSP:
rtsp://admin:admin@192.168.8.248:554/tcp/av0_1
rtsp://admin:admin@192.168.8.248:554/tcp/av0_0
```

如需立即人工查看实时画面：

```text
本机浏览器打开：
http://127.0.0.1:8090/viewer
```

### 已经完成

1. 设备类型判断完成
2. App 添加类型判断完成
3. 远程后台地址验证完成
4. 浏览器后台功能侦察完成
5. 本地工具链整理完成
6. RTSP/链路/静态 IP 脚本准备完成
7. 已成功打通 RTSP 本地预览
8. 已成功实现不经控制台/App 的本地浏览器查看方案
9. 已补齐模块化运行时、配置文件、日志落盘和标准化 API 基础结构
10. 已补齐单实例启动/停止/状态脚本
11. 已补齐可配置的 Basic Auth 认证层，并验证 401 与授权访问行为
12. 已补齐计划任务式服务化脚本（安装/卸载），但默认不自动注册
13. 已补齐无需管理员权限的“当前用户 Startup 启动项”自动拉起方案，并已实际安装成功
14. 已完成 ONVIF 第一轮本地探测，结论为当前设备在 `192.168.8.248:10080/onvif/...` 标准路径上未监听，需转后台配置页进一步核查

### 尚未完成

1. ONVIF 验证
2. HLS 真实地址确认
3. RTMP 推流配置确认
4. WebRTC 配置确认
5. 更强的进程守护和完整服务化验证
6. 实际项目接入实现

### 当前最关键的一句

```text
已经足够向工作人员提出明确要求；RTSP 本地预览已打通，接下来重点转向 ONVIF、HLS、RTMP、WebRTC 和项目正式接入。
```
