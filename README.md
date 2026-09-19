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

## Estructura

```
app.py              API Flask y modelos de datos
init_database.py    Utilidad de base de datos
index.html          Página única que carga la aplicación
js/config.js        URL de la API (detecta si la sirve Flask)
js/api.js           Cliente HTTP
js/ai.js            Cliente del asistente de IA (pendiente de backend)
js/ui.js            Plantillas HTML
js/app.js           Estado, vistas y eventos
css/style.css       Estilos propios
docs/               Documentación y capturas del sistema
uploads/            Archivos subidos (fuera del control de versiones)
instance/           Base de datos y clave JWT (fuera del control de versiones)
```

## Asistente de IA (en preparación)

La interfaz del asistente ya está integrada: botón flotante en la esquina
inferior derecha, panel de conversación y presentación de fuentes citadas.

**El backend todavía no existe.** Mientras `/api/ai/*` devuelva 404, el widget
muestra un aviso y deja el campo de escritura deshabilitado, en lugar de fallar.

Para activarlo hay que implementar en `app.py` los tres endpoints descritos en la
cabecera de `js/ai.js`:

| Endpoint | Función |
|---|---|
| `POST /api/ai/chat` | Recibe la pregunta, devuelve respuesta y fuentes |
| `GET /api/ai/status` | Indica si el modelo está disponible |
| `GET /api/ai/history` | Historial de una conversación (opcional) |

El plan completo —arquitectura RAG, instalación de Ollama, requisitos de
hardware y fases— está en `docs/UFG_Knowledge_Hub_Documentacion.docx`.

> **Importante al implementarlo:** el índice contendrá recursos públicos,
> privados y de grupo. El filtro por permisos debe aplicarse **en la búsqueda**,
> antes de construir el prompt. Si se filtra después, el asistente puede acabar
> citando la nota privada de otro estudiante.

## Notas de seguridad

- Los archivos **privados** y los de **grupo** sólo se descargan con sesión
  iniciada y comprobando que quien pide es el dueño o un miembro del grupo. No
  los sirvas nunca como archivos estáticos.
- Sólo se aceptan las extensiones de `ALLOWED_EXTENSIONS` (`app.py`). `.html` y
  `.svg` están excluidos a propósito porque pueden ejecutar JavaScript.
- Todo texto que escribe un usuario se pasa por `escapeHtml()` antes de
  insertarse en la página (`js/ui.js`).
- No subas `.env` ni `instance/` al repositorio.
