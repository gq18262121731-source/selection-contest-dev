import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/services/audio_service.dart';
import '../../care/providers/care_provider.dart';
import '../models/voice_model.dart';
import '../repositories/voice_repository.dart';

enum VoiceLoadStatus { initial, loading, loaded, error }

class VoiceProvider extends ChangeNotifier {
  VoiceRepository _repository;
  AudioService _audioService;

  VoiceLoadStatus _status = VoiceLoadStatus.initial;
  VoiceStatus? _voiceStatus;
  String? _errorMessage;

  bool _isProcessing = false;
  bool _isRecording = false;
  String _lastAsrText = '';
  String _lastTtsUrl = '';

  VoiceProvider(this._repository, this._audioService);

  VoiceLoadStatus get status => _status;
  VoiceStatus? get voiceStatus => _voiceStatus;
  String? get errorMessage => _errorMessage;
  bool get isProcessing => _isProcessing;
  bool get isRecording => _isRecording;
  String get lastAsrText => _lastAsrText;
  String get lastTtsUrl => _lastTtsUrl;
  bool get isVoiceAvailable => _voiceStatus?.configured ?? false;

  void updateDependencies(VoiceRepository repository, AudioService audioService) {
    _repository = repository;
    _audioService = audioService;
  }

  Future<void> checkStatus() async {
    _status = VoiceLoadStatus.loading;
    _errorMessage = null;
    notifyListeners();

    try {
      _voiceStatus = await _repository.getVoiceStatus();
      _status = VoiceLoadStatus.loaded;
    } catch (_) {
      _status = VoiceLoadStatus.error;
      _errorMessage = '获取语音服务状态失败。';
    }
    notifyListeners();
  }

  Future<void> startRecording() async {
    if (!isVoiceAvailable) {
      _errorMessage = '语音服务未就绪，请先检查后端语音配置。';
      notifyListeners();
      return;
    }

    final path = await _audioService.startRecording();
    if (path == null) {
      _errorMessage = '录音启动失败，请检查麦克风权限。';
      notifyListeners();
      return;
    }

    _errorMessage = null;
    _isRecording = true;
    notifyListeners();
  }

  Future<String?> stopRecording({
    bool processOmni = true,
    BuildContext? context,
  }) async {
    if (!_isRecording) {
      return null;
    }

    _isRecording = false;
    notifyListeners();

    final path = await _audioService.stopRecording();
    if (path == null) {
      _errorMessage = '录音保存失败，请重试。';
      notifyListeners();
      return null;
    }

    await Future<void>.delayed(const Duration(milliseconds: 300));
    final file = File(path);
    if (!await file.exists()) {
      _errorMessage = '录音文件不存在，请重新录音。';
      notifyListeners();
      return null;
    }

    final size = await file.length();
    if (size <= 0) {
      _errorMessage = '录音内容为空，请重新录音。';
      notifyListeners();
      return null;
    }

    final resolvedDeviceMac =
        context?.read<CareProvider>().profile?.boundDeviceMacs.firstOrNull;

    if (processOmni) {
      await processOmniChat(path, deviceMac: resolvedDeviceMac);
    }
    return path;
  }

  Future<void> processOmniChat(String audioPath, {String? deviceMac}) async {
    if (!isVoiceAvailable) {
      _errorMessage = '语音服务未就绪，请先检查后端语音配置。';
      notifyListeners();
      return;
    }

    _isProcessing = true;
    _errorMessage = null;
    notifyListeners();

    try {
      final response = await _repository.omniChat(
        audioPath,
        deviceMac: deviceMac,
        role: 'elder',
      );

      _lastAsrText = response.text;

      if (response.audioBase64.trim().isNotEmpty) {
        await _audioService.playBase64(response.audioBase64, response.audioFormat);
      } else if (response.audioUrl.trim().isNotEmpty) {
        await _audioService.play(response.audioUrl);
      } else if (_lastAsrText.trim().isNotEmpty) {
        await processTts(_lastAsrText);
      } else {
        _errorMessage = '语音服务未返回文字或音频结果。';
      }
    } catch (error) {
      debugPrint('OmniChat error: $error');
      if (error is DioException) {
        debugPrint('Dio error details: ${error.response?.statusCode} - ${error.response?.data}');
      }
      final message = error.toString().replaceFirst('Exception: ', '').trim();
      _errorMessage = message.isEmpty ? '语音对话失败，请检查网络或服务配置。' : message;
    } finally {
      _isProcessing = false;
      notifyListeners();
    }
  }

  Future<String?> processAsr(String base64Audio) async {
    if (!isVoiceAvailable) {
      _errorMessage = '语音服务未就绪，请先检查后端语音配置。';
      notifyListeners();
      return null;
    }

    _isProcessing = true;
    _errorMessage = null;
    notifyListeners();

    try {
      final response = await _repository.speechToText(base64Audio);
      if (!response.ok) {
        throw Exception(response.error ?? '语音识别失败。');
      }
      _lastAsrText = response.text;
      return _lastAsrText;
    } catch (error) {
      final message = error.toString().replaceFirst('Exception: ', '').trim();
      _errorMessage = message.isEmpty ? '语音识别失败。' : message;
      return null;
    } finally {
      _isProcessing = false;
      notifyListeners();
    }
  }

  Future<void> processTts(String text) async {
    if (text.trim().isEmpty) {
      return;
    }

    if (!isVoiceAvailable) {
      _errorMessage = '语音服务未就绪，请先检查后端语音配置。';
      notifyListeners();
      return;
    }

    _isProcessing = true;
    _errorMessage = null;
    _lastTtsUrl = '';
    notifyListeners();

    try {
      final response = await _repository.textToSpeech(text);
      if (!response.ok) {
        _errorMessage = response.error?.trim().isNotEmpty == true
            ? response.error
            : '语音播报失败。';
        return;
      }

      _lastTtsUrl = response.audioUrl;
      if (!response.hasAudio) {
        _errorMessage = '语音服务未返回可播放音频。';
        return;
      }

      if (response.audioBase64.trim().isNotEmpty) {
        await _audioService.playBase64(response.audioBase64, response.format);
      } else if (_lastTtsUrl.startsWith('data:audio')) {
        await _audioService.play(_lastTtsUrl);
      } else if (_lastTtsUrl.startsWith('http://') || _lastTtsUrl.startsWith('https://')) {
        await _audioService.play(_lastTtsUrl);
      } else if (_lastTtsUrl.trim().isNotEmpty) {
        final finalUrl = '${_repository.apiEndpoint}/$_lastTtsUrl'
            .replaceAll('//', '/')
            .replaceFirst(':/', '://');
        await _audioService.play(finalUrl);
      } else {
        _errorMessage = '语音服务未返回可播放音频。';
      }
    } catch (error) {
      debugPrint('TTS error: $error');
      if (error is DioException) {
        debugPrint('Dio error details: ${error.response?.statusCode} - ${error.response?.data}');
      }
      final message = error.toString().replaceFirst('Exception: ', '').trim();
      _errorMessage = message.isEmpty ? '语音播报失败。' : message;
    } finally {
      _isProcessing = false;
      notifyListeners();
    }
  }
}
