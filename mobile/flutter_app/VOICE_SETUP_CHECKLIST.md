# Flutter 语音交互功能 - 快速配置检查清单

## ✅ 代码集成检查

### 1. 文件创建确认

```
✅ lib/features/voice/services/omni_realtime_service.dart (266 行)
   - WebSocket 客户端
   - 连接、音频处理、事件处理

✅ lib/features/voice/providers/omni_voice_provider.dart (195 行)
   - Provider 状态管理
   - 录音流程、音频上传、响应处理

✅ lib/features/voice/widgets/elder_voice_interaction_widget.dart (338 行)
   - 可复用 UI Widget
   - 状态显示、录音按钮、响应显示

✅ lib/features/voice/screens/elder_voice_screen.dart (276 行)
   - 完整屏幕
   - 欢迎卡片、指导、建议问题
```

### 2. 文件修改确认

```
✅ lib/main.dart
   修改项：添加 OmniVoiceProvider 和 OmniRealtimeService 导入
   修改项：在 Provider 列表中注册 OmniVoiceProvider

✅ lib/core/services/audio_service.dart
   修改项：添加公开方法 playBytes(List<int> bytes, String format)

✅ lib/features/care/screens/elder_home_screen.dart
   修改项：添加"语音对话"按钮
   修改项：添加导航到 ElderVoiceScreen
```

### 3. 依赖检查

在 `pubspec.yaml` 中确认以下依赖版本：

```yaml
dependencies:
  # 现有依赖
  flutter:
    sdk: flutter
  provider: ^6.0.0          # 状态管理
  web_socket_channel: ^3.0.3  # WebSocket (需要)
  audioplayers: ^5.2.1        # 音频播放 (需要)
  record: ^5.2.1              # 音频录制 (需要)
  
  # 应已存在
  dio: ^5.7.0
  path_provider: ^2.1.3
  permission_handler: ^11.3.1
```

**操作：** 运行 `flutter pub get` 确保所有依赖已安装。

## 🔐 配置检查

### 1. API 密钥配置

在 `lib/main.dart` 中确认 API 密钥设置：

```dart
// ❌ 开发期间可以硬编码，但要注意安全
const apiKey = 'sk-67d1be1cac0649b9a8839d2328bbb845';

// 或从环境变量读取
import 'dart:String environment';
const apiKey = str.environment['DASHSCOPE_API_KEY'] ?? '';
```

### 2. 模型配置

在 `main.dart` 中确认：

```dart
OmniRealtimeService(
  apiKey: apiKey,
  model: 'qwen3.5-omni-plus-realtime',  // ✅ 必须使用此模型
  voice: 'Tina',  // 可选: Tina, Daisy, Alfie, Chelsie
  enableAudioOutput: false,  // 设置为 true 启用音频响应
)
```

## 📱 Android 配置

### AndroidManifest.xml 权限

在 `android/app/src/main/AndroidManifest.xml` 中添加：

```xml
<manifest ...>
    <!-- 麦克风权限 (必需) -->
    <uses-permission android:name="android.permission.RECORD_AUDIO" />
    
    <!-- 网络权限 (必需) -->
    <uses-permission android:name="android.permission.INTERNET" />
    
    <!-- 文件读取权限 (需要，用于音频文件) -->
    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" />
    <uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" />
    
    <application ...>
        <!-- 现有配置 -->
    </application>
</manifest>
```

### Gradle 配置

在 `android/app/build.gradle` 中确认：

```gradle
android {
    compileSdkVersion 34  // 或更高
    
    defaultConfig {
        targetSdkVersion 34  // 或更高
        minSdkVersion 21  // 或更高
    }
}
```

## 🍎 iOS 配置

### Info.plist 权限

在 `ios/Runner/Info.plist` 中添加：

```xml
<dict>
    <!-- 麦克风权限 (必需) -->
    <key>NSMicrophoneUsageDescription</key>
    <string>应用需要访问麦克风进行语音交互</string>
    
    <!-- 网络权限 -->
    <key>NSLocalNetworkUsageDescription</key>
    <string>应用需要访问本地网络</string>
    
    <key>NSBonjourServices</key>
    <array>
        <string>_http._tcp</string>
    </array>
</dict>
```

### Podfile 检查

在 `ios/Podfile` 中确认：

```ruby
post_install do |installer|
  installer.pods_project.targets.each do |target|
    # record 插件需要的配置
    flutter_additional_ios_build_settings(target)
  end
end
```

## 🧪 运行前检查

### 1. 代码编译检查

```bash
# 在项目根目录运行
cd mobile/flutter_app/

# 检查依赖
flutter pub get

# 检查分析
flutter analyze

# 检查编译
flutter build apk --analyze-size  # Android
flutter build ios --analyze-size  # iOS
```

### 2. 权限测试

```bash
# 运行应用
flutter run

# 在应用中：
# 1. 导航到"语音对话"
# 2. 应该看到权限请求提示
# 3. 授予权限后，应该能点击"按住说话"
```

