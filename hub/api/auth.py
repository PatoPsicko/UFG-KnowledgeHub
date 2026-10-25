"""Registro, inicio de sesión y datos de la cuenta.

Todas las reglas se aplican en el servidor (el frontend sólo las repite para
avisar antes de enviar):

* Sólo correos de ALLOWED_EMAIL_DOMAINS (por defecto @ufg.edu.sv). El correo
  se normaliza: forma Unicode NFKC, sin caracteres invisibles, sin espacios y
  en minúsculas, así «  Ana.Lopez@UFG.edu.sv » y «ana.lopez@ufg.edu.sv» son
  la misma cuenta.
* Contraseña de PASSWORD_MIN_LENGTH caracteres o más, con letras y números,
  que no contenga el usuario del correo ni sea de las más comunes.
* Tras LOGIN_MAX_FAILURES fallos seguidos, el correo queda bloqueado
  LOGIN_LOCK_MINUTES minutos. Se aplica también a correos que no existen, así
  el bloqueo no delata qué cuentas hay.
* Ningún mensaje revela si un correo está registrado: el registro responde lo
  mismo para un correo nuevo y para uno existente, y el inicio de sesión dice
  «Correo o contraseña incorrectos» en ambos casos (con el mismo tiempo de
  respuesta, porque también se calcula un bcrypt cuando la cuenta no existe).
* Verificación por correo opcional (EMAIL_VERIFICATION=1 y SMTP en .env).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import timedelta

from flask import Blueprint, current_app, jsonify, redirect, request
from flask_jwt_extended import create_access_token
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.exc import IntegrityError

from .. import mailer
from ..config import env_int
from ..errors import ApiError
from ..extensions import bcrypt, db
from ..models import LoginThrottle, User, utcnow
from ..utils import SlidingWindowLimiter, clean_text, client_ip, current_user, json_body, login_required

bp = Blueprint('auth', __name__, url_prefix='/api')

# Contra ataques de fuerza bruta: 10 intentos por minuto por IP y correo, y
# 60 por minuto por IP en total (para quien prueba muchos correos distintos).
login_limiter = SlidingWindowLimiter(10, 60)
login_ip_limiter = SlidingWindowLimiter(env_int('LOGIN_IP_RATE_LIMIT', 60), 60)
# Registros por IP cada 10 minutos. Generoso a propósito: un salón entero que
# se registra desde el mismo Wi-Fi comparte la misma IP pública.
register_limiter = SlidingWindowLimiter(env_int('REGISTER_RATE_LIMIT', 40), 600)
resend_limiter = SlidingWindowLimiter(3, 600)

_RE_COLOR = re.compile(r'#[0-9A-Fa-f]{6}')
# Usuario: letras, números y . _ % + -, sin puntos al inicio, al final ni seguidos.
_RE_EMAIL = re.compile(r'(?!\.)(?!.*\.\.)[a-z0-9._%+-]{1,64}(?<!\.)@([a-z0-9-]+\.)+[a-z]{2,}')
_RE_INVISIBLES = re.compile('[­​-‏⁠﻿]')
CONTRASENAS_COMUNES = {
    '12345678', '123456789', '1234567890', '87654321', 'password', 'password1', 'contraseña', 'contrasena',
    'qwerty123', 'qwertyui', 'abc12345', 'abcd1234', 'iloveyou', '11111111', '00000000', 'ufg12345',
    'ufg2025', 'ufg2026', 'ufg20252026', 'universidad', 'estudiante', 'estudiante1', 'elsalvador',
    'elsalvador1', 'sansalvador', 'admin123', 'administrador', 'bienvenido', 'bienvenido1',
}
VERIFY_SALT = 'verificar-correo'
VERIFY_MAX_AGE = 48 * 3600
_hash_ficticio: str | None = None


# --- Reglas -------------------------------------------------------------------

def normalize_email(valor) -> str:
    texto = unicodedata.normalize('NFKC', valor if isinstance(valor, str) else '')
    return _RE_INVISIBLES.sub('', texto).strip().lower()


def domain_allowed(dominio: str, permitidos: list[str]) -> bool:
    for d in permitidos:
        if d == '*':
            return True
        if d.startswith('*.'):
            base = d[2:]
            if dominio == base or dominio.endswith('.' + base):
                return True
        elif dominio == d:
            return True
    return False


def domains_label() -> str:
    return ', '.join('@' + d.lstrip('*.') for d in current_app.config['ALLOWED_EMAIL_DOMAINS'] if d != '*')


def validate_email(email: str) -> str:
    if not email:
        raise ApiError('Escribe tu correo institucional.', 400, 'missing_field', {'field': 'correo'})
    if len(email) > 150 or not _RE_EMAIL.fullmatch(email):
        raise ApiError('El correo electrónico no es válido.', 400, 'invalid_email')
    if not domain_allowed(email.rsplit('@', 1)[1], current_app.config['ALLOWED_EMAIL_DOMAINS']):
        raise ApiError(f'Sólo se puede crear una cuenta con el correo institucional ({domains_label()}).',
                       400, 'email_domain')
    return email


def validate_password(password: str, email: str = '') -> None:
    """Lanza ApiError 400 (weak_password) si la contraseña no cumple la política."""
    minimo = current_app.config['PASSWORD_MIN_LENGTH']
    if len(password) < minimo:
        raise ApiError(f'La contraseña debe tener al menos {minimo} caracteres.', 400, 'weak_password')
    # bcrypt sólo usa los primeros 72 bytes: más largo daría una falsa sensación de seguridad.
    if len(password.encode('utf-8')) > 72:
        raise ApiError('La contraseña no puede superar los 72 caracteres.', 400, 'weak_password')
    if not (re.search(r'[^\W\d_]', password) and re.search(r'\d', password)):
        raise ApiError('La contraseña debe combinar letras y números.', 400, 'weak_password')
    baja = password.lower()
    usuario = email.split('@')[0] if email else ''
    if baja in CONTRASENAS_COMUNES or (len(usuario) >= 4 and usuario in baja):
        raise ApiError('Esa contraseña es muy fácil de adivinar. Elige otra.', 400, 'weak_password')


def _sync_role(user: User) -> None:
    """Los correos de ADMIN_EMAILS entran como administradores (si el correo está verificado)."""
    if (user.email.lower() in current_app.config['ADMIN_EMAILS'] and user.role != 'admin'
            and user.email_verified is not False):
        user.role = 'admin'


# --- Bloqueo por intentos fallidos -------------------------------------------

def _lock_remaining(email: str) -> int:
    """Segundos de bloqueo que le quedan a un correo (0 si no está bloqueado)."""
    fila = db.session.get(LoginThrottle, email[:190])
    if not fila or not fila.locked_until:
        return 0
    return max(0, int((fila.locked_until - utcnow()).total_seconds()))


def _register_failure(email: str) -> None:
    cfg = current_app.config
    ventana = timedelta(minutes=cfg['LOGIN_LOCK_MINUTES'])
    ahora = utcnow()
    for _ in range(2):  # dos hilos pueden crear la misma fila a la vez
        fila = db.session.get(LoginThrottle, email[:190])
        if fila is None:
            fila = LoginThrottle(email=email[:190], failures=0)
            db.session.add(fila)
        if fila.first_failure_at is None or ahora - fila.first_failure_at > ventana:
            fila.failures, fila.first_failure_at = 0, ahora
        fila.failures = (fila.failures or 0) + 1
        if fila.failures >= cfg['LOGIN_MAX_FAILURES']:
            fila.locked_until = ahora + ventana
            fila.failures, fila.first_failure_at = 0, None
        try:
            db.session.commit()
            return
        except IntegrityError:
            db.session.rollback()


def _clear_failures(email: str) -> None:
    LoginThrottle.query.filter_by(email=email[:190]).delete()


def _check_password(user: User | None, password: str) -> bool:
    global _hash_ficticio
    if user is None:
        # Mismo coste que una comprobación real: el tiempo de respuesta no
        # delata si el correo existe.
        if _hash_ficticio is None:
            _hash_ficticio = bcrypt.generate_password_hash('cuenta-que-no-existe-1').decode('utf-8')
        bcrypt.check_password_hash(_hash_ficticio, password)
        return False
    return bcrypt.check_password_hash(user.password, password)


# --- Verificación por correo -------------------------------------------------

def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config['JWT_SECRET_KEY'], salt=VERIFY_SALT)


def _send_verification(user: User) -> bool:
    token = _serializer().dumps({'uid': user.id, 'email': user.email})
    base = current_app.config['APP_PUBLIC_URL'] or request.host_url.rstrip('/')
    enlace = f'{base}/api/verify-email?token={token}'
    return mailer.send(user.email, 'Confirma tu cuenta de UFG Knowledge Hub',
                       f'Hola, {user.name}:\n\nPara activar tu cuenta abre este enlace (vale 48 horas):\n\n'
                       f'{enlace}\n\nSi no creaste una cuenta, ignora este correo.\n\nUFG Knowledge Hub')


# --- Rutas ------------------------------------------------------------------

@bp.get('/auth/policy')
def policy():
    """Reglas de registro para que el formulario las muestre."""
    cfg = current_app.config
    return jsonify({'domains': [d for d in cfg['ALLOWED_EMAIL_DOMAINS']], 'domains_label': domains_label(),
                    'password_min_length': cfg['PASSWORD_MIN_LENGTH'],
                    'email_verification': bool(cfg['EMAIL_VERIFICATION'])}), 200


@bp.post('/register')
def register():
    if not register_limiter.allow(client_ip()):
        raise ApiError('Demasiados registros desde esta conexión. Espera unos minutos.', 429, 'rate_limited')
    data = json_body()
    name = clean_text(data.get('name'), 'nombre', required=True, max_len=150)
    email = validate_email(normalize_email(data.get('email')))
    password = data.get('password') if isinstance(data.get('password'), str) else ''
    validate_password(password, email)
    color = data.get('profile_color') or '#0A6CC2'
    verificar = bool(current_app.config['EMAIL_VERIFICATION'])

    # Misma respuesta exista o no la cuenta: el registro no sirve para averiguar
    # qué correos están dados de alta.
    mensaje = ('Te enviamos un enlace a tu correo institucional para activar la cuenta.' if verificar else
               'Listo. Si el correo no tenía cuenta, ya está creada: entra con tu contraseña.')
    if User.query.filter(db.func.lower(User.email) == email).first():
        return jsonify({'message': mensaje, 'verification_required': verificar}), 201

    user = User(name=name, email=email, password=bcrypt.generate_password_hash(password).decode('utf-8'),
                profile_color=color if isinstance(color, str) and _RE_COLOR.fullmatch(color) else '#0A6CC2',
                email_verified=not verificar)
    _sync_role(user)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:  # dos registros simultáneos con el mismo correo
        db.session.rollback()
        return jsonify({'message': mensaje, 'verification_required': verificar}), 201
    if verificar:
        _send_verification(user)
    return jsonify({'message': mensaje, 'verification_required': verificar}), 201


@bp.post('/login')
def login():
    data = json_body()
    email = normalize_email(data.get('email'))
    password = data.get('password') if isinstance(data.get('password'), str) else ''
    if not email or not password:
        raise ApiError('Escribe tu correo y tu contraseña.', 400, 'missing_credentials')
    ip = client_ip()
    if not login_limiter.allow((ip, email)) or not login_ip_limiter.allow(ip):
        raise ApiError('Demasiados intentos. Espera un minuto antes de volver a probar.', 429, 'rate_limited')
    restante = _lock_remaining(email)
    if restante:
        minutos = max(1, round(restante / 60))
        raise ApiError(f'Demasiados intentos fallidos con este correo. Vuelve a intentarlo en {minutos} min.',
                       429, 'account_locked', {'retry_after': restante})

    user = User.query.filter(db.func.lower(User.email) == email).first()
    if not _check_password(user, password):
        _register_failure(email)
        raise ApiError('Correo o contraseña incorrectos.', 401, 'invalid_credentials')

    _clear_failures(email)
    if user.email_verified is False and current_app.config['EMAIL_VERIFICATION']:
        db.session.commit()
        raise ApiError('Confirma tu correo antes de entrar: abre el enlace que te enviamos.', 403,
                       'email_unverified')
    _sync_role(user)
    db.session.commit()
    token = create_access_token(identity=str(user.id))
    return jsonify({'message': 'Sesión iniciada', 'token': token, 'user': user.private_dict()}), 200


@bp.get('/verify-email')
def verify_email():
    """Enlace del correo de verificación: activa la cuenta y vuelve a la app."""
    try:
        datos = _serializer().loads(request.args.get('token') or '', max_age=VERIFY_MAX_AGE)
    except SignatureExpired:
        return redirect('/?verificacion=caducada')
    except BadSignature:
        return redirect('/?verificacion=invalida')
    user = db.session.get(User, int(datos.get('uid') or 0))
    if not user or user.email != datos.get('email'):
        return redirect('/?verificacion=invalida')
    user.email_verified = True
    _sync_role(user)
    db.session.commit()
    return redirect('/?verificacion=ok')


@bp.post('/resend-verification')
def resend_verification():
    email = normalize_email(json_body().get('email'))
    if email and current_app.config['EMAIL_VERIFICATION'] and resend_limiter.allow((client_ip(), email)):
        user = User.query.filter(db.func.lower(User.email) == email).first()
        if user and user.email_verified is False:
            _send_verification(user)
    return jsonify({'message': 'Si la cuenta existe y falta confirmarla, te enviamos un enlace nuevo.'}), 200


@bp.get('/verify-token')
@login_required
def verify_token():
    return jsonify({'valid': True, 'user': current_user().private_dict()}), 200


@bp.get('/me')
@login_required
def me():
    return jsonify({'user': current_user().private_dict()}), 200
