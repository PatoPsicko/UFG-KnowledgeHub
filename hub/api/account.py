"""Acceso a la cuenta: sesiones abiertas y verificación en dos pasos.

    GET    /api/auth/sessions                dispositivos con la sesión abierta
    DELETE /api/auth/sessions/<id>           cierra una
    POST   /api/auth/sessions/revoke-others  cierra todas menos la actual

    GET    /api/auth/2fa                     estado
    POST   /api/auth/2fa/setup               {password} -> secreto y QR (aún no activa nada)
    POST   /api/auth/2fa/enable              {code} -> activa y devuelve los códigos de respaldo
    POST   /api/auth/2fa/step-up             {code} -> marca esta sesión como verificada
    POST   /api/auth/2fa/recovery-codes      {password} -> códigos de respaldo nuevos
    POST   /api/auth/2fa/disable             {password, code}
"""

from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify

from .. import audit, sessions, twofactor
from ..errors import ApiError
from ..extensions import bcrypt, db
from ..models import UserSession
from ..utils import SlidingWindowLimiter, current_user, json_body, login_required

bp = Blueprint('account', __name__, url_prefix='/api/auth')

# Contra quien prueba códigos con una sesión robada: 10 intentos cada 5 minutos por cuenta.
code_limiter = SlidingWindowLimiter(10, 300)


def _require_password(data: dict) -> None:
    password = data.get('password') if isinstance(data.get('password'), str) else ''
    if not bcrypt.check_password_hash(current_user().password, password):
        raise ApiError('La contraseña no es correcta.', 400, 'wrong_password')


def _require_code(code) -> str:
    user = current_user()
    if not code_limiter.allow(user.id):
        raise ApiError('Demasiados intentos. Espera unos minutos.', 429, 'rate_limited')
    via = twofactor.check(user, code)
    if not via:
        audit.record('login_2fa_failed', user=user, where='account')
        db.session.commit()
        raise ApiError('El código no es correcto o ya se usó. Prueba con el que muestra ahora la app.',
                       400, 'invalid_code')
    if via == 'recovery':
        audit.record('2fa_recovery_used', user=user, left=twofactor.recovery_left(user))
    return via


def _status() -> dict:
    user = current_user()
    return {
        'enabled': bool(user.totp_enabled),
        'required': bool(user.is_admin and current_app.config['ADMIN_REQUIRE_2FA']),
        'session_verified': bool(g.user_session.two_factor),
        'recovery_left': twofactor.recovery_left(user) if user.totp_enabled else 0,
    }


# --- Sesiones -------------------------------------------------------------------

@bp.get('/sessions')
@login_required
def list_sessions():
    actual = sessions.current_id()
    return jsonify({'sessions': [s.to_dict(actual) for s in sessions.active_for(current_user().id)]}), 200


@bp.delete('/sessions/<int:session_id>')
@login_required
def revoke_session(session_id: int):
    user = current_user()
    sesion = db.session.get(UserSession, session_id)
    if sesion is None or sesion.user_id != user.id or sesion.revoked_at is not None:
        raise ApiError('Esa sesión ya no está abierta.', 404, 'not_found')
    sessions.revoke(sesion, 'user')
    audit.record('session_revoked', user=user, target=f'session:{sesion.id}', device=sesion.device)
    db.session.commit()
    return jsonify({'message': 'Sesión cerrada en ese dispositivo.',
                    'current': sesion.id == sessions.current_id()}), 200


@bp.post('/sessions/revoke-others')
@login_required
def revoke_others():
    user = current_user()
    cerradas = sessions.revoke_all(user.id, 'user', except_id=sessions.current_id())
    audit.record('sessions_revoked_others', user=user, closed=cerradas)
    db.session.commit()
    return jsonify({'message': 'Listo, sólo queda abierta esta sesión.', 'closed': cerradas}), 200


# --- Verificación en dos pasos --------------------------------------------------

@bp.get('/2fa')
@login_required
def two_factor_status():
    return jsonify(_status()), 200


@bp.post('/2fa/setup')
@login_required
def two_factor_setup():
    user = current_user()
    if user.totp_enabled:
        raise ApiError('La verificación en dos pasos ya está activa.', 409, 'already_enabled')
    _require_password(json_body())
    user.totp_secret = twofactor.new_secret()
    user.totp_last_step = None
    db.session.commit()
    uri = twofactor.provisioning_uri(user.totp_secret, user.email)
    return jsonify({'secret': user.totp_secret, 'uri': uri, 'qr_svg': twofactor.qr_svg(uri)}), 200


@bp.post('/2fa/enable')
@login_required
def two_factor_enable():
    user = current_user()
    if user.totp_enabled:
        raise ApiError('La verificación en dos pasos ya está activa.', 409, 'already_enabled')
    if not user.totp_secret:
        raise ApiError('Primero escanea el código QR.', 400, 'setup_required')
    if not code_limiter.allow(user.id):
        raise ApiError('Demasiados intentos. Espera unos minutos.', 429, 'rate_limited')
    paso = twofactor.match(user.totp_secret, json_body().get('code'))
    if paso is None:
        raise ApiError('El código no coincide. Revisa que la hora del celular esté en automático y prueba '
                       'con el código que aparece ahora.', 400, 'invalid_code')
    user.totp_enabled = True
    user.totp_last_step = paso
    codigos = twofactor.new_recovery_codes(user)
    g.user_session.two_factor = True  # quien acaba de escribir el código está verificado
    audit.record('2fa_enabled', user=user)
    db.session.commit()
    return jsonify({'message': 'Verificación en dos pasos activada.', 'recovery_codes': codigos,
                    'status': _status()}), 200


@bp.post('/2fa/step-up')
@login_required
def two_factor_step_up():
    user = current_user()
    if not user.totp_enabled:
        raise ApiError('Primero activa la verificación en dos pasos.', 400, 'setup_required')
    _require_code(json_body().get('code'))
    g.user_session.two_factor = True
    audit.record('2fa_step_up', user=user, target=f'session:{g.user_session.id}')
    db.session.commit()
    return jsonify({'message': 'Sesión verificada.', 'status': _status()}), 200


@bp.post('/2fa/recovery-codes')
@login_required
def two_factor_recovery_codes():
    user = current_user()
    if not user.totp_enabled:
        raise ApiError('Primero activa la verificación en dos pasos.', 400, 'setup_required')
    _require_password(json_body())
    codigos = twofactor.new_recovery_codes(user)
    audit.record('2fa_recovery_regenerated', user=user)
    db.session.commit()
    return jsonify({'recovery_codes': codigos, 'status': _status()}), 200


@bp.post('/2fa/disable')
@login_required
def two_factor_disable():
    user = current_user()
    if not user.totp_enabled:
        raise ApiError('La verificación en dos pasos no está activa.', 400, 'not_enabled')
    if user.is_admin and current_app.config['ADMIN_REQUIRE_2FA']:
        raise ApiError('Los administradores no pueden desactivarla. Si perdiste el celular, usa un código de '
                       'respaldo o pide que la reinicien con manage.py reset-2fa.', 403, 'two_factor_required')
    data = json_body()
    _require_password(data)
    _require_code(data.get('code'))
    twofactor.disable(user)
    audit.record('2fa_disabled', user=user)
    db.session.commit()
    return jsonify({'message': 'Verificación en dos pasos desactivada.', 'status': _status()}), 200
