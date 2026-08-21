import 'package:web_socket_channel/web_socket_channel.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/server_endpoint_config.dart';
import '../models/health_model.dart';
import '../models/history_model.dart';

class HealthRepository {
  final ApiClient _apiClient;
  final ServerEndpointConfig _endpointConfig;

  HealthRepository(this._apiClient, {required ServerEndpointConfig endpointConfig})
      : _endpointConfig = endpointConfig;

  Future<HealthData> getRealtimeSnapshot(String mac) async {
    final response = await _apiClient.get('health/realtime/$mac');
    return HealthData.fromJson(response.data);
  }

  Future<List<HealthData>> getRealtimeTrend(
    String mac, {
    int minutes = 60,
    int limit = 120,
  }) async {
    final response = await _apiClient.get(
      'health/trend/$mac',
      queryParameters: {
        'minutes': minutes,
        'limit': limit,
      },
    );
    final points = (response.data as List<dynamic>)
        .map((entry) => HealthData.fromJson(entry as Map<String, dynamic>))
        .toList()
      ..sort((a, b) => a.timestamp.compareTo(b.timestamp));
    return points;
  }

  Future<List<TrendPoint>> getTrend(String mac) async {
    final response = await _apiClient.get('health/trend/$mac');
    final points = (response.data as List<dynamic>)
        .map((entry) => TrendPoint.fromJson(entry as Map<String, dynamic>))
        .toList()
      ..sort((a, b) => a.timestamp.compareTo(b.timestamp));
    return points;
  }

  Future<DeviceHistoryResponse> getHistory(String mac, {String window = 'day'}) async {
    final response = await _apiClient.get(
      'health/devices/$mac/history',
      queryParameters: {'window': window},
    );
    return DeviceHistoryResponse.fromJson(response.data);
  }

  WebSocketChannel connectToRealtime(String mac) {
    return WebSocketChannel.connect(Uri.parse('${_endpointConfig.wsBaseUrl}/ws/health/$mac'));
  }
}
