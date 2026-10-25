# Asistente de IA — UFG Knowledge Hub

> **Fase 1 (octubre de 2026):** el asistente ya no depende de un modelo local.
> Un router de modelos usa proveedores gratuitos en la nube (Gemini, Groq,
> OpenRouter) y deja Ollama como respaldo. Se movió del botón flotante a la
> página de **Inicio** (donde estaba el chat global) y tiene su propia sección
> **Asistente** con historial.
>
> **Fase 2:** preparado para 20 personas a la vez con la cuenta gratuita de
> Groq: el router conoce la cuota de cada modelo, las preguntas esperan en cola
> con aviso en pantalla, las repetidas salen de una caché y, si la cuota se
> agota, el estudiante recibe igualmente los documentos encontrados. Ver la
> sección 5.

## 1. Qué hace

El estudiante pregunta en lenguaje normal y el asistente:

1. Busca en los documentos que esa persona puede ver (biblioteca, sus
   anotaciones y los archivos de sus grupos), por significado y por palabras.
2. Arma un **catálogo** de los documentos relacionados y los **extractos**
   numerados más relevantes.
3. Responde citando cada dato con `[1]`, `[2]`... Las citas son botones que
   muestran el extracto y abren el documento.
4. Si piden material («¿qué hay sobre bases de datos?») lista los documentos
   con su ubicación; si no hay material del tema, responde con conocimiento
   general y empieza avisándolo.

Desde cualquier documento (biblioteca, grupo o anotación) el botón **Preguntar
al asistente** limita la conversación a ese documento: sirve para resumir,
explicar partes o pedir preguntas de repaso.

Frente a la versión local anterior, que respondía «plano» y se iba poco a los
documentos, cambió lo siguiente:

| Antes | Ahora |
|---|---|
| `llama3.1:8b` local, ~70 s la primera respuesta sin GPU | Modelos en la nube (Gemini Flash, gpt-oss-120b en Groq): segundos |
| 5 fragmentos y citas por título | 6 extractos numerados + catálogo de documentos, citas `[n]` clicables |
| Sin vista de documentos relacionados | «Documentos mencionados» con enlace a cada uno |
| No se podía preguntar sobre un documento concreto | Modo documento (`doc_key`) |
| Texto plano | Markdown seguro: listas, negritas, código |
| Un solo modelo: si fallaba, no había asistente | Router con failover entre proveedores y modelos |

## 2. Router de modelos (`hub/ai/llm.py`)

Gemini, Groq, OpenRouter y Ollama exponen la misma API «compatible con OpenAI»
(`/chat/completions`, `/embeddings`), así que un único cliente con la
biblioteca estándar los sirve a todos.

- `AI_PROVIDERS=gemini,groq,openrouter,ollama` fija el orden. Cada proveedor
  puede tener varios modelos (`GEMINI_CHAT_MODELS=gemini-3.6-flash,gemini-3.5-flash-lite`).
- Ante un **429** (cuota gratuita agotada), un 5xx o un *timeout*, ese modelo
  queda «en enfriamiento» (`Retry-After` o `AI_COOLDOWN_SECONDS`) y se prueba el
  siguiente. En *streaming* conmuta si el fallo ocurre antes del primer trozo.
- Ante un **401/403** (clave inválida) el proveedor se desactiva hasta reiniciar.
- Un proveedor sin clave se ignora; Ollama sólo se usa si responde en `/api/tags`.
- El vigilante de seguridad usa su propio orden (`SECURITY_AI_PROVIDERS`) y
  sus modelos (`GROQ_SECURITY_MODELS`): el mismo `openai/gpt-oss-120b` del
  asistente, con `gpt-oss-20b` de respaldo, dejando siempre una reserva de
  tokens para las preguntas de los estudiantes (`AI_SECURITY_RESERVE_TOKENS`).
- Las citas que gpt-oss escribe a su manera (`【2】`, `【2†L1-L4】`) se convierten
  a `[2]` para que se puedan pulsar.

### Modelos configurados (octubre de 2026)

| Uso | Modelos, en orden | Cuota gratuita de cada uno |
|---|---|---|
| Asistente | `openai/gpt-oss-120b` → `qwen/qwen3.8-27b` → `openai/gpt-oss-20b` (Groq) | 8.000 tokens/min y 1.000 peticiones/día |
| Vigilante | `openai/gpt-oss-120b` → `openai/gpt-oss-20b` (Groq) | la misma (se comparte con el asistente) |
| Instrucciones ocultas | `meta-llama/llama-prompt-guard-2-86m` (Groq) | aparte |
| Respaldo opcional | Gemini (falta la clave), OpenRouter, Ollama local | — |

Los números salen de las cabeceras `x-ratelimit-*` que Groq devolvió a esta
cuenta (se ven en vivo en el panel de Seguridad). Cada modelo tiene su propia
cuota, por eso el asistente rota entre tres: suman unas 24.000 tokens por
minuto y 3.000 preguntas al día.

## 2b. Cuotas con 20 personas a la vez

Una pregunta con extractos usa entre 2.500 y 4.500 tokens (pregunta, catálogo,
cinco extractos y hasta 1.200 de respuesta, que Groq descuenta por adelantado).
Con 24.000 tokens por minuto caben **entre 5 y 8 respuestas nuevas por minuto**.

Qué hace el sistema cuando llegan más:

1. **Sabe cuánto queda.** Tras cada respuesta, el router guarda los tokens que
   le quedan a ese modelo en el minuto y las peticiones del día (Groq los rellena
   de forma continua). Antes de enviar, reserva el cupo; si no cabe, prueba el
   siguiente modelo sin llegar a provocar un error 429.
