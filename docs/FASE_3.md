# Fase 3 — Seguridad completa

Plan para cerrar el módulo de seguridad. Lo que ya existía (vigilante de tres
barreras, cuarentena, correos @ufg.edu.sv, bloqueo por intentos, enlaces de
descarga firmados, cabeceras CSP) está en `SEGURIDAD.md`.

| Fase | Qué incluye | Depende de | Estado |
|---|---|---|---|
| **3A. Sesiones y control** | Sesiones por dispositivo con cierre real, renovación automática, cierre de las demás al cambiar la contraseña, bitácora y verificación en dos pasos (obligatoria para admin) | Nadie | Hecha |
| **3B. Correo** | Verificación al registrarse, recuperar contraseña, aviso de nuevo inicio de sesión | SMTP de la UFG | Pendiente |
| **3C. Moderación y privacidad** | Reportar documentos, panel de reportes, suspensión de subidas, borrar la cuenta, descargar mis datos, aviso de privacidad | Revisión legal del aviso (ley de datos personales) | Hecha (falta la revisión legal y el rol de moderador) |
| **3D. Endurecimiento y prueba** | Respaldos diarios con restauración probada, HSTS, `pip-audit`, escaneo OWASP ZAP, documento de pruebas | Servidor definitivo | Respaldos y HSTS hechos; `pip-audit` y ZAP al desplegar |

## 3A: lo que se hizo

**Backend**

- `user_session`: una fila por dispositivo. El JWT dura 30 min y lleva el id de
  la sesión; la cookie HttpOnly `hub_refresh` lo renueva y se cambia en cada
  renovación (detecta copias robadas). `login_required` comprueba la sesión en
  cada petición.
- `POST /api/auth/refresh`, `POST /api/auth/logout`, `GET/DELETE /api/auth/sessions`,
  `POST /api/auth/sessions/revoke-others`.
- Verificación en dos pasos TOTP sin dependencias nuevas: `/api/auth/2fa`
  (estado, setup, enable, step-up, recovery-codes, disable) y
  `POST /api/login/2fa` con reto firmado de 5 minutos.
- `ADMIN_REQUIRE_2FA=1`: el panel exige la verificación (403 `two_factor_setup`
  o `two_factor_step_up`).
- `audit_event` + `GET /api/admin/audit` con filtros y paginación; el resumen del
  panel suma intentos fallidos en 24 h y sesiones activas.
- `python manage.py reset-2fa correo`.
- Limpieza cada 6 h de sesiones viejas y de la bitácora (180 días).

**Frontend**

- `js/core/api.js` renueva el token antes de que caduque o tras un 401 y repite
  la petición; si `localStorage` se borró, la cookie recupera la sesión al abrir.
- Acceso: paso del código tras la contraseña (acepta códigos de respaldo).
- Mi perfil → **Acceso y sesiones**: estado de la verificación, activar (QR),
  códigos nuevos, desactivar; lista de dispositivos con «Cerrar» y «Cerrar las
  otras sesiones».
- Seguridad: puerta para activar o confirmar la verificación y pestaña
  **Bitácora**.

**Variables nuevas** (`.env.example`): `JWT_MINUTES` (reemplaza a `JWT_HOURS`),
`SESSION_IDLE_DAYS`, `SESSION_MAX_DAYS`, `ADMIN_REQUIRE_2FA`, `AUDIT_RETENTION_DAYS`.

**Pruebas**: `tests/test_sessions.py` (12 pruebas: vector del RFC 6238,
sesiones por dispositivo, renovación y reutilización de la cookie, cierre de
sesiones, cambio de contraseña, inactividad, tokens antiguos, enlaces de
descarga, verificación en dos pasos con códigos y respaldo, bloqueo, panel de
admin y bitácora). En total 99 pruebas pasan.

**Revisado en el navegador** (escritorio en modo oscuro y celular a 375 px en
modo claro): puerta del panel, QR y activación, códigos de respaldo, bitácora,
panel de sesiones, cerrar una sesión de otro dispositivo, recuperar la sesión
sin `localStorage`, renovación con token caducado, cerrar sesión y volver a
entrar con código.

