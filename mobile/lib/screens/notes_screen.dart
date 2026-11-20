// Mi espacio: notas tipo post-it y archivos personales (sólo los ve su dueño).
import 'package:file_picker/file_picker.dart';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';

import '../core/api.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'shell.dart';

const _colores = [Color(0xFFFFF4B8), Color(0xFFFFE0C2), Color(0xFFD9F0FF), Color(0xFFDFF5DD)];

class NotesScreen extends StatefulWidget {
  const NotesScreen({super.key});

  @override
  State<NotesScreen> createState() => _NotesScreenState();
}

class _NotesScreenState extends State<NotesScreen> {
  List _items = [];
  bool _cargando = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    try {
      final d = await Api.instance.get('/api/private-resources') as Map;
      setState(() {
        _items = d['resources'] as List;
        _error = null;
      });
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _cargando = false);
    }
  }

  Future<void> _editar([Map? nota]) async {
    final titulo = TextEditingController(text: nota?['title'] as String? ?? '');
    final contenido = TextEditingController(text: nota?['content'] as String? ?? '');
    final accion = await Navigator.push<String>(context, MaterialPageRoute(builder: (ctx) => Scaffold(
      backgroundColor: const Color(0xFFFFF4B8),
      appBar: AppBar(
        backgroundColor: const Color(0xFFFFF4B8),
        foregroundColor: const Color(0xFF2B2412),
        actions: [
          if (nota != null) ...[
            IconButton(tooltip: 'Preguntar a Francis', icon: const Icon(Icons.smart_toy_outlined), onPressed: () => Navigator.pop(ctx, 'ask')),
            IconButton(tooltip: 'Eliminar', icon: const Icon(Icons.delete_outline), onPressed: () => Navigator.pop(ctx, 'delete')),
          ],
          TextButton(onPressed: () => Navigator.pop(ctx, 'save'), child: const Text('Guardar')),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
        child: Column(children: [
          TextField(
            controller: titulo,
            style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700, color: Color(0xFF2B2412)),
            decoration: const InputDecoration(hintText: 'Título', border: InputBorder.none, filled: false),
          ),
          Expanded(
            child: TextField(
              controller: contenido,
              autofocus: nota == null,
              maxLines: null,
              expands: true,
              style: const TextStyle(fontSize: 16, height: 1.55, color: Color(0xFF2B2412)),
              decoration: const InputDecoration(
                  hintText: 'Escribe aquí tus ideas, resúmenes o pendientes…', border: InputBorder.none, filled: false),
            ),
          ),
        ]),
      ),
    )));
    if (!mounted || accion == null) return;
    try {
      if (accion == 'save') {
        final datos = {'title': titulo.text.trim().isEmpty ? 'Nota sin título' : titulo.text.trim(), 'content': contenido.text};
        if (nota == null) {
          await Api.instance.post('/api/private-resources', datos);
        } else {
          await Api.instance.put('/api/private-resources/${nota['id']}', datos);
        }
        if (mounted) toast(context, 'Nota guardada');
      } else if (accion == 'delete') {
        await Api.instance.delete('/api/private-resources/${nota!['id']}');
        if (mounted) toast(context, 'Nota eliminada');
      } else if (accion == 'ask') {
        ShellController.openFrancis(docKey: nota!['doc_key'] as String, title: nota['title'] as String);
      }
      _cargar();
    } on ApiException catch (e) {
      if (mounted) toast(context, e.message, error: true);
    }
  }

  Future<void> _subir() async {
    final r = await FilePicker.pickFiles();
    final ruta = r.isEmpty ? null : r.single.path;
    if (ruta == null) return;
    try {
      await Api.instance.upload('/api/private-resources', File(ruta), {'title': r.single.name});
      if (mounted) toast(context, 'Archivo guardado');
      _cargar();
    } on ApiException catch (e) {
      if (mounted) toast(context, e.message, error: true);
    }
  }

  Future<void> _abrir(Map f) async {
    try {
      final archivo = await Api.instance.download(f['download_url'] as String, f['original_filename'] as String);
      await OpenFilex.open(archivo.path);
    } on ApiException catch (e) {
      if (mounted) toast(context, e.message, error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final notas = _items.where((i) => i['type'] == 'note').toList();
    final archivos = _items.where((i) => i['type'] == 'file').toList();
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Mi espacio'),
          bottom: const TabBar(
            indicatorColor: Ufg.orange,
            tabs: [Tab(icon: Icon(Icons.sticky_note_2_outlined), text: 'Mis notas'), Tab(icon: Icon(Icons.attach_file), text: 'Mis archivos')],
          ),
        ),
        body: _cargando
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? EmptyState(icon: Icons.cloud_off, title: 'No se pudo cargar', text: _error)
                : TabBarView(children: [
                    RefreshIndicator(
                      onRefresh: _cargar,
                      child: GridView.builder(
                        padding: const EdgeInsets.all(16),
                        gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                            maxCrossAxisExtent: 220, mainAxisSpacing: 14, crossAxisSpacing: 14, childAspectRatio: 0.92),
                        itemCount: notas.length + 1,
                        itemBuilder: (_, i) {
                          if (i == 0) {
                            return InkWell(
                              onTap: () => _editar(),
                              borderRadius: BorderRadius.circular(12),
                              child: Container(
                                decoration: BoxDecoration(
                                    border: Border.all(color: Ufg.line, width: 2), borderRadius: BorderRadius.circular(12)),
                                child: const Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                                  Icon(Icons.add, size: 30, color: Ufg.ink3),
                                  Text('Nueva nota', style: TextStyle(color: Ufg.ink3, fontWeight: FontWeight.w600)),
                                ]),
                              ),
                            );
                          }
                          final n = notas[i - 1] as Map;
                          return Transform.rotate(
                            angle: (i % 2 == 0 ? 1 : -1) * 0.008,
                            child: Material(
                              color: _colores[(i - 1) % _colores.length],
                              elevation: 2,
                              borderRadius: const BorderRadius.only(
                                  topLeft: Radius.circular(4), topRight: Radius.circular(4),
                                  bottomLeft: Radius.circular(4), bottomRight: Radius.circular(14)),
                              child: InkWell(
                                onTap: () => _editar(n),
                                child: Padding(
                                  padding: const EdgeInsets.all(14),
                                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                                    Text(n['title'] as String, maxLines: 2, overflow: TextOverflow.ellipsis,
                                        style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16, color: Color(0xFF2B2412))),
                                    const SizedBox(height: 6),
                                    Expanded(
                                      child: Text((n['content'] as String?)?.isNotEmpty == true ? n['content'] as String : 'Sin contenido',
                                          overflow: TextOverflow.fade, style: const TextStyle(color: Color(0xFF2B2412), height: 1.45)),
                                    ),
                                    Text(timeAgo(n['updated_at'] as String?),
                                        style: const TextStyle(fontSize: 12, color: Color(0x992B2412))),
                                  ]),
                                ),
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                    Scaffold(
                      floatingActionButton: FloatingActionButton.extended(
                          onPressed: _subir, icon: const Icon(Icons.upload_file), label: const Text('Subir archivo')),
                      body: archivos.isEmpty
                          ? const EmptyState(icon: Icons.attach_file, title: 'Sin archivos personales',
                              text: 'Guarda aquí documentos que sólo quieres para ti.')
                          : ListView.separated(
                              padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
                              itemCount: archivos.length,
                              separatorBuilder: (_, _) => const SizedBox(height: 8),
                              itemBuilder: (_, i) {
                                final f = archivos[i] as Map;
                                return Card(
                                  child: ListTile(
                                    onTap: () => _abrir(f),
                                    leading: FileIcon(f['extension'] as String?, size: 36),
                                    title: Text(f['title'] as String, maxLines: 1, overflow: TextOverflow.ellipsis),
                                    subtitle: Text('${fileSize(f['file_size'] as num?)}  ${timeAgo(f['created_at'] as String?)}'),
                                    trailing: IconButton(
                                      icon: const Icon(Icons.smart_toy_outlined),
                                      tooltip: 'Preguntar a Francis',
                                      onPressed: () => ShellController.openFrancis(docKey: f['doc_key'] as String, title: f['title'] as String),
                                    ),
                                  ),
                                );
                              },
                            ),
                    ),
                  ]),
      ),
    );
  }
}
