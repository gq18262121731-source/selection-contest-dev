# Flutter 语音交互系统 - 架构和系统设计

## 📐 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                      Flutter Mobile App                         │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    UI Layer (Presentation)               │   │
│  │                                                           │   │
│  │  ┌─────────────────────────────────────────────────────┐ │   │
│  │  │         ElderVoiceScreen                             │ │   │
│  │  │  - 完整语音对话屏幕                                   │ │   │
│  │  │  - 欢迎卡片                                           │ │   │
│  │  │  - 指导和建议                                         │ │   │
│  │  └─────────────────────────────────────────────────────┘ │   │
│  │                                                           │   │
│  │  ┌─────────────────────────────────────────────────────┐ │   │
│  │  │     ElderVoiceInteractionWidget (Reusable)           │ │   │
│  │  │  - 状态指示器                                         │ │   │
│  │  │  - 录音/停止按钮                                      │ │   │
│  │  │  - 响应显示                                           │ │   │
│  │  │  - 错误卡片                                           │ │   │
│  │  └─────────────────────────────────────────────────────┘ │   │
│  │                                                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                            ↑                                     │
│                      Provider Pattern                            │
│                            ↓                                     │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │               State Management Layer                      │   │
│  │                                                           │   │
│  │  ┌─────────────────────────────────────────────────────┐ │   │
│  │  │         OmniVoiceProvider                            │ │   │
│  │  │  - 状态管理 (idle, connecting, recording, ...)       │ │   │
│  │  │  - 生命周期管理                                       │ │   │
│  │  │  - 事件处理                                           │ │   │
│  │  └─────────────────────────────────────────────────────┘ │   │
│  │                                                           │   │
│  │  ┌─────────────────────────────────────────────────────┐ │   │
│  │  │    Other Providers (Auth, Care, etc.)               │ │   │
│  │  └─────────────────────────────────────────────────────┘ │   │
│  │                                                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                            ↑                                     │
│              Repository Pattern / Service Layer                 │
│                            ↓                                     │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Service Layer                         │   │
│  │                                                           │   │
│  │  ┌──────────────────┐  ┌──────────────────┐              │   │
│  │  │ OmniRealtimeServ │  │  AudioService    │              │   │
│  │  │ - WebSocket 管理  │  │ - 录音           │              │   │
│  │  │ - 协议处理       │  │ - 播放           │              │   │
│  │  │ - 事件发射       │  │ - 格式转换       │              │   │
│  │  └──────────────────┘  └──────────────────┘              │   │
│  │                                                           │   │
│  │  ┌─────────────────────────────────────────────────────┐ │   │
│  │  │  Other Services (Auth, Care, etc.)                  │ │   │
│  │  └─────────────────────────────────────────────────────┘ │   │
│  │                                                           │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                ↓
                          Network Layer
                                ↓
              ┌──────────────────────────────────────┐
              │  Qwen Omni Realtime API              │
              │  - WebSocket: wss://dashscope...    │
              │  - Model: qwen3.5-omni-plus-realtime│
              │  - Audio Format: PCM Base64         │
              │  - Response: Text + Audio (optional)│
              └──────────────────────────────────────┘
```

## 🔄 用户交互流程

```
用户打开应用
    ↓
登录/进入老人界面
    ↓
点击"语音对话"按钮
    ├─→ Navigator.push(ElderVoiceScreen)
    ↓
ElderVoiceScreen 初始化
    ├─→ 读取用户信息（AuthProvider）
    ├─→ 读取设备信息（CareProvider）
    ├─→ 初始化 OmniVoiceProvider
    ├─→ 连接到 Qwen Omni 服务
    ↓
屏幕显示欢迎、指导、建议
    ↓
用户长按"按住说话"按钮
    ├─→ OmniVoiceProvider.startRecording()
    ├─→ AudioService.startRecording()
    ├─→ 状态: recording
    ↓
用户说话（3-30秒）
    ↓
用户释放按钮（onPointerUp）
    ├─→ OmniVoiceProvider.stopRecordingAndProcess()
    │
    ├─→ AudioService.stopRecording() → 获得 .wav 文件
    ├─→ 读取文件内容 → List<int> audioBytes
    ├─→ 转换为 Base64 编码
    ├─→ 状态: processing
    │
    ├─→ OmniRealtimeService.appendAudio(base64String)
    │   ├─→ WebSocket 发送 append_audio 消息
    │   ├─→ 等待 audio_appended 事件
    │
    ├─→ OmniRealtimeService.commitAudio()
    │   ├─→ WebSocket 发送 commit_audio 消息
    │   ├─→ 等待 audio_committed 事件
    │   ├─→ 状态: responding
    ↓
