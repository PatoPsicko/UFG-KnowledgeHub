# Asistente de IA — UFG Knowledge Hub

> **Fase 1 (octubre de 2026):** el asistente ya no depende de un modelo local.
> Un router de modelos usa proveedores gratuitos en la nube (Gemini, Groq,
> OpenRouter) y deja Ollama como respaldo. Se movió del botón flotante a la
> página de **Inicio** (donde estaba el chat global) y tiene su propia sección
> **Asistente** con historial.

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
  modelos más pequeños, así no compite con el asistente por la misma cuota.

Las cuotas gratuitas cambian a menudo y dependen de cada proyecto: los límites
reales se ven en Google AI Studio y en la consola de Groq. Con varios
proveedores configurados, el sitio sigue respondiendo aunque uno se agote a
media clase.

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

## 5. Carga

- `AI_RATE_LIMIT` preguntas por usuario y minuto (12).
- `AI_MAX_CONCURRENT` respuestas generándose a la vez (6 en la nube; con Ollama
  sin GPU conviene 1) y `AI_QUEUE_TIMEOUT` de espera en cola.
- Saludos y agradecimientos se contestan con texto fijo: no gastan cuota.

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
  conviene configurar Gemini **y** Groq.
- El límite por usuario vive en memoria: con varios procesos habría que llevarlo
  a Redis (con `python wsgi.py` hay un solo proceso, así que no aplica).
