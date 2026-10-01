# UFG Knowledge Hub

Plataforma donde los estudiantes de la Universidad Francisco Gavidia comparten
recursos entre facultades: biblioteca común, grupos de trabajo, contactos, chat
y anotaciones privadas.

## Puesta en marcha

```bash
# 1. Crear el entorno virtual (el .venv del repositorio no sirve: se creó en
#    otra máquina y apunta a una ruta de Python que no existe aquí)
python -m venv .venv

# 2. Activarlo
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux / macOS

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configuración (opcional en desarrollo)
copy .env.example .env          # Windows
cp .env.example .env            # Linux / macOS

# 5. Preparar la base de datos
python init_database.py         # crea las tablas que falten, no borra nada
python init_database.py --demo  # además crea un usuario de prueba

# 6. Arrancar
python app.py
```

Abre **http://127.0.0.1:5001** en el navegador. Flask sirve la API y el frontend
en el mismo puerto, así que ya no hace falta Live Server ni configurar CORS.

## Comandos de `init_database.py`

| Comando | Qué hace |
|---|---|
| `python init_database.py` | Crea las tablas que falten. **No borra datos.** |
| `python init_database.py --demo` | Añade un usuario de prueba con contraseña aleatoria. |
| `python init_database.py --reset` | Borra la base y la recrea vacía. Pide confirmación escrita. |

## Configuración (`.env`)

| Variable | Para qué sirve |
|---|---|
| `JWT_SECRET_KEY` | Clave que firma las sesiones. Si se deja vacía se genera una y se guarda en `instance/.jwt_secret`. |
| `CORS_ORIGINS` | Orígenes autorizados, separados por comas. Sólo hace falta si sirves el frontend aparte. |
| `DATABASE_PATH` | Ruta alternativa de la base SQLite. Vacío = `instance/database.db`. |
| `FLASK_DEBUG` | `1` activa el depurador de Werkzeug. **Déjalo en 0** salvo que estés depurando. |
| `APP_HOST` / `APP_PORT` | Dirección y puerto de `python app.py`. Vacío = `127.0.0.1:5001`. |
| `OLLAMA_URL`, `OLLAMA_MODEL`... | Configuración del asistente de IA. Ver `docs/ASISTENTE_IA.md`. |

## Estructura

```
app.py              API Flask y modelos de datos
ai_service.py       Asistente de IA: búsqueda en documentos + Ollama
wsgi.py             Entrada para servidores de producción (waitress/gunicorn)
init_database.py    Utilidad de base de datos
index.html          Página única que carga la aplicación
js/config.js        URL de la API (detecta si la sirve Flask)
js/api.js           Cliente HTTP
js/ai.js            Cliente del asistente de IA
js/ui.js            Plantillas HTML
js/app.js           Estado, vistas y eventos
css/style.css       Estilos propios
docs/               Documentación y capturas del sistema
uploads/            Archivos subidos (fuera del control de versiones)
instance/           Base de datos y clave JWT (fuera del control de versiones)
```

## Asistente de IA

> **Hoy funciona en local** (Flask y Ollama en la misma PC). El proyecto está
> preparado para desplegarse en un servidor cambiando sólo el `.env`.

Botón flotante en la esquina inferior derecha. Responde preguntas sobre los
documentos de la plataforma usando **Ollama + Llama 3.1 8B** y cita las fuentes
de cada respuesta. Sólo consulta lo que el usuario tiene permiso de ver: la
biblioteca pública, sus propias anotaciones y los recursos de sus grupos.

```powershell
winget install Ollama.Ollama
ollama pull llama3.1:8b
```

Con Ollama en marcha, `python app.py` lo detecta solo. Si no está disponible, el
widget lo avisa y el resto de la aplicación funciona igual.

| Endpoint | Función |
|---|---|
| `POST /api/ai/chat` | Recibe la pregunta, devuelve respuesta y fuentes |
| `GET /api/ai/status` | Indica si el modelo está disponible |
| `GET /api/ai/history` | Historial de una conversación |

Arquitectura, configuración, pruebas de permisos y **guía de paso a servidor**:
[`docs/ASISTENTE_IA.md`](docs/ASISTENTE_IA.md).

## Notas de seguridad

- Los archivos **privados** y los de **grupo** sólo se descargan con sesión
  iniciada y comprobando que quien pide es el dueño o un miembro del grupo. No
  los sirvas nunca como archivos estáticos.
- Sólo se aceptan las extensiones de `ALLOWED_EXTENSIONS` (`app.py`). `.html` y
  `.svg` están excluidos a propósito porque pueden ejecutar JavaScript.
- Todo texto que escribe un usuario se pasa por `escapeHtml()` antes de
  insertarse en la página (`js/ui.js`).
- No subas `.env` ni `instance/` al repositorio.