监听 Omni 服务事件流
    ├─→ textDelta 事件
    │   ├─→ 累积文本到 fullResponse
    │   ├─→ UI 实时显示文本更新
    │
    ├─→ audioDelta 事件（可选）
    │   ├─→ 接收音频 base64 编码
    │   ├─→ AudioService.playBytes()
    │   ├─→ 播放音频响应
    │
    ├─→ responseDone 事件
    │   ├─→ 状态: idle
    │   ├─→ 响应完全接收
    ↓
显示完整响应
    ├─→ 文本显示在卡片中
    ├─→ 音频播放完毕
    ↓
用户可以开始下一个对话
    └─→ 回到第 3 步「用户长按按钮」
        或
        点击返回返回到首页
```

## 🔌 数据流

### 1. 音频数据流

```
麦克风（硬件）
    ↓ [原始音频信号]
AudioService.record 包
    ↓ [16kHz, 16-bit PCM, WAV 格式]
临时文件：/tmp/record_xxx.wav
    ↓ [从磁盘读取]
原始字节数组：List<int>
    ↓ [Base64 编码]
Base64 字符串：String
    ↓ [WebSocket 传输]
OmniRealtimeService（WebSocket）
    ↓ [JSON 消息]
Qwen Omni API
    ↓ [处理音频]
AI 响应（文本 + 可选音频）
```

### 2. 状态流转

```
┌─────────┐
│  idle   │ ← 初始状态
└────┬────┘
     │ 用户点击语音对话
     ↓
┌──────────────┐
│ connecting   │ ← 连接 Qwen Omni
└────┬─────────┘
     │ 连接成功
     ↓
┌─────┐    长按开始
│idle │←────────────────┐
└────┬┘                 │
     │                  │
     │ 用户长按按钮      │
     ↓                  │
┌──────────────┐        │
│ recording    │ ← 录音中
└────┬─────────┘        │
     │ 用户释放按钮      │
     ↓                  │
┌──────────────┐        │
│ processing   │ ← 上传/处理中
└────┬─────────┘        │
     │ 服务开始处理      │
     ↓                  │
┌──────────────┐        │
│ responding   │ ← 接收响应中
└────┬─────────┘        │
     │ 响应完成         │
     └──→回到 idle ────┘

┌─────────┐
│ error   │ ← 任何错误（可恢复或重试）
└────┬────┘
     │ 用户决定重试
     └──→回到 idle
```

### 3. 事件处理流

```
WebSocket 消息（来自 Qwen Omni）
    ↓
OmniRealtimeService._handleMessage()
    ├─→ JSON 解析
    ├─→ 事件类型识别
    ↓
    ├─→ type == "response"
    │   ├─→ payload.response_type == "session_created"
    │   │   └─→ emit OmniEvent.sessionCreated()
    │   ├─→ payload.response_type == "text"
    │   │   ├─→ payload.delta == "你好"
    │   │   └─→ emit OmniEvent.textDelta("你好")
    │   ├─→ payload.response_type == "audio"
    │   │   ├─→ payload.delta == "<base64>"
    │   │   └─→ emit OmniEvent.audioDelta("<base64>")
    │   └─→ payload.response_type == "done"
    │       └─→ emit OmniEvent.responseDone()
    │
    ├─→ type == "error"
    │   └─→ emit OmniEvent.error("message")
    │
    └─→ 其他
        └─→ emit OmniEvent.unknown()
    ↓
OmniVoiceProvider 监听事件流
    ├─→ OmniEvent.textDelta(text)
    │   ├─→ fullResponse += text
    │   ├─→ notifyListeners() → UI 更新
    │
    ├─→ OmniEvent.audioDelta(base64Audio)
    │   ├─→ decode base64
    │   ├─→ AudioService.playBytes()
    │   └─→ 播放音频
    │
    ├─→ OmniEvent.responseDone()
    │   ├─→ status = idle
    │   └─→ notifyListeners()
    │
    └─→ OmniEvent.error(message)
        ├─→ status = error
        ├─→ statusMessage = message
        └─→ notifyListeners()
    ↓
UI 层（ElderVoiceInteractionWidget）
    ├─→ Consumer<OmniVoiceProvider>
    ├─→ watch status, fullResponse
    ├─→ rebuild 显示最新状态
    └─→ 用户看到实时更新
```

## 🏗️ 文件结构

```
lib/features/voice/
├── services/
│   └── omni_realtime_service.dart       [NEW] WebSocket 客户端
├── providers/
│   └── omni_voice_provider.dart         [NEW] 状态管理
├── screens/
│   └── elder_voice_screen.dart          [NEW] 完整屏幕
├── widgets/
│   └── elder_voice_interaction_widget.dart [NEW] 可复用组件
└── models/
    └── omni_event.dart                  [NEW] 事件定义（sealed class）

