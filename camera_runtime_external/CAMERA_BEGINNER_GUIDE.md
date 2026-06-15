# 迅思维 XSWCAM-WB4MP 摄像头傻瓜式使用与二次开发指南

适用设备：照片中的 `xstrive / 迅思维科技` 网络摄像机，型号 `XSWCAM-WB4MP`。

目标：让你先看到摄像头画面，再用代码读取画面，最后把它二次开发成项目里的硬件设备。

---

## 0. 先说结论

这台摄像头优先按普通 IP 摄像头使用：

```text
摄像头 -> 网线/路由器 -> 局域网 IP -> RTSP 视频流 -> VLC/OpenCV/后端服务
```

最重要的 RTSP 地址模板是：

```text
rtsp://admin:明文密码@摄像头IP:10554/tcp/av0_0
rtsp://admin:明文密码@摄像头IP:10554/tcp/av0_1
```

含义：

| 部分 | 含义 |
| --- | --- |
| `admin` | 默认账号 |
| `明文密码` | 需要在厂家 App 里开启/设置 |
| `10554` | RTSP 固定端口 |
| `tcp` | 推荐先用 TCP，更稳 |
| `av0_0` | 主码流，清晰，适合算法 |
| `av0_1` | 子码流，轻量，适合预览 |

ONVIF 常用信息：

```text
地址：http://摄像头IP:10080/onvif/device_service
账号：admin
密码：你设置的明文密码
```

注意：你现在说摄像头已通过网线连接电脑，但我在本机检查到 Windows 的“以太网”状态是 `Disconnected`。这说明电脑网口暂时没有检测到物理连接。请先按第 1 节排查，否则后续找 IP、拉流都会失败。

---

## 1. 接线与供电，先让电脑真的“看见网线”

### 1.1 摄像头必须供电

网线不一定给摄像头供电。请确认你的摄像头属于哪种供电：

| 情况 | 你要做什么 |
| --- | --- |
| 摄像头有圆口电源 | 插上 12V 电源适配器 |
| 摄像头写着 PoE | 需要 PoE 交换机或 PoE 注入器 |
| 只插普通电脑网口 | 大多数情况下不能给摄像头供电 |

判断是否上电：

1. 摄像头红外灯、指示灯是否亮。
2. 摄像头是否有启动声音或镜头自检动作。
3. 网口旁边的灯是否亮或闪烁。

### 1.2 不推荐摄像头网线直连电脑

直连电脑不是完全不行，但对新手不友好，因为没有路由器 DHCP 自动分配地址。

推荐接法：

```text
摄像头网线 -> 路由器 LAN 口
电脑网线/Wi-Fi -> 同一个路由器
摄像头电源 -> 12V 或 PoE
```

如果你坚持直连电脑，则电脑和摄像头必须在同一个网段，后面第 5 节有直连方案。

### 1.3 检查 Windows 是否识别网线

在 PowerShell 执行：

```powershell
Get-NetAdapter | Format-Table -Auto Name,Status,LinkSpeed,MacAddress
```

你希望看到类似：

```text
以太网  Up  1 Gbps
```

如果还是：

```text
以太网  Disconnected  0 bps
```

请先处理：

1. 摄像头是否供电。
2. 换一根网线。
3. 网线是否插在摄像头网口，不是电源口。
4. 电脑网口灯是否亮。
5. 如果摄像头是 PoE，普通电脑网口不能直接供电。

---

## 2. 第一次初始化摄像头

这类摄像头通常必须先用厂家 App 初始化一次，否则 RTSP/ONVIF 不稳定或不可用。

### 2.1 手机 App 初始化

1. 给摄像头上电。
2. 手机安装厂家说明书二维码对应的监控 App。
3. 用 App 添加/绑定摄像头。
4. 在 App 的摄像头设置里找到“明文密码”。
5. 开启“明文密码”。
6. 设置一个新密码，并记下来。

建议记录：

```text
账号：admin
明文密码：你设置的新密码
```

