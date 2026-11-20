# Fase 4: app nativa para Android (Flutter)

La app vive en `mobile/`. Es una app nativa hecha con Flutter, no una web dentro de un
marco: las pantallas se dibujan con widgets propios y usan la misma API del servidor
Flask que ya usa la web. No hay una segunda base de datos ni otro backend.

## Qué incluye esta primera versión

| Pantalla | Qué hace |
|---|---|
| Inicio de sesión | Correo y contraseña, segundo paso con código de 6 dígitos si la cuenta tiene verificación en dos pasos, y un botón «Servidor» para elegir a qué dirección conectarse. |
| Inicio | Saludo, búsqueda rápida, cifras de la biblioteca, acceso a Francis y lo recién compartido. |
| Francis | Chat con respuesta en vivo (va apareciendo mientras escribe), citas `[1]` que se pueden tocar, lista de fuentes y modo «preguntar sobre este documento». |
| Biblioteca | Búsqueda, filtros Todo / Guardados / Míos, detalle del documento (abrir, guardar, reportar, preguntar a Francis) y subida de archivos con área, materia, etiquetas y descripción. |
| Mi espacio | Notas tipo post-it (crear, editar, borrar) y archivos personales (subir, abrir). |
| Perfil | Datos de la cuenta, tema claro / oscuro / sistema, servidor en uso y cerrar sesión. |

Quedan para la siguiente versión: grupos, notificaciones push, panel de administración
(sigue en la web) y la administración de sesiones y dos pasos (también en la web).

## Cómo se conecta la app con el servidor

- La app manda el encabezado `X-Client: mobile` en todas las peticiones.
- Al iniciar sesión el servidor le devuelve el token de renovación **en el cuerpo** de la
  respuesta (la web lo recibe en una cookie). La app lo guarda cifrado con
  `flutter_secure_storage` (Keystore de Android).
- El token de acceso dura 30 minutos. Cuando vence, la app pide uno nuevo a
  `/api/auth/refresh` mandando el token de renovación; el servidor lo rota y devuelve
  el siguiente. Si dos peticiones intentan renovar a la vez, la app espera a la primera.
- Si una renovación se repite dentro de los 30 segundos de gracia (por ejemplo, porque
  se cortó la red justo al recibir la respuesta), el servidor entrega un token nuevo en
  lugar de tratarlo como robo de token. Fuera de ese margen, reusar un token viejo
  cierra la sesión del dispositivo, igual que en la web.
- Cerrar sesión en el teléfono revoca sólo la sesión del teléfono.
- Cada teléfono aparece como un dispositivo más en «Mi perfil → Sesiones» de la web,
  desde donde se puede cerrar a distancia.

Cambios del servidor: `hub/sessions.py` (`rotate(..., reissue=True)`,
`is_mobile_client()`, `mobile_refresh_token()`) y `hub/api/auth.py` (login, refresh y
logout). La prueba es `test_mobile_client_gets_refresh_token_in_body` en
`tests/test_sessions.py`.

## Requisitos para compilar

- Flutter 3.47 o superior (`flutter --version`).
- Android SDK con la plataforma 34 o superior (la instala Android Studio).
- Para probar: un teléfono Android con depuración USB activada o un emulador creado en
  Android Studio (Device Manager).

## Compilar e instalar

```powershell
cd mobile
flutter pub get
flutter build apk --release
```

El archivo queda en `mobile/build/app/outputs/flutter-apk/app-release.apk`. Se puede
copiar al teléfono e instalarlo (Android pedirá permitir «instalar apps de origen
desconocido»). Para desarrollo con recarga en caliente:

```powershell
flutter run
```

## A qué servidor se conecta

| Caso | Dirección |
|---|---|
| Emulador de Android en la misma PC | `http://10.0.2.2:5001` (la predeterminada) |
| Teléfono en la misma red Wi-Fi | `http://IP-de-la-PC:5001` |
| Teléfono fuera de la red | el enlace público que muestra `iniciar.bat` (https) |

La dirección se cambia desde el botón «Servidor» en la pantalla de inicio de sesión, o al
compilar:

```powershell
flutter build apk --release --dart-define=SERVER_URL=https://tu-enlace-publico
```

La app permite `http://` sólo para poder probar con el servidor local
(`android:usesCleartextTraffic` en el manifiesto). Antes de publicar la app en una tienda
conviene quitarlo y usar únicamente el enlace https.

## Estructura

```
mobile/lib/
  main.dart              arranque, tema, idioma español, decide login o app
  theme.dart             colores UFG (azul y naranja) y tipografías
  core/api.dart          cliente HTTP: tokens, renovación, subidas, descargas, streaming
  core/session.dart      usuario actual, tema elegido, cerrar sesión
  core/categories.dart   áreas y materias (copiadas de js/data/categories.js)
  widgets/common.dart    íconos de archivo, estados vacíos, avisos, Markdown de Francis
  screens/               una pantalla por archivo
```

Si cambian las áreas o materias en `js/data/categories.js`, hay que actualizar
`core/categories.dart` a mano.
