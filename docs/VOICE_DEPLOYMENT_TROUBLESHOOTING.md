# Flutter 语音交互功能 - 部署和故障排查指南

## 🚀 部署步骤

### 第 1 步：准备工作

```bash
cd d:\code\health\mobile\flutter_app

# 清理旧的构建
flutter clean

# 获取依赖
flutter pub get

# 检查依赖是否完整
flutter pub upgrade web_socket_channel audioplayers record
```

### 第 2 步：验证文件完整性

运行以下命令检查所有文件是否存在：

```bash
# 检查核心文件
test -f lib/features/voice/services/omni_realtime_service.dart && echo "✅ omni_realtime_service.dart"
test -f lib/features/voice/providers/omni_voice_provider.dart && echo "✅ omni_voice_provider.dart"
test -f lib/features/voice/screens/elder_voice_screen.dart && echo "✅ elder_voice_screen.dart"
test -f lib/features/voice/widgets/elder_voice_interaction_widget.dart && echo "✅ elder_voice_interaction_widget.dart"
```

### 第 3 步：配置和修改检查

确认 `lib/main.dart` 中的修改：

```dart
// ✅ 检查这些导入是否存在
import 'features/voice/providers/omni_voice_provider.dart';
import 'features/voice/services/omni_realtime_service.dart';

// ✅ 检查 Provider 注册
MultiProvider(
  providers: [
    // ...
    ChangeNotifierProvider(
      create: (_) => OmniVoiceProvider(
        apiKey: 'sk-67d1be1cac0649b9a8839d2328bbb845',
        omniService: OmniRealtimeService(
          apiKey: 'sk-67d1be1cac0649b9a8839d2328bbb845',
          model: 'qwen3.5-omni-plus-realtime',
          voice: 'Tina',
          enableAudioOutput: false,
        ),
      ),
    ),
  ],
  // ...
)
```

### 第 4 步：编译验证

```bash
# 分析代码
flutter analyze

# 编译 APK（Android 构建）
flutter build apk
# 或
flutter build apk --release

# 编译 iOS（macOS 需要）
# flutter build ios --release
```

### 第 5 步：设备部署

#### Android

```bash
# 列出连接的设备
flutter devices

# 安装并运行
flutter run  # 开发版本
# 或
flutter install  # 仅安装

# 使用特定设备
flutter run -d <device-id>
```

#### iOS

```bash
# 需要 macOS 和 Xcode
flutter run

# 或指定特定设备
flutter run -d "iPhone 15"
```

### 第 6 步：权限配置

#### Android - AndroidManifest.xml

```xml
<!-- android/app/src/main/AndroidManifest.xml -->
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.RECORD_AUDIO" />
    <uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" />
    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" />
    
    <application ...>
        <!-- 现有配置 -->
    </application>
</manifest>
```

#### iOS - Info.plist

```xml
<!-- ios/Runner/Info.plist -->
<dict>
    <key>NSMicrophoneUsageDescription</key>
    <string>我们需要使用你的麦克风来进行语音对话</string>
    
    <key>NSLocalNetworkUsageDescription</key>
    <string>应用需要访问本地网络进行通信</string>
</dict>
```

### 第 7 步：首次运行

```bash
# 运行应用
flutter run

# 应该看到：
# - 应用启动
# - 进入登录/首页
# - 找到"语音对话"按钮
# - 点击进入语音屏幕
```

## 🐛 故障排查

### 问题 1: "Permission denied" 错误

**症状：**
```
E/flutter: android.permission.RECORD_AUDIO permission denied
```

**原因：** 应用没有录音权限

**解决方案：**

1. **检查 AndroidManifest.xml**
   ```xml
   <uses-permission android:name="android.permission.RECORD_AUDIO" />
   ```

2. **在设置中授予权限**
   - 进入 Android 设置 → 应用 → [App Name] → 权限 → 麦克风
   - 选择"允许"

3. **检查 permission_handler 配置**
   ```dart
   import 'package:permission_handler/permission_handler.dart';
   
   // 在使用麦克风前请求权限
   final status = await Permission.microphone.request();
   if (status.isGranted) {
     // 可以使用麦克风
   }
   ```

### 问题 2: "Could not find 'web_socket_channel'" 错误

**症状：**
```
Error: Could not find 'web_socket_channel' in package:...
```

**原因：** pubspec.yaml 中缺少依赖或版本冲突

**解决方案：**

```bash
# 更新所有依赖
flutter pub get
flutter pub upgrade

# 或明确安装
flutter pub add web_socket_channel:^3.0.3
flutter pub add audioplayers:^5.2.1
flutter pub add record:^5.2.1

# 清理和重建
flutter clean
flutter pub get
```

### 问题 3: WebSocket 连接失败

**症状：**
```
E/flutter: WebSocket connection failed: Connection refused
```

**原因可能：**
1. 网络问题
2. API 密钥错误
3. 防火墙阻止
4. DNS 解析失败

**解决方案：**

