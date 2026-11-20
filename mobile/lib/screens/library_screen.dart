// Biblioteca: buscar, filtrar (todos, guardados, míos), ver el detalle, descargar y subir.
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';

import '../core/api.dart';
import '../core/categories.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'shell.dart';

class LibraryScreen extends StatefulWidget {
  const LibraryScreen({super.key});

  @override
  State<LibraryScreen> createState() => _LibraryScreenState();
}

class _LibraryScreenState extends State<LibraryScreen> {
  final _q = TextEditingController();
  String _scope = 'all';
  List _docs = [];
  int _total = 0;
  bool _cargando = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    ShellController.libraryQuery.addListener(_desdeFuera);
    _cargar();
  }

  @override
  void dispose() {
    ShellController.libraryQuery.removeListener(_desdeFuera);
    super.dispose();
  }

  void _desdeFuera() {
    final q = ShellController.libraryQuery.value;
    if (q == null) return;
    _q.text = q;
    _scope = 'all';
    ShellController.libraryQuery.value = null;
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() => _cargando = true);
    try {
      final q = Uri.encodeQueryComponent(_q.text.trim());
      final r = await Api.instance.get('/api/resources?limit=100&scope=$_scope${q.isEmpty ? '' : '&q=$q'}') as Map;
      setState(() {
        _docs = r['resources'] as List;
        _total = r['total'] as int? ?? _docs.length;
        _error = null;
      });
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _cargando = false);
    }
  }

  Future<void> _subir() async {
    final hecho = await Navigator.push<bool>(context, MaterialPageRoute(builder: (_) => const UploadScreen()));
    if (hecho == true) _cargar();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Biblioteca')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _subir,
        icon: const Icon(Icons.upload_file),
        label: const Text('Subir'),
      ),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
          child: TextField(
            controller: _q,
            textInputAction: TextInputAction.search,
            onSubmitted: (_) => _cargar(),
            decoration: InputDecoration(
              prefixIcon: const Icon(Icons.search),
              hintText: 'Título, autor, etiqueta o tema',
              suffixIcon: _q.text.isEmpty
                  ? null
                  : IconButton(icon: const Icon(Icons.close), onPressed: () { _q.clear(); _cargar(); }),
            ),
          ),
        ),
        SizedBox(
          height: 40,
          child: ListView(scrollDirection: Axis.horizontal, padding: const EdgeInsets.symmetric(horizontal: 16), children: [
            for (final (k, l) in [('all', 'Todos'), ('saved', 'Guardados'), ('mine', 'Subidos por mí')])
              Padding(
                padding: const EdgeInsets.only(right: 8),
                child: ChoiceChip(
                  label: Text(l),
                  selected: _scope == k,
                  onSelected: (_) { setState(() => _scope = k); _cargar(); },
                ),
              ),
          ]),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(18, 6, 18, 4),
          child: Align(
            alignment: Alignment.centerLeft,
            child: Text('$_total ${_total == 1 ? 'documento' : 'documentos'}', style: const TextStyle(color: Ufg.ink3)),
          ),
        ),
        Expanded(
          child: RefreshIndicator(
            onRefresh: _cargar,
            child: _cargando
                ? const Center(child: CircularProgressIndicator())
                : _error != null
                    ? ListView(children: [EmptyState(icon: Icons.cloud_off, title: 'No se pudo cargar', text: _error)])
                    : _docs.isEmpty
                        ? ListView(children: const [
                            EmptyState(icon: Icons.search_off, title: 'Sin resultados',
                                text: 'Prueba con otras palabras o pregúntale a Francis: busca dentro del contenido.'),
                          ])
                        : ListView.separated(
                            padding: const EdgeInsets.fromLTRB(16, 4, 16, 96),
                            itemCount: _docs.length,
                            separatorBuilder: (_, _) => const SizedBox(height: 8),
                            itemBuilder: (_, i) => ResourceTile(resource: _docs[i] as Map, onChanged: _cargar),
                          ),
          ),
        ),
      ]),
    );
  }
}

class ResourceTile extends StatelessWidget {
  const ResourceTile({super.key, required this.resource, this.onChanged});
  final Map resource;
  final VoidCallback? onChanged;

