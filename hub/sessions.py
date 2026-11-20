"""Sesiones por dispositivo.

Al iniciar sesión se crea una fila UserSession y el navegador recibe:

* un token de acceso (JWT) que dura JWT_MINUTES y lleva el id de la sesión
  (`sid`). Va en la cabecera Authorization de cada petición.
* un token de renovación aleatorio en la cookie HttpOnly `hub_refresh`,
  limitada a /api/auth y SameSite=Strict. JavaScript no puede leerla, así que
  un script inyectado no puede llevarse la sesión larga.

Cada petición comprueba que la sesión siga abierta (una consulta por clave
primaria). Cuando el token de acceso caduca, el navegador llama a
/api/auth/refresh: se entrega uno nuevo y se cambia el de renovación. Si
alguien vuelve a usar un token de renovación ya cambiado, es una copia robada
y la sesión se cierra en todos lados.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import timedelta

from flask import current_app, g, request
from flask_jwt_extended import create_access_token, get_jwt
from sqlalchemy import update

from .errors import ApiError
from .extensions import db
from .models import User, UserSession, utcnow
from .utils import client_ip

REFRESH_COOKIE = 'hub_refresh'
COOKIE_PATH = '/api/auth'
# Dos pestañas pueden renovar a la vez con la misma cookie: la segunda no es un robo.
ROTATION_GRACE = timedelta(seconds=30)
# last_seen_at se actualiza como mucho una vez por minuto (no en cada petición).
TOUCH_EVERY = timedelta(seconds=60)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


# --- Nombre del dispositivo ------------------------------------------------------

_SISTEMAS = (('iPhone', 'iPhone'), ('iPad', 'iPad'), ('Android', 'Android'), ('Windows', 'Windows'),
             ('Macintosh', 'Mac'), ('CrOS', 'Chromebook'), ('Linux', 'Linux'))
# El orden importa: Edge y Opera también dicen «Chrome», y Chrome dice «Safari».
_NAVEGADORES = (('WhatsApp', 'WhatsApp'), ('Instagram', 'Instagram'), ('FBAN', 'Facebook'), ('FBAV', 'Facebook'),
                ('Edg/', 'Edge'), ('OPR/', 'Opera'), ('SamsungBrowser', 'Samsung Internet'),
                ('Firefox', 'Firefox'), ('FxiOS', 'Firefox'), ('CriOS', 'Chrome'), ('Chrome', 'Chrome'),
                ('Safari', 'Safari'))


def device_label(user_agent: str) -> str:
    """«Chrome en Android», «Safari en iPhone»... a partir del User-Agent."""
    ua = user_agent or ''
    sistema = next((nombre for clave, nombre in _SISTEMAS if clave in ua), '')
    navegador = next((nombre for clave, nombre in _NAVEGADORES if clave in ua), '')
    if re.search(r'python|curl|wget|httpx|werkzeug', ua, re.I):
        navegador, sistema = 'Script', ''
    if navegador and sistema:
        return f'{navegador} en {sistema}'
    return navegador or sistema or 'Navegador'


# --- Crear y comprobar ------------------------------------------------------------

def open_session(user: User, *, two_factor: bool = False) -> tuple[UserSession, str]:
    """Crea la sesión (sin commit) y devuelve también el token de renovación en claro."""
    token = secrets.token_urlsafe(32)
    ahora = utcnow()
    ua = request.headers.get('User-Agent', '')
    sesion = UserSession(user_id=user.id, token_hash=_hash(token), device=device_label(ua), user_agent=ua[:300],
                         ip=client_ip()[:64], two_factor=two_factor, created_at=ahora, last_seen_at=ahora,
                         expires_at=ahora + timedelta(days=current_app.config['SESSION_MAX_DAYS']))
    db.session.add(sesion)
    db.session.flush()
    return sesion, token


def access_token(user: User, sesion: UserSession) -> str:
    return create_access_token(identity=str(user.id), additional_claims={'sid': sesion.id})


def is_active(sesion: UserSession | None) -> bool:
    if sesion is None or sesion.revoked_at is not None:
        return False
    ahora = utcnow()
    inactiva = timedelta(days=current_app.config['SESSION_IDLE_DAYS'])
    return ahora < sesion.expires_at and ahora - (sesion.last_seen_at or sesion.created_at) < inactiva


def _touch(sesion: UserSession) -> None:
    ahora = utcnow()
    if sesion.last_seen_at is None or ahora - sesion.last_seen_at >= TOUCH_EVERY:
        sesion.last_seen_at = ahora
        sesion.ip = client_ip()[:64]
        db.session.commit()


def check(sid, user_id: int) -> UserSession:
    """La sesión `sid` de `user_id` si sigue abierta; si no, 401."""
    sesion = db.session.get(UserSession, int(sid)) if isinstance(sid, int) else None
    if sesion is None or sesion.user_id != user_id:
        raise ApiError('Tu sesión no es válida. Inicia sesión de nuevo.', 401, 'invalid_token')
    if not is_active(sesion):
        raise ApiError('Esta sesión se cerró. Inicia sesión de nuevo.', 401, 'session_closed')
    _touch(sesion)
    return sesion


def load_current(user_id: int) -> UserSession:
    """Sesión del token de acceso de esta petición (se guarda en g)."""
    if 'user_session' not in g:
        g.user_session = check(get_jwt().get('sid'), user_id)
    return g.user_session


def current_id() -> int | None:
    sesion = g.get('user_session')
    return sesion.id if sesion else None


# --- Renovación -----------------------------------------------------------------

def rotate(token: str | None, *, reissue: bool = False) -> tuple[UserSession, User, str | None]:
    """Valida el token de renovación y lo cambia por uno nuevo.

    Devuelve (sesión, usuario, token nuevo). El token nuevo es None cuando otra
    pestaña acaba de renovar con la misma cookie: la sesión vale y el navegador
    ya tiene la cookie nueva.
    """
    from . import audit
    if not token:
        raise ApiError('Inicia sesión para continuar.', 401, 'auth_required')
    huella = _hash(token)
    sesion = UserSession.query.filter_by(token_hash=huella).first()
    nuevo = None
    if sesion is not None:
        if not is_active(sesion):
            raise ApiError('Tu sesión se cerró. Inicia sesión de nuevo.', 401, 'session_closed')
        candidato = secrets.token_urlsafe(32)
        ahora = utcnow()
        # Compara y cambia en una sola sentencia: si dos peticiones llegan a la
        # vez, sólo una cambia la cookie y la otra cae en el período de gracia.
        cambiadas = db.session.execute(
            update(UserSession).where(UserSession.id == sesion.id, UserSession.token_hash == huella)
            .values(token_hash=_hash(candidato), previous_hash=huella, rotated_at=ahora)
        ).rowcount
        db.session.commit()
        db.session.refresh(sesion)
        if cambiadas:
            nuevo = candidato
    else:
        sesion = UserSession.query.filter_by(previous_hash=huella).first()
        if sesion is None:
            raise ApiError('Tu sesión no es válida. Inicia sesión de nuevo.', 401, 'invalid_token')
        reciente = sesion.rotated_at and utcnow() - sesion.rotated_at <= ROTATION_GRACE
        if not reciente or not is_active(sesion):
            if sesion.revoked_at is None:
                revoke(sesion, 'reuse')
                audit.record('token_reuse', user_id=sesion.user_id, target=f'session:{sesion.id}',
                             device=sesion.device)
                db.session.commit()
            raise ApiError('Por seguridad cerramos esta sesión. Inicia sesión de nuevo.', 401, 'session_closed')
        if reissue:
            # La app no guarda cookies: si repite la renovación (p. ej. se perdió la
            # respuesta), recibe otro token y el anterior que nunca le llegó deja de valer.
            nuevo = secrets.token_urlsafe(32)
            sesion.token_hash, sesion.previous_hash, sesion.rotated_at = _hash(nuevo), huella, utcnow()
            db.session.commit()
    _touch(sesion)
    user = db.session.get(User, sesion.user_id)
    if user is None:
        raise ApiError('Tu cuenta ya no existe.', 401, 'user_not_found')
    return sesion, user, nuevo


def is_mobile_client() -> bool:
    """La app de Flutter se identifica con la cabecera X-Client: mobile."""
    return request.headers.get('X-Client', '').lower() == 'mobile'


def mobile_refresh_token() -> str | None:
    datos = request.get_json(silent=True)
    token = datos.get('refresh_token') if isinstance(datos, dict) else None
    return token if isinstance(token, str) and 20 <= len(token) <= 200 else None


def find_by_refresh(token: str | None) -> UserSession | None:
    if not token:
        return None
    huella = _hash(token)
    return (UserSession.query.filter_by(token_hash=huella).first()
            or UserSession.query.filter_by(previous_hash=huella).first())


# --- Cookie ---------------------------------------------------------------------

def _secure_request() -> bool:
    """HTTPS directo o detrás del túnel (Tailscale Funnel, Cloudflare), que llega por 127.0.0.1."""
    if request.is_secure:
        return True
    if (request.remote_addr or '') in ('127.0.0.1', '::1'):
        return (request.headers.get('X-Forwarded-Proto', '').lower() == 'https'
                or request.headers.get('Origin', '').startswith('https://'))
    return False


def set_cookie(respuesta, token: str) -> None:
    respuesta.set_cookie(REFRESH_COOKIE, token, max_age=current_app.config['SESSION_MAX_DAYS'] * 86400,
                         path=COOKIE_PATH, httponly=True, samesite='Strict', secure=_secure_request())


def clear_cookie(respuesta) -> None:
    respuesta.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH, httponly=True, samesite='Strict')


# --- Cerrar ---------------------------------------------------------------------

def revoke(sesion: UserSession, reason: str) -> None:
    if sesion.revoked_at is None:
        sesion.revoked_at = utcnow()
        sesion.revoked_reason = reason[:40]


def revoke_all(user_id: int, reason: str, *, except_id: int | None = None) -> int:
    consulta = UserSession.query.filter(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_id is not None:
        consulta = consulta.filter(UserSession.id != except_id)
    return consulta.update({'revoked_at': utcnow(), 'revoked_reason': reason[:40]}, synchronize_session=False)


def active_for(user_id: int) -> list[UserSession]:
    filas = (UserSession.query.filter(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
             .order_by(UserSession.last_seen_at.desc()).all())
    return [s for s in filas if is_active(s)]


def purge() -> int:
    """Borra las sesiones cerradas o caducadas hace más de 30 días."""
    limite = utcnow() - timedelta(days=30)
    inactiva = utcnow() - timedelta(days=current_app.config['SESSION_IDLE_DAYS'] + 30)
    borradas = UserSession.query.filter(
        (UserSession.revoked_at < limite) | (UserSession.expires_at < limite) | (UserSession.last_seen_at < inactiva)
    ).delete(synchronize_session=False)
    db.session.commit()
    return borradas
