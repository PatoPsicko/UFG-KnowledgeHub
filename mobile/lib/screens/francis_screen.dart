// Francis, el asistente de estudio: responde mientras escribe, cita los documentos
// con [1], [2] y puede limitarse a un documento («Preguntar sobre este documento»).
import 'package:flutter/material.dart';

import '../core/api.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'library_screen.dart';

class DocScope {
  const DocScope(this.key, this.title);
  final String key;
  final String title;
}

class FrancisController {
  static final scope = ValueNotifier<DocScope?>(null);
}

class _Turno {
  _Turno(this.role, this.text, {this.pending = false});
  final String role;
  String text;
  bool pending;
  bool error = false;
  List sources = [];
  List documents = [];
}

class FrancisScreen extends StatefulWidget {
  const FrancisScreen({super.key});

  @override
  State<FrancisScreen> createState() => _FrancisScreenState();
}

class _FrancisScreenState extends State<FrancisScreen> {
  final _input = TextEditingController();
  final _scroll = ScrollController();
  final List<_Turno> _turnos = [];
  String? _conversacion;
  String? _modelo;
  bool _enviando = false;

  static const _sugerencias = [
    '¿Qué material hay sobre bases de datos?',
    'Explícame la tercera forma normal con un ejemplo',
    'Hazme 3 preguntas de repaso de cálculo',
  ];

  @override
  void initState() {
    super.initState();
    FrancisController.scope.addListener(_nuevoAlcance);
    Api.instance.get('/api/ai/status').then((d) {
      if (mounted) setState(() => _modelo = (d as Map)['available'] == true ? '${d['provider_label'] ?? d['provider']}: ${d['model']}' : null);
    }).catchError((_) {});
  }

  @override
  void dispose() {
    FrancisController.scope.removeListener(_nuevoAlcance);
    super.dispose();
  }

  void _nuevoAlcance() => _reiniciar();

  void _reiniciar() => setState(() {
        _turnos.clear();
        _conversacion = null;
      });

