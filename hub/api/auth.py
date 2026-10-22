"""Registro, inicio de sesión y datos de la cuenta."""

from __future__ import annotations

import re

from flask import Blueprint, current_app, jsonify
from flask_jwt_extended import create_access_token

from ..config import env_int
from ..errors import ApiError
from ..extensions import bcrypt, db
from ..models import User
from ..utils import SlidingWindowLimiter, clean_text, client_ip, current_user, json_body, login_required

bp = Blueprint('auth', __name__, url_prefix='/api')

# Contra ataques de fuerza bruta: 10 intentos por minuto por IP y correo.
login_limiter = SlidingWindowLimiter(10, 60)
# Registros por IP cada 10 minutos. Generoso a propósito: un salón entero que
# se registra desde el mismo Wi-Fi comparte la misma IP pública.
register_limiter = SlidingWindowLimiter(env_int('REGISTER_RATE_LIMIT', 40), 600)

MIN_PASSWORD = 8
_RE_COLOR = re.compile(r'#[0-9A-Fa-f]{6}')


def _sync_role(user: User) -> None:
    """Los correos de ADMIN_EMAILS entran como administradores."""
    if user.email.lower() in current_app.config['ADMIN_EMAILS'] and user.role != 'admin':
        user.role = 'admin'


@bp.post('/register')
def register():
    if not register_limiter.allow(client_ip()):
        raise ApiError('Demasiados registros desde esta conexión. Espera unos minutos.', 429)
    data = json_body()
    name = clean_text(data.get('name'), 'nombre', required=True, max_len=150)
    email = (clean_text(data.get('email'), 'correo', required=True, max_len=150) or '').lower()
    password = data.get('password') or ''
    color = data.get('profile_color') or '#0A6CC2'

    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
        raise ApiError('El correo electrónico no es válido.', 400, 'invalid_email')
    dominios = current_app.config['ALLOWED_EMAIL_DOMAINS']
    if dominios and email.rsplit('@', 1)[1] not in dominios:
        raise ApiError('Usa tu correo institucional (' + ', '.join('@' + d for d in dominios) + ').',
                       400, 'email_domain')
    if len(password) < MIN_PASSWORD:
        raise ApiError(f'La contraseña debe tener al menos {MIN_PASSWORD} caracteres.', 400, 'weak_password')
    if User.query.filter(db.func.lower(User.email) == email).first():
        raise ApiError('Ya existe una cuenta con ese correo.', 409, 'email_taken')

    user = User(name=name, email=email, password=bcrypt.generate_password_hash(password).decode('utf-8'),
                profile_color=color if isinstance(color, str) and _RE_COLOR.fullmatch(color) else '#0A6CC2')
    _sync_role(user)
    db.session.add(user)
    db.session.commit()
    return jsonify({'message': 'Cuenta creada. Ya puedes iniciar sesión.', 'user_id': user.id}), 201


@bp.post('/login')
def login():
    data = json_body()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    if not email or not password:
        raise ApiError('Escribe tu correo y tu contraseña.', 400, 'missing_credentials')
    if not login_limiter.allow((client_ip(), email)):
        raise ApiError('Demasiados intentos. Espera un minuto antes de volver a probar.', 429, 'rate_limited')

    user = User.query.filter(db.func.lower(User.email) == email).first()
    # Mismo mensaje si el correo no existe o la contraseña falla: no se revela
    # qué correos están registrados.
    if not user or not bcrypt.check_password_hash(user.password, password):
        raise ApiError('Correo o contraseña incorrectos.', 401, 'invalid_credentials')

    _sync_role(user)
    db.session.commit()
    token = create_access_token(identity=str(user.id))
    return jsonify({'message': 'Sesión iniciada', 'token': token, 'user': user.private_dict()}), 200


@bp.get('/verify-token')
@login_required
def verify_token():
    return jsonify({'valid': True, 'user': current_user().private_dict()}), 200


@bp.get('/me')
@login_required
def me():
    return jsonify({'user': current_user().private_dict()}), 200
