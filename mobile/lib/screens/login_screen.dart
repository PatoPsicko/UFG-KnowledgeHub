// Acceso: correo @ufg.edu.sv, contraseña y, si la cuenta lo tiene, el código de dos pasos.
import 'package:flutter/material.dart';

import '../core/api.dart';
import '../core/session.dart';
import '../theme.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _email = TextEditingController();
  final _pass = TextEditingController();
  final _code = TextEditingController();
  String? _reto;
  String? _error;
  bool _cargando = false;
  bool _ver = false;

  Future<void> _entrar() async {
    setState(() {
      _cargando = true;
      _error = null;
    });
    try {
      if (_reto == null) {
        final r = await Api.instance.login(_email.text.trim(), _pass.text);
        if (r['two_factor_required'] == true) {
          setState(() => _reto = r['challenge'] as String);
        } else {
          Session.instance.signedIn(r);
        }
      } else {
        final r = await Api.instance.loginTwoFactor(_reto!, _code.text.trim());
        Session.instance.signedIn(r);
      }
    } on ApiException catch (e) {
      setState(() {
        _error = e.message;
        if (e.code == 'challenge_expired' || e.code == 'challenge_invalid') _reto = null;
      });
    } finally {
      if (mounted) setState(() => _cargando = false);
    }
  }

  Future<void> _servidor() async {
    final c = TextEditingController(text: Api.instance.baseUrl);
    final url = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Servidor'),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('El link que muestra iniciar.bat (por ejemplo https://tu-pc.tu-red.ts.net).'),
          const SizedBox(height: 12),
          TextField(controller: c, keyboardType: TextInputType.url, autocorrect: false),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancelar')),
          FilledButton(onPressed: () => Navigator.pop(ctx, c.text), child: const Text('Guardar')),
        ],
      ),
    );
    if (url != null && url.trim().isNotEmpty) {
      await Api.instance.setServer(url);
      setState(() {});
    }
  }

  @override
  Widget build(BuildContext context) {
    final tema = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(24, 28, 24, 24),
          children: [
            Align(alignment: Alignment.centerLeft, child: Image.asset('assets/logo_hub.png', height: 64)),
            const SizedBox(height: 28),
            Text(_reto == null ? 'Inicia sesión' : 'Verificación en dos pasos', style: tema.textTheme.headlineMedium),
            const SizedBox(height: 6),
            Text(
              _reto == null
                  ? 'Apuntes, guías y proyectos de toda la UFG, en un solo lugar.'
                  : 'Escribe el código de 6 dígitos de tu app de verificación (o un código de respaldo).',
              style: const TextStyle(color: Ufg.ink3, fontSize: 16),
            ),
            const SizedBox(height: 26),
            if (_reto == null) ...[
              TextField(
                controller: _email,
                keyboardType: TextInputType.emailAddress,
                autofillHints: const [AutofillHints.email],
                autocorrect: false,
                decoration: const InputDecoration(labelText: 'Correo', hintText: 'tu.nombre@ufg.edu.sv'),
              ),
              const SizedBox(height: 14),
              TextField(
                controller: _pass,
                obscureText: !_ver,
                autofillHints: const [AutofillHints.password],
                onSubmitted: (_) => _entrar(),
                decoration: InputDecoration(
                  labelText: 'Contraseña',
                  suffixIcon: IconButton(
                    icon: Icon(_ver ? Icons.visibility_off_outlined : Icons.visibility_outlined),
                    onPressed: () => setState(() => _ver = !_ver),
                  ),
                ),
              ),
            ] else
              TextField(
                controller: _code,
                keyboardType: TextInputType.number,
                autofocus: true,
                onSubmitted: (_) => _entrar(),
                decoration: const InputDecoration(labelText: 'Código'),
              ),
            if (_error != null) ...[
              const SizedBox(height: 14),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(color: Ufg.danger.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(10)),
                child: Row(children: [
                  const Icon(Icons.error_outline, color: Ufg.danger, size: 20),
                  const SizedBox(width: 8),
                  Expanded(child: Text(_error!, style: const TextStyle(color: Ufg.danger))),
                ]),
              ),
            ],
            const SizedBox(height: 22),
            FilledButton(
              onPressed: _cargando ? null : _entrar,
              child: _cargando
                  ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white))
                  : Text(_reto == null ? 'Entrar' : 'Verificar'),
            ),
            if (_reto != null)
              TextButton(onPressed: () => setState(() => _reto = null), child: const Text('Volver')),
            const SizedBox(height: 28),
            Center(
              child: TextButton.icon(
                onPressed: _servidor,
                icon: const Icon(Icons.dns_outlined, size: 18),
                label: Text('Servidor: ${Api.instance.baseUrl}', overflow: TextOverflow.ellipsis),
              ),
            ),
            const Center(
              child: Text('¿No tienes cuenta? Créala en la web con tu correo @ufg.edu.sv.',
                  style: TextStyle(color: Ufg.ink3, fontSize: 13), textAlign: TextAlign.center),
            ),
          ],
        ),
      ),
    );
  }
}
