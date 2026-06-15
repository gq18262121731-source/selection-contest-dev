# 摄像头配置说明

## 当前配置

**摄像头信息**：
- 型号：IPC-SDK (8MP-升级版) - P2P摄像头
- IP：192.168.8.254
- 端口：10554
- 用户名：admin
- 密码：8888888

**工作模式**：快照中继模式（P2P摄像头不支持标准RTSP）

## 已应用的优化

### 1. 代码优化
- 快照模式FPS上限：2fps → 6fps
- CORS配置：添加明确的允许来源

### 2. 配置优化（`.env`）
```env
CAMERA_IP=192.168.8.254
CAMERA_USER=admin
CAMERA_PASSWORD=8888888
CAMERA_SOURCE_MODE=rtsp
CAMERA_RTSP_PORT=10554
CAMERA_STREAM_FPS=6
CAMERA_SNAPSHOT_TIMEOUT_SECONDS=3.0
CAMERA_PROBE_TIMEOUT_SECONDS=2.0
CAMERA_STREAM_JPEG_QUALITY=8
```

## 重启服务

修改配置后需要重启后端服务：

```bash
# 停止当前后端（Ctrl+C）
python run.py
```

## 性能说明

**快照模式特点**：
- FPS：1-6帧/秒（取决于摄像头响应速度）
- 延迟：低（10-20ms）
- 带宽：低
- 适用场景：监控、跌倒检测

**为什么不能达到更高FPS**：
- 这是P2P摄像头，使用专有协议
- 不支持标准RTSP流媒体
- 快照接口有速度限制

## 如需高FPS（15-30fps）

### 选项1：使用摄像头专用APP
- 下载IPC360或V380等APP
- 使用UID添加：AAC2621503XM5V
- 密码：8888888

### 选项2：更换为标准RTSP摄像头
推荐品牌：
- 海康威视（Hikvision）
- 大华（Dahua）
- 支持ONVIF/RTSP的IP摄像头

## 故障排除

### 问题1：CORS错误
**症状**：浏览器控制台显示CORS policy错误

**解决**：
1. 确认后端已重启
2. 清除浏览器缓存
3. 使用相同的地址访问（都用localhost或都用127.0.0.1）

### 问题2：视频暂停或连接中
**症状**：显示"Video paused"或"Connecting"

**解决**：
1. 检查后端是否正常运行
2. 刷新页面
3. 查看后端日志是否有错误

### 问题3：FPS仍然很低
**症状**：FPS低于1

**原因**：
- 摄像头响应慢
- 网络延迟
- 摄像头负载高

**解决**：
1. 重启摄像头
2. 检查网络连接
3. 关闭摄像头上的其他连接

## 技术细节

### 工作流程
```
摄像头 → HTTP快照 → 后端缓存 → WebSocket → 前端显示
(P2P)    (定期请求)   (中继)      (推送)     (视频流)
```

### 系统行为
1. 后端首先尝试RTSP流（会失败）
2. 自动降级到快照模式
3. 定期从摄像头抓取JPEG
4. 通过WebSocket推送给前端

### 配置说明
- `CAMERA_STREAM_FPS=6`：目标帧率（快照模式上限）
- `CAMERA_SNAPSHOT_TIMEOUT_SECONDS=3.0`：单次快照超时
- `CAMERA_PROBE_TIMEOUT_SECONDS=2.0`：连接探测超时
- `CAMERA_STREAM_JPEG_QUALITY=8`：JPEG质量（2-12，越高越清晰）
