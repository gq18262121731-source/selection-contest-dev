# Flutter 移动端 - Qwen Omni 实时语音交互集成指南

## 📋 功能概述

本指南说明如何在 Flutter 移动应用中集成 Qwen Omni 实时语音交互功能，用于老人登录后的语音问答。

## 🎯 核心功能

- ✅ 实时 WebSocket 连接到 Qwen Omni 服务
- ✅ PCM 格式音频录制和上传
- ✅ 实时处理 AI 响应并播放音频/文本
- ✅ 友好的 UI 和错误处理
- ✅ 完整集成到现有应用架构

## 📦 新增文件清单

### 核心服务

| 文件 | 用途 |
|------|------|
| `lib/features/voice/services/omni_realtime_service.dart` | WebSocket 服务，管理与 Qwen Omni 的连接 |
| `lib/features/voice/providers/omni_voice_provider.dart` | Provider，管理语音交互的完整流程 |

### UI 组件

| 文件 | 用途 |
|------|------|
| `lib/features/voice/screens/elder_voice_screen.dart` | 完整的语音对话屏幕 |
| `lib/features/voice/widgets/elder_voice_interaction_widget.dart` | 可复用的语音交互 Widget |

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `lib/main.dart` | 添加 OmniVoiceProvider 注册 |
| `lib/core/services/audio_service.dart` | 添加公开的 `playBytes()` 方法 |
| `lib/features/care/screens/elder_home_screen.dart` | 添加"语音对话"按钮 |

## 🚀 快速开始

### 1. 依赖

确保 `pubspec.yaml` 中包含以下依赖：

```yaml
dependencies:
  web_socket_channel: ^3.0.3  # WebSocket
  audioplayers: ^5.2.1         # 音频播放
  record: ^5.2.1               # 音频录制
```

### 2. API 密钥配置

在 `main.dart` 中配置你的 DashScope API 密钥：

```dart
const apiKey = 'sk-your-api-key-here';

final omniService = OmniRealtimeService(
  apiKey: apiKey,
  model: 'qwen3.5-omni-plus-realtime',
  voice: 'Tina', // Tina, Daisy, Alfie, Chelsie
  enableAudioOutput: false, // 仅输出文本
);
```

### 3. 用户界面集成

在老人首页（ElderHomeScreen）中已自动添加了"语音对话"按钮，点击进入 ElderVoiceScreen。

## 🔧 使用方式

### 基本流程

```
1. 用户点击"语音对话"按钮 → ElderVoiceScreen
   ↓
2. 连接到 Qwen Omni 服务
   ↓
3. 点击"按住说话"开始录音
   ↓
4. 说出问题，点击"停止说话"
   ↓
5. 系统将音频上传并处理
   ↓
6. AI 返回文本响应（可选：返回音频）
   ↓
7. 显示响应并播放（如果有音频）
```

### 架构流程

```
ElderHomeScreen
    ↓
ElderVoiceScreen (新增)
    ↓
ElderVoiceInteractionWidget (新增)
    ↓
OmniVoiceProvider (新增)
    ↓
OmniRealtimeService (新增)
    ↓
WebSocket → Qwen Omni API
```

## 📱 UI 组件说明

### ElderVoiceScreen - 完整屏幕

```dart
ElderVoiceScreen(
  deviceMac: '...',  // 设备 MAC 地址
)
```

**功能：**
- 欢迎卡片
- 语音交互 Widget
- 使用说明
- 常见问题建议

### ElderVoiceInteractionWidget - 可复用组件

```dart
ElderVoiceInteractionWidget(
  deviceMac: '...',
  voice: 'Tina',  // 语音角色
  onResponseReceived: () {
    // 响应接收回调
  },
)
```

**功能：**
- 实时状态显示
- 录音按钮
- 响应文本显示
- 错误提示

## 🎤 音频规格

系统使用以下音频规格：

| 参数 | 值 |
|------|-----|
| 采样率 | 16000 Hz |
| 比特深度 | 16-bit |
| 通道 | 单声道 |
| 格式 | PCM |
| 编码 | WAV |

**注意：** 所有音频都自动转换为 PCM 格式，不支持 MP3。

## 🔌 OmniRealtimeService API

### 初始化

