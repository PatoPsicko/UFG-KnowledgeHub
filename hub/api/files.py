"""Enlaces de descarga firmados y espacio usado por cada estudiante.

Las descargas necesitan la sesión, pero un enlace normal (<a href>) no puede
enviar la cabecera Authorization. Antes el navegador bajaba el archivo con
fetch() y lo guardaba como «blob»; eso falla en el celular dentro de las web
views (WhatsApp, Instagram, Facebook...), que no saben guardar blobs.

Ahora el navegador pide aquí un enlace de un solo uso práctico:

    POST /api/files/link {"path": "/api/resources/7/file?download=1"}
      -> {"url": "/api/resources/7/file?download=1&dl=<token>", "expires_in": 300}

El token va firmado con la clave del servidor, sólo vale para esa ruta, para
GET y durante LINK_SECONDS; quien lo usa actúa como el estudiante que lo pidió
y la ruta vuelve a comprobar todos los permisos y el resultado del vigilante.
"""

from __future__ import annotations

import re

from flask import Blueprint, jsonify

from .. import storage
from ..errors import ApiError
from ..utils import current_user, json_body, login_required, make_download_token

bp = Blueprint('files', __name__, url_prefix='/api/files')

LINK_SECONDS = 300
# Sólo las rutas que entregan archivos.
_RUTAS = re.compile(r'^/api/(resources/\d+/file|private-resources/\d+/download|groups/\d+/resources/\d+/download)$')


@bp.post('/link')
@login_required
def link():
    ruta = str(json_body().get('path') or '')
    base, _, consulta = ruta.partition('?')
    if not _RUTAS.fullmatch(base):
        raise ApiError('Esa ruta no entrega archivos.', 400, 'invalid_path')
    if consulta and not re.fullmatch(r'(download|inline)=1', consulta):
        raise ApiError('Parámetros no válidos.', 400, 'invalid_path')
    token = make_download_token(current_user().id, base)
    url = f'{base}?{consulta + "&" if consulta else ""}dl={token}'
    return jsonify({'url': url, 'expires_in': LINK_SECONDS}), 200


@bp.get('/usage')
@login_required
def usage():
    """Espacio que ocupan mis archivos y subidas de las últimas 24 h."""
    return jsonify(storage.user_usage(current_user().id)), 200