lib/core/services/
├── audio_service.dart                   [MODIFIED] 添加 playBytes()
└── ...

lib/core/services/
├── main.dart                            [MODIFIED] 添加 Provider 注册

lib/features/care/screens/
├── elder_home_screen.dart               [MODIFIED] 添加导航按钮
└── ...
```

## 🔐 安全设计

### 1. API 密钥管理

```
开发环境：
└─ lib/main.dart
   └─ const apiKey = 'sk-...'  ⚠️ 仅用于开发

生产环境（推荐）：
├─ 后端 API
│  └─ GET /api/voice/token
│     └─ 返回临时 token（有过期时间）
│
或
│
├─ 原生代码
│  └─ android/key.properties（Git ignore）
│  └─ ios/Keys.plist（Git ignore）
│
或
│
└─ 安全存储（flutter_secure_storage）
   └─ keychain (iOS) / Keystore (Android)
```

### 2. 数据隐私

- 音频文件存储在临时目录，完成后删除
- WebSocket 使用 WSS（加密）连接
- 用户数据不存储在本地（除了当前会话）
- 隐私政策应明确说明音频数据的使用

### 3. 权限管理

```dart
// 启动前请求权限
final status = await Permission.microphone.request();
if (status.isDenied) {
  // 权限被拒绝
} else if (status.isGranted) {
  // 已授予，可以使用
}
```

## 📊 状态管理设计

### Provider 树结构

```
Consumer
  ├─ AuthProvider
  │  └─ 用户信息、登录状态
  ├─ CareProvider
  │  └─ 设备列表、老人信息
  └─ OmniVoiceProvider ← 新增
     ├─ status
     ├─ statusMessage
     ├─ fullResponse
     └─ isConnected
```

### FutureProvider vs ChangeNotifierProvider

**选择 ChangeNotifierProvider 原因：**
1. 需要频繁状态更新（实时文本、音频）
2. 需要响应用户交互（长按、释放）
3. 需要控制 WebSocket 生命周期

## 🧪 可测试性设计

### 依赖注入

```dart
class OmniVoiceProvider extends ChangeNotifier {
  final OmniRealtimeService _omniService;
  final AudioService _audioService;

  OmniVoiceProvider({
    required OmniRealtimeService omniService,
    required AudioService audioService,
  })  : _omniService = omniService,
        _audioService = audioService;
}
```

### Mock 友好

- 所有依赖通过构造函数注入
- 接口清晰定义（通过抽象类或 abstract）
- 事件流可以 mock

## ⚡ 性能考虑

### 1. 内存优化

- 音频文件完成后立即删除
- Base64 编码后原始字节可以 GC
- WebSocket 事件流限制大小

### 2. 网络优化

- WebSocket 长连接（避免重复握手）
- 增量发送音频（appendAudio 可多次调用）
- 使用 commitAudio 标记结束

### 3. UI 优化

- 使用 Consumer 而非 Builder（避免重构整棵树）
- Lazy 初始化（只在进入屏幕时连接）
- 及时清理资源（dispose）

## 🔄 扩展点

### 1. 添加新的语音角色

```dart
OmniRealtimeService(
  voice: 'NewVoice',  // 添加新角色
)
```

### 2. 支持多语言

```dart
// 后端支持不同语言的 Qwen 模型
OmniRealtimeService(
  model: 'qwen3.5-omni-plus-realtime-zh',  // 中文
  // 或
  model: 'qwen3.5-omni-plus-realtime-en',  // 英文
)
```

### 3. 集成对话历史

```dart
class ConversationHistory {
  List<ConversationTurn> turns;  // 存储用户问题和 AI 回答
}

// 在 ElderVoiceScreen 中显示历史
```

### 4. 支持多轮对话

```dart
// 当前已支持，用户可以直接连续提问
// OmniVoiceProvider 保持连接，可以发送多个音频
```

## 📈 监控和日志

### 关键指标

- WebSocket 连接成功率
- 音频上传成功率
- 平均响应时间
- 错误率和错误分布

### 日志级别

```dart
enum LogLevel { trace, debug, info, warn, error }

// 在 OmniVoiceProvider
void _log(LogLevel level, String message) {
  if (kDebugMode) {
    print('[$level] [OmniVoiceProvider] $message');
  }
  // 生产环境应发送到分析平台
}
```

---

**架构版本：** 1.0  
**更新时间：** 2026年4月  
**设计者：** GitHub Copilot + AI Analysis
