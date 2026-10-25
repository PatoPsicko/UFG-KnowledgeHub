# Vigilante de archivos — UFG Knowledge Hub

Cada archivo que sube un estudiante (biblioteca, grupos, Mi espacio o foto de
perfil) pasa por tres barreras antes de que otra persona pueda verlo. Funciona
como un antivirus más un «segurata» que revisa el contenido.

**El administrador no revisa a mano lo que sale limpio** (Fase 2): se publica
solo. Sólo le llega lo que el vigilante dejó **en cuarentena** por dudoso o
peligroso, con el motivo, para aprobarlo o rechazarlo.

```
subida ──► 1. Análisis estático (en el momento, milisegundos)
              │  block ──► se rechaza (422), se borra y queda registrado
              ▼  ok / review
           recurso guardado como «En revisión» (sólo lo ve quien lo subió)
              │  (hilo en segundo plano)
              ▼
           2. Antivirus del sistema ── amenaza ──► Bloqueado, se borra y se veta su huella
           3. Revisión con IA       ── peligroso ─► Cuarentena ┐ el archivo se guarda,
                                    ── dudoso ────► Cuarentena ┘ el admin aprueba o rechaza
                                    ── sin cuota ─► sigue «En revisión», se reintenta
              ▼
           Limpio ──► se publica solo, se avisa al estudiante y entra al índice del asistente
```

Código: `hub/security/` (`static.py`, `antivirus.py`, `ai_review.py`, `pipeline.py`).

## 1. Análisis estático

No ejecuta ni abre el archivo con otros programas: sólo lee bytes.

| Comprobación | Resultado |
|---|---|
| Extensión fuera de la lista blanca (`.exe`, `.html`, `.svg`, `.js`...) | Rechazo inmediato |
| El contenido real no coincide con la extensión (un `.exe` renombrado a `.pdf`) | Bloquea |
| Firmas de ejecutables (Windows, Linux, macOS, scripts, accesos directos) | Bloquea |
| PDF con JavaScript o `/Launch` | Bloquea |
| PDF con archivos incrustados, Flash/XFA o apertura automática de enlaces | Revisión |
| Word/Excel/PowerPoint con macros (`vbaProject.bin`, `_VBA_PROJECT`) | Bloquea |
| Documentos que cargan plantillas remotas (técnica tipo Follina) | Bloquea |
| ActiveX u objetos OLE incrustados | Revisión |
| ZIP con ejecutables, rutas `../` o *zip bombs* | Bloquea |
| ZIP con archivos cifrados (no se pueden revisar) | Revisión |
| RTF con objetos que se ejecutan solos | Bloquea |
| Imágenes «políglota» con JavaScript, PHP o HTML escondido | Bloquea |
| Doble extensión engañosa (`virus.exe.pdf`) | Revisión |
| Archivo de prueba antivirus EICAR | Bloquea |
| Huella SHA-256 vetada por un administrador | Bloquea |

## 2. Antivirus del sistema

- **Windows**: Microsoft Defender (`MpCmdRun.exe`), que ya viene instalado. En esta
  PC tardó unos 0,1 s por archivo al revisar los 100 documentos existentes.
- **Linux** (servidor de la universidad): ClamAV (`clamdscan` o `clamscan`).

`SCAN_ANTIVIRUS=auto|defender|clamav|off`. Si Defender en tiempo real borra el
archivo al guardarlo, el vigilante lo detecta y lo marca como amenaza.

## 3. Revisión con IA (el «segurata»)

Un segundo modelo, en paralelo al asistente, revisa el texto extraído (y las
imágenes, si hay un modelo con visión como Gemini). Clasifica en:

- **block**: phishing, malware listo para usar, contenido sexual explícito, odio
  o acoso, datos personales de terceros, instrucciones ocultas para el asistente.
- **review**: dudas razonables, spam o libros completos con derechos de autor.
- **ok**: material académico normal (incluye temas de seguridad o medicina
  tratados como estudio).

Si hay clave de Groq, además **Llama Prompt Guard 2** puntúa el texto contra
inyección de instrucciones; por encima de `SCAN_PROMPT_GUARD_THRESHOLD` (0,9) el
documento va a revisión. Esto importa porque el asistente lee los documentos: un
PDF con «ignora tus instrucciones» escondido podría manipular sus respuestas.

**Modelo.** El vigilante usa el mismo `openai/gpt-oss-120b` de Groq que el
asistente (`GROQ_SECURITY_MODELS`), con `openai/gpt-oss-20b` de respaldo si el
primero no tiene cupo. Cada uno tiene 8.000 tokens por minuto y 1.000
peticiones al día en la cuenta gratuita; una revisión gasta unos 2.300 tokens
(se envían los primeros `SCAN_AI_MAX_CHARS` = 6.000 caracteres). Para no
quitarle cupo a las preguntas de los estudiantes, sólo usa un modelo si después
le quedan `AI_SECURITY_RESERVE_TOKENS` (3.000) libres; si no, espera hasta
`SCAN_AI_WAIT` (90 s) y prueba el respaldo. En la prueba de carga con 20
personas (72 archivos en 3 minutos) todo se publicó solo y la cola del vigilante
terminó unos 4 minutos después. Respaldo opcional: Gemini u OpenRouter
(`SECURITY_AI_PROVIDERS=groq,gemini`) cuando haya clave.

