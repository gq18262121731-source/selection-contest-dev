import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

class Omni7bVoiceService {
  final String apiKey;
  final String apiBase;
  final String model;

  late final Dio _dio;

  Omni7bVoiceService({
    required this.apiKey,
    required this.apiBase,
    this.model = 'qwen2.5-omni-7b',
  }) {
    _dio = Dio(
      BaseOptions(
        baseUrl: apiBase,
        headers: <String, Object>{
          'Authorization': 'Bearer $apiKey',
          'Content-Type': 'application/json',
        },
        sendTimeout: const Duration(seconds: 120),
        receiveTimeout: const Duration(seconds: 120),
      ),
    );
    _dio.interceptors.add(_LoggingInterceptor());
  }

  Future<String> sendMessage(String message) async {
    final response = await _postChat(
      messages: <Map<String, Object>>[
        <String, Object>{
          'role': 'user',
          'content': message,
        },
      ],
    );
    return _extractAssistantText(response.data);
  }

  Future<String> sendAudio(String audioPath) async {
    final audioInput = await _buildAudioInput(audioPath);
    final response = await _postChat(
      messages: <Map<String, Object>>[
        <String, Object>{
          'role': 'user',
          'content': <Map<String, Object>>[audioInput],
        },
      ],
    );
    return _extractAssistantText(response.data);
  }

  Future<String> sendTextWithAudio({
    required String text,
    required String audioPath,
  }) async {
    final audioInput = await _buildAudioInput(audioPath);
    final response = await _postChat(
      messages: <Map<String, Object>>[
        <String, Object>{
          'role': 'user',
          'content': <Map<String, Object>>[
            <String, Object>{
              'type': 'text',
              'text': text,
            },
            audioInput,
          ],
        },
      ],
    );
    return _extractAssistantText(response.data);
  }

  Future<Response<dynamic>> _postChat({
    required List<Map<String, Object>> messages,
  }) async {
    try {
      final response = await _dio.post(
        '/chat/completions',
        data: <String, Object>{
          'model': model,
          'messages': messages,
          'stream': false,
          'max_tokens': 2048,
        },
      );
      if (response.statusCode == 200) {
        return response;
      }
      throw Exception('API error: ${response.statusCode}');
    } on DioException catch (error) {
      final data = error.response?.data;
      if (data is Map<String, dynamic>) {
        final detail = data['detail'];
        if (detail is String && detail.trim().isNotEmpty) {
          throw Exception(detail);
        }
      }
      throw Exception('Network error: ${error.message}');
    }
  }

  Future<Map<String, Object>> _buildAudioInput(String audioPath) async {
    final file = File(audioPath);
    if (!file.existsSync()) {
      throw Exception('Audio file not found: $audioPath');
    }

    final bytes = await file.readAsBytes();
    final base64Audio = base64Encode(bytes);
    final format = _normalizeAudioFormat(audioPath.split('.').last);

    return <String, Object>{
      'type': 'input_audio',
      'input_audio': <String, Object>{
        'data': 'data:;base64,$base64Audio',
        'format': format,
      },
    };
  }

  String _normalizeAudioFormat(String extension) {
    final lower = extension.trim().toLowerCase();
    switch (lower) {
      case 'wav':
      case 'wave':
        return 'wav';
      case 'mp3':
      case 'mpeg':
        return 'mp3';
      case 'm4a':
      case 'aac':
      case 'mp4':
        return 'aac';
      case 'amr':
      case '3gp':
      case '3gpp':
        return lower;
      default:
        return 'wav';
    }
  }

  String _extractAssistantText(dynamic data) {
    if (data is! Map<String, dynamic>) {
      return '';
    }

    final choices = data['choices'];
    if (choices is! List || choices.isEmpty) {
      return '';
    }

    final first = choices.first;
    if (first is! Map<String, dynamic>) {
      return '';
    }

    final message = first['message'];
    if (message is! Map<String, dynamic>) {
      return '';
    }

    final content = message['content'];
    if (content is String) {
      return content;
    }
    if (content is List) {
      return content
          .whereType<Map<String, dynamic>>()
          .map((item) => item['text'])
          .whereType<String>()
          .join();
    }
    return '';
  }

  void dispose() {
    _dio.close();
  }
}

class _LoggingInterceptor extends Interceptor {
  @override
  void onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) {
    debugPrint('[request] ${options.method} ${options.path}');
    super.onRequest(options, handler);
  }

  @override
  void onResponse(
    Response<dynamic> response,
    ResponseInterceptorHandler handler,
  ) {
    debugPrint('[response] ${response.statusCode}');
    super.onResponse(response, handler);
  }

  @override
  void onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) {
    debugPrint('[error] ${err.message}');
    super.onError(err, handler);
  }
}
