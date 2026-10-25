# UFG Knowledge Hub

Plataforma donde los estudiantes de la Universidad Francisco Gavidia comparten
material entre facultades: biblioteca común, asistente de estudio con IA,
grupos de trabajo (chat, tablero de tareas y archivos) y «Mi espacio» con notas
y archivos privados. Cada archivo que se sube pasa por un vigilante de seguridad
antes de publicarse.

**Fase 1** (octubre de 2026): IA en la nube con varios proveedores gratuitos,
vigilante de archivos, rediseño completo con modo oscuro y grupos de trabajo
terminados. Detalle en [`docs/FASE_1.md`](docs/FASE_1.md).

**Fase 2** (octubre de 2026): lista para 20 personas a la vez desde un link
(compu o celular), registro sólo con correo @ufg.edu.sv, vigilante que publica
solo lo limpio y deja en cuarentena lo dudoso, app instalable en el celular y
luces en el asistente. Detalle en [`docs/FASE_2.md`](docs/FASE_2.md) y guía de
la demostración en [`docs/DEMO_20_USUARIOS.md`](docs/DEMO_20_USUARIOS.md).

## Puesta en marcha

**Lo más fácil:** doble clic en `iniciar.bat`. La primera vez crea el entorno,
instala las dependencias y pide la clave gratuita de Groq; después arranca el
servidor, abre el link público de Cloudflare y lo muestra (ya copiado) junto a
la dirección para la red local. Para apagar todo: Ctrl+C o cerrar la ventana.

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
| `python manage.py storage` | Archivos y espacio por carpeta (`--limpiar` borra huérfanos). |
| `python manage.py db --reset` | Borra la base y la deja vacía (pide confirmación). |
| `python seed_test_data.py` | Con el servidor encendido: 8 usuarios, 100 documentos, grupos y mensajes. |
| `python -m pytest` | Pruebas automáticas del backend (sin red). |
| `python scripts/prueba_carga.py --aislado` | 20 estudiantes usando todo a la vez, con IA simulada y datos temporales. |

## IA gratis en la nube

El asistente y el vigilante usan un **router de modelos**: prueba los proveedores
en orden y, si uno se queda sin cuota gratuita, pasa solo al siguiente. Hoy usa
`openai/gpt-oss-120b`, `qwen/qwen3.8-27b` y `openai/gpt-oss-20b` de Groq (cada
uno con 8.000 tokens por minuto y 1.000 peticiones al día gratis); el vigilante
usa el mismo `gpt-oss-120b` con `gpt-oss-20b` de respaldo. Con mucha gente a la
vez las preguntas esperan en cola con aviso, las repetidas salen de una caché
y, si se agota la cuota, se responde con los documentos encontrados.

| Proveedor | Clave gratuita | Qué aporta |
|---|---|---|
| Google Gemini | https://aistudio.google.com/apikey | Asistente, vectores para la búsqueda y revisión de imágenes |
| Groq | https://console.groq.com/keys | Respuestas muy rápidas, vigilante y detector de instrucciones ocultas |
| OpenRouter (opcional) | https://openrouter.ai/keys | Modelos `:free` adicionales |
| Ollama (opcional) | `winget install Ollama.Ollama` | Respaldo local sin internet |

Pega las claves en `.env` (`GEMINI_API_KEY=...`, `GROQ_API_KEY=...`). Nunca las
subas al repositorio. Más detalles en [`docs/ASISTENTE_IA.md`](docs/ASISTENTE_IA.md).

## Probar con ~20 personas sin pagar nada

1. Doble clic en `iniciar.bat`: arranca `python wsgi.py` (waitress, 32 hilos) y
   un túnel gratuito de Cloudflare (sin cuenta, sin tocar el router ni el
   firewall). Comparte la dirección `https://…trycloudflare.com` que aparece.
   Hace falta `winget install Cloudflare.cloudflared` una vez (ya instalado aquí).
2. Desde el celular se usa igual que en la compu (barra de secciones abajo) y se
   puede instalar como app. Funciona también abierto desde WhatsApp.
3. Si todos están en la misma red Wi-Fi, también sirve `http://<IP-de-esta-PC>:5001`
   (Windows pedirá permitir Python en el firewall la primera vez).

Con la IA en la nube la PC sólo atiende la web. En la prueba de carga de la
Fase 2, 20 estudiantes usando todo a la vez durante 3 minutos (subir,
descargar, buscar, grupos y asistente) dieron **0 errores** y menos de 40 ms
(p95) en todo lo que no es IA. Detalle y guion en
[`docs/DEMO_20_USUARIOS.md`](docs/DEMO_20_USUARIOS.md).

## Estructura

```
app.py / wsgi.py        arranque (desarrollo / multiusuario)
manage.py               herramientas de consola
hub/                    backend Flask
  config.py             variables de entorno (.env)
  models.py, schema.py  tablas SQLite y migración automática de columnas
  storage.py            archivos subidos: carpetas, límites, cuotas y limpieza
  mailer.py             correo de verificación (SMTP, apagado por defecto)
  errors.py             errores JSON uniformes
  api/                  Blueprints: auth, library, social, chat, groups, notes,
                        profile, realtime (pulso y notificaciones), assistant,
                        admin, files (enlaces de descarga firmados)
  ai/                   router de modelos con cuotas, índice híbrido, prompt del
                        asistente e IA simulada para pruebas de carga
  security/             vigilante: estático + antivirus + revisión con IA
index.html, css/app.css frontend (sin compilación, sin CDN de estilos)
manifest.webmanifest, sw.js   app instalable (PWA)
js/core/                API, plantillas seguras, enrutador, estado, sondeo, preferencias
js/ui/                  iconos, componentes, diálogos, conversación
js/views/               una vista por sección
img/icons/              íconos de la app (scripts/generar_iconos.py)
tests/                  pruebas con pytest (sin red: IA y antivirus simulados)
scripts/                prueba de carga, túnel de Cloudflare e íconos
iniciar.bat / .ps1      arranque con un doble clic (servidor + link público)
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
- Lo limpio se publica solo; lo dudoso o peligroso queda **en cuarentena** y un
  administrador lo aprueba o lo rechaza desde el panel de Seguridad.
- Registro sólo con correo **@ufg.edu.sv** (comprobado en el servidor), contraseña
  con letras y números, bloqueo de 15 minutos tras 5 intentos fallidos y mensajes
  que no revelan si una cuenta existe. Verificación por correo lista pero apagada
  hasta tener un SMTP.
- Descargas con enlaces firmados de 5 minutos (funcionan en el celular y en web views).
- Límites de peticiones en el inicio de sesión, el registro, el chat y el asistente.
- No subas `.env` ni `instance/` al repositorio.
