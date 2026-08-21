# 单元测试和集成测试示例

## 📝 OmniRealtimeService 单元测试

创建 `test/features/voice/services/omni_realtime_service_test.dart`：

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/mockito.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:elder_care/features/voice/services/omni_realtime_service.dart';

// Mock 类
class MockWebSocketChannel extends Mock implements WebSocketChannel {}

void main() {
  group('OmniRealtimeService', () {
    late OmniRealtimeService service;
    late MockWebSocketChannel mockWebSocket;

    setUp(() {
      mockWebSocket = MockWebSocketChannel();
      service = OmniRealtimeService(
        apiKey: 'test-key',
        model: 'qwen3.5-omni-plus-realtime',
        voice: 'Tina',
      );
    });

    test('初始化时状态应为未连接', () {
      expect(service.isConnected, false);
    });

    test('appendAudio 应调用 WebSocket send', () async {
      // 设置期望
      when(mockWebSocket.innerWebSocket)
          .thenAnswer((_) => Future.value());

      // 验证
      verify(mockWebSocket.sink.add(any)).called(greaterThan(0));
    });

    test('commitAudio 应提交待处理音频', () async {
      // 实装类似于 appendAudio 的测试
    });

    test('连接失败时应触发错误事件', () async {
      // 模拟连接失败
      expect(
        () => service.connect(),
        throwsException,
      );
    });

    test('事件流应发出正确的事件类型', (WidgetTester tester) async {
      // 调用 connect
      // 监听事件
      // 验证事件类型和数据
    });
  });
}
```

## 🧪 OmniVoiceProvider 单元测试

创建 `test/features/voice/providers/omni_voice_provider_test.dart`：

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/mockito.dart';
import 'package:provider/provider.dart';
import 'package:elder_care/features/voice/providers/omni_voice_provider.dart';
import 'package:elder_care/features/voice/services/omni_realtime_service.dart';
import 'package:elder_care/core/services/audio_service.dart';

// Mock 类
class MockOmniRealtimeService extends Mock 
    implements OmniRealtimeService {}

class MockAudioService extends Mock implements AudioService {}

void main() {
  group('OmniVoiceProvider', () {
    late OmniVoiceProvider provider;
    late MockOmniRealtimeService mockOmniService;
    late MockAudioService mockAudioService;

    setUp(() {
      mockOmniService = MockOmniRealtimeService();
      mockAudioService = MockAudioService();

      provider = OmniVoiceProvider(
        apiKey: 'test-key',
        omniService: mockOmniService,
        audioService: mockAudioService,
      );
    });

    test('初始状态应为 idle', () {
      expect(provider.status, OmniVoiceStatus.idle);
      expect(provider.statusMessage, isNotEmpty);
    });

    test('连接时状态变为 connecting', () async {
      when(mockOmniService.connect())
          .thenAnswer((_) => Future.value());

      await provider.connect();

      expect(provider.status, OmniVoiceStatus.connecting);
    });

    test('成功连接后状态变为 idle', () async {
      when(mockOmniService.connect())
          .thenAnswer((_) => Future.value());
      when(mockOmniService.isConnected).thenReturn(true);

      final result = await provider.connect();

      expect(result, true);
      // 注意: 实际状态取决于事件处理
    });

    test('开始录音时状态变为 recording', () async {
      when(mockAudioService.startRecording())
          .thenAnswer((_) => Future.value('/path/to/audio.wav'));

      await provider.startRecording();

      expect(provider.status, OmniVoiceStatus.recording);
    });

    test('停止录音并处理', () async {
      // 设置前置条件
      when(mockAudioService.startRecording())
          .thenAnswer((_) => Future.value('/path/to/audio.wav'));
      when(mockOmniService.appendAudio(any))
          .thenAnswer((_) => Future.value());
      when(mockOmniService.commitAudio())
          .thenAnswer((_) => Future.value());

      await provider.startRecording();
      await provider.stopRecordingAndProcess();

      expect(provider.status, OmniVoiceStatus.processing);
      // 验证 Omni 服务被调用
      verify(mockOmniService.appendAudio(any)).called(1);
      verify(mockOmniService.commitAudio()).called(1);
    });

    test('断开连接时应清理资源', () async {
      when(mockOmniService.disconnect())
          .thenAnswer((_) => Future.value());

      await provider.disconnect();

      verify(mockOmniService.disconnect()).called(1);
    });

    test('状态改变时应触发 notifyListeners', () async {
      bool notified = false;

      provider.addListener(() {
        notified = true;
      });

      when(mockAudioService.startRecording())
          .thenAnswer((_) => Future.value('/path/to/audio.wav'));

      await provider.startRecording();

      expect(notified, true);
    });
  });
}
```

