"""Archivos subidos: validación de extensión, nombres únicos y rutas.

Estructura en disco (UPLOAD_FOLDER):

    uploads/<archivo>                    biblioteca pública
    uploads/private/<archivo>            anotaciones privadas
    uploads/groups/<id>/<archivo>        recursos de grupo
    uploads/profile/<archivo>            fotos de perfil

Ninguna de estas carpetas se sirve como estática: cada descarga pasa por una
ruta que comprueba permisos y el resultado del escáner de seguridad.
"""

from __future__ import annotations

import os
import uuid

from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from .errors import ApiError

# .html, .htm y .svg quedan fuera a propósito: servidos desde el mismo origen
# podrían ejecutar JavaScript y robar la sesión de quien los abra.
ALLOWED_EXTENSIONS = {
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
    'txt', 'md', 'csv', 'rtf', 'odt', 'odp', 'ods',
    'png', 'jpg', 'jpeg', 'gif', 'webp',
    'zip', 'rar', '7z',
}
IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def extension(filename: str) -> str:
    return filename.rsplit('.', 1)[1].lower() if filename and '.' in filename else ''


def folder_for(kind: str, group_id: int | None = None) -> str:
    base = current_app.config['UPLOAD_FOLDER']
    if kind == 'private':
        return os.path.join(base, 'private')
    if kind == 'group':
        return os.path.join(base, 'groups', str(group_id))
    if kind == 'avatar':
        return os.path.join(base, 'profile')
    return base


def path_for(kind: str, stored_name: str, group_id: int | None = None) -> str:
    # secure_filename impide que un nombre manipulado escape de la carpeta (../).
    return os.path.join(folder_for(kind, group_id), secure_filename(stored_name or ''))


def save_upload(file: FileStorage | None, kind: str, group_id: int | None = None,
                allowed: set[str] | None = None) -> tuple[str, str, int]:
    """Valida la extensión y guarda el archivo con un nombre único.

    Devuelve (nombre_guardado, ruta_absoluta, tamaño). Lanza ApiError si no
    hay archivo o la extensión no está permitida. El análisis de contenido lo
    hace después hub.security.
    """
    if file is None or not file.filename:
        raise ApiError('No se seleccionó ningún archivo.', 400, 'missing_file')
    permitidas = allowed or ALLOWED_EXTENSIONS
    if extension(file.filename) not in permitidas:
        raise ApiError('Tipo de archivo no permitido. Formatos aceptados: '
                       + ', '.join(sorted(permitidas)), 400, 'extension_not_allowed')

    seguro = secure_filename(file.filename) or 'archivo'
    # secure_filename quita las tildes y puede dejar el nombre sin extensión.
    if '.' not in seguro:
        seguro = f'{seguro}.{extension(file.filename)}'
    stored = f'{uuid.uuid4().hex}_{seguro}'
    carpeta = folder_for(kind, group_id)
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, stored)
    file.save(ruta)
    return stored, ruta, os.path.getsize(ruta)


def delete_upload(kind: str, stored_name: str | None, group_id: int | None = None) -> None:
    """Borra un archivo si existe, sin propagar errores de disco."""
    if not stored_name:
        return
    ruta = path_for(kind, stored_name, group_id)
    try:
        if os.path.exists(ruta):
            os.remove(ruta)
    except OSError as exc:
        current_app.logger.warning('No se pudo borrar %s: %s', ruta, exc)
