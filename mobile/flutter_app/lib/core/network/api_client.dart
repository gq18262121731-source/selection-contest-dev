import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'server_endpoint_config.dart';
import '../../features/session/services/session_manager.dart';

class ApiClient {
  final Dio _dio;
  final ServerEndpointConfig _endpointConfig;
  final SessionManager _sessionManager;
  final void Function() onUnauthorized;

  ApiClient({
    required ServerEndpointConfig endpointConfig,
    required SessionManager sessionManager,
    required this.onUnauthorized,
  })  : _dio = Dio(BaseOptions(
          baseUrl: endpointConfig.apiBaseUrl,
          connectTimeout: const Duration(seconds: 5),
          receiveTimeout: const Duration(seconds: 3),
        )),
        _endpointConfig = endpointConfig,
        _sessionManager = sessionManager {
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) {
        final token = _sessionManager.token;
        if (token != null) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        return handler.next(options);
      },
      onError: (error, handler) {
        if (error.response?.statusCode == 401) {
          _sessionManager.clearSession();
          onUnauthorized();
        }
        return handler.next(error);
      },
    ));
  }

  void _syncBaseUrl() {
    _dio.options.baseUrl = _endpointConfig.apiBaseUrl;
  }

  Future<Response> get(String path, {Map<String, dynamic>? queryParameters}) {
    _syncBaseUrl();
    return _dio.get(path, queryParameters: queryParameters);
  }

  Future<Response> post(String path, {dynamic data, Options? options}) {
    _syncBaseUrl();
    return _dio.post(path, data: data, options: options);
  }

  Future<Response> postStream(
    String path, {
    dynamic data,
    Duration? sendTimeout,
    Duration? receiveTimeout,
  }) {
    _syncBaseUrl();
    // On Web, ResponseType.stream is not supported by the default BrowserHttpClientAdapter.
    // We fallback to ResponseType.plain and let the repository handle it as a single chunk
    // or simulate a stream for compatibility.
    final responseType = kIsWeb ? ResponseType.plain : ResponseType.stream;
    return _dio.post(
      path,
      data: data,
      options: Options(
        responseType: responseType,
        sendTimeout: sendTimeout,
        receiveTimeout: receiveTimeout ?? const Duration(seconds: 60),
      ),
    );
  }

  String get baseUrl => _endpointConfig.apiBaseUrl;
}
