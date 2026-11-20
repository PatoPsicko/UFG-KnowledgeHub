// Inicio: saludo, búsqueda rápida y lo recién compartido.
import 'package:flutter/material.dart';

import '../core/api.dart';
import '../core/session.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'library_screen.dart';
import 'shell.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  List recientes = [];
  Map? stats;
  String? error;
  bool cargando = true;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    try {
      final r = await Future.wait([Api.instance.get('/api/resources?limit=8&sort=recent'), Api.instance.get('/api/user/stats')]);
      setState(() {
        recientes = (r[0] as Map)['resources'] as List;
        stats = r[1] as Map;
        error = null;
      });
    } on ApiException catch (e) {
      setState(() => error = e.message);
    } finally {
      if (mounted) setState(() => cargando = false);
    }
  }

  String get _saludo {
    final h = DateTime.now().hour;
    return h < 12 ? 'Buenos días' : h < 19 ? 'Buenas tardes' : 'Buenas noches';
  }

  @override
  Widget build(BuildContext context) {
    final tema = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _cargar,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(18, 16, 18, 24),
            children: [
              Row(children: [
                Image.asset('assets/logo_hub.png', height: 34),
                const Spacer(),
              ]),
              const SizedBox(height: 18),
              Text('$_saludo, ${Session.instance.firstName}', style: tema.textTheme.headlineSmall),
              const SizedBox(height: 4),
              const Text('Busca material de tus materias o pregúntale a Francis.', style: TextStyle(color: Ufg.ink3)),
              const SizedBox(height: 16),
              TextField(
                textInputAction: TextInputAction.search,
                onSubmitted: (q) => ShellController.openLibrary(query: q.trim()),
                decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: '¿Qué necesitas estudiar hoy?'),
              ),
              const SizedBox(height: 16),
              if (stats != null)
                Wrap(spacing: 18, runSpacing: 6, children: [
                  _dato('${stats!['library_size'] ?? 0}', 'documentos'),
                  _dato('${stats!['resources_count'] ?? 0}', 'aportes tuyos'),
                  _dato('${stats!['downloads_received'] ?? 0}', 'descargas de tus aportes'),
                ]),
              const SizedBox(height: 16),
              Card(
                color: Ufg.navy,
                child: ListTile(
                  contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  leading: Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(color: Ufg.orange, borderRadius: BorderRadius.circular(10)),
                    child: const Icon(Icons.smart_toy, color: Ufg.navy),
                  ),
                  title: const Text('Pregúntale a Francis', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700)),
                  subtitle: const Text('Responde citando los documentos de la biblioteca',
                      style: TextStyle(color: Color(0xFFB6C5D8))),
                  trailing: const Icon(Icons.chevron_right, color: Colors.white),
                  onTap: () => ShellController.openFrancis(),
                ),
              ),
              const SizedBox(height: 22),
              Row(children: [
                Text('Recién compartido', style: tema.textTheme.titleMedium),
                const Spacer(),
                TextButton(onPressed: () => ShellController.openLibrary(), child: const Text('Ver todo')),
              ]),
              if (cargando)
                const Padding(padding: EdgeInsets.all(32), child: Center(child: CircularProgressIndicator()))
              else if (error != null)
                EmptyState(icon: Icons.cloud_off, title: 'No se pudo cargar', text: error)
              else if (recientes.isEmpty)
                const EmptyState(icon: Icons.menu_book_outlined, title: 'Todavía no hay documentos')
              else
                ...recientes.map((r) => Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: ResourceTile(resource: r as Map, onChanged: _cargar),
                    )),
            ],
          ),
        ),
      ),
    );
  }

  Widget _dato(String n, String l) => Text.rich(TextSpan(children: [
        TextSpan(text: '$n ', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        TextSpan(text: l, style: const TextStyle(color: Ufg.ink3)),
      ]));
}
