import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/health_model.dart';
import '../repositories/health_repository.dart';

enum HealthStatus { initial, loading, loaded, error }

class HealthProvider extends ChangeNotifier {
  final HealthRepository _repository;
  final String _deviceMac;

  HealthStatus _status = HealthStatus.initial;
  HealthData? _data;
  final List<HealthData> _historyBuffer = [];
  String? _errorMessage;
  bool _isWsConnected = false;
  bool _isInitializing = false;

  WebSocketChannel? _channel;
  StreamSubscription? _subscription;
  Timer? _reconnectTimer;
  Timer? _pollingTimer;
  int _reconnectAttempts = 0;

  HealthProvider(this._repository, this._deviceMac);

  HealthStatus get status => _status;
  HealthData? get data => _data;
  List<HealthData> get historyBuffer => _historyBuffer;
  String? get errorMessage => _errorMessage;
  bool get isWsConnected => _isWsConnected;

  Future<void> init() async {
    if (_isInitializing) return;
    _isInitializing = true;

    _reconnectTimer?.cancel();
    _pollingTimer?.cancel();
    _closeWebSocket();

    _status = HealthStatus.loading;
    _errorMessage = null;
    notifyListeners();

    try {
      HealthData? snapshot;
      List<HealthData> trend = const [];

      try {
        snapshot = await _repository.getRealtimeSnapshot(_deviceMac);
      } catch (_) {
        snapshot = null;
      }

      try {
        trend = await _repository.getRealtimeTrend(_deviceMac);
      } catch (_) {
        trend = const [];
      }

      if (snapshot == null && trend.isEmpty) {
        throw StateError('no realtime data');
      }

      _seedHistory(trend, snapshot: snapshot);
      _status = HealthStatus.loaded;
      notifyListeners();

      _connectWebSocket();
      _startPollingFallback();
    } catch (_) {
      _status = HealthStatus.error;
      _errorMessage = '无法获取实时数据';
      notifyListeners();
    } finally {
      _isInitializing = false;
    }
  }

  void _seedHistory(List<HealthData> trend, {HealthData? snapshot}) {
    final ordered = [...trend]
      ..sort((a, b) => a.timestamp.compareTo(b.timestamp));
    final merged = <HealthData>[];

    for (final sample in ordered) {
      final next = merged.isEmpty ? sample : merged.last.mergeWith(sample);
      _upsertHistoryPoint(merged, next);
    }

    if (snapshot != null) {
      final next = merged.isEmpty ? snapshot : merged.last.mergeWith(snapshot);
      _upsertHistoryPoint(merged, next);
    }

    if (merged.isEmpty) {
      _historyBuffer.clear();
      _data = snapshot;
      if (snapshot != null) {
        _historyBuffer.add(snapshot);
      }
      return;
    }

    final start = merged.length > 120 ? merged.length - 120 : 0;
    _historyBuffer
      ..clear()
      ..addAll(merged.sublist(start));
    _data = _historyBuffer.last;
  }

  void _upsertHistoryPoint(List<HealthData> target, HealthData sample) {
    if (target.isEmpty) {
      target.add(sample);
      return;
    }

    final existingIndex = target.indexWhere(
      (item) => item.timestamp.isAtSameMomentAs(sample.timestamp),
    );
    if (existingIndex != -1) {
      target[existingIndex] = sample;
      return;
    }

    target.add(sample);
    target.sort((a, b) => a.timestamp.compareTo(b.timestamp));
  }

  void _storeIncomingSample(HealthData incoming, {bool notify = true}) {
    final merged = _data == null ? incoming : _data!.mergeWith(incoming);
    _data = merged;
    _upsertHistoryPoint(_historyBuffer, merged);

    if (_historyBuffer.length > 120) {
      _historyBuffer.removeRange(0, _historyBuffer.length - 120);
    }

    if (_status != HealthStatus.loaded) {
      _status = HealthStatus.loaded;
    }

    if (notify) {
      notifyListeners();
    }
  }

  void _connectWebSocket() {
    _closeWebSocket();

    try {
      _channel = _repository.connectToRealtime(_deviceMac);
      _isWsConnected = true;
      _reconnectAttempts = 0;

      _subscription = _channel!.stream.listen(
        _handleWsMessage,
        onError: (_) => _handleWsDisconnect(),
        onDone: _handleWsDisconnect,
      );
    } catch (_) {
      _handleWsDisconnect();
    }

    notifyListeners();
  }

  Future<void> _pollSnapshot({bool includeTrend = false}) async {
    try {
      final snapshot = await _repository.getRealtimeSnapshot(_deviceMac);
      _storeIncomingSample(snapshot, notify: false);

      if (includeTrend) {
        final trend = await _repository.getRealtimeTrend(_deviceMac);
        _seedHistory(trend, snapshot: snapshot);
      }

      if (_status == HealthStatus.error) {
        _status = HealthStatus.loaded;
      }

      notifyListeners();
    } catch (_) {
      // Keep the last valid sample on screen when polling fails.
    }
  }

  void _startPollingFallback() {
    _pollingTimer?.cancel();
    _pollingTimer = Timer.periodic(const Duration(seconds: 2), (_) {
      unawaited(_pollSnapshot(
          includeTrend: _historyBuffer.length < 2 || !_isWsConnected));
    });
  }

  void _handleWsMessage(dynamic message) {
    try {
      final json = jsonDecode(message as String) as Map<String, dynamic>;
      final incoming = HealthData.fromJson(json);
      _storeIncomingSample(incoming);
    } catch (_) {
      // Ignore malformed packets and keep the last valid sample on screen.
    }
  }

  void _handleWsDisconnect() {
    _isWsConnected = false;
    notifyListeners();

    _reconnectTimer?.cancel();
    final delay = Duration(seconds: (1 << _reconnectAttempts).clamp(1, 30));
    _reconnectTimer = Timer(delay, () {
      _reconnectAttempts++;
      _connectWebSocket();
    });

    unawaited(_pollSnapshot(includeTrend: _historyBuffer.length < 2));
  }

  void _closeWebSocket() {
    _subscription?.cancel();
    _subscription = null;
    _channel?.sink.close();
    _channel = null;
    _isWsConnected = false;
  }

  @override
  void dispose() {
    _reconnectTimer?.cancel();
    _pollingTimer?.cancel();
    _closeWebSocket();
    super.dispose();
  }
}
