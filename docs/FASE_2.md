# Fase 2 — 20 personas desde un link, celular, cuentas UFG y vigilante automático

Avance de octubre de 2026 sobre la Fase 1. La meta de la entrega: unas 20
personas conectadas a la vez desde un link (en la compu, en el celular o dentro
de una web view como WhatsApp) contra la PC del estudiante, usando todo el
sistema, sin pagar nada.

## Lo que se pidió y lo que se hizo

| Pedido | Qué se hizo |
|---|---|
| Chat del asistente con «luces» como Gemini, en azul y naranja UFG, y animaciones suaves en toda la interfaz | Un anillo de luz azul y naranja gira alrededor de la caja de texto al enfocarla; mientras el asistente piensa gira más rápido, el ícono late y aparece un brillo difuso bajo la cabecera; al escribir se calma. Pantalla de entrada con el logo y una línea de luz, y botones que se hunden al tocarlos. Todo respeta «reducir movimiento» del sistema y una preferencia propia (Automáticas / Reducidas / Completas). No se cambió la base del diseño. |
| Archivos y datos de cada usuario bien guardados | Carpetas por tipo y por dueño (`library/`, `private/<usuario>/`, `groups/<grupo>/`, `profile/`, `tmp/`), escritura atómica, nombres seguros y cortos, límites por archivo, cuota de 300 MB y 40 subidas al día por estudiante, control de espacio libre, limpieza automática de huérfanos y migración sola de la estructura anterior. Preferencias guardadas por cuenta (tema, animaciones, orden de la biblioteca) que siguen al estudiante a otro equipo. |
| 20 usuarios a la vez usando todo; prueba de carga; límites gratuitos de Groq y Gemini | Router de IA que lee la cuota real de cada modelo, cola con aviso en pantalla, caché de respuestas, respuesta con documentos si se agota la cuota y prioridad del asistente sobre el vigilante. `scripts/prueba_carga.py --aislado` simula 20 estudiantes subiendo, descargando, buscando, en grupos y preguntando al asistente con IA simulada (mismos límites que Groq). Resultados abajo. |
| Registro sólo con correos @ufg.edu.sv y login más seguro | Dominio comprobado en el servidor, correos normalizados, contraseña con letras y números (mín. 8), bloqueo de 15 min tras 5 fallos, mensajes y tiempos que no revelan si una cuenta existe. Verificación por correo lista pero apagada (falta un SMTP con credenciales). |
| Celular igual de fácil que en la compu, PWA | Barra inferior con las cinco secciones, menú y campana arriba, alturas reales del celular (`dvh`), diálogos como hoja inferior, historial del asistente en panel, áreas de la biblioteca en chips, PDF en el visor del teléfono, descargas que funcionan en web views y campos de 16 px (el iPhone no hace zoom). App instalable: manifest, íconos con el logo UFG, color del tema y service worker. Probado a 375 px y en escritorio. |
| Vigilante con IA; el admin sólo revisa lo dudoso o peligroso | Lo limpio se publica solo. Lo dudoso o peligroso queda en cuarentena con el motivo; el panel de Seguridad abre en «En cuarentena» con Aprobar / Rechazar. Usa el mismo `openai/gpt-oss-120b` de Groq, con `gpt-oss-20b` de respaldo. Sin cuota reintenta más tarde en lugar de publicar a ciegas, y retoma lo pendiente al reiniciar. |
| Link para la demo | `cloudflared` 2026.10.3 instalado con winget. `iniciar.bat` arranca el servidor, abre el túnel, muestra el link (ya copiado) y la dirección de la red local, y apaga todo al cerrar. Se probó el arranque local completo (`iniciar.ps1 -SinTunel`); la prueba con el link público quedó pendiente (ver abajo). |
| Documentación | Este documento, `README.md`, `ASISTENTE_IA.md`, `SEGURIDAD.md` y `DEMO_20_USUARIOS.md`. |

## Cambios de backend

- `hub/api/auth.py`: dominio, normalización, política de contraseñas, bloqueo
  (`LoginThrottle` en SQLite), respuestas que no revelan cuentas, verificación
  por correo (`hub/mailer.py`) y `GET /api/auth/policy` para el formulario.
- `hub/storage.py`: carpetas, límites, cuotas, `migrate_layout()`,
  `backfill_sizes()`, `cleanup()` y `stats()`; `python manage.py storage`.
- `hub/api/files.py`: enlaces de descarga firmados de 5 minutos (las
  descargas ya no usan «blobs», que fallan en las web views) y uso de espacio.
- `hub/security/pipeline.py`: cuarentena, reintentos sin cuota,
  `requeue_pending()` al arrancar y avisos sólo de lo que necesita al admin.
- `hub/ai/llm.py`: cupo por modelo con las cabeceras `x-ratelimit-*`,
  `wait_time()`, `CapacityError`, reserva para el asistente y `quotas()` para
  el panel. `hub/ai/simulado.py`: IA simulada para las pruebas de carga.
- `hub/ai/assistant.py` y `hub/api/assistant.py`: cola con eventos `queue`,
  caché, respuesta sin IA, historial recortado y citas `【n】` normalizadas.
- Esquema (`hub/schema.py` las crea solas al arrancar): columnas
  `user.email_verified`, `user.preferences` y `file_scan.ai_attempts`; tabla
  `login_throttle`.

## Cuotas gratuitas con 20 personas

