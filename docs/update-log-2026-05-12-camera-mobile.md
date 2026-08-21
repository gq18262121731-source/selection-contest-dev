# 2026-05-12 摄像头与移动端模型控制更新日志

## 更新内容

- 移动端家属摄像头页移除“开始视频”按钮，进入页面后默认启动视频预览与状态刷新。
- 增加跌倒检测模型、姿态检测模型的开启/关闭控制，并接入后端统一模型状态接口。
- 增加浏览器本地摄像头预览组件，用于 Web 调试时展示流畅视频，同时定时抽帧提交后端分析。
- 补充后端视频帧分析接口，支持前端上传单帧图片后触发姿态/跌倒识别，并回传最新识别结果。
- 优化后端本地摄像头取帧逻辑，过滤黑屏、低亮度、低纹理帧，降低模型误判和空帧问题。
- 恢复 Flutter 登录页到 GitHub 最初版本的视觉样式，保留当前登录、注册、服务器设置逻辑。
- Web 管理端摄像头卡片增加实时画面、跌倒检测、姿态检测模式切换，以及跌倒告警状态展示。

## 后端接口

- `GET /api/v1/camera/detection-models/status`
- `POST /api/v1/camera/detection-models/enabled`
- `POST /api/v1/camera/analyze-frame`
- `GET /api/v1/camera/analyze-frame/status`
- 保留兼容接口：
  - `POST /api/v1/camera/fall-detection/enabled`
  - `POST /api/v1/camera/pose-detection/enabled`

## 构建与验证

- `dart analyze`：通过，无 error / warning；仅保留项目既有 info 级提示。
- `flutter build apk --debug --verbose`：通过。
- APK 产物：`mobile/flutter_app/build/app/outputs/flutter-apk/app-debug.apk`
- APK 大小：`208630672` 字节。
- APK 生成时间：`2026-05-12 06:47:34`

## 上传说明

- `955640c` 提交只上传源码与更新日志。
- 后续补充提交会通过 Git LFS 上传 APK 构建产物和摄像头 SDK/说明书目录。
- 本地摄像头运行配置 `camera_runtime_external/camera_live_config.json` 会随补充提交上传，用于私有仓库内保留当前调试配置。
- 仍不上传缓存目录、临时备份文件、Python `__pycache__` 和无关副本文件。
