// Barra inferior con las cinco secciones (igual que la web en el celular).
import 'package:flutter/material.dart';

import 'francis_screen.dart';
import 'home_screen.dart';
import 'library_screen.dart';
import 'notes_screen.dart';
import 'profile_screen.dart';

/// Permite cambiar de pestaña desde cualquier pantalla (p. ej. «Preguntar a Francis»).
class ShellController {
  static final tab = ValueNotifier<int>(0);
  static final libraryQuery = ValueNotifier<String?>(null);

  static void openFrancis({String? docKey, String? title}) {
    FrancisController.scope.value = docKey == null ? null : DocScope(docKey, title ?? '');
    tab.value = 1;
  }

  static void openLibrary({String? query}) {
    libraryQuery.value = query;
    tab.value = 2;
  }
}

class Shell extends StatelessWidget {
  const Shell({super.key});

  static const _paginas = [HomeScreen(), FrancisScreen(), LibraryScreen(), NotesScreen(), ProfileScreen()];

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<int>(
      valueListenable: ShellController.tab,
      builder: (context, i, _) => Scaffold(
        body: IndexedStack(index: i, children: _paginas),
        bottomNavigationBar: NavigationBar(
          selectedIndex: i,
          onDestinationSelected: (n) => ShellController.tab.value = n,
          destinations: const [
            NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: 'Inicio'),
            NavigationDestination(icon: Icon(Icons.smart_toy_outlined), selectedIcon: Icon(Icons.smart_toy), label: 'Francis'),
            NavigationDestination(icon: Icon(Icons.menu_book_outlined), selectedIcon: Icon(Icons.menu_book), label: 'Biblioteca'),
            NavigationDestination(icon: Icon(Icons.sticky_note_2_outlined), selectedIcon: Icon(Icons.sticky_note_2), label: 'Mi espacio'),
            NavigationDestination(icon: Icon(Icons.person_outline), selectedIcon: Icon(Icons.person), label: 'Perfil'),
          ],
        ),
      ),
    );
  }
}
