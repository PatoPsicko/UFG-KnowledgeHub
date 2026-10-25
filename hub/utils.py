"""Utilidades compartidas por los Blueprints."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from functools import wraps
from typing import Any, Callable

from flask import current_app, g, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .errors import ApiError
from .extensions import db
from .models import Contact, GroupMember, Notification, User

MAX_MESSAGE_LENGTH = 2000


# --- Autenticación -----------------------------------------------------------

def current_user_id() -> int:
    return int(get_jwt_identity())


def current_user() -> User:
    """Usuario autenticado (se consulta una vez por petición)."""
    if 'current_user' not in g:
        user = db.session.get(User, current_user_id())
        if user is None:
            raise ApiError('Tu cuenta ya no existe. Inicia sesión de nuevo.', 401, 'user_not_found')
        g.current_user = user
    return g.current_user


DOWNLOAD_LINK_SECONDS = 300


def _download_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config['JWT_SECRET_KEY'], salt='enlace-descarga')


def make_download_token(user_id: int, path: str) -> str:
    """Token para un enlace de descarga: sólo vale para `path`, por GET y unos minutos."""
    return _download_serializer().dumps({'u': user_id, 'p': path})


def _download_link_user() -> bool:
    """Si la petición trae ?dl=<token> válido para esta ruta, la atiende como su dueño."""
    token = request.args.get('dl')
    if not token or request.method != 'GET':
        return False
    try:
        datos = _download_serializer().loads(token, max_age=DOWNLOAD_LINK_SECONDS)
    except BadSignature:
        raise ApiError('El enlace caducó. Vuelve a pulsar Descargar en la app.', 403, 'link_expired')
    if datos.get('p') != request.path:
        raise ApiError('Este enlace no corresponde a este archivo.', 403, 'link_invalid')
    user = db.session.get(User, int(datos.get('u') or 0))
    if user is None:
        raise ApiError('Tu cuenta ya no existe.', 403, 'user_not_found')
    g.current_user = user
    return True


def login_required(fn: Callable) -> Callable:
    """Igual que @jwt_required() pero además carga el usuario.

    En las rutas de archivos también se acepta un enlace firmado (?dl=...),
    ver hub/api/files.py.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not _download_link_user():
            verify_jwt_in_request()
        current_user()
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn: Callable) -> Callable:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        if not current_user().is_admin:
            raise ApiError('Esta sección es sólo para administradores.', 403, 'admin_only')
        return fn(*args, **kwargs)
    return wrapper


# --- Lectura de datos de la petición -----------------------------------------

def json_body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def form_or_json() -> dict:
    """Campos de un formulario multipart o de un JSON, indistintamente."""
    if request.form:
        return request.form.to_dict()
    return json_body()


def clean_text(value: Any, field: str, *, required: bool = False, max_len: int = 200) -> str | None:
    """Recorta espacios y valida longitud. Devuelve None si viene vacío."""
    texto = value.strip() if isinstance(value, str) else ('' if value is None else str(value).strip())
    if not texto:
        if required:
            raise ApiError(f'El campo «{field}» es obligatorio.', 400, 'missing_field', {'field': field})
        return None
    if len(texto) > max_len:
        raise ApiError(f'«{field}» no puede superar los {max_len} caracteres.', 400, 'too_long',
                       {'field': field, 'max': max_len})
    return texto


def message_text(data: dict) -> str:
    texto = clean_text(data.get('message'), 'mensaje', required=True, max_len=MAX_MESSAGE_LENGTH)
    return texto


def parse_int(value: Any, field: str, *, required: bool = True) -> int | None:
    if value in (None, ''):
        if required:
            raise ApiError(f'El campo «{field}» es obligatorio.', 400, 'missing_field', {'field': field})
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ApiError(f'«{field}» no es un número válido.', 400, 'invalid_field', {'field': field})


def query_int(name: str, default: int = 0, *, minimum: int = 0, maximum: int | None = None) -> int:
    try:
        valor = int(request.args.get(name, default))
    except (TypeError, ValueError):
        valor = default
    valor = max(minimum, valor)
    return min(valor, maximum) if maximum is not None else valor


# --- Relaciones --------------------------------------------------------------

def contact_between(user_a: int, user_b: int) -> Contact | None:
    return Contact.query.filter(
        ((Contact.user_id == user_a) & (Contact.contact_id == user_b)) |
        ((Contact.user_id == user_b) & (Contact.contact_id == user_a))
    ).first()


def are_contacts(user_a: int, user_b: int) -> bool:
    contacto = contact_between(user_a, user_b)
    return contacto is not None and contacto.status == 'accepted'


def contact_ids(user_id: int) -> list[int]:
    filas = Contact.query.filter(
        ((Contact.user_id == user_id) | (Contact.contact_id == user_id)) & (Contact.status == 'accepted')
    ).all()
    return [c.contact_id if c.user_id == user_id else c.user_id for c in filas]


def membership(group_id: int, user_id: int) -> GroupMember | None:
    return GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()


def user_group_ids(user_id: int) -> list[int]:
    return [m.group_id for m in GroupMember.query.filter_by(user_id=user_id).all()]


def notify(user_id: int, type_: str, title: str, message: str, related_id: int | None = None) -> None:
    """Crea una notificación (se confirma con el commit de quien llama)."""
    db.session.add(Notification(user_id=user_id, type=type_, title=title[:200],
                                message=message, related_id=related_id))


# --- Límite de peticiones ----------------------------------------------------

class SlidingWindowLimiter:
    """Como máximo `limit` eventos por clave en `window` segundos.

    Vive en memoria del proceso: suficiente con waitress (un proceso con
    varios hilos). Con varios procesos habría que llevarlo a Redis.
    """

    def __init__(self, limit: int, window: float = 60):
        self.limit = limit
        self.window = window
        self._marks: dict[Any, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: Any) -> bool:
        ahora = time.monotonic()
        with self._lock:
            marcas = self._marks[key]
            while marcas and ahora - marcas[0] > self.window:
                marcas.popleft()
            if len(marcas) >= self.limit:
                return False
            marcas.append(ahora)
            return True

    def reset(self) -> None:
        with self._lock:
            self._marks.clear()


def client_ip() -> str:
    """IP del cliente para los límites de peticiones.

    Detrás de Cloudflare Tunnel (o un proxy en la misma máquina) todas las
    peticiones llegan desde 127.0.0.1 y la IP real viene en CF-Connecting-IP o
    X-Forwarded-For. Esas cabeceras sólo se creen si la conexión viene de la
    propia máquina: desde fuera cualquiera podría inventarlas.
    """
    directa = request.remote_addr or 'desconocida'
    if directa in ('127.0.0.1', '::1'):
        reenviada = (request.headers.get('CF-Connecting-IP')
                     or (request.headers.get('X-Forwarded-For') or '').split(',')[0].strip())
        if reenviada:
            return reenviada
    return directa