```dart
// 1. 检查 API 密钥
const apiKey = 'sk-67d1be1cac0649b9a8839d2328bbb845';  // ✅ 确认这是正确的

// 2. 检查网络连接
final connectivity = await Connectivity().checkConnectivity();
if (connectivity == ConnectivityResult.none) {
  // 没有网络连接
}

// 3. 添加调试日志
print('[DEBUG] Connecting to Qwen Omni...');
print('[DEBUG] API Key: $apiKey');
print('[DEBUG] Model: qwen3.5-omni-plus-realtime');

// 4. 尝试连接到网址
final uri = Uri.parse('https://dashscope.aliyuncs.com/api-ws/v1/realtime');
print('[DEBUG] WebSocket URI: $uri');
```

### 问题 4: 录音不工作

**症状：**
```
I/flutter: Audio file not found at /data/...
```

**原因：** 麦克风初始化失败或权限问题

**解决方案：**

```dart
// 1. 验证权限已授予
final micStatus = await Permission.microphone.request();
assert(micStatus.isGranted);

// 2. 初始化 AudioService
final audioService = AudioService();
await audioService.init();  // 如果有 init 方法

// 3. 检查临时目录是否可写
final tempDir = await getTemporaryDirectory();
print('[DEBUG] Temp directory: ${tempDir.path}');
assert(tempDir.existsSync());

// 4. 测试简单的录音
try {
  final path = await audioService.startRecording();
  await Future.delayed(Duration(seconds: 2));
  final path2 = await audioService.stopRecording();
  print('[DEBUG] Recording saved to: $path2');
} catch (e) {
  print('[ERROR] Recording failed: $e');
}
```

### 问题 5: 文本不显示

**症状：**
```
UI 显示为空，没有 AI 响应记录
```

**原因可能：**
1. 响应未接收
2. Widget 未监听状态变化
3. 状态被重置了

**解决方案：**

```dart
// 确保使用 Consumer 而非 Builder
Consumer<OmniVoiceProvider>(
  builder: (context, voiceProvider, _) {
    return Text(voiceProvider.fullResponse);  // ✅
  },
)

// ❌ 不要这样做（状态变化不会刷新 UI）
final response = Provider.of<OmniVoiceProvider>(context).fullResponse;
return Text(response);
```

### 问题 6: 音频播放失败

**症状：**
```
没有听到音频响应，但文本显示正常
```

**原因可能：**
1. 音频数据损坏
2. 喇叭静音
3. 格式不支持
4. AudioService 问题

**解决方案：**

```dart
// 1. 检查音量
// 确保设备音量不是 0 和静音键已关闭

// 2. 验证音频数据
if (audioDelta.isNotEmpty) {
  print('[DEBUG] Audio delta received: ${audioDelta.length} bytes');
  
  // 3. 尝试播放测试声音
  await audioService.play('assets/test_sound.wav');  // 如果有测试文件
}

// 4. 检查 enableAudioOutput
final service = OmniRealtimeService(
  enableAudioOutput: true,  // ✅ 必须启用
);
```

### 问题 7: 状态卡在"处理中..."

**症状：**
```
状态显示"处理中..."，但从不变为"完成"或"错误"
```

**原因：** WebSocket 未收到响应或连接中断

**解决方案：**

```dart
// 1. 添加超时机制
Future<void> processWithTimeout() async {
  try {
    await voiceProvider.stopRecordingAndProcess()
        .timeout(Duration(seconds: 30), onTimeout: () {
      throw TimeoutException('Qwen Omni 响应超时');
    });
  } on TimeoutException {
    // 处理超时
    voiceProvider.status = OmniVoiceStatus.error;
    voiceProvider.statusMessage = '响应超时，请重试';
  }
}

// 2. 检查 WebSocket 连接
print('[DEBUG] Is connected: ${omniService.isConnected}');

// 3. 重新连接
if (!omniService.isConnected) {
  await omniService.disconnect();
  await omniService.connect();
}
```

### 问题 8: 应用崩溃

**症状：**
```
E/flutter: Unhandled Exception: ...
应用关闭
```

**解决方案：**

```bash
# 查看完整的错误日志
flutter logs

# 或收集 crash log
adb logcat | grep flutter
```

**常见崩溃原因：**

1. **空指针异常**
   ```dart
   // ✅ 添加空值检查
   if (voiceProvider != null) {
     voiceProvider.connect();
   }
   ```

2. **资源泄漏**
   ```dart
   @override
   void dispose() {
     voiceProvider.dispose();  // ✅ 及时清理
     super.dispose();
   }
   ```

3. **未处理的异步错误**
   ```dart
   // ✅ 使用 try-catch
   try {
     await voiceProvider.stopRecordingAndProcess();
   } catch (e) {
     print('Error: $e');
   }
   ```

## 📋 诊断检查清单

如果功能不工作，按顺序检查：

### 基础检查

- [ ] 应用已编译并运行（`flutter run` 成功）
- [ ] 没有编译错误（`flutter analyze` 通过）
- [ ] 设备已连接（`flutter devices` 列出设备）
- [ ] 网络连接正常（可以访问 dashscope.aliyuncs.com）

