# Fase 1 — IA en la nube, vigilante de archivos, rediseño y parte social

Avance de octubre de 2026 sobre la versión que corría con Ollama en local.

## Observaciones atendidas

| Observación | Qué se hizo |
|---|---|
| El modelo local respondía «plano» y no se enfocaba en los documentos | Router de modelos gratuitos en la nube (Gemini, Groq, OpenRouter) con Ollama de respaldo y cambio automático cuando uno se queda sin cuota. Prompt nuevo con catálogo de documentos, extractos numerados y citas `[n]` clicables, más el modo «preguntar sobre este documento». Ver `ASISTENTE_IA.md`. |
| Un modelo que vigile lo que suben los alumnos (antivirus + «segurata») | Tres barreras: análisis estático (macros, JavaScript en PDF, ejecutables disfrazados, ZIP peligrosos...), antivirus del sistema (Defender o ClamAV) y un segundo modelo de IA que revisa el contenido en paralelo al asistente, con Prompt Guard contra instrucciones ocultas. Incluye panel de Seguridad para administradores. Ver `SEGURIDAD.md`. |
| Rediseño más moderno, sin «estilo IA», con colores y logo UFG | Frontend reescrito con un sistema de diseño propio: azul y naranja del logotipo, tipografía Jost (eco de las letras del logo) y Source Sans 3. Cada documento lleva un «lomo» de color según su área, como libros en una estantería. Se quitó Tailwind por CDN. |
| El chatbot donde estaba el chat global; el chat global junto a los mensajes directos | En Inicio, el asistente ocupa la columna derecha. El chat global UFG queda fijado arriba en **Mensajes**, junto a las conversaciones con amigos. |
| ~20 personas a la vez, gratis y sin saturar la PC | `python wsgi.py` (waitress, 32 hilos) + SQLite en modo WAL + un único «pulso» ligero cada 4 s. Con la IA en la nube la PC sólo sirve la web. Para compartir: túnel gratuito de Cloudflare (`scripts/compartir.ps1`). |
| Terminar grupos, amigos y mensajes | Amigos: buscar, sugerencias, enviar, aceptar, rechazar, cancelar y eliminar. Conversaciones con no leídos y estado en línea. Grupos: crear con amigos, editar, salir (el liderazgo pasa al siguiente), retirar miembros, eliminar; chat con no leídos; tablero de tareas (pendiente, en progreso, hecha) con responsable y fecha; archivos del grupo revisados por el vigilante. |
| Flask + SQLite, sin abrir editores de base de datos | Se mantiene. Las tablas y columnas nuevas se crean solas al arrancar (`hub/schema.py`); las tareas de mantenimiento están en `python manage.py`. |

## Arquitectura

```
Navegador (HTML + CSS + módulos JS, sin compilación)
   │  JSON / NDJSON   (mismo origen: no hace falta CORS)
   ▼
Flask (hub/) ── Blueprints: auth · library · social · chat · groups · notes ·
   │             profile · realtime · assistant · admin · frontend
   ├── SQLite (WAL)              usuarios, documentos, mensajes, grupos, escaneos
   ├── Índice del asistente      ChromaDB (vectores) + SQLite FTS5 (BM25)
   ├── Vigilante (hilo de fondo) estático → Defender/ClamAV → modelo de seguridad
   └── Router de IA ──► Gemini ─► Groq ─► OpenRouter ─► Ollama (local)
```

Cambios de backend respecto a la versión anterior:

- `app.py` (2.250 líneas en un archivo) pasó a un paquete `hub/` con Blueprints por
  dominio, *type hints*, configuración en `.env` y errores JSON uniformes
  (`{message, code, details}`) con manejadores globales.
- Seguridad: CSP sin scripts en línea, cabeceras `nosniff`/`DENY`, límites de
  peticiones en login, registro, chat y asistente; las fotos de perfil también
  pasan por el vigilante; la descarga pública sin sesión (`/api/uploads/<archivo>`)
  se eliminó: toda descarga comprueba sesión, permisos y estado del escaneo.
- Biblioteca: búsqueda y filtros en el servidor, guardados, descargas
  contadas, descripción y vista previa (PDF, imágenes, texto).
- El contrato anterior se mantiene (`seed_test_data.py` funciona sin cambios);
  sólo se añadieron rutas y campos.

## Pruebas

**Automáticas** — `python -m pytest`: 58 pruebas (autenticación, vigilante,
biblioteca, amigos y mensajes, grupos, asistente y conmutación del router). No
usan red: la IA y el antivirus se simulan.

**Carga** — `python scripts/prueba_carga.py` (cada usuario virtual pide el pulso
cada 4 s, abre la biblioteca, busca, escribe en el chat global, en privado y en
su grupo):

| Usuarios | Duración | Peticiones | Errores | p95 más alto |
|---|---|---|---|---|
| 20 | 2 min | 1.688 (13,6/s) | 0 | 34 ms (biblioteca) |
| 50 | 1 min | 2.164 (33,8/s) | 0 | 50 ms (detalle de grupo) |

El inicio de sesión tarda ~200 ms a propósito (bcrypt). Las respuestas del
asistente dependen del proveedor: segundos en la nube; con Ollama local sin GPU,
unos 25-70 s.

**Manual** — revisado en el navegador a 1440 px y a 375 px (móvil): acceso,
inicio con asistente, biblioteca con áreas y vista previa, mensajes (chat global
y privados), amigos, grupos (chat y tablero), anotaciones, perfil y Seguridad.
El vigilante se probó con un `.exe` renombrado a `.pdf` (bloqueado), un `.zip`
falso (bloqueado) y un `.txt` normal (pasó las tres barreras: Defender + IA).

## Cómo hacer la demostración

1. `python wsgi.py` y, si van a entrar desde otros equipos, `scripts\compartir.ps1`.
2. Inicio: pregunta «¿Qué material hay sobre bases de datos?» y abre una cita.
3. Biblioteca: abre un documento → **Preguntar al asistente** → «resúmelo en 5 puntos».
4. Sube un archivo normal: aparece «En revisión» y luego la notificación «Archivo publicado».
5. Sube un `.exe` renombrado a `.pdf`: se rechaza con el motivo.
6. Con una cuenta de `ADMIN_EMAILS`: sección **Seguridad** con el informe de las tres barreras.
7. Mensajes → Chat global con dos cuentas abiertas a la vez: los mensajes llegan en ~4 s.

## Pendiente para próximas fases (propuestas)

- Desplegar en el servidor de la universidad (Linux + ClamAV + `gunicorn --workers 1 --threads 32`).
- OCR para PDF escaneados.
- Visión por computadora de las clases 10 y 11: revisión de imágenes con un
  detector local (YOLO) como cuarta barrera, o inicio de sesión biométrico
  opcional con DeepFace/MediaPipe.
- Notificaciones en tiempo real con WebSockets si se supera el centenar de usuarios.
