// UFG Knowledge Hub — app nativa para Android (Flutter).
//
// Habla con la misma API Flask que la web (ver lib/core/api.dart).
//   lib/core/     cliente de la API y sesión
//   lib/screens/  una pantalla por sección
//   lib/widgets/  piezas reutilizables
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'core/session.dart';
import 'screens/login_screen.dart';
import 'screens/shell.dart';
import 'theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  Session.instance.boot();
  runApp(const UfgHubApp());
}

class UfgHubApp extends StatelessWidget {
  const UfgHubApp({super.key});

  @override
  Widget build(BuildContext context) {
    final sesion = Session.instance;
    return ListenableBuilder(
      listenable: sesion,
      builder: (context, _) => MaterialApp(
        title: 'UFG Knowledge Hub',
        debugShowCheckedModeBanner: false,
        theme: buildTheme(Brightness.light),
        darkTheme: buildTheme(Brightness.dark),
        themeMode: sesion.themeMode,
        locale: const Locale('es', 'SV'),
        supportedLocales: const [Locale('es', 'SV'), Locale('es')],
        localizationsDelegates: const [
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        home: !sesion.ready
            ? const _Splash()
            : sesion.loggedIn
                ? const Shell()
                : const LoginScreen(),
      ),
    );
  }
}

class _Splash extends StatelessWidget {
  const _Splash();

  @override
  Widget build(BuildContext context) => Scaffold(
        body: Center(child: Image.asset('assets/logo_hub.png', width: 220)),
      );
}
