# UFG Knowledge Hub

Plataforma donde los estudiantes de la Universidad Francisco Gavidia comparten
material entre facultades: biblioteca común, asistente de estudio con IA,
grupos de trabajo (chat, tablero de tareas y archivos) y «Mi espacio» con notas
y archivos privados. Cada archivo que se sube pasa por un vigilante de seguridad
antes de publicarse.

**Fase 1** (octubre de 2026): IA en la nube con varios proveedores gratuitos,
vigilante de archivos, rediseño completo con modo oscuro y grupos de trabajo
terminados. Detalle en [`docs/FASE_1.md`](docs/FASE_1.md).

## Puesta en marcha

**Lo más fácil:** doble clic en `iniciar.bat`. La primera vez crea el entorno,
instala las dependencias y pide la clave gratuita de Groq; después arranca el
servidor directamente.

A mano:

```bash
python -m venv .venv
.venv\Scripts\activate              # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env              # Linux/macOS: cp .env.example .env
```

Abre `.env` y pega al menos una clave de IA gratuita (ver abajo). Luego:

```bash
python wsgi.py                      # servidor para varias personas (waitress, 32 hilos)
```

Abre **http://127.0.0.1:5001**. La base de datos se crea y se actualiza sola al
arrancar: no hace falta ningún editor de bases de datos.

| Comando | Para qué |
|---|---|
| `python app.py` | Servidor de desarrollo (sólo esta PC). |
| `python wsgi.py` | Servidor para pruebas con 20+ personas a la vez. |
| `python manage.py demo` | Crea un usuario de prueba con contraseña aleatoria. |
| `python manage.py admin correo@ufg.edu.sv` | Da acceso al panel de Seguridad. |
| `python manage.py ai --test "pregunta"` | Comprueba qué modelo de IA responde. |
| `python manage.py scan archivo.pdf` | Pasa un archivo por las 3 barreras del vigilante. |
| `python manage.py index --stats` | Estado del índice de búsqueda del asistente. |
| `python manage.py db --reset` | Borra la base y la deja vacía (pide confirmación). |
| `python seed_test_data.py` | Con el servidor encendido: 8 usuarios, 100 documentos, grupos y mensajes. |
| `python -m pytest` | 58 pruebas automáticas del backend. |
| `python scripts/prueba_carga.py` | Simula 20 estudiantes usando el sitio a la vez. |

## IA gratis en la nube

El asistente y el vigilante usan un **router de modelos**: prueba los proveedores
en orden y, si uno se queda sin cuota gratuita, pasa solo al siguiente.

| Proveedor | Clave gratuita | Qué aporta |
|---|---|---|
| Google Gemini | https://aistudio.google.com/apikey | Asistente, vectores para la búsqueda y revisión de imágenes |
| Groq | https://console.groq.com/keys | Respuestas muy rápidas, vigilante y detector de instrucciones ocultas |
| OpenRouter (opcional) | https://openrouter.ai/keys | Modelos `:free` adicionales |
| Ollama (opcional) | `winget install Ollama.Ollama` | Respaldo local sin internet |

Pega las claves en `.env` (`GEMINI_API_KEY=...`, `GROQ_API_KEY=...`). Nunca las
subas al repositorio. Más detalles en [`docs/ASISTENTE_IA.md`](docs/ASISTENTE_IA.md).

## Probar con ~20 personas sin pagar nada

1. `python wsgi.py` en esta PC. Con la IA en la nube la PC sólo atiende la web:
   en la prueba de carga, 20 usuarios simultáneos dieron 0 errores y respuestas
   de menos de 35 ms (p95); 50 usuarios, también 0 errores.
2. Para que entren desde sus casas o celulares, abre un túnel gratuito de
   Cloudflare (sin cuenta, sin tocar el router ni el firewall):

   ```powershell
   winget install Cloudflare.cloudflared
   powershell -ExecutionPolicy Bypass -File scripts\compartir.ps1
   ```

   Comparte la dirección `https://…trycloudflare.com` que aparece.
3. Si todos están en la misma red Wi-Fi, también sirve `http://<IP-de-esta-PC>:5001`
   (Windows pedirá permitir Python en el firewall la primera vez).

## Estructura

```
app.py / wsgi.py        arranque (desarrollo / multiusuario)
manage.py               herramientas de consola
hub/                    backend Flask
  config.py             variables de entorno (.env)
  models.py, schema.py  tablas SQLite y migración automática de columnas
  errors.py             errores JSON uniformes
  api/                  Blueprints: auth, library, social, chat, groups, notes,
                        profile, realtime (pulso y notificaciones), assistant, admin
  ai/                   router de modelos, índice híbrido, prompt del asistente
  security/             vigilante: estático + antivirus + revisión con IA
index.html, css/app.css frontend (sin compilación, sin CDN de estilos)
js/core/                API, plantillas seguras, enrutador, estado, sondeo
js/ui/                  iconos, componentes, diálogos, conversación
js/views/               una vista por sección
tests/                  pruebas con pytest (sin red: IA y antivirus simulados)
scripts/                prueba de carga y túnel de Cloudflare
docs/                   documentación
```

## Seguridad

- Cada archivo pasa por **tres barreras** antes de publicarse: análisis estático,
  antivirus del sistema (Defender o ClamAV) y revisión con un segundo modelo de IA.
  Ver [`docs/SEGURIDAD.md`](docs/SEGURIDAD.md).
- Ningún archivo subido se sirve como estático: toda descarga comprueba la sesión,
  los permisos y el resultado del vigilante.
- Todo texto de usuario se escapa al pintarse (`html\`...\`` en `js/core/dom.js`) y
  la política CSP sólo permite scripts propios.
- Límites de peticiones en el inicio de sesión, el registro, el chat y el asistente.
- No subas `.env` ni `instance/` al repositorio.