### 2.2 没有外网怎么办

如果现场路由器完全没有外网：

1. 长按摄像头 Reset，把摄像头恢复出厂。
2. 摄像头会发出类似 `@IPC-` 开头的 Wi-Fi 热点。
3. 手机连接这个热点。
4. 打开厂家 App 添加设备。
5. 在设置里开启明文密码。

---

## 3. 找到摄像头 IP

### 3.1 推荐：用厂家内网查找器

如果你有 `CamFinder_1.0.6.18.exe`，直接运行它。

你要记下：

```text
摄像头 IP
摄像头名称
端口信息
```

例如：

```text
192.168.1.126
```

### 3.2 不用查找器：用 PowerShell 粗略找

先看电脑自己的 IP：

```powershell
ipconfig
```

如果电脑是：

```text
192.168.1.50
```

那摄像头大概率也是：

```text
192.168.1.xxx
```

可以尝试：

```powershell
arp -a
```

也可以用本文附带脚本做常见 IP 探测。

---

## 4. 用 VLC 先看画面

不要一上来写代码。先用 VLC 播放，确认摄像头本身能出画面。

1. 打开 VLC。
2. 选择“媒体”。
3. 选择“打开网络串流”。
4. 输入 RTSP 地址。

先试子码流：

```text
rtsp://admin:你的明文密码@摄像头IP:10554/tcp/av0_1
```

如果能播放，再试主码流：

```text
rtsp://admin:你的明文密码@摄像头IP:10554/tcp/av0_0
```

如果 TCP 不行，再试 UDP：

```text
rtsp://admin:你的明文密码@摄像头IP:10554/udp/av0_1
rtsp://admin:你的明文密码@摄像头IP:10554/udp/av0_0
```

成功标准：VLC 能看到实时画面。

---

## 5. 网线直连电脑的特殊做法

更推荐接路由器。如果你必须网线直连电脑，需要给电脑手动设置一个静态 IP。

### 5.1 先猜摄像头默认网段

厂家资料里出现过示例 IP：

```text
192.168.1.126
```

之前项目里也使用过：

```text
192.168.8.253
```

所以可以先尝试两个网段：

| 摄像头可能 IP | 电脑以太网可设置成 |
| --- | --- |
| `192.168.1.126` | `192.168.1.10` |
| `192.168.8.253` | `192.168.8.10` |

### 5.2 Windows 设置静态 IP

打开：

```text
控制面板 -> 网络和 Internet -> 网络连接 -> 以太网 -> 属性 -> IPv4
```

设置示例一：

```text
IP 地址：192.168.1.10
子网掩码：255.255.255.0
默认网关：留空或 192.168.1.1
DNS：留空
```

设置示例二：

```text
IP 地址：192.168.8.10
子网掩码：255.255.255.0
默认网关：留空或 192.168.8.1
DNS：留空
```

然后测试：

```powershell
ping 192.168.1.126
ping 192.168.8.253
```

如果 ping 不通，不一定代表摄像头不在线，有些设备禁 ping。还要测试端口：

```powershell
Test-NetConnection 192.168.1.126 -Port 10554
Test-NetConnection 192.168.8.253 -Port 10554
```

---

## 6. 用 Python 测试拉流

当前目录提供了脚本：

```text
camera_probe_xstrive.py
```

先安装依赖：

```powershell
pip install opencv-python
```

测试子码流：

```powershell
python .\camera_probe_xstrive.py --host 192.168.1.126 --password 你的明文密码 --stream sub --transport tcp
```

测试主码流：

```powershell
python .\camera_probe_xstrive.py --host 192.168.1.126 --password 你的明文密码 --stream main --transport tcp
```

如果你想直接传完整 RTSP：

```powershell
python .\camera_probe_xstrive.py --source "rtsp://admin:你的明文密码@192.168.1.126:10554/tcp/av0_1"
```

成功后会输出 JSON，并保存一张截图：

