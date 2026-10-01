# Asistente de IA — UFG Knowledge Hub

> **Estado actual: funcionando en LOCAL.**
> El asistente corre hoy en una sola PC: la app Flask y Ollama (con el modelo
> `llama3.1:8b`) están en la misma máquina y se comunican por `127.0.0.1`.
>
> **El proyecto está preparado para moverse a un servidor** sin cambiar código:
> todas las direcciones, puertos y el modelo se leen de variables de entorno
> (`.env`), y existe un punto de entrada de producción (`wsgi.py`). La sección
> [Paso a servidor](#paso-a-servidor) explica qué cambiar el día que se
> despliegue.

---

## 1. Qué hace

El botón flotante de la esquina inferior derecha abre un chat donde el estudiante
pregunta en lenguaje natural sobre el material de la plataforma:

- «¿Qué es la tercera forma normal?»
- «¿Qué material hay sobre redes?»
- «Resume mis apuntes de cálculo»

El asistente **busca primero en los documentos que ese estudiante puede ver**,
entrega los fragmentos encontrados al modelo y responde citando de dónde sacó la
información. Debajo de cada respuesta aparecen las **Fuentes** (título, origen y
un extracto), para que el estudiante pueda comprobarlo.

Si no encuentra la respuesta en los documentos, lo dice explícitamente en lugar
de inventarla.

## 2. Arquitectura

```
 Navegador (index.html + js/)
   │  js/ai.js  ──  POST /api/ai/chat   { question, conversation_id }
   ▼
 Flask (app.py)  ─────────────────────────────────────────────────────────
   │ 1. Verifica el JWT (usuario con sesión)
   │ 2. collect_ai_documents(user_id)   ◄── FILTRO DE PERMISOS
   │      · Biblioteca pública           (todos)
   │      · Anotaciones privadas         (sólo las del propio usuario)
   │      · Recursos de grupo            (sólo grupos de los que es miembro)
   ▼
 ai_service.py ───────────────────────────────────────────────────────────
   │ 3. extract_text()   txt/md/csv/pdf/docx → texto (con caché en memoria)
   │ 4. search()         trocea en fragmentos y los ordena con BM25
   │ 5. answer()         prompt = reglas + fragmentos + historial + pregunta
   ▼
 Ollama  (http://127.0.0.1:11434)  ── modelo llama3.1:8b
   │
   ▼
 Respuesta + fuentes → se guarda en la BD (ai_conversation / ai_message)
                     → se devuelve al navegador
```

Este patrón se llama **RAG** (*Retrieval-Augmented Generation*): el modelo no
«sabe» lo que hay en la plataforma; se le entrega en cada pregunta.

### Archivos implicados

| Archivo | Papel |
|---|---|
| `ai_service.py` | **Nuevo.** Cliente de Ollama, extracción de texto, búsqueda BM25 y prompt. No conoce la BD ni Flask. |
| `app.py` | Modelos `AIConversation` / `AIMessage`, función `collect_ai_documents()` (permisos) y los endpoints `/api/ai/*`. |
| `wsgi.py` | **Nuevo.** Punto de entrada para servidores de producción (waitress / gunicorn). |
| `js/ai.js` | Cliente del asistente en el navegador (ya existía; sólo se actualizaron comentarios). |
| `js/ui.js` | Panel del chat. Ahora muestra el origen de cada fuente y respeta los saltos de línea. |
| `.env.example` | Nuevas variables `OLLAMA_*`, `AI_TOP_K`, `APP_HOST`, `APP_PORT`. |
| `requirements.txt` | Añade `pypdf` y `python-docx` para leer PDF y Word. |

### Por qué el filtro de permisos está antes de la búsqueda

Los documentos se filtran **antes** de buscar y antes de construir el prompt. Si
se filtraran después, el modelo ya habría leído la nota privada de otro
estudiante y podría repetirla en la respuesta. `ai_service.py` sólo recibe
documentos ya autorizados, así que no hay forma de saltarse el filtro desde ahí.

Esto está probado: un usuario pregunta por una contraseña guardada en la nota
privada de otro y el asistente responde que no lo encontró; el dueño de la nota
hace la misma pregunta y sí obtiene la respuesta, con la nota como fuente.

## 3. API

Todos los endpoints requieren sesión (`Authorization: Bearer <token>`).

### `GET /api/ai/status`

```json
{ "available": true, "model": "llama3.1:8b", "indexed_documents": 37 }
```

`available` es `false` si Ollama no responde o el modelo no está descargado. El
widget muestra entonces un aviso y deshabilita el campo de escritura. Con
`FLASK_DEBUG=1` se añade `detail` con el motivo exacto.

### `POST /api/ai/chat`

Petición:
```json
{ "question": "¿Qué es la 3FN?", "conversation_id": null }
```

Respuesta:
```json
{
  "answer": "La tercera forma normal (3FN) elimina dependencias transitivas. [Apuntes de Bases de Datos]",
  "conversation_id": "8f0c…",
  "sources": [
    { "resource_id": 12, "type": "public", "title": "Apuntes de Bases de Datos",
      "origin": "Biblioteca", "snippet": "…", "score": 1.0 }
  ]
}
```

- `type`: `public`, `private_note`, `private_file` o `group`.
- `score`: relevancia relativa (1.0 = el fragmento más relevante).
- Enviar el `conversation_id` recibido permite preguntas de seguimiento
  («¿y la segunda?»); se envían al modelo los últimos 6 mensajes.
- **503** si Ollama no responde; **400** si la pregunta está vacía o supera los
  2000 caracteres.

### `GET /api/ai/history?conversation_id=<uuid>`

Devuelve los mensajes de una conversación propia. 404 si no existe o es de otro
usuario.

## 4. Puesta en marcha en local (situación actual)

Requisitos de la PC: Windows 10/11, Python 3.12, **16 GB de RAM recomendados**
(el modelo ocupa unos 5 GB en memoria). En la PC de pruebas (31 GB de RAM) las
respuestas tardaron 1–5 s; en equipos sin GPU dedicada pueden tardar de 30 s a
más de un minuto.

```powershell
# 1. Ollama y el modelo (una sola vez)
winget install Ollama.Ollama
ollama pull llama3.1:8b

# 2. Proyecto
git clone https://github.com/PatoPsicko/UFG-KnowledgeHub
cd UFG-KnowledgeHub
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python init_database.py          # crea también las tablas del asistente

# 3. Arrancar
python app.py
```

Abrir **http://127.0.0.1:5001**, iniciar sesión y pulsar el botón azul de abajo
a la derecha. El punto verde junto a «Asistente IA» indica que el modelo está
conectado.

Ollama se instala como servicio y arranca solo con Windows. Para comprobarlo:

```powershell
ollama list                      # debe aparecer llama3.1:8b
curl http://127.0.0.1:11434      # "Ollama is running"
```

## 5. Configuración (`.env`)

| Variable | Por defecto | Para qué sirve |
|---|---|---|
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Dónde está Ollama. En servidor puede ser otra máquina. |
| `OLLAMA_MODEL` | `llama3.1:8b` | Modelo que responde. Debe estar descargado (`ollama pull`). |
| `OLLAMA_TIMEOUT` | `300` | Segundos máximos de espera por respuesta. |
| `OLLAMA_NUM_CTX` | `4096` | Ventana de contexto en tokens. Más alto = más RAM. |
| `OLLAMA_KEEP_ALIVE` | `30m` | Tiempo que el modelo queda cargado tras la última pregunta. |
| `AI_TOP_K` | `4` | Fragmentos de documentos que se envían al modelo por pregunta. |
| `APP_HOST` | `127.0.0.1` | Dirección de escucha de `python app.py`. |
| `APP_PORT` | `5001` | Puerto de `python app.py`. |

## 6. Paso a servidor

El código ya no tiene direcciones fijas, así que desplegarlo es cuestión de
configuración:

1. **Instalar Ollama en el servidor** (o en una máquina con GPU de la red) y
   descargar el modelo: `ollama pull llama3.1:8b`.
   - Si Ollama está en **otra máquina**, arrancarlo con
     `OLLAMA_HOST=0.0.0.0` y poner en el `.env` de la app
     `OLLAMA_URL=http://<ip-de-esa-maquina>:11434`.
   - **No exponer el puerto 11434 a Internet**: Ollama no tiene autenticación.
     Sólo debe ser accesible desde la app (red interna o firewall).
2. **Configurar el `.env`** del servidor:
   - `JWT_SECRET_KEY` propia (`python -c "import secrets; print(secrets.token_urlsafe(48))"`).
   - `FLASK_DEBUG=0`.
   - `CORS_ORIGINS` sólo si el frontend se sirve desde otro dominio.
3. **Usar un servidor WSGI** en lugar de `python app.py`:
   ```bash
   # Linux
   pip install gunicorn
   gunicorn --bind 0.0.0.0:5001 --workers 2 --timeout 300 wsgi:app

   # Windows Server
   pip install waitress
   waitress-serve --host 0.0.0.0 --port 5001 wsgi:app
   ```
   El `--timeout 300` es importante: sin GPU una respuesta puede tardar más de
   los 30 s que gunicorn permite por defecto.
4. **Poner HTTPS delante** (Nginx, Caddy o IIS como proxy inverso). Los tokens
   de sesión viajan en cada petición y no deben ir en texto plano.
5. **Hardware**: para varios usuarios simultáneos conviene una GPU con ≥ 8 GB de
   VRAM. Ollama atiende las peticiones de una en una por defecto
   (`OLLAMA_NUM_PARALLEL` permite más, a cambio de memoria).

## 7. Limitaciones conocidas y siguientes pasos

| Limitación | Mejora prevista |
|---|---|
| La búsqueda es por **palabras clave** (BM25): no entiende sinónimos («coche» ≠ «automóvil»). | Búsqueda semántica con embeddings (`ollama pull nomic-embed-text`) y un índice vectorial (ChromaDB o `sqlite-vec`). |
| El texto de los archivos se extrae en memoria y se recalcula al reiniciar la app. Con miles de PDFs la primera pregunta tras arrancar será lenta. | Índice persistente que se actualice al subir, editar o borrar un recurso. |
| Sólo se lee el texto de `txt`, `md`, `csv`, `pdf` y `docx`. PowerPoint, Excel e imágenes participan sólo por título, autor, categoría y etiquetas. | Añadir extractores (`python-pptx`, `openpyxl`, OCR). |
| PDFs escaneados (imagen) no tienen texto extraíble. | OCR (Tesseract). |
| La respuesta llega completa, no palabra por palabra. | Streaming (`stream: true` en Ollama + Server-Sent Events). |
| Sin límite de preguntas por usuario. | Límite de uso (p. ej. Flask-Limiter) antes de abrirlo a toda la universidad. |
