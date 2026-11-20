// Cliente de la API de UFG Knowledge Hub (el mismo backend Flask que usa la web).
//
// La app se identifica con la cabecera X-Client: mobile. Así el servidor le
// entrega el token de renovación en el cuerpo (la web lo recibe en una cookie)
// y la app lo guarda en el almacenamiento seguro del teléfono (Android Keystore).
// El token de acceso dura 30 minutos: cuando caduca se renueva solo y se repite
// la petición.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

class ApiException implements Exception {
  ApiException(this.message, {this.status = 0, this.code});
  final String message;
  final int status;
  final String? code;
  @override
  String toString() => message;
}

class Api {
  Api._();
  static final Api instance = Api._();

  /// Dirección del servidor. Se puede fijar al compilar con
  /// --dart-define=SERVER_URL=https://... o cambiar en la pantalla de acceso.
  static const _porDefecto = String.fromEnvironment('SERVER_URL', defaultValue: 'http://10.0.2.2:5001');

  final _seguro = const FlutterSecureStorage();
  final _http = http.Client();
  String baseUrl = _porDefecto;
  String? _token;
  String? _refresh;
  Completer<bool>? _renovando;

  /// Se llama cuando la sesión ya no se puede renovar (para volver al acceso).
  void Function()? onSessionLost;

  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    baseUrl = prefs.getString('server_url') ?? _porDefecto;
    _refresh = await _seguro.read(key: 'refresh_token');
  }

  bool get hasSession => _refresh != null;

  Future<void> setServer(String url) async {
    var limpio = url.trim();
    while (limpio.endsWith('/')) {
      limpio = limpio.substring(0, limpio.length - 1);
    }
    if (!limpio.startsWith('http')) limpio = 'https://$limpio';
    baseUrl = limpio;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('server_url', limpio);
  }

  Map<String, String> _headers({bool json = true}) => {
        'X-Client': 'mobile',
        'Accept': 'application/json',
        if (json) 'Content-Type': 'application/json',
        if (_token != null) 'Authorization': 'Bearer $_token',
      };

  Future<void> _saveTokens(Map data) async {
    _token = data['token'] as String?;
    final r = data['refresh_token'] as String?;
    if (r != null) {
      _refresh = r;
      await _seguro.write(key: 'refresh_token', value: r);
    }
  }

  Future<void> clearSession() async {
    _token = null;
    _refresh = null;
    await _seguro.delete(key: 'refresh_token');
  }

  /// Renueva el token de acceso. Varias peticiones a la vez esperan una sola renovación.
  Future<bool> refresh() async {
    if (_refresh == null) return false;
    if (_renovando != null) return _renovando!.future;
    final c = Completer<bool>();
    _renovando = c;
    try {
      final r = await _http
          .post(Uri.parse('$baseUrl/api/auth/refresh'),
              headers: {'X-Client': 'mobile', 'Content-Type': 'application/json'},
              body: jsonEncode({'refresh_token': _refresh}))
          .timeout(const Duration(seconds: 20));
      if (r.statusCode == 200) {
        await _saveTokens(jsonDecode(utf8.decode(r.bodyBytes)) as Map);
        c.complete(true);
      } else {
        if (r.statusCode == 401) {
          await clearSession();
          onSessionLost?.call();
        }
        c.complete(false);
      }
    } catch (_) {
      c.complete(false);
    } finally {
      _renovando = null;
    }
    return c.future;
  }

  Future<dynamic> _send(String method, String path, {Object? body, bool retry = true}) async {
    if (_token == null && _refresh != null && !path.startsWith('/api/login')) {
      await refresh();
    }
    final uri = Uri.parse('$baseUrl$path');
    http.Response r;
    try {
      final req = http.Request(method, uri)..headers.addAll(_headers());
      if (body != null) req.body = jsonEncode(body);
      r = await http.Response.fromStream(await _http.send(req).timeout(const Duration(seconds: 40)));
    } on SocketException {
      throw ApiException('No hay conexión con el servidor. Revisa tu internet o la dirección del servidor.');
    } on TimeoutException {
      throw ApiException('El servidor tardó demasiado en responder.');
    } on http.ClientException {
      throw ApiException('No se pudo conectar con el servidor.');
    }
    if (r.statusCode == 401 && retry && _refresh != null && !path.startsWith('/api/login')) {
      if (await refresh()) return _send(method, path, body: body, retry: false);
    }
    return _parse(r);
  }

  dynamic _parse(http.Response r) {
    dynamic data;
    try {
      data = r.bodyBytes.isEmpty ? {} : jsonDecode(utf8.decode(r.bodyBytes));
    } catch (_) {
      data = {'message': 'Respuesta inesperada del servidor (${r.statusCode}).'};
    }
    if (r.statusCode >= 400) {
      final m = data is Map ? data : {};
      throw ApiException((m['message'] ?? 'Error ${r.statusCode}').toString(),
          status: r.statusCode, code: m['code']?.toString());
    }
    return data;
  }

  Future<dynamic> get(String path) => _send('GET', path);
  Future<dynamic> post(String path, [Object? body]) => _send('POST', path, body: body ?? {});
  Future<dynamic> put(String path, [Object? body]) => _send('PUT', path, body: body ?? {});
  Future<dynamic> delete(String path) => _send('DELETE', path);

  // --- Sesión -----------------------------------------------------------------
  /// Devuelve el usuario, o un mapa con 'two_factor_required' y 'challenge'.
  Future<Map> login(String email, String password) async {
    final data = await post('/api/login', {'email': email, 'password': password}) as Map;
    if (data['token'] != null) await _saveTokens(data);
    return data;
  }

  Future<Map> loginTwoFactor(String challenge, String code) async {
    final data = await post('/api/login/2fa', {'challenge': challenge, 'code': code}) as Map;
    await _saveTokens(data);
    return data;
  }

  Future<void> logout() async {
    try {
      await _http.post(Uri.parse('$baseUrl/api/auth/logout'),
          headers: _headers(), body: jsonEncode({'refresh_token': _refresh})).timeout(const Duration(seconds: 10));
    } catch (_) {}
    await clearSession();
  }

  // --- Archivos ---------------------------------------------------------------
  /// Descarga un archivo protegido a la carpeta de la app y devuelve su ruta.
  Future<File> download(String path, String filename) async {
    Future<http.Response> pedir() => _http.get(Uri.parse('$baseUrl$path'), headers: _headers(json: false));
    var r = await pedir().timeout(const Duration(minutes: 2));
    if (r.statusCode == 401 && await refresh()) r = await pedir();
    if (r.statusCode >= 400) _parse(r);
    final carpeta = await getApplicationDocumentsDirectory();
    final destino = Directory('${carpeta.path}/descargas');
    await destino.create(recursive: true);
    final nombre = filename.replaceAll(RegExp(r'[\\/:*?"<>|]'), '_');
    final archivo = File('${destino.path}/$nombre');
    await archivo.writeAsBytes(r.bodyBytes);
    return archivo;
  }

  /// Sube un archivo con campos de formulario (multipart).
  Future<dynamic> upload(String path, File file, Map<String, String> fields) async {
    Future<http.StreamedResponse> enviar() async {
      final req = http.MultipartRequest('POST', Uri.parse('$baseUrl$path'))
        ..headers.addAll(_headers(json: false))
        ..fields.addAll(fields)
        ..files.add(await http.MultipartFile.fromPath('file', file.path));
      return _http.send(req).timeout(const Duration(minutes: 3));
    }

    var r = await http.Response.fromStream(await enviar());
    if (r.statusCode == 401 && await refresh()) r = await http.Response.fromStream(await enviar());
    return _parse(r);
  }

  /// POST con respuesta NDJSON (Francis responde mientras escribe).
  Stream<Map> stream(String path, Map body) async* {
    Future<http.StreamedResponse> enviar() {
      final req = http.Request('POST', Uri.parse('$baseUrl$path'))
        ..headers.addAll(_headers())
        ..body = jsonEncode(body);
      return _http.send(req);
    }

    if (_token == null) await refresh();
    var r = await enviar();
    if (r.statusCode == 401 && await refresh()) r = await enviar();
    if (r.statusCode >= 400) {
      _parse(await http.Response.fromStream(r));
      return;
    }
    var pendiente = '';
    await for (final trozo in r.stream.transform(utf8.decoder)) {
      pendiente += trozo;
      final lineas = pendiente.split('\n');
      pendiente = lineas.removeLast();
      for (final l in lineas) {
        if (l.trim().isNotEmpty) yield jsonDecode(l) as Map;
      }
    }
    if (pendiente.trim().isNotEmpty) yield jsonDecode(pendiente) as Map;
  }
}