```text
artifacts/camera_probe_frame.jpg
```

---

## 7. 二次开发路线

### 阶段一：最稳的通用开发

先别碰厂商 SDK，直接用 RTSP：

```text
RTSP -> OpenCV/FFmpeg -> 取帧 -> AI 算法/截图/录像/推流
```

适合开发：

1. 实时预览。
2. 截图。
3. 录像。
4. 人体检测。
5. 跌倒检测。
6. 入侵检测。
7. 离岗/久坐/异常姿态检测。
8. 视频流转 WebSocket/MJPEG/HTTP-FLV/WebRTC。

Python 最小示例：

```python
import cv2

url = "rtsp://admin:你的明文密码@192.168.1.126:10554/tcp/av0_1"
cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)

if not cap.isOpened():
    raise RuntimeError("摄像头打不开")

while True:
    ok, frame = cap.read()
    if not ok:
        continue
    cv2.imshow("camera", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
```

### 阶段二：设备化接入项目

建议把摄像头当成一类硬件设备管理：

```text
camera_id
name
sn
ip
username
password_secret_key
rtsp_main_url
rtsp_sub_url
onvif_url
room_id
elder_id
roi_rect
enabled
last_seen_at
```

注意：真实密码不要存明文在代码里，放 `.env`、数据库加密字段或密钥管理系统。

### 阶段三：AI 能力开发

推荐处理链：

```text
摄像头 RTSP
  -> 拉帧服务
  -> 降帧/缩放
  -> 人体检测/姿态估计
  -> 事件判断
  -> 告警
  -> 截图留证
  -> 前端展示/家属通知
```

不要一开始就追求复杂。先完成：

1. 每秒稳定拿到 5 到 15 帧。
2. 能保存截图。
3. 能识别画面里有没有人。
4. 能把异常事件写成 JSON。
5. 能让前端看到事件。

### 阶段四：ONVIF 控制

如果设备支持 ONVIF，可以做：

1. 查询设备信息。
2. 查询媒体配置。
3. 获取 RTSP 地址。
4. 云台控制。
5. 预置位。

但照片里的 `XSWCAM-WB4MP` 看起来像固定镜头，不是 PTZ 云台机，云台控制不一定可用。

### 阶段五：厂商 SDK

只有下面这些需求才建议研究厂商 SDK：

1. 远程 P2P 连接，不在同一局域网也要看。
2. 双向语音对讲。
3. SD 卡录像回放。
4. App 私有能力。
5. 设备配网。
6. 厂商云平台能力。

一般视频 AI 二开不需要 SDK，RTSP 更简单、更稳、更跨平台。

---

## 8. 常见错误

### 错误一：电脑以太网显示 Disconnected

这不是代码问题。先查：

1. 摄像头有没有供电。
2. 是否需要 PoE。
3. 网线是否可用。
4. 网口灯是否亮。
5. 是否插到了路由器 LAN 口。

### 错误二：找不到 IP

优先把摄像头和电脑接到同一个路由器。然后用 CamFinder。

### 错误三：VLC 播放失败

按顺序试：

```text
/tcp/av0_1
/tcp/av0_0
/udp/av0_1
/udp/av0_0
```

同时确认：

1. IP 正确。
2. 明文密码已开启。
3. 密码没有输错。
4. 端口是 `10554`。

### 错误四：能看画面，但很卡

先用子码流：

```text
av0_1
```

再降低算法处理帧率，比如每秒只处理 5 帧。

---

## 9. 推荐你现在马上做的 5 步

1. 确认摄像头供电，电脑以太网从 `Disconnected` 变成 `Up`。
2. 最好把摄像头接到路由器 LAN 口，不要直连电脑。
3. 用厂家 App 开启“明文密码”。
4. 用 CamFinder 找到摄像头 IP。
5. 用 VLC 播放 `rtsp://admin:明文密码@IP:10554/tcp/av0_1`。

只要 VLC 能出画面，二次开发基本就打通了一半。