  @override
  Widget build(BuildContext context) {
    final r = resource;
    final estado = r['scan_status'] as String? ?? 'clean';
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: () async {
          final cambio = await Navigator.push<bool>(
              context, MaterialPageRoute(builder: (_) => ResourceDetailScreen(id: r['id'] as int)));
          if (cambio == true) onChanged?.call();
        },
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(children: [
            FileIcon(r['extension'] as String?),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(r['title'] as String? ?? '', maxLines: 2, overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15.5)),
                const SizedBox(height: 3),
                Text('${r['author']} · ${r['category']}', maxLines: 1, overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: Ufg.ink3, fontSize: 13)),
                const SizedBox(height: 3),
                Row(children: [
                  const Icon(Icons.download_outlined, size: 14, color: Ufg.ink3),
                  Text(' ${r['downloads'] ?? 0}   ${timeAgo(r['created_at'] as String?)}',
                      style: const TextStyle(color: Ufg.ink3, fontSize: 12.5)),
                  if (estado != 'clean') ...[const SizedBox(width: 8), ScanChip(estado)],
                ]),
              ]),
            ),
            if (r['saved'] == true) const Icon(Icons.bookmark, color: Ufg.orange, size: 20),
          ]),
        ),
      ),
    );
  }
}

class ScanChip extends StatelessWidget {
  const ScanChip(this.estado, {super.key});
  final String estado;

  @override
  Widget build(BuildContext context) {
    final (texto, color) = switch (estado) {
      'pending' => ('En revisión', Ufg.blue),
      'review' => ('En cuarentena', Ufg.orange),
      'blocked' => ('Bloqueado', Ufg.danger),
      _ => ('Verificado', Ufg.green),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(99)),
      child: Text(texto, style: TextStyle(color: color, fontWeight: FontWeight.w700, fontSize: 11.5)),
    );
  }
}

// --- Detalle --------------------------------------------------------------------
class ResourceDetailScreen extends StatefulWidget {
  const ResourceDetailScreen({super.key, required this.id});
  final int id;

  @override
  State<ResourceDetailScreen> createState() => _ResourceDetailScreenState();
}

