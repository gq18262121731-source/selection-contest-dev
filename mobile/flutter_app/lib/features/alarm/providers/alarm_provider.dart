import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/alarm_model.dart';
import '../repositories/alarm_repository.dart';

enum AlarmLoadStatus { initial, loading, loaded, error }

class AlarmProvider extends ChangeNotifier {
  final AlarmRepository _repository;

  AlarmLoadStatus _status = AlarmLoadStatus.initial;
  List<AlarmRecord> _alarms = [];
  List<AlarmQueueItem> _queue = [];
  List<MobilePushRecord> _pushes = [];
  String? _errorMessage;

  WebSocketChannel? _channel;
  StreamSubscription? _subscription;
  Timer? _reconnectTimer;
  int _reconnectAttempts = 0;
  bool _started = false;

  AlarmProvider(this._repository);

  AlarmLoadStatus get status => _status;
  List<AlarmRecord> get alarms => _alarms;
  List<AlarmQueueItem> get queue => _queue;
  List<MobilePushRecord> get pushes => _pushes;
  String? get errorMessage => _errorMessage;

  Future<void> ensureStarted() async {
    if (_started && _channel != null) {
      return;
    }
    await init();
  }

  Future<void> init() async {
    _started = true;
    _status = AlarmLoadStatus.loading;
    _errorMessage = null;
    notifyListeners();

    try {
      final results = await Future.wait([
        _repository.getAlarms(),
        _repository.getAlarmQueue(),
        _repository.getMobilePushes(),
      ]);

      _alarms = results[0] as List<AlarmRecord>;
      _queue = results[1] as List<AlarmQueueItem>;
      _pushes = results[2] as List<MobilePushRecord>;
      _sortAlarms();

      _status = AlarmLoadStatus.loaded;
      notifyListeners();

      _connectWebSocket();
    } catch (_) {
      _status = AlarmLoadStatus.error;
      _errorMessage = '获取告警信息失败';
      notifyListeners();
    }
  }

  void _connectWebSocket() {
    _closeWebSocket();
    try {
      _channel = _repository.connectToAlarms();
      _subscription = _channel!.stream.listen(
        _handleWsMessage,
        onError: (_) => _handleWsDisconnect(),
        onDone: () => _handleWsDisconnect(),
      );
      _reconnectAttempts = 0;
    } catch (_) {
      _handleWsDisconnect();
    }
  }

  void _handleWsMessage(dynamic message) {
    try {
      final data = jsonDecode(message as String);
      if (data is! Map<String, dynamic>) {
        return;
      }

      final msgType = data['type'] as String?;
      if (msgType == 'alarm_queue') {
        _reconcileActiveQueue(data['queue'] as List<dynamic>?);
        notifyListeners();
        return;
      }

      if (data.containsKey('id') && data.containsKey('alarm_type')) {
        final newAlarm = AlarmRecord.fromJson(data);
        final index = _alarms.indexWhere((a) => a.id == newAlarm.id);
        if (index != -1) {
          _alarms[index] = newAlarm;
        } else {
          _alarms.insert(0, newAlarm);
        }
        _sortAlarms();
        notifyListeners();
      }
    } catch (_) {}
  }

  void _reconcileActiveQueue(List<dynamic>? rawQueue) {
    if (rawQueue != null) {
      _queue = rawQueue
          .map((e) => AlarmQueueItem.fromJson(e as Map<String, dynamic>))
          .toList();
    }

    final queueAlarmById = <String, AlarmRecord>{
      for (final item in _queue) item.alarm.id: item.alarm,
    };

    _alarms = _alarms.map((alarm) {
      final queued = queueAlarmById[alarm.id];
      if (queued != null) {
        return queued;
      }
      if (!alarm.acknowledged) {
        return AlarmRecord(
          id: alarm.id,
          deviceMac: alarm.deviceMac,
          alarmType: alarm.alarmType,
          alarmLevel: alarm.alarmLevel,
          alarmPriority: alarm.alarmPriority,
          message: alarm.message,
          createdAt: alarm.createdAt,
          acknowledged: true,
          anomalyProbability: alarm.anomalyProbability,
        );
      }
      return alarm;
    }).toList();

    for (final queued in queueAlarmById.values) {
      final index = _alarms.indexWhere((alarm) => alarm.id == queued.id);
      if (index != -1) {
        _alarms[index] = queued;
      } else {
        _alarms.insert(0, queued);
      }
    }

    _sortAlarms();
  }

  void _sortAlarms() {
    _alarms.sort((a, b) {
      final aTime = a.createdAtDateTime ?? DateTime.fromMillisecondsSinceEpoch(0);
      final bTime = b.createdAtDateTime ?? DateTime.fromMillisecondsSinceEpoch(0);
      return bTime.compareTo(aTime);
    });
  }

  Future<void> acknowledge(String alarmId) async {
    final index = _alarms.indexWhere((a) => a.id == alarmId);
    bool previousAcknowledged = false;
    if (index != -1) {
      previousAcknowledged = _alarms[index].acknowledged;
      _alarms[index].acknowledged = true;
      notifyListeners();
    }
    try {
      await _repository.acknowledgeAlarm(alarmId);
    } catch (_) {
      if (index != -1) {
        _alarms[index].acknowledged = previousAcknowledged;
        notifyListeners();
      }
    }
  }

  void reset() {
    _started = false;
    _status = AlarmLoadStatus.initial;
    _alarms = [];
    _queue = [];
    _pushes = [];
    _errorMessage = null;
    _reconnectTimer?.cancel();
    _closeWebSocket();
    notifyListeners();
  }

  void reloadFromEndpointChange() {
    if (!_started) {
      return;
    }
    init();
  }

  void _handleWsDisconnect() {
    _reconnectTimer?.cancel();
    final delay = Duration(seconds: (1 << _reconnectAttempts).clamp(1, 30));
    _reconnectTimer = Timer(delay, () {
      _reconnectAttempts++;
      _connectWebSocket();
    });
  }

  void _closeWebSocket() {
    _subscription?.cancel();
    _channel?.sink.close();
  }

  @override
  void dispose() {
    _reconnectTimer?.cancel();
    _closeWebSocket();
    super.dispose();
  }
}
