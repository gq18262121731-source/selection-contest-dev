import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/user_model.dart';

class SessionManager {
  static const _keyToken = 'auth_token';
  static const _keyUser = 'session_user';

  final SharedPreferences _prefs;

  SessionManager(this._prefs);

  String? get token => _prefs.getString(_keyToken);
  
  SessionUser? get user {
    final userStr = _prefs.getString(_keyUser);
    if (userStr == null) return null;
    try {
      return SessionUser.fromJson(jsonDecode(userStr));
    } catch (_) {
      return null;
    }
  }

  Future<void> saveSession(String token, SessionUser user) async {
    await _prefs.setString(_keyToken, token);
    await _prefs.setString(_keyUser, jsonEncode(user.toJson()));
  }

  Future<void> clearSession() async {
    await _prefs.remove(_keyToken);
    await _prefs.remove(_keyUser);
  }

  bool get isAuthenticated => token != null && user != null;
}
