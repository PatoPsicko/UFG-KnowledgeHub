# Fase 3 — Seguridad completa

Plan para cerrar el módulo de seguridad. Lo que ya existía (vigilante de tres
barreras, cuarentena, correos @ufg.edu.sv, bloqueo por intentos, enlaces de
descarga firmados, cabeceras CSP) está en `SEGURIDAD.md`.

| Fase | Qué incluye | Depende de | Estado |
|---|---|---|---|
| **3A. Sesiones y control** | Sesiones por dispositivo con cierre real, renovación automática, cierre de las demás al cambiar la contraseña, bitácora y verificación en dos pasos (obligatoria para admin) | Nadie | Hecha |
| **3B. Correo** | Verificación al registrarse, recuperar contraseña, aviso de nuevo inicio de sesión | SMTP de la UFG | Pendiente |
| **3C. Moderación y privacidad** | Reportar documentos o mensajes, rol de moderador, borrar la cuenta, descargar mis datos, aviso de privacidad | Confirmar requisitos de la ley de datos personales | Pendiente |
| **3D. Endurecimiento y prueba** | Respaldos diarios con restauración probada, `pip-audit`, escaneo OWASP ZAP, HTTPS obligatorio (HSTS), documento de pruebas | Servidor definitivo | Pendiente |

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
