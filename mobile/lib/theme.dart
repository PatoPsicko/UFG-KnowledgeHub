// Colores y tipografía de UFG Knowledge Hub (los mismos de la web: css/app.css).
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class Ufg {
  static const blue = Color(0xFF0B6FCB);
  static const blueDark = Color(0xFF084E8F);
  static const orange = Color(0xFFF08A0B);
  static const navy = Color(0xFF0B2545);
  static const green = Color(0xFF1D8A5A);
  static const paper = Color(0xFFF4F6F9);
  static const ink = Color(0xFF13233A);
  static const ink2 = Color(0xFF4A5A70);
  static const ink3 = Color(0xFF6E7D91);
  static const line = Color(0xFFDDE3EB);
  static const danger = Color(0xFFC33B2E);

  /// Color del icono según el tipo de archivo (igual que en la web).
  static Color fileColor(String? ext) {
    switch ((ext ?? '').toLowerCase()) {
      case 'pdf':
        return const Color(0xFFD93025);
      case 'doc':
      case 'docx':
      case 'odt':
      case 'rtf':
        return const Color(0xFF1A5FD0);
      case 'xls':
      case 'xlsx':
      case 'ods':
      case 'csv':
        return const Color(0xFF1E8E4E);
      case 'ppt':
      case 'pptx':
      case 'odp':
        return const Color(0xFFE8710A);
      case 'png':
      case 'jpg':
      case 'jpeg':
      case 'gif':
      case 'webp':
        return const Color(0xFF8E44AD);
      case 'zip':
      case 'rar':
      case '7z':
        return const Color(0xFF8A6D1F);
      default:
        return ink2;
    }
  }
}

ThemeData buildTheme(Brightness brillo) {
  final oscuro = brillo == Brightness.dark;
  final esquema = ColorScheme.fromSeed(
    seedColor: Ufg.blue,
    brightness: brillo,
    primary: oscuro ? const Color(0xFF2F8FE6) : Ufg.blue,
    secondary: Ufg.orange,
    surface: oscuro ? const Color(0xFF1C1C1C) : Colors.white,
  );
  final cuerpo = GoogleFonts.sourceSans3TextTheme(ThemeData(brightness: brillo).textTheme);
  final titulos = GoogleFonts.jostTextTheme(cuerpo);
  return ThemeData(
    useMaterial3: true,
    colorScheme: esquema,
    scaffoldBackgroundColor: oscuro ? const Color(0xFF121212) : Ufg.paper,
    textTheme: cuerpo.copyWith(
      headlineMedium: titulos.headlineMedium?.copyWith(fontWeight: FontWeight.w600),
      headlineSmall: titulos.headlineSmall?.copyWith(fontWeight: FontWeight.w600),
      titleLarge: titulos.titleLarge?.copyWith(fontWeight: FontWeight.w600),
      titleMedium: titulos.titleMedium?.copyWith(fontWeight: FontWeight.w600),
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: oscuro ? const Color(0xFF121212) : Ufg.paper,
      foregroundColor: oscuro ? Colors.white : Ufg.ink,
      elevation: 0,
      scrolledUnderElevation: 1,
      titleTextStyle: GoogleFonts.jost(fontSize: 22, fontWeight: FontWeight.w600, color: oscuro ? Colors.white : Ufg.ink),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      color: esquema.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: oscuro ? const Color(0xFF333333) : Ufg.line),
      ),
      margin: EdgeInsets.zero,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: oscuro ? const Color(0xFF242424) : Colors.white,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: const BorderSide(color: Ufg.line)),
      enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: oscuro ? const Color(0xFF333333) : Ufg.line)),
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(0, 48),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        textStyle: GoogleFonts.sourceSans3(fontWeight: FontWeight.w700, fontSize: 16),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      indicatorColor: Ufg.orange.withValues(alpha: 0.22),
      labelTextStyle: WidgetStatePropertyAll(GoogleFonts.sourceSans3(fontSize: 12.5, fontWeight: FontWeight.w600)),
    ),
  );
}
