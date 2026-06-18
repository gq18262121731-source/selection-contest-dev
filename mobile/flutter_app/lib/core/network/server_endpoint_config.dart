import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class ServerEndpointConfig extends ChangeNotifier {
  static const _keyHost = 'server_host';
  static const _keyPort = 'server_port';
  static const _keyScheme = 'server_scheme';
  static const _envHost =
      String.fromEnvironment('APP_SERVER_HOST', defaultValue: '');
  static const _envPort =
      int.fromEnvironment('APP_SERVER_PORT', defaultValue: -1);
  static const _envScheme =
      String.fromEnvironment('APP_SERVER_SCHEME', defaultValue: '');

  final SharedPreferences _prefs;

  late String _host;
  late int _port;
  late String _scheme;
  int _revision = 0;

  ServerEndpointConfig(this._prefs) {
    final storedHost = _prefs.getString(_keyHost)?.trim();
    final storedPort = _prefs.getInt(_keyPort);
    final storedScheme = _prefs.getString(_keyScheme);

    _host = _configuredHost(storedHost);
    _port = _configuredPort(storedPort);
    _scheme = _configuredScheme(storedScheme);
  }

  String get host => _host;
  int get port => _port;
  String get scheme => _scheme;
  int get revision => _revision;

  String get origin => '$_scheme://$_host:$_port';
  String get apiBaseUrl => '$origin/api/v1/';
  String get wsBaseUrl =>
      '${_scheme == 'https' ? 'wss' : 'ws'}://$_host:$_port';

  static String _normalizeScheme(String value) {
    return value.toLowerCase() == 'https' ? 'https' : 'http';
  }

  static String _configuredHost(String? storedHost) {
    final envHost = _envHost.trim();
    if (envHost.isNotEmpty) {
      return envHost;
    }
    if (storedHost != null && storedHost.isNotEmpty) {
      return storedHost;
    }
    return _defaultHost();
  }

  static int _configuredPort(int? storedPort) {
    if (_envPort > 0) {
      return _envPort;
    }
    return storedPort ?? 8000;
  }

  static String _configuredScheme(String? storedScheme) {
    final envScheme = _envScheme.trim();
    if (envScheme.isNotEmpty) {
      return _normalizeScheme(envScheme);
    }
    return _normalizeScheme(storedScheme ?? 'http');
  }

  static String _defaultHost() {
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      return '10.0.2.2';
    }
    return '127.0.0.1';
  }

  Future<void> save({
    required String host,
    required int port,
    required String scheme,
  }) async {
    final normalizedHost = host.trim();
    final normalizedScheme = _normalizeScheme(scheme);

    await _prefs.setString(_keyHost, normalizedHost);
    await _prefs.setInt(_keyPort, port);
    await _prefs.setString(_keyScheme, normalizedScheme);

    _host = normalizedHost;
    _port = port;
    _scheme = normalizedScheme;
    _revision += 1;
    notifyListeners();
  }

  Future<String?> testConnection({
    required String host,
    required int port,
    required String scheme,
  }) async {
    final normalizedHost = host.trim();
    final normalizedScheme = _normalizeScheme(scheme);

    try {
      final dio = Dio(
        BaseOptions(
          baseUrl: '$normalizedScheme://$normalizedHost:$port',
          connectTimeout: const Duration(seconds: 3),
          receiveTimeout: const Duration(seconds: 3),
        ),
      );
      final response = await dio.get('/healthz');
      final data = response.data;
      if (response.statusCode == 200 && data is Map && data['status'] == 'ok') {
        return null;
      }
      return '服务器已响应，但健康检查结果异常。';
    } on DioException catch (error) {
      if (error.type == DioExceptionType.connectionTimeout ||
          error.type == DioExceptionType.receiveTimeout) {
        return '连接超时，请确认服务器地址和端口是否正确。';
      }
      final message = error.message?.trim();
      if (message != null && message.isNotEmpty) {
        return '连接失败：$message';
      }
      return '连接失败，请检查手机和服务器是否在同一局域网。';
    } catch (_) {
      return '连接失败，请检查服务器是否已经启动。';
    }
  }
}