Datos leídos de las cabeceras de Groq para esta cuenta (octubre de 2026):

| Modelo | Tokens por minuto | Peticiones por día | Uso |
|---|---|---|---|
| `openai/gpt-oss-120b` | 8.000 | 1.000 | asistente y vigilante |
| `qwen/qwen3.8-27b` | 8.000 | 1.000 | asistente |
| `openai/gpt-oss-20b` | 8.000 | 1.000 | asistente y respaldo del vigilante |

Una pregunta con extractos gasta 2.500-4.500 tokens y una revisión del
vigilante unos 2.300. Entre los tres modelos caben 5-8 respuestas nuevas por
minuto. Qué pasa al pasarse, en `ASISTENTE_IA.md` (sección 2b). Gemini no
está configurado (falta la clave): sería el respaldo con más margen.

## Prueba de carga

`python scripts/prueba_carga.py --aislado` (20 estudiantes, 3 minutos, IA
simulada con los límites de Groq, Defender revisando cada archivo). Cada
estudiante pide el pulso cada 4 s, navega y busca en la biblioteca, abre,
previsualiza y descarga documentos, sube un archivo a la biblioteca, otro a
Mi espacio y otro al grupo, escribe en el chat del grupo y hace 3 preguntas al
asistente por streaming.

Se corrió dos veces: con preguntas que se repiten (lo normal en una clase,
todos preguntan lo mismo) y con todas las preguntas distintas (el peor caso
para la cuota de IA, sin caché).

| | Repetidas (caché) | Todas distintas |
|---|---|---|
| Peticiones | 1.716 en 184 s (9,3/s) | 799 en 237 s (3,4/s)* |
| Errores | **0** | **0** |
| Biblioteca, búsqueda, documento (p95) | 29-30 ms | 31-32 ms |
| Vista previa / descarga con enlace firmado (p95) | 28 ms / 28 ms | 32 ms / 30 ms |
| Subir a biblioteca, Mi espacio y grupo (p95) | 35-38 ms | 37-38 ms |
| Pulso cada 4 s (p95) | 30 ms | 30 ms |
| Inicio de sesión (p95, bcrypt a propósito) | 283 ms | 270 ms |
| Asistente: respuestas | 18 con IA + 41 de caché | 27 con IA + 9 sólo con documentos |
| Asistente: esperaron en cola | 12 de 59 | 34 de 36 |
| Asistente: hasta la primera palabra (p50 / p95) | 0 s / 51 s | 56 s / 149 s |
| Vigilante | 72 archivos publicados solos, cola vacía 222 s después | 70 publicados solos, cola vacía 238 s después |
| Memoria del servidor | — | 97 MB |

\* En la segunda corrida los estudiantes pasan más tiempo esperando al
asistente, por eso hacen menos peticiones en el mismo tiempo.

Lectura: la PC atiende sin esfuerzo a 20 personas en todo lo que no es IA
(siempre por debajo de 40 ms). El límite real es la cuota gratuita de la IA:
unas 7 respuestas nuevas por minuto entre los tres modelos de Groq. Si todos
preguntan cosas distintas a la vez, esperan en cola con aviso en pantalla y,
pasados 150 s, reciben los documentos encontrados en lugar de un error. Con la
clave de Gemini la capacidad sube bastante. El vigilante revisa en segundo
plano a su ritmo y deja siempre cupo al asistente: ningún archivo limpio
necesitó a un administrador.

## Pruebas

**Automáticas** — `python -m pytest`: 85 pruebas (antes 58). Nuevas:
dominio y normalización de correos, política de contraseñas, bloqueo y
mensajes iguales para cuentas inexistentes, verificación por correo,
preferencias, carpetas y límites de archivos, migración y limpieza, enlaces
firmados, cuarentena y reintentos del vigilante, cupos del router, caché, cola
y respuesta sin IA.

**Manual** — en el navegador a 375 px (celular) y en escritorio, en modo claro
y oscuro: acceso, inicio, asistente (luces y citas con la IA real de Groq),
biblioteca, descarga con enlace firmado, grupos, perfil con preferencias y
Seguridad. El arranque con `iniciar.ps1` se probó en modo local; el túnel
público no se pudo abrir durante la noche (ver Pendiente).

## Pendiente (necesita al usuario o a la universidad)

- **Probar el link público**: durante la noche el modo automático de Claude
  Code no permitió abrir el túnel de Cloudflare sin supervisión (expone la PC a
  internet). Basta con doble clic en `iniciar.bat` y abrir el link que aparece
  desde un celular con datos móviles.

- **Clave de Gemini** (`GEMINI_API_KEY`): cupo extra para el asistente,
  vectores para la búsqueda y revisión de imágenes. Hay que crearla con una
  cuenta de Google.
- **SMTP de la universidad** para activar la verificación por correo
  (`EMAIL_VERIFICATION=1`): hacen falta servidor, usuario y contraseña reales.
- **Cuenta de administrador real**: poner el correo en `ADMIN_EMAILS` y crear
  esa cuenta antes de la demo.
- El link de Cloudflare cambia cada vez que se abre: para uno fijo hace falta
  una cuenta de Cloudflare con dominio (gratis, pero requiere registrarse).
- Propuestas para la siguiente fase: OCR para PDF escaneados, código QR del
  link en la pantalla de inicio, despliegue en un servidor de la universidad.
