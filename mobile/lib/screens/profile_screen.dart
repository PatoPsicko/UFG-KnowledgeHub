// Perfil: datos de la cuenta, tema, servidor y cerrar sesión.
import 'package:flutter/material.dart';

import '../core/api.dart';
import '../core/session.dart';
import '../theme.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final sesion = Session.instance;
    return ListenableBuilder(
      listenable: sesion,
      builder: (context, _) {
        final u = sesion.user ?? {};
        final nombre = u['name'] as String? ?? '';
        final iniciales = nombre.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).take(2).map((p) => p[0]).join().toUpperCase();
        Color color;
        try {
          color = Color(int.parse((u['profile_color'] as String? ?? '#0B6FCB').substring(1), radix: 16) | 0xFF000000);
        } catch (_) {
          color = Ufg.blue;
        }
        return Scaffold(
          appBar: AppBar(title: const Text('Mi perfil')),
          body: ListView(padding: const EdgeInsets.all(18), children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(children: [
                  CircleAvatar(radius: 40, backgroundColor: color,
                      child: Text(iniciales, style: const TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.w600))),
                  const SizedBox(height: 12),
                  Text(nombre, style: Theme.of(context).textTheme.titleLarge),
                  Text(u['career'] as String? ?? 'Carrera sin indicar', style: const TextStyle(color: Ufg.ink3)),
                  Text(u['email'] as String? ?? '', style: const TextStyle(color: Ufg.ink3)),
                ]),
              ),
            ),
            const SizedBox(height: 16),
            Text('Apariencia', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            SegmentedButton<ThemeMode>(
              segments: const [
                ButtonSegment(value: ThemeMode.system, label: Text('Sistema'), icon: Icon(Icons.brightness_auto)),
                ButtonSegment(value: ThemeMode.light, label: Text('Claro'), icon: Icon(Icons.light_mode)),
                ButtonSegment(value: ThemeMode.dark, label: Text('Oscuro'), icon: Icon(Icons.dark_mode)),
              ],
              selected: {sesion.themeMode},
              onSelectionChanged: (s) => sesion.setTheme(s.first),
            ),
            const SizedBox(height: 20),
            Card(
              child: Column(children: [
                ListTile(
                  leading: const Icon(Icons.dns_outlined),
                  title: const Text('Servidor'),
                  subtitle: Text(Api.instance.baseUrl),
                ),
                const Divider(height: 1),
                const ListTile(
                  leading: Icon(Icons.shield_outlined),
                  title: Text('Sesiones, verificación en dos pasos y privacidad'),
                  subtitle: Text('Se administran desde la web, en Mi perfil.'),
                ),
              ]),
            ),
            const SizedBox(height: 20),
            OutlinedButton.icon(
              style: OutlinedButton.styleFrom(minimumSize: const Size(0, 48), foregroundColor: Ufg.danger),
              onPressed: () async {
                final ok = await showDialog<bool>(
                  context: context,
                  builder: (ctx) => AlertDialog(
                    title: const Text('Cerrar sesión'),
                    content: const Text('Se cerrará la sesión en este teléfono.'),
                    actions: [
                      TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
                      FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Cerrar sesión')),
                    ],
                  ),
                );
                if (ok == true) await sesion.logout();
              },
              icon: const Icon(Icons.logout),
              label: const Text('Cerrar sesión'),
            ),
          ]),
        );
      },
    );
  }
}