  void _abajo() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(_scroll.position.maxScrollExtent, duration: const Duration(milliseconds: 200), curve: Curves.easeOut);
      }
    });
  }

  Future<void> _preguntar(String pregunta) async {
    pregunta = pregunta.trim();
    if (pregunta.isEmpty || _enviando) return;
    _input.clear();
    final turno = _Turno('assistant', '', pending: true);
    setState(() {
      _turnos.add(_Turno('user', pregunta));
      _turnos.add(turno);
      _enviando = true;
    });
    _abajo();
    try {
      await for (final ev in Api.instance.stream('/api/ai/chat/stream', {
        'question': pregunta,
        'conversation_id': _conversacion,
        'doc_key': FrancisController.scope.value?.key,
      })) {
        switch (ev['type']) {
          case 'token':
            setState(() => turno.text += ev['content'] as String? ?? '');
            _abajo();
          case 'queue':
            setState(() => turno.text = turno.text.isEmpty ? '⏳ Hay mucha gente preguntando; te respondo en unos segundos…' : turno.text);
          case 'done':
            setState(() {
              turno.pending = false;
              turno.sources = ev['sources'] as List? ?? [];
              turno.documents = ev['documents'] as List? ?? [];
              _conversacion = ev['conversation_id'] as String? ?? _conversacion;
              if (turno.text.startsWith('⏳')) turno.text = turno.text.replaceFirst(RegExp(r'^⏳[^\n]*…'), '').trimLeft();
            });
          case 'error':
            setState(() {
              turno.pending = false;
              turno.error = true;
              turno.text = ev['message'] as String? ?? 'Algo salió mal.';
            });
        }
      }
    } on ApiException catch (e) {
      setState(() {
        turno.error = true;
        turno.text = e.message;
      });
    } catch (_) {
      setState(() {
        turno.error = true;
        turno.text = 'Se cortó la conexión mientras llegaba la respuesta.';
      });
    } finally {
      setState(() {
        turno.pending = false;
        _enviando = false;
      });
      _abajo();
    }
  }

  void _verFuente(Map f) {
    showModalBottomSheet(
      context: context,
      builder: (ctx) => Padding(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 28),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(f['title'] as String? ?? '', style: Theme.of(ctx).textTheme.titleMedium),
          Text('${f['origin'] ?? ''}${f['page'] != null ? ', página ${f['page']}' : ''}', style: const TextStyle(color: Ufg.ink3)),
          if (f['snippet'] != null) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.only(left: 12),
              decoration: const BoxDecoration(border: Border(left: BorderSide(color: Ufg.orange, width: 3))),
              child: Text(f['snippet'] as String),
            ),
          ],
          if (f['type'] == 'public') ...[
            const SizedBox(height: 16),
            FilledButton(
              onPressed: () {
                Navigator.pop(ctx);
                Navigator.push(context, MaterialPageRoute(builder: (_) => ResourceDetailScreen(id: f['resource_id'] as int)));
              },
              child: const Text('Abrir documento'),
            ),
          ],
        ]),
      ),
    );
  }

  Widget _burbuja(_Turno t) {
    if (t.role == 'user') {
      return Align(
        alignment: Alignment.centerRight,
        child: Container(
          margin: const EdgeInsets.only(left: 48, bottom: 12),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: const BoxDecoration(
            color: Ufg.blue,
            borderRadius: BorderRadius.only(
                topLeft: Radius.circular(16), topRight: Radius.circular(16),
                bottomLeft: Radius.circular(16), bottomRight: Radius.circular(4)),
          ),
          child: Text(t.text, style: const TextStyle(color: Colors.white, fontSize: 15.5)),
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.only(bottom: 16, right: 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (t.pending && t.text.isEmpty)
          const Padding(padding: EdgeInsets.all(6), child: SizedBox(width: 26, height: 26, child: CircularProgressIndicator(strokeWidth: 2.5)))
        else if (t.error)
          Text(t.text, style: const TextStyle(color: Color(0xFFFFB4AA)))
        else
          MarkdownText(t.text, color: Colors.white, onCite: (n) {
            final f = t.sources.cast<Map>().where((s) => s['n'] == n).firstOrNull;
            if (f != null) _verFuente(f);
          }),
        if (t.sources.isNotEmpty || t.documents.isNotEmpty) ...[
          const SizedBox(height: 8),
          const Text('Fuentes', style: TextStyle(color: Color(0xFF8EA3BD), fontSize: 12.5)),
          const SizedBox(height: 4),
          for (final f in [...t.sources, ...t.documents].cast<Map>())
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Material(
                color: Colors.white.withValues(alpha: 0.06),
                borderRadius: BorderRadius.circular(8),
                child: ListTile(
                  dense: true,
                  onTap: () => _verFuente(f),
                  leading: Text(f['n'] != null ? '${f['n']}' : '•',
                      style: const TextStyle(color: Ufg.orange, fontWeight: FontWeight.w700, fontSize: 15)),
                  title: Text(f['title'] as String? ?? '', maxLines: 1, overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
                  subtitle: Text('${f['origin'] ?? ''}${f['page'] != null ? ', pág. ${f['page']}' : ''}',
                      style: const TextStyle(color: Color(0xFF8EA3BD))),
                  trailing: const Icon(Icons.chevron_right, color: Color(0xFF8EA3BD)),
                ),
              ),
            ),
        ],
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    final alcance = FrancisController.scope.value;
    return Scaffold(
      backgroundColor: Ufg.navy,
      appBar: AppBar(
        backgroundColor: Ufg.navy,
        foregroundColor: Colors.white,
        titleSpacing: 12,
        title: Row(children: [
          Container(
            padding: const EdgeInsets.all(7),
            decoration: BoxDecoration(color: Ufg.orange, borderRadius: BorderRadius.circular(10)),
            child: const Icon(Icons.smart_toy, color: Ufg.navy, size: 22),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('Francis', style: TextStyle(color: Colors.white, fontSize: 19)),
              Text(_modelo ?? 'Asistente de estudio', style: const TextStyle(color: Color(0xFF9FB3CC), fontSize: 12.5)),
            ]),
          ),
        ]),
        actions: [IconButton(tooltip: 'Nueva conversación', onPressed: _reiniciar, icon: const Icon(Icons.add))],
      ),
      body: SafeArea(
        child: Column(children: [
          if (alcance != null)
            Container(
              margin: const EdgeInsets.fromLTRB(14, 4, 14, 0),
              padding: const EdgeInsets.fromLTRB(12, 4, 4, 4),
              decoration: BoxDecoration(color: Ufg.orange.withValues(alpha: 0.16), borderRadius: BorderRadius.circular(10)),
              child: Row(children: [
                const Icon(Icons.description_outlined, color: Color(0xFFFFD9A8), size: 18),
                const SizedBox(width: 8),
                Expanded(child: Text('Preguntando sobre «${alcance.title}»', style: const TextStyle(color: Color(0xFFFFD9A8)))),
                IconButton(
                  onPressed: () => FrancisController.scope.value = null,
                  icon: const Icon(Icons.close, color: Color(0xFFFFD9A8), size: 18),
                ),
              ]),
            ),
          Expanded(
            child: _turnos.isEmpty
                ? ListView(padding: const EdgeInsets.all(20), children: [
                    Text(alcance == null ? 'Pregúntale a la biblioteca' : 'Pregunta lo que quieras sobre este documento',
                        style: Theme.of(context).textTheme.titleLarge?.copyWith(color: Colors.white)),
                    const SizedBox(height: 8),
                    const Text('Busco en los documentos que puedes ver y te respondo citando de dónde sale cada dato. '
                        'Sólo hablo de temas de estudio 📚',
                        style: TextStyle(color: Color(0xFFB6C5D8), fontSize: 15)),
                    const SizedBox(height: 20),
                    if (alcance == null)
                      Wrap(spacing: 8, runSpacing: 8, children: [
                        for (final s in _sugerencias)
                          ActionChip(
                            label: Text(s),
                            labelStyle: const TextStyle(color: Color(0xFFC7D4E4)),
                            backgroundColor: Colors.transparent,
                            side: const BorderSide(color: Color(0x33FFFFFF)),
                            onPressed: () => _preguntar(s),
                          ),
                      ]),
                  ])
                : ListView.builder(
                    controller: _scroll,
                    padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                    itemCount: _turnos.length,
                    itemBuilder: (_, i) => _burbuja(_turnos[i]),
                  ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 6, 12, 10),
            child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
              Expanded(
                child: TextField(
                  controller: _input,
                  minLines: 1,
                  maxLines: 5,
                  textInputAction: TextInputAction.send,
                  onSubmitted: _preguntar,
                  style: const TextStyle(color: Colors.white),
                  decoration: InputDecoration(
                    hintText: 'Pregunta sobre tus materias…',
                    hintStyle: const TextStyle(color: Color(0xFF8EA3BD)),
                    fillColor: Colors.white.withValues(alpha: 0.07),
                    enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: Color(0x24FFFFFF))),
                    focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: Ufg.orange)),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              IconButton.filled(
                style: IconButton.styleFrom(backgroundColor: Ufg.orange, foregroundColor: Ufg.navy, minimumSize: const Size(50, 50)),
                onPressed: _enviando ? null : () => _preguntar(_input.text),
                icon: const Icon(Icons.send),
              ),
            ]),
          ),
        ]),
      ),
    );
  }
}
