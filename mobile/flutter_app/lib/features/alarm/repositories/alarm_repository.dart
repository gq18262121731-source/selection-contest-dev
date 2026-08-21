import 'package:web_socket_channel/web_socket_channel.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/server_endpoint_config.dart';
import '../models/alarm_model.dart';

class AlarmRepository {
  final ApiClient _apiClient;
  final ServerEndpointConfig _endpointConfig;

  AlarmRepository(this._apiClient, {required ServerEndpointConfig endpointConfig})
      : _endpointConfig = endpointConfig;

  Future<List<AlarmRecord>> getAlarms({bool activeOnly = false}) async {
    final response = await _apiClient.get('alarms', queryParameters: {'active_only': activeOnly});
    return (response.data as List).map((e) => AlarmRecord.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<AlarmQueueItem>> getAlarmQueue() async {
    final response = await _apiClient.get('alarms/queue');
    return (response.data as List).map((e) => AlarmQueueItem.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<MobilePushRecord>> getMobilePushes() async {
    final response = await _apiClient.get('alarms/mobile-pushes');
    return (response.data as List).map((e) => MobilePushRecord.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<void> acknowledgeAlarm(String alarmId) async {
    await _apiClient.post('alarms/$alarmId/acknowledge');
  }

  WebSocketChannel connectToAlarms() {
    return WebSocketChannel.connect(Uri.parse('${_endpointConfig.wsBaseUrl}/ws/alarms'));
  }
}