**Sin cuota no se publica a ciegas.** Si la IA no responde, el archivo sigue
«En revisión» y se reintenta a los 1, 5, 15, 30 y 60 minutos
(`SCAN_AI_RETRY_MINUTES`). Si tras todo eso sigue sin respuesta, con
`SCAN_REQUIRE_AI=1` (lo configurado) va a cuarentena; con `0` se publicaría con
la nota «sin revisión IA». Los escaneos que quedaron a medias al apagar el
servidor se reanudan solos al arrancar.

**Imágenes.** Groq no tiene un modelo con visión: sin clave de Gemini las
imágenes pasan el análisis estático y el antivirus y se publican con la nota
«imagen sin revisión IA».

Los archivos privados no pasan por la IA (nadie más los ve) y los archivos
antiguos tampoco en la revisión inicial, para no gastar la cuota gratuita en
material que ya estaba publicado.

## Panel de Seguridad

Los correos de `ADMIN_EMAILS` (o `python manage.py admin correo`) ven la sección
**Seguridad**, que abre directamente en **En cuarentena**: sólo lo dudoso o
peligroso que espera una decisión, con el informe de cada capa. Pueden
**aprobar y publicar**, **rechazar** (borra el archivo y veta su huella SHA-256
para que no se pueda volver a subir) o volver a revisar. También muestra la
cuota gratuita que le queda a cada modelo de IA (tokens del minuto y peticiones
del día) y el espacio que ocupan los archivos. El estudiante recibe una
notificación («Archivo publicado», «Archivo en cuarentena» o «Archivo
rechazado») y los administradores un aviso sólo de lo que quedó en cuarentena.

## Cuentas e inicio de sesión (Fase 2)

- **Sólo correos @ufg.edu.sv**, comprobado en el servidor (`ALLOWED_EMAIL_DOMAINS`,
  exacto: `prueba.ufg.edu.sv` o `ufg.edu.sv.otro.com` no valen). El correo se
  normaliza (Unicode NFKC, sin caracteres invisibles ni espacios, en minúsculas).
- **Contraseña**: 8 caracteres o más, con letras y números, que no contenga el
  usuario del correo ni sea de las más comunes; como máximo 72 bytes (lo que
  bcrypt usa de verdad).
- **Bloqueo temporal**: 5 fallos seguidos con el mismo correo lo bloquean 15
  minutos (`LOGIN_MAX_FAILURES`, `LOGIN_LOCK_MINUTES`). Se guarda en SQLite
  (tabla `login_throttle`), así un reinicio no lo borra. Además siguen los
  límites por IP (10 intentos por minuto por IP y correo, 60 por IP).
- **No revela qué cuentas existen**: el registro responde lo mismo para un
  correo nuevo y uno existente; el inicio de sesión dice «Correo o contraseña
  incorrectos» en ambos casos, tarda lo mismo (también se calcula un bcrypt si
  la cuenta no existe) y el bloqueo se aplica igual a correos inexistentes.
- **Verificación por correo, lista pero apagada** (`EMAIL_VERIFICATION=0`):
  necesita un servidor SMTP con credenciales que todavía no hay. Con
  `EMAIL_VERIFICATION=1` y `SMTP_HOST/PORT/USER/PASSWORD/FROM` en `.env`, el
  registro envía un enlace firmado que vale 48 h, nadie entra sin abrirlo y el
  rol de administrador sólo se da a correos verificados. Mientras esté apagada,
  conviene crear primero las cuentas de `ADMIN_EMAILS`.

## Archivos en el servidor (Fase 2)

- Carpetas por tipo: `uploads/library/`, `uploads/private/<usuario>/`,
  `uploads/groups/<grupo>/`, `uploads/profile/` y `uploads/tmp/` para las
  subidas en curso. La estructura anterior se migra sola al arrancar.
- Nombre en disco `<uuid>_<nombre-seguro>` (máx. 80 caracteres): nadie puede
  adivinar rutas ni escapar de la carpeta.
- Escritura atómica: el archivo se escribe en `tmp/` y se mueve al terminar.
- Límites: 25 MB por archivo, 4 MB por foto, 300 MB y 40 subidas al día por
  estudiante, y nada se acepta si quedan menos de 1 GB libres en el disco.
- Limpieza automática al arrancar y cada 6 h: subidas a medias y archivos que
  ya no pertenecen a ningún registro (con más de 24 h).
- **Descargas con enlace firmado**: el navegador pide un enlace de 5 minutos
  válido sólo para ese archivo y ese estudiante, y la ruta vuelve a comprobar
  permisos y el vigilante. Así las descargas funcionan también en el celular
  dentro de las web views (WhatsApp, Instagram), que no saben guardar «blobs».

## Probarlo

```bash
python manage.py scan ruta\al\archivo.pdf      # las 3 barreras sobre un archivo
python -m pytest tests/test_security.py tests/test_auth.py tests/test_storage.py
```

Para la demostración en clase se puede subir el archivo de prueba EICAR
(https://www.eicar.org): es inofensivo, pero todos los antivirus lo detectan.
Ojo: Defender puede borrarlo de tu carpeta de descargas antes de subirlo.