### 文件检查

- [ ] 4 个新文件已创建（omni_realtime_service.dart 等）
- [ ] 3 个文件已修改（main.dart, audio_service.dart, elder_home_screen.dart）
- [ ] pubspec.yaml 中的依赖完整

### 配置检查

- [ ] API 密钥已配置：`sk-67d1be1cac0649b9a8839d2328bbb845`
- [ ] 模型已配置：`qwen3.5-omni-plus-realtime`
- [ ] AndroidManifest.xml 包含所需权限
- [ ] Info.plist 包含所需描述

### 权限检查

- [ ] 麦克风权限已声明
- [ ] 网络权限已声明
- [ ] 在设备设置中已授予麦克风权限

### 功能检查

- [ ] 能导航到"语音对话"屏幕
- [ ] 屏幕显示欢迎卡片和指导
- [ ] 能点击"按住说话"按钮
- [ ] 麦克风开始录音（听得到蜂鸣音或看到状态变化）
- [ ] 释放按钮后显示"处理中..."
- [ ] 几秒后收到 AI 响应

### 日志检查

```bash
# 查看应用日志
flutter logs

# 查看详细的 WebSocket 日志（如果已添加）
flutter logs | grep -i websocket

# 查看 Dart 异常
flutter logs | grep -i exception
```

## 🔌 网络问题诊断

### 检查网络连接

```bash
# Ping DashScope 服务器
ping dashscope.aliyuncs.com

# 或用 curl 检查 HTTP(S)
curl -I https://dashscope.aliyuncs.com

# 检查 DNS
nslookup dashscope.aliyuncs.com
```

### 防火墙和代理

如果后面有防火墙或代理：

```dart
// 配置代理（如果需要）
HttpClient httpClient = HttpClient();
httpClient.findProxy = (uri) {
  return 'PROXY proxy.example.com:8080';
};
```

### VPN/科学上网

某些地区可能需要 VPN：

- Android：设置 → VPN → 添加配置并连接
- iOS：设置 → VPN 与设备管理 → 添加配置

## 📊 性能诊断

### 检查内存使用

```dart
import 'dart:developer' as developer;

// 在应用中
developer.Timeline.instantSync('Memory checkpoint');

// 监视内存
print(developer.Service.getVM());
```

### 检查 WebSocket 消息大小

```dart
// 在 omni_realtime_service.dart 中添加
void _sendMessage(Map<String, dynamic> message) {
  final jsonStr = jsonEncode(message);
  print('[WebSocket] Sending ${jsonStr.length} bytes');
  _channel.sink.add(jsonStr);
}
```

## 🔄 恢复步骤

如果一切都失效，尝试以下步骤：

### 完全清理和重建

```bash
cd d:\code\health\mobile\flutter_app

# 1. 清理构建设备缓存
flutter clean

# 2. 删除依赖缓存（可选）
rm -rf pubspec.lock
rm -rf .dart_tool

# 3. 重新获取依赖
flutter pub get

# 4. 获取依赖升级
flutter pub upgrade

# 5. 重新分析
flutter analyze

# 6. 重新编译
flutter run
```

### 重置应用状态

```bash
# Android - 卸载应用并重装
adb uninstall [package-name]
flutter run

# iOS
# 在设置 → 通用 → iPhone 存储空间 → [App Name] → 删除应用
# 或 Xcode 中清理构建文件夹
```

## 📞 获取更多帮助

### 查看日志

```bash
# 实时日志
flutter logs -f

# 保存到文件
flutter logs > app.log 2>&1

# 过滤特定标签
flutter logs | grep "OmniVoice"
```

### 启用调试模式

在 `omni_voice_provider.dart` 中：

```dart
void _debug(String message) {
  if (kDebugMode) {
    print('[OmniVoiceProvider DEBUG] $message');
  }
}
```

### 检查 GitHub Issues

查看相关项目的 GitHub Issues 可能找到类似的问题：

- web_socket_channel issues
- audioplayers issues
- record issues
- flutter issues

## 🎓 最佳实践

### 1. 开发环节

```dart
// ✅ 使用 kDebugMode 添加调试代码
if (kDebugMode) {
  print('[DEBUG] $message');
}

// ✅ 使用 assert 进行开发时检查
assert(apiKey.isNotEmpty, 'API key must not be empty');
```

### 2. 生产环节

```dart
// ✅ 移除所有调试日志
// ❌ 不要在生产中暴露 API 密钥
// ✅ 使用安全存储或后端获取密钥
```

### 3. 错误处理

```dart
// ✅ 总是使用 try-catch
try {
  await voiceProvider.connect();
} on SocketException catch (e) {
  // 网络错误
} on FormatException catch (e) {
  // 数据格式错误
} catch (e) {
  // 其他错误
}
```

---

**部署版本：** 1.0  
**最后更新：** 2026年4月  
**支持频率：** 持续更新