```dart
final service = OmniRealtimeService(
  apiKey: 'your-api-key',
  model: 'qwen3.5-omni-plus-realtime',
  voice: 'Tina',
  enableAudioOutput: false,
);
```

### 主要方法

```dart
// 连接到服务
await service.connect();

// 追加音频（Base64 编码）
await service.appendAudio(audioBase64);

// 提交音频
await service.commitAudio();

// 监听事件
service.eventStream.listen((event) {
  // 处理事件
});

// 断开连接
await service.disconnect();
```

### 事件类型

| 事件 | 说明 |
|------|------|
| `OmniEvent.connected()` | 已连接 |
| `OmniEvent.disconnected()` | 已断开 |
| `OmniEvent.audioAppended()` | 音频已追加 |
| `OmniEvent.audioCommitted()` | 音频已提交 |
| `OmniEvent.textDelta(text)` | 接收文本 delta |
| `OmniEvent.audioDelta(audio, format)` | 接收音频 delta |
| `OmniEvent.responseDone()` | 响应完成 |
| `OmniEvent.error(message)` | 错误 |

## 👴 OmniVoiceProvider API

### 状态管理

```dart
class OmniVoiceProvider extends ChangeNotifier {
  // 状态
  OmniVoiceStatus status;  // idle, connecting, recording, processing, responding, error
  String statusMessage;
  String fullResponse;
  
  // 方法
  Future<bool> connect({String voice = 'Tina'});
  Future<bool> startRecording();
  Future<bool> stopRecordingAndProcess();
  Future<void> disconnect();
}
```

### 使用示例

```dart
final voiceProvider = context.read<OmniVoiceProvider>();

// 连接
await voiceProvider.connect(voice: 'Daisy');

// 开始录音
await voiceProvider.startRecording();

// 停止并处理
await voiceProvider.stopRecordingAndProcess();

// 监听状态
context.watch<OmniVoiceProvider>().status;
```

## 🎨 语音角色

支持四种语音角色：

- **Tina**（默认）- 清晰女声
- **Daisy** - 温柔女声
- **Alfie** - 男声
- **Chelsie** - 自然女声

在初始化时选择：

```dart
final service = OmniRealtimeService(
  apiKey: apiKey,
  voice: 'Daisy',  // 选择语音
);
```

## 📊 状态流转图

```
idle
  ↓
connecting → idle
  ↓
idle
  ↓
recording → processing → responding → idle
  ↓
error (any state)
```

## 🐛 故障排查

### 问题 1: 无法连接到 Qwen Omni

**症状：**
```
状态: 错误
消息: 连接失败：xxx
```

**解决方案：**
1. 检查 API 密钥是否正确
2. 检查网络连接
3. 确保 Qwen Omni 服务可访问（需要科学上网）

### 问题 2: 录音失败

**症状：**
```
状态: 错误
消息: 无法启动录音
```

**解决方案：**
1. 检查麦克风权限
2. 在手机设置中授予应用麦克风权限
3. 尝试重启应用

### 问题 3: 无响应

**症状：**
```
状态: 处理中...（一直不变）
```

**解决方案：**
1. 检查网络连接
2. 查看控制台日志了解详细错误
3. 尝试重新连接

### 问题 4: 音频播放失败

**症状：**
```
提交后没有声音
```

**解决方案：**
1. 检查手机音量
2. 确保喇叭未静音
3. 检查手机音频权限

## 🔐 安全考虑

### API 密钥管理

**当前（开发）：**
```dart
const apiKey = 'sk-...';  // 硬编码
```

**生产部署：**
```dart
// 方式 1: 从后端获取
final response = await apiClient.get('voice/api-key');
final apiKey = response.data['api_key'];

// 方式 2: 使用环境变量
import 'dart:String environment';
final apiKey = str.environment['DASHSCOPE_API_KEY'];

// 方式 3: 从安全存储读取
final apiKey = await secureStorage.read(key: 'dashscope_api_key');
```

## 📈 性能优化

### 1. 连接管理

```dart
// ✅ 好 - 缓存连接
if (!voiceProvider.isConnected) {
  await voiceProvider.connect();
}

// ❌ 差 - 每次都重连
await voiceProvider.disconnect();
await voiceProvider.connect();
```

