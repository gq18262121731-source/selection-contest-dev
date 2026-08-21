import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/services/audio_service.dart';
import '../../voice/providers/voice_provider.dart';
import '../repositories/agent_repository.dart';

enum AgentStatus { initial, loading, streaming, loaded, error }

class AgentProvider extends ChangeNotifier {
  AgentRepository _repository;
  AudioService _audioService;

  AgentStatus _status = AgentStatus.initial;
  String? _errorMessage;
  final List<AgentMessage> _messages = <AgentMessage>[];

  AgentProvider(this._repository, this._audioService);

  AgentStatus get status => _status;
  String? get errorMessage => _errorMessage;
  List<AgentMessage> get messages => _messages;

  void updateDependencies(
      AgentRepository repository, AudioService audioService) {
    _repository = repository;
    _audioService = audioService;
  }

  void init([String? initialGreeting]) {
    _messages.clear();
    if (initialGreeting != null && initialGreeting.trim().isNotEmpty) {
      _messages.add(
        AgentMessage(role: 'assistant', content: initialGreeting.trim()),
      );
    }
    _status = AgentStatus.loaded;
    _errorMessage = null;
    notifyListeners();
  }

  Future<void> sendMessage(
    String text, {
    String? deviceMac,
    List<String> deviceMacs = const <String>[],
    required String role,
  }) async {
    final normalizedText = text.trim();
    if (normalizedText.isEmpty) {
      return;
    }

    final userMessage = AgentMessage(role: 'user', content: normalizedText);
    _messages.add(userMessage);

    _status = AgentStatus.loading;
    _errorMessage = null;
    notifyListeners();

    final assistantMessage = AgentMessage(role: 'assistant', content: '');
    _messages.add(assistantMessage);
    notifyListeners();

    try {
      _status = AgentStatus.streaming;
      notifyListeners();

      await for (final delta in _repository.streamAgentAnalysis(
        normalizedText,
        deviceMac,
        deviceMacs: deviceMacs,
        role: role,
      )) {
        assistantMessage.content += delta;
        notifyListeners();
      }

      _status = AgentStatus.loaded;
    } catch (_) {
      _errorMessage = '暂时无法连接到健康助手，请稍后再试。';
      _status = AgentStatus.error;
      if (assistantMessage.content.isEmpty) {
        assistantMessage.content = '连接失败，请稍后重试。';
      }
    }

    notifyListeners();
  }

  Future<void> sendVoiceMessageFromPath(
    String audioPath, {
    String? deviceMac,
    required String role,
  }) async {
    final audioBytes = await _audioService.readBytes(audioPath);
    await sendVoiceMessage(
      audioBytes,
      deviceMac: deviceMac,
      role: role,
    );
  }

  Future<void> sendVoiceMessage(
    List<int> audioBytes, {
    String? deviceMac,
    required String role,
  }) async {
    if (audioBytes.isEmpty) {
      return;
    }

    final userMessage = AgentMessage(role: 'user', content: '[语音消息]');
    _messages.add(userMessage);

    _status = AgentStatus.loading;
    _errorMessage = null;
    notifyListeners();

    final assistantMessage = AgentMessage(role: 'assistant', content: '');
    _messages.add(assistantMessage);
    notifyListeners();

    var streamingAudioStarted = false;
    var streamingAudioUnavailable = false;
    try {
      AgentOmniResponse? audioResponse;
      AgentOmniResponse? completedResponse;

      _status = AgentStatus.streaming;
      notifyListeners();

      await for (final event in _repository.streamOmniMessage(
        audioBytes,
        deviceMac,
        role: role,
      )) {
        switch (event.type) {
          case AgentOmniStreamEventType.delta:
            assistantMessage.content += event.delta;
            notifyListeners();
            break;
          case AgentOmniStreamEventType.audioDelta:
            if (!streamingAudioStarted && !streamingAudioUnavailable) {
              streamingAudioStarted = await _audioService.startPcmStream(
                sampleRate: event.sampleRate,
                channels: event.channels,
                encoding: event.encoding,
              );
              streamingAudioUnavailable = !streamingAudioStarted;
            }
            if (streamingAudioStarted) {
              final accepted =
                  await _audioService.writePcmBase64Chunk(event.delta);
              if (!accepted) {
                await _audioService.abortPcmStream();
                streamingAudioStarted = false;
                streamingAudioUnavailable = true;
              }
            }
            break;
          case AgentOmniStreamEventType.audioCompleted:
            audioResponse = event.response;
            break;
          case AgentOmniStreamEventType.completed:
            completedResponse = event.response;
            if (assistantMessage.content.trim().isEmpty &&
                completedResponse != null &&
                completedResponse.text.trim().isNotEmpty) {
              assistantMessage.content = completedResponse.text;
              notifyListeners();
            }
            break;
        }
      }

      if (assistantMessage.content.trim().isEmpty) {
        throw Exception('语音服务未返回文字回复');
      }

      if (streamingAudioStarted) {
        await _audioService.finishPcmStream();
      } else if (audioResponse != null &&
          audioResponse.audioBase64.trim().isNotEmpty) {
        await _audioService.playBase64(
          audioResponse.audioBase64,
          audioResponse.audioFormat,
        );
      } else if (audioResponse != null &&
          audioResponse.audioUrl.trim().isNotEmpty) {
        await _audioService.play(audioResponse.audioUrl);
      }

      _status = AgentStatus.loaded;
    } catch (error) {
      if (streamingAudioStarted) {
        await _audioService.abortPcmStream();
      }
      final message = error.toString().replaceFirst('Exception: ', '').trim();
      _errorMessage = message.isEmpty ? '语音分析失败，请稍后再试。' : message;
      _status = AgentStatus.error;
      if (assistantMessage.content.isEmpty) {
        assistantMessage.content = _errorMessage!;
      }
    }

    notifyListeners();
  }

  Future<void> ttsSpeak(BuildContext context, String text) async {
    if (text.trim().isEmpty) {
      return;
    }

    final voiceProvider = context.read<VoiceProvider>();

    _status = AgentStatus.loading;
    notifyListeners();

    try {
      await voiceProvider.processTts(text);
      _status = AgentStatus.loaded;
    } catch (_) {
      _errorMessage = '播报失败。';
      _status = AgentStatus.error;
    }
    notifyListeners();
  }
}
