// Piezas reutilizables: icono de archivo, estado vacío, avisos y markdown simple.
import 'package:flutter/material.dart';

import '../theme.dart';

class FileIcon extends StatelessWidget {
  const FileIcon(this.ext, {super.key, this.size = 44});
  final String? ext;
  final double size;

  @override
  Widget build(BuildContext context) {
    final c = Ufg.fileColor(ext);
    final texto = (ext ?? 'ARCH').toUpperCase();
    return Container(
      width: size,
      height: size * 1.18,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: c.withValues(alpha: 0.11),
        border: Border.all(color: c.withValues(alpha: 0.28)),
        borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(6), topRight: Radius.circular(10),
            bottomLeft: Radius.circular(6), bottomRight: Radius.circular(6)),
      ),
      child: Text(texto.length > 4 ? texto.substring(0, 4) : texto,
          style: TextStyle(color: c, fontWeight: FontWeight.w700, fontSize: size * 0.24)),
    );
  }
}

class EmptyState extends StatelessWidget {
  const EmptyState({super.key, required this.icon, required this.title, this.text, this.action});
  final IconData icon;
  final String title;
  final String? text;
  final Widget? action;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Icon(icon, size: 40, color: Ufg.ink3),
            const SizedBox(height: 12),
            Text(title, style: Theme.of(context).textTheme.titleMedium, textAlign: TextAlign.center),
            if (text != null) ...[
              const SizedBox(height: 6),
              Text(text!, textAlign: TextAlign.center, style: const TextStyle(color: Ufg.ink3)),
            ],
            if (action != null) ...[const SizedBox(height: 16), action!],
          ]),
        ),
      );
}

void toast(BuildContext context, String mensaje, {bool error = false}) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(
      content: Text(mensaje),
      backgroundColor: error ? Ufg.danger : null,
      behavior: SnackBarBehavior.floating,
    ));
}

String timeAgo(String? iso) {
  if (iso == null) return '';
  final fecha = DateTime.tryParse(iso);
  if (fecha == null) return '';
  final d = DateTime.now().toUtc().difference(fecha.toUtc());
  if (d.inMinutes < 1) return 'ahora';
  if (d.inMinutes < 60) return 'hace ${d.inMinutes} min';
  if (d.inHours < 24) return 'hace ${d.inHours} h';
  if (d.inDays < 7) return 'hace ${d.inDays} d';
  const meses = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
  final l = fecha.toLocal();
  return '${l.day} ${meses[l.month - 1]}';
}

String fileSize(num? bytes) {
  if (bytes == null) return '';
  if (bytes < 1024) return '$bytes B';
  if (bytes < 1024 * 1024) return '${(bytes / 1024).round()} KB';
  return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
}

/// Markdown ligero para las respuestas de Francis: párrafos, listas, **negrita**,
/// `código` y citas [1] (que se pueden tocar).
class MarkdownText extends StatelessWidget {
  const MarkdownText(this.source, {super.key, this.onCite, this.color});
  final String source;
  final void Function(int n)? onCite;
  final Color? color;

  List<InlineSpan> _inline(String texto, TextStyle base, BuildContext context) {
    final spans = <InlineSpan>[];
    final patron = RegExp(r'\*\*([^*]+)\*\*|`([^`]+)`|\[(\d{1,2})\]|【(\d{1,2})】');
    var i = 0;
    for (final m in patron.allMatches(texto)) {
      if (m.start > i) spans.add(TextSpan(text: texto.substring(i, m.start)));
      if (m.group(1) != null) {
        spans.add(TextSpan(text: m.group(1), style: const TextStyle(fontWeight: FontWeight.w700)));
      } else if (m.group(2) != null) {
        spans.add(TextSpan(
            text: m.group(2),
            style: TextStyle(fontFamily: 'monospace', backgroundColor: Colors.black.withValues(alpha: 0.08))));
      } else {
        final n = int.parse(m.group(3) ?? m.group(4)!);
        spans.add(WidgetSpan(
          alignment: PlaceholderAlignment.middle,
          child: GestureDetector(
            onTap: onCite == null ? null : () => onCite!(n),
            child: Container(
              margin: const EdgeInsets.symmetric(horizontal: 2),
              padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
              decoration: BoxDecoration(color: Ufg.orange.withValues(alpha: 0.2), borderRadius: BorderRadius.circular(5)),
              child: Text('$n', style: const TextStyle(color: Ufg.orange, fontWeight: FontWeight.w700, fontSize: 12)),
            ),
          ),
        ));
      }
      i = m.end;
    }
    if (i < texto.length) spans.add(TextSpan(text: texto.substring(i)));
    return spans;
  }

  @override
  Widget build(BuildContext context) {
    final base = Theme.of(context).textTheme.bodyLarge!.copyWith(height: 1.5, color: color);
    final bloques = <Widget>[];
    for (final parrafo in source.split(RegExp(r'\n\s*\n'))) {
      final lineas = parrafo.split('\n').where((l) => l.trim().isNotEmpty).toList();
      if (lineas.isEmpty) continue;
      for (final linea in lineas) {
        final lista = RegExp(r'^\s*([-*•]|\d+[.)])\s+(.*)$').firstMatch(linea);
        final titulo = RegExp(r'^\s*#{1,6}\s+(.*)$').firstMatch(linea);
        if (lista != null) {
          bloques.add(Padding(
            padding: const EdgeInsets.only(left: 4, bottom: 3),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(lista.group(1)!.startsWith(RegExp(r'\d')) ? '${lista.group(1)} ' : '•  ', style: base),
              Expanded(child: Text.rich(TextSpan(style: base, children: _inline(lista.group(2)!, base, context)))),
            ]),
          ));
        } else if (titulo != null) {
          bloques.add(Padding(
            padding: const EdgeInsets.only(top: 6, bottom: 2),
            child: Text.rich(TextSpan(
                style: base.copyWith(fontWeight: FontWeight.w700), children: _inline(titulo.group(1)!, base, context))),
          ));
        } else {
          bloques.add(Text.rich(TextSpan(style: base, children: _inline(linea, base, context))));
        }
      }
      bloques.add(const SizedBox(height: 8));
    }
    if (bloques.isNotEmpty) bloques.removeLast();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: bloques);
  }
}