### 2. 内存管理

```dart
// ✅ 好 - 及时清理
@override
void dispose() {
  voiceProvider.dispose();  // 主动释放
  super.dispose();
}
```

### 3. 网络优化

```dart
// ✅ 好 - 只在需要时连接
await voiceProvider.connect();
// 使用...
await voiceProvider.disconnect();

// ❌ 差 - 一直保持连接
```

## 🧪 测试

### 单元测试示例

```dart
test('OmniVoiceProvider 初始化', () {
  final provider = OmniVoiceProvider(
    apiKey: 'test-key',
    omniService: MockOmniRealtimeService(),
    audioService: MockAudioService(),
  );
  
  expect(provider.status, OmniVoiceStatus.idle);
  expect(provider.isConnected, false);
});

test('连接到 Omni 服务', () async {
  // ...
});
```

## 📚 进阶用法

### 自定义 Widget

```dart
class CustomVoiceWidget extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Consumer<OmniVoiceProvider>(
      builder: (context, voiceProvider, _) {
        return Column(
          children: [
            // 自定义 UI
            Text(voiceProvider.statusMessage),
            // ...
          ],
        );
      },
    );
  }
}
```

### 与其他功能集成

```dart
// 与 AgentProvider 集成
Future<void> _handleVoiceToAgent() async {
  final voiceProvider = context.read<OmniVoiceProvider>();
  final agentProvider = context.read<AgentProvider>();
  
  // 使用语音获取文本
  await voiceProvider.stopRecordingAndProcess();
  
  // 将文本发送给 Agent
  final text = voiceProvider.lastAsrText;
  await agentProvider.sendMessage(text);
}
```

## 🔄 与后端集成

### 当前架构（直连 Qwen Omni）

```
Flutter Client → WebSocket → Qwen Omni API
```

### 推荐架构（通过后端）

```
Flutter Client → HTTP → Backend Server
                           ↓
                         WebSocket ↔ Qwen Omni API
```

**优点：**
- 更安全（不暴露 API 密钥）
- 更灵活（后端可添加日志、分析等）
- 更稳定（由后端管理连接）

## 📝 配置清单

部署前检查：

- [ ] API 密钥已配置
- [ ] 麦克风权限已声明（AndroidManifest.xml, Info.plist）
- [ ] 网络权限已声明
- [ ] 音频权限已声明
- [ ] ErrorBoundary 已实现
- [ ] 离线模式已考虑
- [ ] 日志记录已实现
- [ ] 测试已完成

## 🎓 学习资源

### 相关文档

1. [Qwen Omni 官方文档](https://dashscope.aliyuncs.com/)
2. [PCM 音频指南](../../PCM_AUDIO_GUIDE.md)
3. [SDK API 参考](../../SDK_API_REFERENCE.md)

### 示例应用

- 完整屏幕：`ElderVoiceScreen`
- 可复用组件：`ElderVoiceInteractionWidget`
- 核心服务：`OmniRealtimeService` + `OmniVoiceProvider`

## 🤝 常见集成问题

### Q: 如何同时支持文本和语音输出？

A:
```dart
final service = OmniRealtimeService(
  apiKey: apiKey,
  enableAudioOutput: true,  // 启用音频输出
);
```

### Q: 如何使用不同的语音角色？

A:
```dart
await voiceProvider.connect(voice: 'Daisy');
```

### Q: 如何处理长时间运行？

A:
```dart
// 定期检查连接状态
Timer.periodic(Duration(minutes: 5), (_) {
  if (!voiceProvider.isConnected) {
    voiceProvider.connect();
  }
});
```

### Q: 如何支持多种语言？

A:
需要后端支持，前端将语言偏好传递给后端，由后端配置相应的 Qwen 模型。

## 📞 支持

如遇到问题，请参考：

1. [故障排查](#-故障排查)
2. [FIX_ACCESS_DENIED.md](../../FIX_ACCESS_DENIED.md)
3. [PCM_AUDIO_GUIDE.md](../../PCM_AUDIO_GUIDE.md)

---

**版本：** 1.0  
**最后更新：** 2026年4月  
**兼容性：** Flutter 3.4+, Dart 3.4+
