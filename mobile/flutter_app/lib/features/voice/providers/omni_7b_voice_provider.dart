import 'package:flutter/foundation.dart';
import '../../../core/services/audio_service.dart';
import '../services/omni_7b_voice_service.dart';

/// 语音服务状态枚举
enum VoiceStatus {
  idle,           // 空闲
  processing,     // 处理中
  sending,        // 发送中
  error,          // 错误
}

/// Qwen2.5-Omni-7B 语音交互 Provider
class ChatMessage {
  final String sender;
  final String text;
  final bool isAudio;

  ChatMessage({
    required this.sender,
    required this.text,
    this.isAudio = false,
  });
}

class Omni7bVoiceProvider extends ChangeNotifier {
  final Omni7bVoiceService _service;
  final AudioService? _audioService;
  
  VoiceStatus _status = VoiceStatus.idle;
  String _statusMessage = '准备就绪';
  String _response = '';
  String? _errorMessage;
  String? _recordedAudioPath;
  final List<ChatMessage> _history = [];
  
  // Getters
  VoiceStatus get status => _status;
  String get statusMessage => _statusMessage;
  String get response => _response;
  String? get errorMessage => _errorMessage;
  String? get recordedAudioPath => _recordedAudioPath;
  List<ChatMessage> get history => List.unmodifiable(_history);
  bool get isLoading => _status == VoiceStatus.processing || _status == VoiceStatus.sending;
  
  Omni7bVoiceProvider({
    required String apiKey,
    required String apiBase,
    AudioService? audioService,
  }) : _service = Omni7bVoiceService(
    apiKey: apiKey,
    apiBase: apiBase,
  ), _audioService = audioService;
  
  /// 插入对话历史
  void _appendHistory({required String sender, required String content, bool isAudio = false}) {
    _history.add(ChatMessage(sender: sender, text: content, isAudio: isAudio));
    notifyListeners();
  }

  /// 发送文本消息
  Future<void> sendText(String message) async {
    if (message.isEmpty) {
      _setError('消息不能为空');
      return;
    }

    try {
      _setProcessing('发送文本...');
      _appendHistory(sender: '用户', content: message);

      final response = await _service.sendMessage(message);

      _response = response;
      _appendHistory(sender: '小助手', content: response);
      _status = VoiceStatus.idle;
      _statusMessage = '完成';
      _errorMessage = null;
      notifyListeners();
    } catch (e) {
      _setError('发送失败: ${e.toString()}');
    }
  }

  /// 发送音频文件
  Future<void> sendAudio(String audioPath) async {
    try {
      if (_audioService == null) {
        _setError('AudioService 未配置');
        return;
      }

      _setProcessing('上传音频...');
      _recordedAudioPath = audioPath;
      _appendHistory(sender: '用户', content: '已录制语音: $audioPath', isAudio: true);

      final response = await _service.sendAudio(audioPath);

      _response = response;
      _appendHistory(sender: '小助手', content: response);
      _status = VoiceStatus.idle;
      _statusMessage = '完成';
      _errorMessage = null;
      notifyListeners();
    } catch (e) {
      _setError('音频处理失败: ${e.toString()}');
    }
  }

  /// 发送文本 + 音频
  Future<void> sendTextWithAudio({
    required String text,
    required String audioPath,
  }) async {
    if (text.isEmpty) {
      _setError('文本不能为空');
      return;
    }

    try {
      _setProcessing('发送文本+音频...');
      _appendHistory(sender: '用户', content: text);
      _recordedAudioPath = audioPath;
      _appendHistory(sender: '用户', content: '已录制语音: $audioPath', isAudio: true);

      final response = await _service.sendTextWithAudio(text: text, audioPath: audioPath);

      _response = response;
      _appendHistory(sender: '小助手', content: response);
      _status = VoiceStatus.idle;
      _statusMessage = '完成';
      _errorMessage = null;
      notifyListeners();
    } catch (e) {
      _setError('请求失败: ${e.toString()}');
    }
  }

  /// 录音开始
  Future<void> startRecording() async {
    if (_audioService == null) {
      _setError('AudioService 未配置');
      return;
    }

    _setProcessing('正在录音...');
    final path = await _audioService.startRecording();
    if (path == null) {
      _setError('录音失败或权限拒绝');
      return;
    }

    _recordedAudioPath = path;
    _status = VoiceStatus.idle;
    _statusMessage = '录音完成，可发送或播放';
    _errorMessage = null;
    notifyListeners();
  }

  /// 录音停止
  Future<void> stopRecording() async {
    if (_audioService == null) {
      _setError('AudioService 未配置');
      return;
    }

    final path = await _audioService.stopRecording();
    if (path == null) {
      _setError('停止录音失败');
      return;
    }

    _recordedAudioPath = path;
    _status = VoiceStatus.idle;
    _statusMessage = '录音已停止，可发送或播放';
    _errorMessage = null;
    notifyListeners();
  }

  /// 播放录音 (本地声音)
  Future<void> playRecordedAudio() async {
    if (_audioService == null || _recordedAudioPath == null) {
      _setError('无可播放录音');
      return;
    }
    await _audioService.play(_recordedAudioPath!);
  }

  /// 清空响应
  void clearResponse() {
    _response = '';
    _status = VoiceStatus.idle;
    _statusMessage = '准备就绪';
    _errorMessage = null;
    _recordedAudioPath = null;
    _history.clear();
    notifyListeners();
  }
  
  /// 重试
  Future<void> retry(String lastMessage) async {
    clearResponse();
    await sendText(lastMessage);
  }
  
  // Private 辅助方法
  void _setProcessing(String message) {
    _status = VoiceStatus.processing;
    _statusMessage = message;
    _errorMessage = null;
    notifyListeners();
  }
  
  void _setError(String message) {
    _status = VoiceStatus.error;
    _statusMessage = '错误';
    _errorMessage = message;
    notifyListeners();
  }
  
  @override
  void dispose() {
    _service.dispose();
    super.dispose();
  }
}
