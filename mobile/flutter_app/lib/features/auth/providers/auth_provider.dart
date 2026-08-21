import 'package:flutter/material.dart';
import '../../session/models/user_model.dart';
import '../../session/services/session_manager.dart';
import '../models/register_models.dart';
import '../repositories/auth_repository.dart';

export '../models/register_models.dart';

enum AuthStatus { initial, authenticating, authenticated, unauthenticated, error }
enum RegisterStatus { idle, submitting, success, error }

class AuthProvider extends ChangeNotifier {
  final AuthRepository _repository;
  final SessionManager _sessionManager;

  AuthStatus _status = AuthStatus.initial;
  RegisterStatus _registerStatus = RegisterStatus.idle;
  SessionUser? _user;
  String? _errorMessage;
  String? _registerError;
  RegisterResponse? _lastRegistered;

  AuthProvider(this._repository, this._sessionManager);

  AuthStatus get status => _status;
  RegisterStatus get registerStatus => _registerStatus;
  SessionUser? get user => _user;
  String? get errorMessage => _errorMessage;
  String? get registerError => _registerError;
  RegisterResponse? get lastRegistered => _lastRegistered;

  Future<void> checkSession() async {
    if (!_sessionManager.isAuthenticated) {
      _status = AuthStatus.unauthenticated;
      notifyListeners();
      return;
    }

    try {
      _user = await _repository.getMe();
      _status = AuthStatus.authenticated;
    } catch (e) {
      _status = AuthStatus.unauthenticated;
      await _sessionManager.clearSession();
    }
    notifyListeners();
  }

  Future<void> login(String username, String password) async {
    _status = AuthStatus.authenticating;
    _errorMessage = null;
    notifyListeners();

    try {
      final response = await _repository.login(username, password);
      await _sessionManager.saveSession(response.token, response.user);
      _user = response.user;
      _status = AuthStatus.authenticated;
    } catch (e) {
      _status = AuthStatus.error;
      _errorMessage = '登录失败，请检查账号密码';
    }
    notifyListeners();
  }

  Future<void> logout() async {
    await _sessionManager.clearSession();
    _user = null;
    _status = AuthStatus.unauthenticated;
    notifyListeners();
  }

  void handleUnauthorized() {
    _user = null;
    _status = AuthStatus.unauthenticated;
    notifyListeners();
  }

  void resetRegisterState() {
    _registerStatus = RegisterStatus.idle;
    _registerError = null;
    _lastRegistered = null;
    notifyListeners();
  }

  Future<bool> registerElder(ElderRegisterRequest request) async {
    return _doRegister(() => _repository.registerElder(request));
  }

  Future<bool> registerFamily(FamilyRegisterRequest request) async {
    return _doRegister(() => _repository.registerFamily(request));
  }

  Future<bool> registerCommunity(CommunityRegisterRequest request) async {
    return _doRegister(() => _repository.registerCommunity(request));
  }

  Future<bool> _doRegister(Future<RegisterResponse> Function() call) async {
    _registerStatus = RegisterStatus.submitting;
    _registerError = null;
    notifyListeners();
    try {
      _lastRegistered = await call();
      _registerStatus = RegisterStatus.success;
      notifyListeners();
      return true;
    } catch (e) {
      _registerStatus = RegisterStatus.error;
      _registerError = _humanizeRegisterError(e.toString());
      notifyListeners();
      return false;
    }
  }

  static String _humanizeRegisterError(String raw) {
    if (raw.contains('PHONE_ALREADY_EXISTS')) return '该手机号已被注册，请更换手机号。';
    if (raw.contains('LOGIN_USERNAME_ALREADY_EXISTS')) return '该账号名已被占用，请更换账号名。';
    if (raw.contains('409')) return '该账号信息已存在，请检查手机号或账号名。';
    if (raw.contains('SocketException') || raw.contains('Connection')) return '无法连接到服务器，请检查网络后重试。';
    return '注册失败，请稍后重试。';
  }
}
