# Vigilante de archivos — UFG Knowledge Hub

Cada archivo que sube un estudiante (biblioteca, grupos, anotaciones o foto de
perfil) pasa por tres barreras antes de que otra persona pueda verlo. Funciona
como un antivirus más un «segurata» que revisa el contenido.

```
subida ──► 1. Análisis estático (en el momento, milisegundos)
              │  block ──► se rechaza (422), se borra y queda registrado
              ▼  ok / review
           recurso guardado como «En revisión» (sólo lo ve quien lo subió)
              │  (hilo en segundo plano)
              ▼
           2. Antivirus del sistema ── amenaza ──► Bloqueado, se borra y se veta su huella
           3. Revisión con IA       ── no apto ──► Bloqueado (queda en cuarentena)
                                    ── dudoso ──► Pendiente de un admin
              ▼
           Limpio ──► se publica, se avisa al estudiante y entra al índice del asistente
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

Un modelo distinto al del asistente, y en paralelo a él, revisa el texto
extraído (y las imágenes, si hay un modelo con visión como Gemini). Clasifica en:

- **block**: phishing, malware listo para usar, contenido sexual explícito, odio
  o acoso, datos personales de terceros, instrucciones ocultas para el asistente.
- **review**: dudas razonables, spam o libros completos con derechos de autor.
- **ok**: material académico normal (incluye temas de seguridad o medicina
  tratados como estudio).

Si hay clave de Groq, además **Llama Prompt Guard 2** puntúa el texto contra
inyección de instrucciones; por encima de `SCAN_PROMPT_GUARD_THRESHOLD` (0,9) el
documento va a revisión. Esto importa porque el asistente lee los documentos: un
PDF con «ignora tus instrucciones» escondido podría manipular sus respuestas.

Por defecto el vigilante usa `openai/gpt-oss-20b` en Groq y, si no hay cuota,
Gemini Flash-Lite u Ollama (`SECURITY_AI_PROVIDERS`). Los archivos privados no
pasan por la IA (nadie más los ve) y los archivos antiguos tampoco en la revisión
inicial, para no gastar la cuota gratuita en material que ya estaba publicado.

`SCAN_REQUIRE_AI=1` hace que, si la IA no está disponible, los archivos esperen
a un administrador en lugar de publicarse sólo con las dos primeras barreras.

## Panel de Seguridad

Los correos de `ADMIN_EMAILS` (o `python manage.py admin correo`) ven la sección
**Seguridad**: estado de las tres barreras, archivos por revisar, bloqueados y
limpios, y el informe de cada capa. Pueden aprobar, bloquear (borra el archivo y
veta su huella) o volver a revisar. El estudiante recibe una notificación con el
resultado y los administradores un aviso de cada archivo dudoso o bloqueado.

## Probarlo

```bash
python manage.py scan ruta\al\archivo.pdf      # las 3 barreras sobre un archivo
python -m pytest tests/test_security.py         # 13 pruebas del vigilante
```

Para la demostración en clase se puede subir el archivo de prueba EICAR
(https://www.eicar.org): es inofensivo, pero todos los antivirus lo detectan.
Ojo: Defender puede borrarlo de tu carpeta de descargas antes de subirlo.