### 3. 连接测试

```bash
# 在应用中测试：
# 1. 确保设备有网络连接
# 2. 点击"按住说话"
# 3. 说出简单问题（如"你好"）
# 4. 应该看到"处理中..."状态
# 5. 几秒后应该收到响应
```

## 🐛 常见编译问题

### 问题 1: `web_socket_channel` 导入错误

```
Error: Could not find 'web_socket_channel'
```

**解决：**
```bash
flutter pub get
flutter pub upgrade web_socket_channel
```

### 问题 2: `Permission denied` 错误

```
E/flutter: Android permission denied
```

**解决：**
1. 检查 AndroidManifest.xml 权限声明
2. 在 Android 设置 → 应用 → 权限中手动授予权限
3. 或在代码中使用 permission_handler 请求权限

### 问题 3: 音频文件不存在

```
I/flutter: Audio file not found at /path/to/file
```

**解决：**
确保 AudioService 正确初始化了临时目录：
```dart
final tempDir = await getTemporaryDirectory();
// 检查路径是否有效
```

### 问题 4: WebSocket 连接失败

```
E/flutter: WebSocket connection failed
```

**解决：**
1. 检查 API 密钥是否正确
2. 检查网络连接
3. 检查防火墙是否屏蔽 WebSocket 连接
4. 查看日志以获得更详细的错误信息

## 📊 功能验证清单

在首次运行时验证以下功能：

| 功能 | 操作 | 预期结果 | 状态 |
|-----|------|---------|------|
| 导航 | 主页 → 语音对话 | 进入 ElderVoiceScreen | [ ] |
| 连接 | 屏幕加载 | 显示"连接中..." | [ ] |
| 麦克风 | 点击"按住说话" | 开始录音，状态变为"录音中" | [ ] |
| 录制 | 说"你好" | 录制约 3 秒 | [ ] |
| 提交 | 释放按钮 | 状态变为"处理中..." | [ ] |
| 响应 | 等待 | 收到文本响应（如"你好，请问有什么帮助吗？"） | [ ] |
| 播放 | 响应显示 | 自动播放音频（如果启用）或显示文本 | [ ] |
| 继续 | 点击"按住说话" | 可以进行下一个问题 | [ ] |
| 返回 | 点击返回按钮 | 返回到主页 | [ ] |

## 🚀 部署清单

### 测试前

```
☐ 所有文件已创建
☐ 所有文件已修改
☐ pubspec.yaml 已更新
☐ AndroidManifest.xml 已更新
☐ Info.plist 已更新
☐ API 密钥已配置
☐ flutter pub get 已运行
☐ flutter analyze 无错误
```

### 本地测试

```
☐ flutter run 正常运行
☐ 权限请求显示正常
☐ 可以选择麦克风
☐ 可以开始录音
☐ 录音文件能生成
☐ WebSocket 连接成功
☐ 能接收 AI 响应
☐ 能显示响应文本
☐ 能播放响应音频
```

### 发布前

```
☐ 移除所有调试日志
☐ API 密钥使用安全存储
☐ 错误处理完善
☐ 性能优化完成
☐ UI 测试完成
☐ 无障碍测试完成
☐ 隐私政策已更新
☐ 用户体验已验证
```

## 📋 快速诊断

### 日志取样

在 `omni_voice_provider.dart` 中添加调试日志：

```dart
void _debugLog(String message) {
  if (kDebugMode) {
    print('[OmniVoiceProvider] $message');
  }
}
```

### 启用详细日志

在 `main.dart` 中：

```dart
void main() {
  // 启用详细日志
  if (kDebugMode) {
    debugPrintBeginFrame = true;
    debugPrintEndFrame = true;
  }
  runApp(const MyApp());
}
```

### 查看 WebSocket 日志

在 `omni_realtime_service.dart` 中：

```dart
void _debugWebSocket(String event, dynamic data) {
  if (kDebugMode) {
    print('[WebSocket] $event: ${jsonEncode(data)}');
  }
}
```

## 🔗 相关文件链接

- [集成指南](./VOICE_INTEGRATION_GUIDE.md) - 详细使用文档
- [音频指南](../../PCM_AUDIO_GUIDE.md) - PCM 格式说明
- [API 参考](../../SDK_API_REFERENCE.md) - API 详细说明
- [故障排查](../../FIX_ACCESS_DENIED.md) - 问题解决

## ✨ 完成标志

当以下条件都满足时，功能部署完成：

✅ 所有文件已创建和修改  
✅ 编译无错误  
✅ 权限请求正常  
✅ 可以成功录音  
✅ 可以连接到 Qwen Omni  
✅ 可以接收和显示响应  
✅ UI 显示正常  
✅ 用户体验满意  

---

**功能版本：** 1.0  
**由 GitHub Copilot 生成**  
**部署日期：** 2026年4月
