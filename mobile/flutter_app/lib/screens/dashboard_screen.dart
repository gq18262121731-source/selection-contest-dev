import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/health_sample.dart';
import '../services/api_service.dart';
import '../widgets/vital_card.dart';
import '../widgets/logout_action.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key, required this.role});

  final String role;

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final ApiService _apiService = ApiService();
  HealthSample? _sample;
  WebSocketChannel? _channel;
  StreamSubscription? _subscription;
  String _selectedMac = '';

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    final devices = await _apiService.fetchDevices();
    if (devices.isEmpty) return;
    _selectedMac = devices.first;
    final sample = await _apiService.fetchRealtime(_selectedMac);
    _connectSocket(_selectedMac);
    setState(() => _sample = sample);
  }

  void _connectSocket(String mac) {
    _channel?.sink.close();
    _subscription?.cancel();
    _channel = _apiService.connectRealtime(mac);
    _subscription = _channel!.stream.listen((event) {
      final payload = jsonDecode(event as String) as Map<String, dynamic>;
      setState(() => _sample = HealthSample.fromJson(payload));
    });
  }

  @override
  void dispose() {
    _subscription?.cancel();
    _channel?.sink.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final sample = _sample;
    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        foregroundColor: Colors.white,
        title: Text('AIoT ${widget.role}监护端'),
        actions: const [LogoutAction()],
      ),
      body: sample == null
          ? const Center(child: CircularProgressIndicator())
          : Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(sample.deviceMac, style: const TextStyle(color: Color(0xFF64748B))),
                  const SizedBox(height: 18),
                  GridView.count(
                    shrinkWrap: true,
                    crossAxisCount: 2,
                    mainAxisSpacing: 12,
                    crossAxisSpacing: 12,
                    childAspectRatio: 1.35,
                    children: [
                      VitalCard(label: '心率', value: '${sample.heartRate} bpm', accent: const Color(0xFF2563EB)),
                      VitalCard(label: '体温', value: '${sample.temperature.toStringAsFixed(1)} ℃', accent: const Color(0xFF60C9A9)),
                      VitalCard(label: '血氧', value: '${sample.bloodOxygen} %', accent: const Color(0xFF82D7F7)),
                      VitalCard(label: '血压', value: sample.bloodPressure, accent: const Color(0xFFF6D36B)),
                    ],
                  ),
                  const SizedBox(height: 20),
                  Container(
                    padding: const EdgeInsets.all(18),
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(20),
                      color: sample.sosFlag ? const Color(0xFF5E1E17) : const Color(0xFF122A31),
                    ),
                    child: Row(
                      children: [
                        Icon(sample.sosFlag ? Icons.sos : Icons.favorite, color: const Color(0xFF0F172A)),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            sample.sosFlag ? 'SOS 已触发，请立即联系现场人员。' : '设备运行正常，正在持续接收实时数据。',
                            style: const TextStyle(color: Color(0xFF0F172A), fontSize: 16),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
    );
  }
}
