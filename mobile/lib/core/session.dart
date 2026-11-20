// Estado de la sesión: quién entró y la preferencia de tema.
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';

class Session extends ChangeNotifier {
  Session._();
  static final Session instance = Session._();

  Map<String, dynamic>? user;
  bool ready = false;
  ThemeMode themeMode = ThemeMode.system;

  bool get loggedIn => user != null;
  String get firstName => (user?['name'] as String? ?? '').split(' ').first;

  Future<void> boot() async {
    await Api.instance.init();
    final prefs = await SharedPreferences.getInstance();
    themeMode = ThemeMode.values.byName(prefs.getString('theme') ?? 'system');
    Api.instance.onSessionLost = () {
      user = null;
      notifyListeners();
    };
    if (Api.instance.hasSession) {
      try {
        final data = await Api.instance.get('/api/me') as Map;
        user = Map<String, dynamic>.from(data['user'] as Map);
      } catch (_) {
        user = null;
      }
    }
    ready = true;
    notifyListeners();
  }

  void signedIn(Map data) {
    user = Map<String, dynamic>.from(data['user'] as Map);
    notifyListeners();
  }

  Future<void> logout() async {
    await Api.instance.logout();
    user = null;
    notifyListeners();
  }

  Future<void> setTheme(ThemeMode modo) async {
    themeMode = modo;
    notifyListeners();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('theme', modo.name);
  }
}