## 🖼️ Widget 测试

创建 `test/features/voice/widgets/elder_voice_interaction_widget_test.dart`：

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/mockito.dart';
import 'package:provider/provider.dart';
import 'package:elder_care/features/voice/widgets/elder_voice_interaction_widget.dart';
import 'package:elder_care/features/voice/providers/omni_voice_provider.dart';

class MockOmniVoiceProvider extends Mock 
    implements OmniVoiceProvider {}

void main() {
  group('ElderVoiceInteractionWidget', () {
    late MockOmniVoiceProvider mockProvider;

    setUp(() {
      mockProvider = MockOmniVoiceProvider();
      when(mockProvider.status)
          .thenReturn(OmniVoiceStatus.idle);
      when(mockProvider.statusMessage)
          .thenReturn('准备好了');
      when(mockProvider.fullResponse).thenReturn('');
    });

    testWidgets('应该正确显示空闲状态', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: ChangeNotifierProvider<OmniVoiceProvider>.value(
            value: mockProvider,
            child: const Scaffold(
              body: ElderVoiceInteractionWidget(
                deviceMac: 'AA:BB:CC:DD:EE:FF',
              ),
            ),
          ),
        ),
      );

      expect(find.text('准备好了'), findsOneWidget);
      expect(find.text('按住说话'), findsOneWidget);
    });

    testWidgets('点击按钮时应调用 startRecording', 
        (WidgetTester tester) async {
      when(mockProvider.startRecording())
          .thenAnswer((_) => Future.value(true));

      await tester.pumpWidget(
        MaterialApp(
          home: ChangeNotifierProvider<OmniVoiceProvider>.value(
            value: mockProvider,
            child: const Scaffold(
              body: ElderVoiceInteractionWidget(
                deviceMac: 'AA:BB:CC:DD:EE:FF',
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.text('按住说话'));
      await tester.pumpAndSettle();

      verify(mockProvider.startRecording()).called(1);
    });

    testWidgets('应该显示响应文本', (WidgetTester tester) async {
      when(mockProvider.status)
          .thenReturn(OmniVoiceStatus.responding);
      when(mockProvider.fullResponse)
          .thenReturn('这是 AI 的响应');

      await tester.pumpWidget(
        MaterialApp(
          home: ChangeNotifierProvider<OmniVoiceProvider>.value(
            value: mockProvider,
            child: const Scaffold(
              body: ElderVoiceInteractionWidget(
                deviceMac: 'AA:BB:CC:DD:EE:FF',
              ),
            ),
          ),
        ),
      );

      expect(find.text('这是 AI 的响应'), findsOneWidget);
    });

    testWidgets('错误状态应显示错误信息', 
        (WidgetTester tester) async {
      when(mockProvider.status)
          .thenReturn(OmniVoiceStatus.error);
      when(mockProvider.statusMessage)
          .thenReturn('连接失败');

      await tester.pumpWidget(
        MaterialApp(
          home: ChangeNotifierProvider<OmniVoiceProvider>.value(
            value: mockProvider,
            child: const Scaffold(
              body: ElderVoiceInteractionWidget(
                deviceMac: 'AA:BB:CC:DD:EE:FF',
              ),
            ),
          ),
        ),
      );

      expect(
        find.byWidgetPredicate(
          (widget) => widget is Card && 
            (widget.child as Widget?) != null,
        ),
        findsOneWidget,
      );
    });
  });
}
```

## 🔄 集成测试

创建 `integration_test/voice_integration_test.dart`：

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:elder_care/main.dart' as app;

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  group('语音交互端到端测试', () {
    testWidgets('用户应该能导航到语音对话页面',
        (WidgetTester tester) async {
      app.main();
      await tester.pumpAndSettle();

      // 模拟登录（根据实际应用调整）
      // 导航到主页
      final homeButton = find.byIcon(Icons.home);
      if (homeButton.evaluate().isNotEmpty) {
        await tester.tap(homeButton);
        await tester.pumpAndSettle();
      }

      // 查找并点击"语音对话"按钮
      final voiceButton = find.text('语音对话');
      expect(voiceButton, findsOneWidget);

      await tester.tap(voiceButton);
      await tester.pumpAndSettle();

      // 验证导航到语音屏幕
      final welcomeCard = find.text('欢迎使用语音对话');
      expect(welcomeCard, findsOneWidget);
    });

    testWidgets('用户应该能开始录音',
        (WidgetTester tester) async {
      app.main();
      await tester.pumpAndSettle();

      // 导航到语音页面（同上）
      // 点击"按住说话"按钮
      final recordButton = find.text('按住说话');
      expect(recordButton, findsOneWidget);

      // 长按（模拟录音）
      await tester.longPress(recordButton);
      await tester.pumpAndSettle(const Duration(seconds: 1));

      // 验证状态为"录音中"
      final recordingStatus = find.text('录音中...');
      expect(recordingStatus, findsOneWidget);

      // 释放
      await tester.release(recordButton);
      await tester.pumpAndSettle();
    });

    testWidgets('应该显示处理状态',
        (WidgetTester tester) async {
      // 同上导航
      // 同上开始录音
      // 释放后应显示"处理中..."
      final processingStatus = find.text('处理中...');
      // 等待一段时间
      await tester.pumpAndSettle(const Duration(seconds: 3));
      // 验证状态更新
    });

    testWidgets('应该显示响应', (WidgetTester tester) async {
      // 继续上面的流程
      // 等待响应
      await tester.pumpAndSettle(const Duration(seconds: 5));

      // 验证响应文本存在
      final responseCard = find.byWidgetPredicate(
        (widget) => widget is Card,
      );
      expect(responseCard, findsWidgets);
    });

    testWidgets('用户应该能返回到主页',
        (WidgetTester tester) async {
      app.main();
      await tester.pumpAndSettle();

      // 导航到语音页面
      // 点击返回按钮
      final backButton = find.byIcon(Icons.arrow_back);
      expect(backButton, findsOneWidget);

      await tester.tap(backButton);
      await tester.pumpAndSettle();

      // 验证返回到主页
      final homeContent = find.byIcon(Icons.home);
      // 验证主页内容
    });
  });
}
```

## 🧬 性能测试

创建 `test/features/voice/performance_test.dart`：

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:performance/performance.dart';

void main() {
  group('语音交互性能测试', () {
    test('Audio 转 Base64 编码性能', () async {
      // 创建测试音频数据（1MB）
      final audioData = List<int>.generate(1024 * 1024, (i) => i % 256);

      // 测量编码时间
      final stopwatch = Stopwatch()..start();
      
      import 'dart:convert';
      final base64String = base64Encode(audioData);
      
      stopwatch.stop();

      print('编码时间: ${stopwatch.elapsedMilliseconds}ms');
      // 应该在 100ms 以内
      expect(stopwatch.elapsedMilliseconds, lessThan(100));
    });

    test('内存使用应该不会凸起', () async {
      // 测量内存
      // 创建多个 Provider 实例
      // 验证内存在合理范围内
    });
  });
}
```

## 🧪 运行测试

### 运行单元测试

```bash
# 运行所有单元测试
flutter test

# 运行特定文件
flutter test test/features/voice/providers/omni_voice_provider_test.dart

# 运行特定 group
flutter test -k "OmniVoiceProvider"

# 生成覆盖率报告
flutter test --coverage
lcov --list coverage/lcov.info
```

### 运行 Widget 测试

```bash
# Widget 测试也通过 flutter test 运行
flutter test test/features/voice/widgets/
```

### 运行集成测试

```bash
# 运行集成测试
flutter test integration_test/voice_integration_test.dart

# 在真实设备上运行
flutter test integration_test/ -d <device-id>
```

## 📊 代码覆盖率目标

| 模块 | 目标 | 实际 |
|------|------|------|
| omni_realtime_service.dart | 90% | TBD |
| omni_voice_provider.dart | 85% | TBD |
| voice widget | 80% | TBD |
| voice screen | 75% | TBD |
| **总体** | **85%** | TBD |

## 🐛 故障排查 - 测试

### 问题: Mock 对象不工作

**解决方案：**
```dart
// ❌ 错误
@Mock
MockService mockService;

// ✅ 正确
late MockService mockService;

setUp(() {
  mockService = MockService();
});
```

### 问题: `pumpAndSettle()` 永不返回

**解决方案：**
```dart
// 添加超时
await tester.pumpAndSettle(
  const Duration(seconds: 5),
);
```

### 问题: WebSocket 无法在测试中连接

**解决方案：**
使用 Mock WebSocket，不要真正连接：
```dart
class MockWebSocketChannel extends Mock 
    implements WebSocketChannel {}
```

## 📋 测试检查清单

部署前测试：

- [ ] 单元测试通过 (OmniRealtimeService)
- [ ] 单元测试通过 (OmniVoiceProvider)
- [ ] Widget 测试通过 (UI 组件)
- [ ] 集成测试通过 (完整流程)
- [ ] 代码覆盖率 > 80%
- [ ] 性能测试通过
- [ ] 没有内存泄漏
- [ ] 设备兼容性测试完成

---

**测试版本：** 1.0  
**框架：** Flutter Test, Mockito, Integration Test
