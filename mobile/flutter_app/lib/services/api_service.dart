import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/health_sample.dart';

class ApiService {
  ApiService({
    // Deprecated: use ServerEndpointConfig for dynamic IPs.
    this.apiBase = 'http://127.0.0.1:8000/api/v1',
    this.wsBase = 'ws://127.0.0.1:8000',
  });

  final String apiBase;
  final String wsBase;

  Future<List<String>> fetchDevices() async {
    final response = await http.get(Uri.parse('$apiBase/devices'));
    final List<dynamic> payload = jsonDecode(response.body) as List<dynamic>;
    return payload.map((item) => item['mac_address'] as String).toList();
  }

  Future<HealthSample> fetchRealtime(String mac) async {
    final response = await http.get(Uri.parse('$apiBase/health/realtime/$mac'));
    return HealthSample.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  WebSocketChannel connectRealtime(String mac) {
    return WebSocketChannel.connect(Uri.parse('$wsBase/ws/health/$mac'));
  }
}