**Al actualizar**: todas las sesiones abiertas antes de esta versión se cierran
una vez (los tokens viejos no tienen sesión). Las cuentas de `ADMIN_EMAILS`
tienen que activar la verificación en dos pasos la primera vez que abran
Seguridad.


## Administración del vigilante (noviembre de 2026)

El panel **Seguridad** quedó como centro de control de las subidas:

| Pestaña | Qué hace |
|---|---|
| **Archivos** | Cinco indicadores (cuarentena, revisados en 24 h, bloqueados, estudiantes suspendidos, cola), actividad de 14 días, motivos más frecuentes, las tres barreras y el registro completo con búsqueda (archivo, estudiante, correo o huella), filtro por sección, paginación y exportación a CSV. En «En cuarentena» se pueden marcar varios y aprobarlos o rechazarlos en lote. |
| Detalle de un archivo | Informe de las tres barreras, **texto extraído** (o la imagen) para decidir sin abrir el original, ficha de quien lo subió con «Sus archivos» y «Suspender subidas», y una **nota** que recibe el estudiante y queda en la bitácora. |
| **Reportes** | Documentos que reportaron los estudiantes, agrupados, con motivos y comentarios: mantener publicado, ocultar y revisar, o eliminar (veta la huella y cuenta como rechazo). |
| **Estudiantes** | Quién acumula archivos marcados o rechazados, su conteo de rechazos y la suspensión manual o automática de subidas. |
| **Huellas vetadas** | Archivos que no se pueden volver a subir, con la opción de quitar el veto. |
| **Política e IA** | Límites de subida, suspensión automática, respaldos (con «Crear respaldo ahora»), cuota de la IA y espacio en disco. |
| **Bitácora** | Eventos de seguridad, ahora también de archivos y privacidad. |

API nueva en `hub/api/admin.py` y `hub/api/reports.py` (ver la cabecera de cada archivo).

## 3C: lo que se hizo

- **Reportar documentos** (biblioteca y grupos): motivo + detalle, uno por persona, 20 por día. Con
  `REPORT_HIDE_THRESHOLD` (3) reportes de personas distintas el documento se oculta solo y entra a la
  cuarentena. Quien reporta recibe aviso del resultado; quien lo subió no sabe quién lo reportó.
- **Suspensión de subidas**: tras `UPLOAD_STRIKES` (3) rechazos en `UPLOAD_STRIKE_DAYS` (30) días las
  subidas se suspenden `UPLOAD_BLOCK_DAYS` (7) días; el admin puede suspender o reactivar a mano.
  El estudiante puede seguir entrando y descargando.
- **Descargar mis datos** (Mi perfil → Privacidad): ZIP con `datos.json` y los archivos que subió.
- **Borrar mi cuenta**: contraseña + escribir BORRAR. Se borran perfil, documentos, notas, mensajes de
  grupo, conversaciones y sesiones; los grupos que lideraba pasan al miembro más antiguo. El último
  administrador no puede borrarse.
- **Aviso de privacidad** en el acceso y en el perfil. Falta que lo revise la universidad.

## 3D: lo que se hizo

- **Respaldos** (`hub/backup.py`): ZIP con la base de datos (copia consistente con el servidor encendido)
  y los archivos, sin el `.env`. Uno al día, se guardan 7. `python manage.py backup` y
  `python manage.py restore <zip>` (guarda lo actual como `*.antes_de_restaurar`). Restauración probada
  en `tests/test_fase3.py`.
- **HSTS** cuando se entra por HTTPS (Tailscale Funnel, Cloudflare o el servidor de la UFG).
- Pendiente al desplegar: `pip-audit` sobre `requirements.txt` y un escaneo OWASP ZAP contra el servidor.

**Pruebas**: `tests/test_admin_files.py` (8) y `tests/test_fase3.py` (10). En total 117.
