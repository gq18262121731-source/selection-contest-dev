import 'package:flutter/material.dart';
import '../models/history_model.dart';
import '../repositories/health_repository.dart';

enum HistoryLoadStatus { initial, loading, loaded, error }

class HistoryProvider extends ChangeNotifier {
  final HealthRepository _repository;
  final String _deviceMac;

  HistoryLoadStatus _status = HistoryLoadStatus.initial;
  List<TrendPoint> _trends = [];
  DeviceHistoryResponse? _history;
  String? _errorMessage;
  String _currentWindow = 'day';

  HistoryProvider(this._repository, this._deviceMac);

  HistoryLoadStatus get status => _status;
  List<TrendPoint> get trends => _trends;
  DeviceHistoryResponse? get history => _history;
  String? get errorMessage => _errorMessage;
  String get currentWindow => _currentWindow;

  Future<void> fetchHistory({String? window}) async {
    if (window != null) _currentWindow = window;
    
    _status = HistoryLoadStatus.loading;
    notifyListeners();

    try {
      // 同时拉取趋势和聚合历史
      final results = await Future.wait([
        _repository.getTrend(_deviceMac),
        _repository.getHistory(_deviceMac, window: _currentWindow),
      ]);

      _trends = results[0] as List<TrendPoint>;
      _history = results[1] as DeviceHistoryResponse;
      _status = HistoryLoadStatus.loaded;
    } catch (e) {
      _status = HistoryLoadStatus.error;
      _errorMessage = '获取历史数据失败';
    }
    notifyListeners();
  }

  void setWindow(String window) {
    if (_currentWindow == window) return;
    fetchHistory(window: window);
  }
}
