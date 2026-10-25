"""Sirve el frontend (index.html, js/, css/, img/) desde el mismo Flask.

Con API y frontend en el mismo origen no hace falta CORS, y el sitio funciona
igual en http://127.0.0.1:5001, en la red local o detrás de Cloudflare Tunnel.
"""

from __future__ import annotations

import os

from flask import Blueprint, jsonify, send_from_directory

from ..config import ROOT_DIR
from ..errors import ApiError

bp = Blueprint('frontend', __name__)

FRONTEND_DIRS = ('js', 'css', 'img')


@bp.get('/')
def index():
    respuesta = send_from_directory(ROOT_DIR, 'index.html', max_age=0)
    respuesta.headers['Cache-Control'] = 'no-cache'
    return respuesta


@bp.get('/manifest.webmanifest')
def manifest():
    """Manifiesto de la app instalable (PWA): nombre, íconos y colores."""
    respuesta = send_from_directory(ROOT_DIR, 'manifest.webmanifest', mimetype='application/manifest+json', max_age=0)
    respuesta.headers['Cache-Control'] = 'no-cache'
    return respuesta


@bp.get('/sw.js')
def service_worker():
    """Service worker en la raíz para que controle toda la app."""
    respuesta = send_from_directory(ROOT_DIR, 'sw.js', mimetype='text/javascript', max_age=0)
    respuesta.headers['Cache-Control'] = 'no-cache'
    respuesta.headers['Service-Worker-Allowed'] = '/'
    return respuesta


@bp.get('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(ROOT_DIR, 'img', 'icons'), 'favicon-32.png', mimetype='image/png',
                               max_age=86400)


@bp.get('/api/health')
def health():
    return jsonify({'status': 'OK', 'message': 'UFG Knowledge Hub API is running'}), 200


@bp.get('/<path:filename>')
def static_files(filename: str):
    """Sólo js/, css/ e img/: el resto del proyecto (código, instance/, uploads/) nunca se sirve."""
    if filename.startswith('api/'):
        raise ApiError('Ruta de la API no encontrada.', 404)
    if filename.split('/')[0] not in FRONTEND_DIRS or '..' in filename.split('/'):
        raise ApiError('Recurso no encontrado.', 404)
    if not os.path.isfile(os.path.join(ROOT_DIR, filename)):
        raise ApiError('Recurso no encontrado.', 404)
    respuesta = send_from_directory(ROOT_DIR, filename, max_age=0)
    # Se revalida en cada carga (ETag): tras actualizar el código nadie se queda
    # con una versión vieja del JavaScript en caché.
    respuesta.headers['Cache-Control'] = 'no-cache'
    return respuesta