class _ResourceDetailScreenState extends State<ResourceDetailScreen> {
  Map? r;
  String? error;
  bool bajando = false;
  bool cambio = false;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    try {
      final d = await Api.instance.get('/api/resources/${widget.id}') as Map;
      setState(() => r = d['resource'] as Map);
    } on ApiException catch (e) {
      setState(() => error = e.message);
    }
  }

  Future<void> _abrir() async {
    setState(() => bajando = true);
    try {
      final archivo = await Api.instance.download('/api/resources/${widget.id}/file?download=1', r!['original_filename'] as String);
      final res = await OpenFilex.open(archivo.path);
      if (res.type != ResultType.done && mounted) {
        toast(context, 'Guardado en ${archivo.path}. No hay una app para abrir este formato.');
      }
    } on ApiException catch (e) {
      if (mounted) toast(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => bajando = false);
    }
  }

  Future<void> _guardar() async {
    try {
      final d = await Api.instance.post('/api/resources/${widget.id}/save') as Map;
      setState(() {
        r!['saved'] = d['saved'];
        cambio = true;
      });
      if (mounted) toast(context, d['saved'] == true ? 'Guardado en tus documentos' : 'Quitado de guardados');
    } on ApiException catch (e) {
      if (mounted) toast(context, e.message, error: true);
    }
  }

  Future<void> _reportar() async {
    const motivos = [
      ('malicious', 'Archivo peligroso o sospechoso'),
      ('inappropriate', 'Contenido inapropiado u ofensivo'),
      ('personal_data', 'Expone datos personales'),
      ('copyright', 'Derechos de autor (libro completo)'),
      ('spam', 'Spam o publicidad'),
      ('wrong', 'No es material de estudio'),
      ('other', 'Otro motivo'),
    ];
    String? elegido;
    final comentario = TextEditingController();
    final enviar = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, set) => Padding(
          padding: EdgeInsets.fromLTRB(20, 20, 20, MediaQuery.of(ctx).viewInsets.bottom + 20),
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Reportar documento', style: Theme.of(ctx).textTheme.titleLarge),
            const SizedBox(height: 4),
            const Text('Un administrador lo revisará; quien lo subió no sabrá quién lo reportó.', style: TextStyle(color: Ufg.ink3)),
            const SizedBox(height: 8),
            RadioGroup<String>(
              groupValue: elegido,
              onChanged: (v) => set(() => elegido = v),
              child: Column(children: [
                for (final (k, l) in motivos) RadioListTile<String>(value: k, title: Text(l), dense: true),
              ]),
            ),
            TextField(controller: comentario, maxLines: 2, decoration: const InputDecoration(hintText: 'Detalle (opcional)')),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: elegido == null ? null : () => Navigator.pop(ctx, true),
                child: const Text('Enviar reporte'),
              ),
            ),
          ]),
        ),
      ),
    );
    if (enviar != true || elegido == null) return;
    try {
      final d = await Api.instance.post('/api/reports',
          {'kind': 'public', 'resource_id': widget.id, 'reason': elegido, 'comment': comentario.text.trim()}) as Map;
      if (mounted) toast(context, d['message'] as String);
    } on ApiException catch (e) {
      if (mounted) toast(context, e.message, error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final tema = Theme.of(context);
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (hecho, _) { if (!hecho) Navigator.pop(context, cambio); },
      child: Scaffold(
        appBar: AppBar(actions: [
          if (r != null && r!['is_owner'] != true && r!['scan_status'] == 'clean')
            IconButton(tooltip: 'Reportar', onPressed: _reportar, icon: const Icon(Icons.flag_outlined)),
        ]),
        body: r == null
            ? (error != null
                ? EmptyState(icon: Icons.error_outline, title: 'No se pudo abrir', text: error)
                : const Center(child: CircularProgressIndicator()))
            : ListView(padding: const EdgeInsets.fromLTRB(18, 4, 18, 24), children: [
                Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  FileIcon(r!['extension'] as String?, size: 52),
                  const SizedBox(width: 14),
                  Expanded(child: Text(r!['title'] as String, style: tema.textTheme.titleLarge)),
                ]),
                const SizedBox(height: 16),
                Row(children: [
                  Expanded(
                    child: FilledButton.icon(
                      onPressed: bajando ? null : _abrir,
                      icon: bajando
                          ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                          : const Icon(Icons.open_in_new),
                      label: const Text('Abrir'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.outlined(
                    tooltip: 'Guardar',
                    onPressed: _guardar,
                    icon: Icon(r!['saved'] == true ? Icons.bookmark : Icons.bookmark_border,
                        color: r!['saved'] == true ? Ufg.orange : null),
                  ),
                ]),
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(minimumSize: const Size(0, 46), foregroundColor: Ufg.orange),
                  onPressed: () {
                    Navigator.pop(context, cambio);
                    ShellController.openFrancis(docKey: r!['doc_key'] as String, title: r!['title'] as String);
                  },
                  icon: const Icon(Icons.smart_toy_outlined),
                  label: const Text('Preguntar a Francis sobre este documento'),
                ),
                if (r!['scan_status'] != 'clean') ...[
                  const SizedBox(height: 14),
                  Row(children: [ScanChip(r!['scan_status'] as String), const SizedBox(width: 8),
                    const Expanded(child: Text('Sólo tú lo ves hasta que pase la revisión de seguridad.',
                        style: TextStyle(color: Ufg.ink3, fontSize: 13)))]),
                ],
                if ((r!['description'] as String? ?? '').isNotEmpty) ...[
                  const SizedBox(height: 16),
                  Text(r!['description'] as String, style: const TextStyle(fontSize: 15.5, height: 1.45)),
                ],
                const SizedBox(height: 18),
                _fila('Autor', r!['author']),
                _fila('Categoría', r!['category']),
                if ((r!['career'] as String? ?? '').isNotEmpty) _fila('Carrera', r!['career']),
                _fila('Subido por', r!['owner_name']),
                _fila('Fecha', timeAgo(r!['created_at'] as String?)),
                _fila('Archivo', '${r!['original_filename']} (${fileSize(r!['file_size'] as num?)})'),
                _fila('Descargas', '${r!['downloads']}'),
                if ((r!['tags'] as String? ?? '').isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Wrap(spacing: 6, runSpacing: 6, children: [
                    for (final t in (r!['tags'] as String).split(',').where((t) => t.trim().isNotEmpty))
                      Chip(label: Text(t.trim()), visualDensity: VisualDensity.compact),
                  ]),
                ],
              ]),
      ),
    );
  }

  Widget _fila(String k, Object? v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 5),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(width: 105, child: Text(k, style: const TextStyle(color: Ufg.ink3))),
          Expanded(child: Text('${v ?? ''}')),
        ]),
      );
}

