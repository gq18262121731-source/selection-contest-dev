import 'package:dio/dio.dart';

import '../../../core/network/api_client.dart';
import '../models/voice_model.dart';

class VoiceRepository {
  final ApiClient _apiClient;
  static const Duration _omniUploadTimeout = Duration(seconds: 20);
  static const Duration _omniReceiveTimeout = Duration(seconds: 120);

  VoiceRepository(this._apiClient);

  String get apiEndpoint => _apiClient.baseUrl;

  Future<VoiceStatus> getVoiceStatus() async {
    final response = await _apiClient.get('voice/status');
    return VoiceStatus.fromJson(Map<String, dynamic>.from(response.data as Map));
  }

  Future<AsrResponse> speechToText(String base64Audio) async {
    final response = await _apiClient.post(
      'voice/asr',
      data: <String, dynamic>{'audio_base64': base64Audio},
    );
    return AsrResponse.fromJson(Map<String, dynamic>.from(response.data as Map));
  }

  Future<AsrResponse> omniChat(
    String audioPath, {
    String? deviceMac,
    String? role,
    String? prompt,
  }) async {
    try {
      final formData = FormData.fromMap(<String, dynamic>{
        'file': await MultipartFile.fromFile(audioPath, filename: 'input.wav'),
        'device_mac': deviceMac ?? '',
        'role': role ?? 'elder',
        if (prompt != null && prompt.trim().isNotEmpty) 'prompt': prompt.trim(),
      });
      final response = await _apiClient.post(
        'omni/analyze',
        data: formData,
        options: Options(
          sendTimeout: _omniUploadTimeout,
          receiveTimeout: _omniReceiveTimeout,
        ),
      );
      return AsrResponse.fromJson(Map<String, dynamic>.from(response.data as Map));
    } on DioException catch (error) {
      if (error.type == DioExceptionType.receiveTimeout) {
        throw Exception('语音请求处理时间较长，请稍候再试。');
      }
      final responseData = error.response?.data;
      if (responseData is Map && responseData['detail'] != null) {
        throw Exception(responseData['detail'].toString());
      }
      throw Exception(error.message ?? '语音对话失败');
    }
  }

  Future<TtsResponse> textToSpeech(String text) async {
    final response = await _apiClient.post(
      'voice/tts',
      data: <String, dynamic>{'text': text},
    );
    return TtsResponse.fromJson(Map<String, dynamic>.from(response.data as Map));
  }
}
