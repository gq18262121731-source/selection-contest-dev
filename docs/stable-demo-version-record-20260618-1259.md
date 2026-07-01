# 稳定演示版本记录

记录时间：2026-06-18 12:59（Asia/Shanghai）

## 1. 当前 Git 变更清单

### 已修改文件
- `.vscode/settings.json`
- `backend/api/camera_api.py`
- `backend/dependencies.py`
- `backend/main.py`
- `backend/services/camera_setup_config_service.py`
- `mobile/flutter_app/lib/features/care/screens/family_video_screen.dart`

### 新增未跟踪文件
- `backend/services/family_camera_stream_service.py`
- `runtime_logs/backend-family-stream.err.log`
- `runtime_logs/backend-family-stream.out.log`
- `runtime_logs/backend-restart-20260618.err.log`
- `runtime_logs/backend-restart-20260618.out.log`
- `runtime_logs/device_check/`

### 当前 diff 统计
- `6 files changed, 684 insertions(+), 352 deletions(-)`

## 2. 当前 APK 信息

### 主 APK 路径
- `D:\health_original\health1\mobile\flutter_app\build\app\outputs\flutter-apk\app-release.apk`

### 稳定备份 APK
- `D:\health_original\health1\mobile\flutter_app\build\app\outputs\flutter-apk\app-release-family-video-balanced-20260618-1248.apk`

## 3. 当前真机安装状态

- 包名：`com.example.ai_health_iot_flutter`
- `versionName=0.1.0`
- `lastUpdateTime=2026-06-18 12:48:08`

## 4. 家属端视频最终参数

- 默认质量档：`balanced`
- 主播放流：`/api/v1/camera/family-stream.mjpg?quality=balanced`
- 探活快照：`/api/v1/camera/family-snapshot?quality=balanced`
- 视频来源：`/tcp/av0_0`
- 来源类型：`main`
- 输出分辨率：`960x540`
- 输出帧率：约 `9.5 - 10.6 fps`，现场稳定观察值常见在 `10.4 - 10.8 fps`
- 平均 JPEG 大小：约 `46KB - 50KB`，现场验收阶段观测峰值可到约 `53KB`
- 画面类型：`clean raw`
- 视觉结果：无检测框、无网格线、无 Processed 调试文字

## 5. 说明

- 本次仅做稳定版本备份与记录，未修改业务逻辑。
- 家属端视频主链路保持为 `family-stream.mjpg`，不回退到 `processed-snapshot`。