2. **Cola con aviso.** Si ningún modelo tiene cupo, la pregunta espera
   (`AI_QUEUE_TIMEOUT`, 150 s) y el navegador muestra «En cola: unos N s». La
   espera se avisa cada pocos segundos para que el túnel de Cloudflare no corte
   la conexión (lo hace a los 100 s sin datos).
3. **Caché.** La misma pregunta con los mismos extractos se responde desde
   memoria durante `AI_CACHE_MINUTES` (15). En una demostración casi todos
   preguntan lo mismo: en la prueba de carga, 41 de 59 respuestas salieron de ahí.
4. **Sin cuota, igual responde.** Si la espera se agota o la cuota del día se
   acaba, el estudiante recibe los documentos que encontró la búsqueda, con sus
   fuentes, y un aviso de cuándo volver a preguntar. No ve un error.
5. **El vigilante no estorba.** Revisa los archivos en segundo plano, sólo usa
   cupo si sobra la reserva del asistente y, sin cuota, reintenta a los 1, 5,
   15, 30 y 60 minutos (ver `SEGURIDAD.md`).

**Si se acaba la cuota del día** (1.000 peticiones por modelo): Groq responde
429 hasta que se recupera (una petición cada ~86 s). El asistente sigue dando
los documentos encontrados y el vigilante deja los archivos «En revisión» hasta
que vuelva a haber cupo. Para tener más margen: añadir `GEMINI_API_KEY` (cuota
aparte y mucho más grande por minuto) o una clave de OpenRouter.

## 3. Búsqueda (`hub/ai/index.py`)

- **Fragmentos** de ~1000 caracteres con 150 de solape, cortando al final de una frase.
- **Vectores**: `gemini-embedding-001` si hay clave de Gemini; si no,
  `nomic-embed-text` en Ollama; si no hay ninguno, sólo búsqueda por palabras.
  Cada modelo tiene su colección en ChromaDB: al cambiar de modelo los
  documentos se vuelven a vectorizar solos (un vigilante lo revisa cada 2 minutos).
- **BM25** con SQLite FTS5 (sin tildes, por prefijo).
- **Fusión** por rango recíproco (RRF, k=60) y umbral de similitud según el
  modelo de vectores (`AI_MIN_SIMILARITY` para fijarlo a mano).
- **Permisos dentro de la búsqueda**: público, privado del dueño o de los grupos
  del usuario. Salir de un grupo corta el acceso al instante.
- Sólo se indexan archivos que el vigilante dejó pasar (ver `SEGURIDAD.md`).

## 4. API

| Ruta | Qué hace |
|---|---|
| `POST /api/ai/chat` | `{question, conversation_id?, doc_key?}` → `{answer, conversation_id, sources, documents, model, search_mode}` |
| `POST /api/ai/chat/stream` | Igual, en NDJSON: `sources`, `model`, `token`..., `done` o `error` |
| `GET /api/ai/status` | Modelo activo, proveedor, modo de búsqueda y documentos accesibles |
| `GET /api/ai/conversations` | Historial de conversaciones |
| `GET /api/ai/history?conversation_id=` | Mensajes de una conversación |
| `DELETE /api/ai/conversations/<id>` | Borra una conversación |

`sources` son los extractos citados (`n`, `title`, `origin`, `page`, `snippet`,
`doc_key`); `documents`, los documentos del catálogo nombrados en la respuesta.

En *streaming* también llegan `{"type": "queue", "seconds": n}` mientras la
pregunta espera cupo, y `done` trae `cached` y `degraded` (respuesta sin IA).

## 5. Carga

- `AI_RATE_LIMIT` preguntas por usuario y minuto (12).
- `AI_MAX_CONCURRENT` respuestas generándose a la vez (6 en la nube; con Ollama
  sin GPU conviene 1) y `AI_QUEUE_TIMEOUT` de espera en cola (150 s).
- `AI_MAX_TOKENS` (1.200) limita cada respuesta; `AI_HISTORY_TURNS` (4) y el
  recorte de respuestas anteriores a 700 caracteres ahorran tokens en las
  conversaciones largas; `AI_TOP_K` (5) extractos por pregunta.
- Saludos y agradecimientos se contestan con texto fijo: no gastan cuota.
- `AI_SIMULATED=1` cambia la IA por una simulada con los mismos límites que
  Groq (`hub/ai/simulado.py`): la usa `scripts/prueba_carga.py --aislado`.

## 6. Comprobar que funciona

```bash
python manage.py ai                         # proveedores configurados y disponibles
python manage.py ai --test "¿Qué es la 3FN?" # qué modelo responde y cuánto tarda
python manage.py ai --embed "hola"          # modelo de vectores activo
python manage.py index --stats              # documentos, fragmentos y vectores
python manage.py index --query "normalización" --user 2
python -m pytest tests/test_assistant.py tests/test_llm_router.py
```

## 7. Limitaciones conocidas

- Los PDF escaneados sin capa de texto sólo se encuentran por su título y
  etiquetas (no hay OCR).
- Las cuotas gratuitas tienen límites diarios: para una prueba con 20 personas
  conviene configurar Gemini **y** Groq. Hoy sólo hay clave de Groq.
- La caché y el conocimiento de la cuota viven en memoria: se pierden al
  reiniciar el servidor (no pasa nada, se vuelven a llenar solos).
- El límite por usuario vive en memoria: con varios procesos habría que llevarlo
  a Redis (con `python wsgi.py` hay un solo proceso, así que no aplica).
