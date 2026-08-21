import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

import '../../session/services/session_manager.dart';
import '../models/care_directory_model.dart';
import '../models/care_profile_model.dart';
import '../repositories/care_repository.dart';

enum CareLoadStatus { initial, loading, loaded, error }

class CareProvider extends ChangeNotifier {
  CareRepository _repository;
  SessionManager _sessionManager;

  CareLoadStatus _status = CareLoadStatus.initial;
  CareAccessProfile? _profile;
  CareDirectory? _familyDirectory;
  String? _errorMessage;
  Timer? _refreshTimer;
  bool _isFetching = false;
  bool _isMutating = false;

  CareProvider(this._repository, this._sessionManager);

  CareLoadStatus get status => _status;
  CareAccessProfile? get profile => _profile;
  CareDirectory? get familyDirectory => _familyDirectory;
  String? get errorMessage => _errorMessage;
  bool get isMutating => _isMutating;

  void updateDependencies(
      CareRepository repository, SessionManager sessionManager) {
    _repository = repository;
    _sessionManager = sessionManager;
  }

  Future<void> fetchProfile({bool silent = false}) async {
    if (_isFetching) return;
    _isFetching = true;

    final shouldShowLoading = !silent || _profile == null;
    if (shouldShowLoading) {
      _status = CareLoadStatus.loading;
      notifyListeners();
    }

    try {
      _profile = await _repository.getAccessProfile();
      final sessionUser = _sessionManager.user;
      if (sessionUser?.role == 'family' && sessionUser?.familyId != null) {
        final relatedElderIds = _profile?.relatedElderIds ?? const <String>[];
        if (!silent || _shouldRefreshFamilyDirectory(relatedElderIds)) {
          _familyDirectory =
              await _repository.getFamilyDirectory(sessionUser!.familyId!);
        }
      } else {
        _familyDirectory = null;
      }
      _errorMessage = null;
      _status = CareLoadStatus.loaded;
    } catch (_) {
      _errorMessage = '获取监护数据失败';
      if (_profile == null || !silent) {
        _status = CareLoadStatus.error;
      }
    } finally {
      _isFetching = false;
    }

    notifyListeners();
  }

  Future<bool> bindSelfDevice(
    String macAddress, {
    String? deviceName,
  }) async {
    if (_isMutating) return false;
    _isMutating = true;
    _errorMessage = null;
    notifyListeners();

    try {
      await _repository.bindSelfDevice(
        macAddress: macAddress,
        deviceName: deviceName,
      );
      await fetchProfile(silent: _profile != null);
      return true;
    } catch (error) {
      _errorMessage = _extractApiErrorMessage(error, '绑定手环失败，请稍后重试');
      return false;
    } finally {
      _isMutating = false;
      notifyListeners();
    }
  }

  Future<bool> unbindSelfDevice() async {
    if (_isMutating) return false;
    _isMutating = true;
    _errorMessage = null;
    notifyListeners();

    try {
      await _repository.unbindSelfDevice();
      await fetchProfile(silent: _profile != null);
      return true;
    } catch (error) {
      _errorMessage = _extractApiErrorMessage(error, '解绑设备失败，请稍后重试');
      return false;
    } finally {
      _isMutating = false;
      notifyListeners();
    }
  }

  void startAutoRefresh({Duration interval = const Duration(seconds: 1)}) {
    stopAutoRefresh();
    Future.microtask(() => fetchProfile(silent: _profile != null));
    _refreshTimer = Timer.periodic(interval, (_) {
      fetchProfile(silent: true);
    });
  }

  void stopAutoRefresh() {
    _refreshTimer?.cancel();
    _refreshTimer = null;
  }

  String _extractApiErrorMessage(Object error, String fallback) {
    if (error is DioException) {
      final responseData = error.response?.data;
      if (responseData is Map<String, dynamic>) {
        final detail = responseData['detail'];
        if (detail is String && detail.trim().isNotEmpty) {
          return _humanizeApiDetail(detail);
        }
        if (detail is Map<String, dynamic>) {
          final message = detail['message'];
          if (message is String && message.trim().isNotEmpty) {
            return _humanizeApiDetail(message);
          }
        }
        if (detail is List && detail.isNotEmpty) {
          final first = detail.first;
          if (first is Map<String, dynamic>) {
            final msg = first['msg'];
            if (msg is String) return _humanizeApiDetail(msg);
          }
        }
      }
      final message = error.message;
      if (message != null && message.trim().isNotEmpty) {
        return message;
      }
    }
    return fallback;
  }

  bool _shouldRefreshFamilyDirectory(List<String> relatedElderIds) {
    if (_familyDirectory == null) {
      return true;
    }

    final currentIds = _familyDirectory!.elders
        .map((elder) => elder.id.trim())
        .where((id) => id.isNotEmpty)
        .toList(growable: false)
      ..sort();
    final expectedIds = relatedElderIds
        .map((id) => id.trim())
        .where((id) => id.isNotEmpty)
        .toList(growable: false)
      ..sort();

    if (currentIds.length != expectedIds.length) {
      return true;
    }

    for (var index = 0; index < currentIds.length; index++) {
      if (currentIds[index] != expectedIds[index]) {
        return true;
      }
    }

    return false;
  }

  String _humanizeApiDetail(String detail) {
    final code = detail.toUpperCase();
    if (code.contains('INVALID_MAC_ADDRESS')) {
      return '手环 MAC 地址格式不正确，请使用 12 位十六进制数';
    }
    if (code.contains('DEVICE_ALREADY_BOUND_TO_TARGET')) {
      return '这只手环已经绑定到当前账号了';
    }
    if (code.contains('DEVICE_ALREADY_BOUND')) {
      return '这只手环已经绑定到其他账号了';
    }
    if (code.contains('TARGET_USER_ALREADY_HAS_DEVICE_OF_SAME_MODEL')) {
      return '当前账号已绑定同型号手环，请先解绑旧设备';
    }
    if (code.contains('NO_BOUND_SERIAL_DEVICE')) {
      return '当前账号还没有已绑定的真实手环';
    }
    if (code.contains('DEVICE_NOT_FOUND')) {
      return '未找到这只手环，请核对 MAC 地址是否输入正确';
    }
    if (code.contains('USER_NOT_FOUND')) {
      return '未找到关联的用户账号信息';
    }
    if (code.contains('INVALID_BIND_TARGET_ROLE')) {
      return '当前账号角色不支持绑定手环设备 (仅限老年版使用)';
    }
    if (code.contains('SELF_BIND_FOR_ELDER_ONLY')) {
      return '只有老人账号本人登录后才能进行手环绑定';
    }
    return detail;
  }

  @override
  void dispose() {
    stopAutoRefresh();
    super.dispose();
  }
}
