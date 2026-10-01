# Asistente de IA — UFG Knowledge Hub

> **Estado actual: implementado y funcionando en LOCAL.**
> Hoy todo corre en una sola PC: la app Flask, Ollama (con `llama3.1:8b` y
> `nomic-embed-text`) y el índice de búsqueda (ChromaDB + SQLite FTS5) están en
> la misma máquina y se comunican por `127.0.0.1`.
>
> **El proyecto está preparado para moverse a un servidor** sin cambiar código:
> direcciones, puertos, modelos y parámetros se leen de variables de entorno
> (`.env`), existe un punto de entrada de producción (`wsgi.py`) y ChromaDB
> puede pasar a modo servidor con una variable. La sección
> [Paso a servidor](#8-paso-a-servidor) explica qué cambiar.

Este documento describe la **implementación** del diseño presentado en
*Integración de inteligencia artificial en la plataforma UFG Knowledge Hub*
(septiembre de 2026). Las referencias «sección X» remiten a ese documento.

---

## 1. Qué hace

El botón flotante de la esquina inferior derecha abre un chat. El estudiante
pregunta en lenguaje normal («¿cómo evito datos repetidos en una tabla?») y
recibe una respuesta construida **sólo** a partir de los documentos que tiene
permiso de ver, con las **fuentes** citadas (título, página y origen) para que
pueda comprobarlas. La respuesta aparece palabra por palabra mientras se genera.

Si la información no está en los documentos responde exactamente:
*«No encontré esa información en los documentos de la plataforma.»* — no
completa con conocimiento propio (sección 5.9).

## 2. Qué se implementó del documento de diseño

| Documento | Implementación | Dónde |
|---|---|---|
| 4.4 Dos modelos en Ollama | `llama3.1:8b` (respuestas) y `nomic-embed-text` (vectores de 768 dim.) | `ai_service.py` |
| 5.1 Fragmentación 500–1000 car., ~100 de solape, con metadatos | 800 / 100, por página; cada fragmento guarda recurso, propietario, acceso, grupo y página | `ai_index.py` → `fragmentar`, `Indice.indexar` |
| 5.2–5.3 Vectores + similitud coseno | Colección ChromaDB con espacio `cosine`; prefijos `search_query:` / `search_document:` de nomic | `ai_index.py` |
| 5.4 Índice HNSW | El de ChromaDB | `ai_index.py` → `coleccion()` |
| 5.5 Búsqueda híbrida + RRF (k = 60) | Vectorial (20) + BM25 sobre FTS5 (20), fusión por rango recíproco | `Indice.buscar` |
| 5.6 Filtro de permisos **dentro** de la búsqueda | `where` de ChromaDB y `WHERE` de FTS5 con la misma condición | `_filtro_chroma`, `_filtro_sql` |
| 5.7 Quedarse con los 5 mejores | `AI_TOP_K=5` | `Indice.buscar` |
| 5.9 Instrucciones estrictas al modelo | Prompt del documento + defensa contra instrucciones dentro de los documentos | `ai_service.SYSTEM_PROMPT` |
| 6.4 Rutas `/api/ai/chat` y `/api/ai/status` | Contrato respetado, más `/api/ai/chat/stream` y `/api/ai/history` | `app.py` |
| Etapa 1: comprobación desde consola | `python ai_index.py --query "..." --user N` | `ai_index.py` |
| Etapa 4: indexar al subir, quitar al borrar | Cola en segundo plano tras cada alta, edición o borrado | `app.py` → `ai_reindex`, `ai_unindex` |
| Etapa 4: streaming | NDJSON desde Ollama hasta el navegador | `/api/ai/chat/stream`, `js/ai.js` |
| Etapa 4: medir tiempos | Cada respuesta devuelve y registra `timings_ms` | `app.py` |
| Riesgo: varias preguntas a la vez | Límite por usuario (10/min) y cola de generación (2 simultáneas) | `ai_service.limitador`, `cola_modelo` |
| Riesgo: PDF escaneados | Se detectan y se marcan con estado `sin_texto` | `extraer_paginas` |
| Riesgo: índice desactualizado | Indexado al subir/editar/borrar + sincronización al arrancar | `iniciar_asistente` |

## 3. Arquitectura

```
 Navegador (index.html + js/)
   │  js/ai.js ── POST /api/ai/chat/stream  { question, conversation_id }
   ▼
 Flask (app.py)
   │ 1. Valida el JWT y el límite de preguntas por minuto
   │ 2. Lee los grupos del usuario  → condición de permisos
   ▼
 ai_index.py ── búsqueda híbrida ──────────────────────────────────────────
   │ 3. Pregunta → vector (nomic-embed-text)
   │ 4. ChromaDB / HNSW   20 candidatos  ┐ el filtro de permisos va DENTRO
   │ 5. SQLite FTS5 / BM25 20 candidatos ┘ de las dos consultas
   │ 6. Fusión por rango recíproco → 5 mejores fragmentos
   ▼
 ai_service.py ────────────────────────────────────────────────────────────
   │ 7. Prompt = instrucciones + historial + fragmentos + pregunta
   │ 8. Turno en la cola (máx. 2 generaciones a la vez)
   │ 9. llama3.1:8b redacta, en streaming
   ▼
 Navegador: texto en vivo + fuentes citadas
 BD: la conversación se guarda en ai_conversation / ai_message
```

**Indexado** (independiente de las preguntas):

```
 Subir / editar / borrar recurso ──► app.py ──► cola ──► hilo "ai-indexador"
                                                         │ extraer texto (pypdf, python-docx)
                                                         │ fragmentar (800 / 100)
                                                         │ vectores (nomic-embed-text)
                                                         ├─► ChromaDB  (instance/ai_index/chroma)
                                                         └─► FTS5      (instance/ai_index/fts.sqlite3)
 Arranque de la app ──► sincronización: indexa lo nuevo o modificado, quita lo borrado
```

La subida de un archivo no espera a que termine el indexado: el usuario recibe
la confirmación y el documento pasa a estar disponible para el asistente unos
segundos después.

### Archivos

| Archivo | Papel |
|---|---|
| `ai_service.py` | Cliente de Ollama (respuesta, streaming, embeddings), prompt, límite por usuario y cola. |
| `ai_index.py` | Extracción, fragmentación, ChromaDB, FTS5, búsqueda híbrida, cola de indexado y herramienta de consola. |
| `app.py` | Qué documentos existen y quién puede verlos (`ai_spec_*`, `ai_user_group_ids`), rutas `/api/ai/*`, modelos `AIConversation` y `AIMessage`, ganchos de indexado. |
| `wsgi.py` | Entrada para servidores de producción. |
| `js/ai.js` | Cliente del navegador, incluido el lector del streaming. |
| `js/app.js`, `js/ui.js` | Panel del chat: texto en vivo, fuentes con página y origen. |

### Los tres tipos de documento (sección 3.2)

| Tipo (`kind`) | Acceso | Quién lo encuentra |
|---|---|---|
| `public` — Biblioteca | `publico` | Cualquier usuario registrado |
| `group` — Recursos de grupo | `grupo` | Sólo miembros del grupo |
| `private_note`, `private_file` — Anotaciones | `privado` | Sólo el propietario |

La condición que acompaña a **cada** búsqueda, tal como la define la sección 5.6:

```
acceso = 'publico'
  OR (acceso = 'privado' AND propietario = <usuario actual>)
  OR (acceso = 'grupo'   AND grupo IN <grupos del usuario>)
```

Los grupos del usuario se consultan en cada pregunta, así que quien sale de un
grupo deja de ver sus documentos de inmediato, sin reindexar nada.

## 4. Pruebas realizadas

Prueba automática de punta a punta con 3 usuarios, 6 documentos (Word, txt, PDF
escaneado, nota privada y recurso de grupo). **26 de 26 comprobaciones
correctas:**

| Comprobación | Resultado |
|---|---|
| Indexado de los 6 documentos, con vectores en ChromaDB | ✔ |
| PDF escaneado detectado y marcado `sin_texto` | ✔ |
| «cómo evitar datos repetidos en una tabla» encuentra la *Guía de laboratorio 4*, cuyo título no menciona la normalización (problemas de cobertura y de vocabulario, sección 2.1) | ✔ 1.ª posición |
| «IDS-104» (código de materia) encuentra el programa de la materia gracias a BM25 (sección 5.5) | ✔ 1.ª posición |
| La nota privada de un usuario **no** aparece a otros, ni en la búsqueda vectorial ni en la BM25 | ✔ |
| Un recurso de grupo sólo aparece a sus miembros | ✔ |
| Un usuario pregunta por la contraseña guardada en la nota privada de otro → «No encontré…» | ✔ |
| Pregunta fuera de los documentos («¿quién ganó el mundial de 1986?») → «No encontré…», sin fuentes | ✔ |
| El dueño de la nota sí obtiene la respuesta, con su nota como única fuente | ✔ |
| Pregunta de seguimiento («¿y qué dice de la segunda?») | ✔ |
| Streaming: fuentes → trozos de texto → fin | ✔ |
| Al borrar un recurso desaparece del índice | ✔ |
| Más de N preguntas por minuto → HTTP 429 | ✔ |
| El historial de una conversación sólo lo ve su dueño | ✔ |

**Tiempos medidos en la PC de pruebas** (31 GB de RAM, índice pequeño):

| Paso | Tiempo |
|---|---|
| Búsqueda vectorial (incluye calcular el vector de la pregunta) | 15–45 ms |
| Búsqueda BM25 (FTS5) | 1–2 ms |
| Generación de la respuesta (llama3.1:8b) | 0,4–0,9 s |
| Primera pregunta tras arrancar (Ollama carga los modelos) | ~6 s |

Como anticipa la sección 5.8, la búsqueda tarda milisegundos y el tiempo que
percibe el estudiante lo marca la generación. En equipos sin GPU dedicada la
generación será mucho más lenta (sección 7); el streaming hace que el texto
empiece a verse enseguida aunque tarde en completarse.

## 5. API

Todos los endpoints requieren sesión (`Authorization: Bearer <token>`).

### `GET /api/ai/status`

```json
{ "available": true, "model": "llama3.1:8b", "embedding_model": "nomic-embed-text",
  "search_mode": "hibrido", "indexed_documents": 37 }
```

- `indexed_documents`: documentos indexados **que ese usuario puede consultar**.
- `search_mode`: `hibrido`, o `lexico` si falta ChromaDB o `nomic-embed-text`
  (el asistente sigue funcionando sólo con BM25).
- Con `FLASK_DEBUG=1` se añade `detail` con el estado de los modelos.

### `POST /api/ai/chat`

```json
// petición
{ "question": "¿Qué es la 3FN?", "conversation_id": null }

// respuesta
{
  "answer": "La tercera forma normal elimina dependencias transitivas. [Guía de laboratorio 4]",
  "conversation_id": "8f0c…",
  "sources": [
    { "resource_id": 12, "type": "public", "title": "Guía de laboratorio 4",
      "origin": "Biblioteca", "page": null, "snippet": "…", "score": 1.0 }
  ],
  "search_mode": "hibrido",
  "timings_ms": { "vectorial": 44.0, "bm25": 1.3, "generacion": 742 }
}
```

- `sources` contiene **sólo los documentos que la respuesta cita**. Si la
  respuesta es «No encontré…», va vacío.
- `page` es el número de página en los PDF; `null` en otros formatos.
- Errores: **400** pregunta vacía o de más de 2000 caracteres; **429** límite de
  preguntas por minuto; **503** Ollama no responde o la cola está llena.

### `POST /api/ai/chat/stream`

Misma petición. Respuesta `application/x-ndjson`, un objeto por línea:

```
{"type": "sources", "sources": [...candidatos...], "search_mode": "hibrido"}
{"type": "token", "content": "La tercera"}
{"type": "token", "content": " forma normal..."}
{"type": "done", "conversation_id": "…", "sources": [...citadas...], "timings_ms": {...}}
```

o `{"type": "error", "message": "..."}` si el modelo falla a mitad. El widget
usa esta ruta; si no existiera, recurre automáticamente a `/api/ai/chat`.

### `GET /api/ai/history?conversation_id=<uuid>`

Mensajes de una conversación propia. 404 si no existe o es de otro usuario.

## 6. Puesta en marcha en local (situación actual)

Requisitos: Windows 10/11, Python 3.12, **16 GB de RAM recomendados**.

```powershell
# 1. Ollama y los dos modelos (una sola vez)
winget install Ollama.Ollama
ollama pull llama3.1:8b
ollama pull nomic-embed-text

# 2. Proyecto
git clone https://github.com/PatoPsicko/UFG-KnowledgeHub
cd UFG-KnowledgeHub
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python init_database.py --demo

# 3. Arrancar
.venv\Scripts\python app.py
```

Abrir **http://127.0.0.1:5001**, iniciar sesión y pulsar el botón azul de abajo
a la derecha. El punto verde junto a «Asistente IA» indica que el modelo está
conectado.

Ollama se instala como servicio y arranca con Windows. Comprobación:

```powershell
ollama list                      # deben aparecer llama3.1:8b y nomic-embed-text
curl http://127.0.0.1:11434      # "Ollama is running"
```

### Herramienta de consola del índice

```powershell
.venv\Scripts\python ai_index.py --stats              # documentos, fragmentos, vectores, estados
.venv\Scripts\python ai_index.py --sync               # indexa lo pendiente
.venv\Scripts\python ai_index.py --rebuild            # rehace el índice desde cero
.venv\Scripts\python ai_index.py --query "cómo evitar datos repetidos" --user 1
```

`--query` muestra los 5 fragmentos elegidos, su posición en cada lista
(vectorial y BM25) y los tiempos: es la comprobación de las etapas 1 y 2.

`--rebuild` es necesario si se cambia `AI_CHUNK_SIZE`, `AI_CHUNK_OVERLAP` u
`OLLAMA_EMBED_MODEL`, porque los vectores antiguos no son comparables con los
nuevos.

## 7. Configuración (`.env`)

| Variable | Por defecto | Para qué sirve |
|---|---|---|
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Dónde está Ollama. |
| `OLLAMA_MODEL` | `llama3.1:8b` | Modelo que redacta. |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Modelo de vectores. |
| `OLLAMA_TIMEOUT` | `300` | Segundos máximos por respuesta. |
| `OLLAMA_NUM_CTX` | `4096` | Ventana de contexto (más = más RAM). |
| `OLLAMA_KEEP_ALIVE` | `30m` | Tiempo que los modelos quedan cargados. |
| `AI_INDEX_DIR` | `instance/ai_index` | Carpeta del índice. |
| `CHROMA_HOST` / `CHROMA_PORT` | vacío / `8000` | ChromaDB en modo servidor. Vacío = embebido. |
| `AI_CHUNK_SIZE` / `AI_CHUNK_OVERLAP` | `800` / `100` | Fragmentación (sección 5.1). |
| `AI_CANDIDATES` | `20` | Candidatos por búsqueda (sección 5.7). |
| `AI_TOP_K` | `5` | Fragmentos que llegan al modelo (sección 5.7). |
| `AI_RATE_LIMIT` | `10` | Preguntas por usuario y minuto. |
| `AI_MAX_CONCURRENT` | `2` | Respuestas generándose a la vez. |
| `AI_QUEUE_TIMEOUT` | `120` | Segundos de espera en cola antes de «ocupado». |
| `APP_HOST` / `APP_PORT` | `127.0.0.1` / `5001` | Dirección de `python app.py`. |

## 8. Paso a servidor

El código no tiene direcciones fijas: desplegar es cuestión de configuración.

1. **Ollama en el servidor** (o en una máquina con GPU de la red interna):
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ollama pull llama3.1:8b
   ollama pull nomic-embed-text
   ```
   Si está en otra máquina: arrancarlo con `OLLAMA_HOST=0.0.0.0` y poner en el
   `.env` de la app `OLLAMA_URL=http://<ip>:11434`.
   **Nunca exponer el puerto 11434 a Internet**: Ollama no tiene autenticación.
2. **`.env` del servidor**: `JWT_SECRET_KEY` propia, `FLASK_DEBUG=0`, y
   `CORS_ORIGINS` sólo si el frontend se sirve desde otro dominio.
3. **Servidor WSGI** en lugar de `python app.py`:
   ```bash
   # Linux
   pip install gunicorn
   gunicorn --bind 0.0.0.0:5001 --workers 1 --threads 8 --timeout 300 wsgi:app

   # Windows Server
   pip install waitress
   waitress-serve --host 0.0.0.0 --port 5001 --threads 8 wsgi:app
   ```
   - `--timeout 300`: sin GPU una respuesta puede superar los 30 s por defecto.
   - **Un proceso con varios hilos** es la configuración recomendada con
     ChromaDB embebido. Para varios procesos (`--workers N`) hay que levantar
     ChromaDB como servicio (`chroma run --path /srv/chroma --port 8000`) y
     definir `CHROMA_HOST`; además el límite por usuario y la cola pasan a
     contarse por proceso (para un límite global haría falta Redis).
4. **HTTPS delante** (Nginx, Caddy o IIS como proxy inverso). Con Nginx, el
   streaming necesita `proxy_buffering off;` en la ruta `/api/ai/` (la app ya
   envía `X-Accel-Buffering: no`).
5. **Hardware** (sección 7): sin GPU, 16 GB de RAM mínimo y respuestas de 20–40 s;
   con GPU de 8 GB de VRAM, 2–5 s. Si el servidor no tiene GPU, probar primero
   un modelo de 3B (`OLLAMA_MODEL=llama3.2:3b`) y medir si la calidad alcanza.
6. **Primera indexación**: al arrancar, la app indexa en segundo plano todo lo
   que haya. Con muchos documentos conviene hacerlo antes con
   `python ai_index.py --sync` y ver el resultado con `--stats`.

## 9. Limitaciones conocidas

| Limitación | Posible mejora |
|---|---|
| PDF escaneados: se detectan (`sin_texto`) pero sólo se encuentran por su título y metadatos. | OCR con Tesseract (fuera del alcance de esta etapa, sección 9). |
| PowerPoint, Excel e imágenes participan sólo por título, autor, categoría y etiquetas. | Extractores `python-pptx`, `openpyxl`. |
| No hay reordenador (*reranker*) tras la fusión. | Segunda fase prevista en la sección 5.7. |
| El borrado del índice ocurre justo después del commit en la BD, no en la misma transacción (ChromaDB no participa en transacciones de SQLite). Si fallara, la sincronización del siguiente arranque lo corrige. | — |
| Límite por usuario y cola viven en memoria del proceso. | Redis si se usan varios procesos. |
| El prompt es estricto a propósito (sección 5.9): si se pide «explica cada capa» y el documento sólo las enumera, responde «No encontré…» en lugar de completar con conocimiento propio. | Es el comportamiento buscado; se puede relajar en `ai_service.SYSTEM_PROMPT` si se prefiere. |
| Detrás de algunos proxys o servidores WSGI el streaming puede llegar agrupado en bloques en vez de palabra por palabra. | Comprobarlo en el servidor real; la respuesta llega completa igualmente. |