// --- Subir ---------------------------------------------------------------------
class UploadScreen extends StatefulWidget {
  const UploadScreen({super.key});

  @override
  State<UploadScreen> createState() => _UploadScreenState();
}

class _UploadScreenState extends State<UploadScreen> {
  File? archivo;
  final titulo = TextEditingController();
  final autor = TextEditingController();
  final etiquetas = TextEditingController();
  final descripcion = TextEditingController();
  final categorias = [for (final a in areas) ...a.$2];
  String? categoria;
  bool enviando = false;
  String? error;

  Future<void> _elegir() async {
    final r = await FilePicker.pickFiles(type: FileType.custom, allowedExtensions: const [
      'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'md', 'csv', 'rtf', 'odt', 'odp', 'ods',
      'png', 'jpg', 'jpeg', 'gif', 'webp', 'zip', 'rar', '7z']);
    final ruta = r.isEmpty ? null : r.single.path;
    if (ruta == null) return;
    setState(() {
      archivo = File(ruta);
      if (titulo.text.isEmpty) {
        titulo.text = r.single.name.replaceAll(RegExp(r'\.[^.]+$'), '').replaceAll(RegExp(r'[-_]+'), ' ');
      }
    });
  }

  Future<void> _enviar() async {
    if (archivo == null || titulo.text.trim().isEmpty || autor.text.trim().isEmpty || categoria == null) {
      setState(() => error = 'Elige el archivo y completa título, autor y categoría.');
      return;
    }
    setState(() { enviando = true; error = null; });
    try {
      final d = await Api.instance.upload('/api/resources', archivo!, {
        'title': titulo.text.trim(), 'author': autor.text.trim(), 'category': categoria!,
        'tags': etiquetas.text.trim(), 'description': descripcion.text.trim(),
      }) as Map;
      if (!mounted) return;
      toast(context, d['message'] as String? ?? 'Documento recibido');
      Navigator.pop(context, true);
    } on ApiException catch (e) {
      setState(() => error = e.message);
    } finally {
      if (mounted) setState(() => enviando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Subir documento')),
      body: ListView(padding: const EdgeInsets.all(18), children: [
        const Text('Lo verá la comunidad UFG después de pasar la revisión de seguridad.', style: TextStyle(color: Ufg.ink3)),
        const SizedBox(height: 14),
        OutlinedButton.icon(
          style: OutlinedButton.styleFrom(minimumSize: const Size(0, 64)),
          onPressed: _elegir,
          icon: const Icon(Icons.attach_file),
          label: Text(archivo == null ? 'Elegir archivo' : archivo!.path.split(Platform.pathSeparator).last,
              overflow: TextOverflow.ellipsis),
        ),
        const SizedBox(height: 14),
        TextField(controller: titulo, decoration: const InputDecoration(labelText: 'Título')),
        const SizedBox(height: 12),
        TextField(controller: autor, decoration: const InputDecoration(labelText: 'Autor')),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          initialValue: categoria,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Categoría'),
          items: [for (final c in categorias) DropdownMenuItem(value: c, child: Text(c))],
          onChanged: (v) => setState(() => categoria = v),
        ),
        const SizedBox(height: 12),
        TextField(controller: etiquetas, decoration: const InputDecoration(labelText: 'Etiquetas', hintText: 'Separadas por comas')),
        const SizedBox(height: 12),
        TextField(controller: descripcion, maxLines: 3, decoration: const InputDecoration(labelText: 'Descripción')),
        if (error != null) ...[
          const SizedBox(height: 12),
          Text(error!, style: const TextStyle(color: Ufg.danger)),
        ],
        const SizedBox(height: 18),
        FilledButton(onPressed: enviando ? null : _enviar, child: Text(enviando ? 'Subiendo…' : 'Subir')),
      ]),
    );
  }
}
