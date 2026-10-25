"""Archivos subidos: validación, nombres únicos, límites, rutas y limpieza.

Estructura en disco (UPLOAD_FOLDER, por defecto uploads/):

    uploads/library/<archivo>              biblioteca pública
    uploads/private/<id_usuario>/<archivo> Mi espacio (una carpeta por estudiante)
    uploads/groups/<id_grupo>/<archivo>    archivos de cada grupo
    uploads/profile/<archivo>              fotos de perfil
    uploads/tmp/                           subidas en curso (se borran solas)

Cada archivo se guarda como <uuid32>_<nombre-seguro>: el prefijo aleatorio
evita choques y que alguien adivine rutas; el nombre legible se recupera con
models.display_filename(). Ninguna carpeta se sirve como estática: toda
descarga pasa por una ruta que comprueba sesión, permisos y el vigilante.

Las versiones anteriores guardaban la biblioteca en la raíz de uploads/ y Mi
espacio en private/ sin subcarpetas; migrate_layout() las mueve al arrancar y
path_for() sigue encontrando los archivos antiguos mientras tanto.

Límites (en .env): MAX_UPLOAD_MB por archivo, AVATAR_MAX_MB por foto,
USER_QUOTA_MB por estudiante, UPLOADS_PER_DAY por estudiante y
MIN_FREE_DISK_MB libres en el disco antes de aceptar nada.
"""

from __future__ import annotations

import logging
import os
import shutil
import time
import uuid
from datetime import timedelta

from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from .errors import ApiError

log = logging.getLogger(__name__)

# .html, .htm y .svg quedan fuera a propósito: servidos desde el mismo origen
# podrían ejecutar JavaScript y robar la sesión de quien los abra.
ALLOWED_EXTENSIONS = {
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
    'txt', 'md', 'csv', 'rtf', 'odt', 'odp', 'ods',
    'png', 'jpg', 'jpeg', 'gif', 'webp',
    'zip', 'rar', '7z',
}
IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

CARPETAS = {'public': 'library', 'private': 'private', 'group': 'groups', 'avatar': 'profile'}
TMP_DIR = 'tmp'
MAX_NOMBRE = 80  # caracteres del nombre legible (sin contar el prefijo ni la extensión)
_CHUNK = 256 * 1024


def extension(filename: str) -> str:
    return filename.rsplit('.', 1)[1].lower() if filename and '.' in filename else ''


def _base() -> str:
    return current_app.config['UPLOAD_FOLDER']


def folder_for(kind: str, scope_id: int | None = None) -> str:
    """Carpeta de un tipo de archivo. scope_id = id del grupo (group) o del dueño (private)."""
    carpeta = os.path.join(_base(), CARPETAS.get(kind, CARPETAS['public']))
    if kind in ('group', 'private') and scope_id is not None:
        carpeta = os.path.join(carpeta, str(int(scope_id)))
    return carpeta


def _legacy_path(kind: str, nombre: str) -> str | None:
    if kind == 'public':
        return os.path.join(_base(), nombre)
    if kind == 'private':
        return os.path.join(_base(), 'private', nombre)
    return None


def path_for(kind: str, stored_name: str, scope_id: int | None = None) -> str:
    """Ruta absoluta de un archivo guardado (también de los guardados con la estructura anterior)."""
    # secure_filename impide que un nombre manipulado escape de la carpeta (../).
    nombre = secure_filename(stored_name or '')
    ruta = os.path.join(folder_for(kind, scope_id), nombre)
    if nombre and not os.path.exists(ruta):
        antigua = _legacy_path(kind, nombre)
        if antigua and os.path.isfile(antigua):
            return antigua
    return ruta


def stored_name_for(original: str) -> str:
    """<uuid32>_<nombre-seguro>.<ext>, con el nombre recortado a MAX_NOMBRE caracteres."""
    ext = extension(original)
    base = original.rsplit('.', 1)[0] if '.' in original else original
    seguro = secure_filename(base)[:MAX_NOMBRE].strip('._') or 'archivo'
    return f'{uuid.uuid4().hex}_{seguro}.{ext}' if ext else f'{uuid.uuid4().hex}_{seguro}'


# --- Límites ---------------------------------------------------------------------

def _check_disk() -> None:
    minimo = current_app.config.get('MIN_FREE_DISK_MB', 1024) * 1024 * 1024
    try:
        libre = shutil.disk_usage(_base()).free
    except OSError:
        return
    if libre < minimo:
        log.error('Disco casi lleno: %.0f MB libres', libre / 1024 / 1024)
        raise ApiError('El servidor se quedó sin espacio para archivos. Avisa al administrador.', 507, 'disk_full')


def user_usage(user_id: int) -> dict:
    """Espacio ocupado y subidas de las últimas 24 h de un estudiante."""
    from .extensions import db
    from .models import FileScan, GroupResource, PrivateResource, Resource, utcnow

    total = 0
    for modelo, campo in ((Resource, Resource.owner_id), (GroupResource, GroupResource.user_id),
                          (PrivateResource, PrivateResource.owner_id)):
        total += db.session.query(db.func.coalesce(db.func.sum(modelo.file_size), 0)).filter(campo == user_id).scalar()
    hoy = FileScan.query.filter(FileScan.user_id == user_id, FileScan.kind != 'avatar',
                                FileScan.created_at >= utcnow() - timedelta(days=1)).count()
    return {'bytes': int(total), 'quota_bytes': current_app.config.get('USER_QUOTA_MB', 300) * 1024 * 1024,
            'uploads_24h': hoy, 'uploads_per_day': current_app.config.get('UPLOADS_PER_DAY', 40)}


def _check_user_limits(user_id: int) -> None:
    uso = user_usage(user_id)
    if uso['uploads_24h'] >= uso['uploads_per_day']:
        raise ApiError(f"Llegaste al máximo de {uso['uploads_per_day']} archivos por día. Vuelve a intentarlo mañana.",
                       429, 'upload_limit')
    if uso['bytes'] >= uso['quota_bytes']:
        raise ApiError(f"Tus archivos ya ocupan {uso['quota_bytes'] // 1024 // 1024} MB, el máximo por estudiante. "
                       'Borra alguno que ya no uses para subir otro.', 413, 'quota_exceeded')


# --- Guardar y borrar ------------------------------------------------------------

def save_upload(file: FileStorage | None, kind: str, scope_id: int | None = None,
                allowed: set[str] | None = None, *, user_id: int | None = None) -> tuple[str, str, int]:
    """Valida y guarda un archivo subido. Devuelve (nombre_guardado, ruta_absoluta, tamaño).

    Se escribe primero en uploads/tmp y se mueve a su carpeta al terminar, así
    nunca queda un archivo a medias donde otra petición pueda leerlo. Lanza
    ApiError si falta el archivo, la extensión no está permitida, está vacío,
    supera el tamaño máximo o el estudiante llegó a su límite. El análisis del
    contenido lo hace después hub.security.
    """
    if file is None or not file.filename:
        raise ApiError('No se seleccionó ningún archivo.', 400, 'missing_file')
    permitidas = allowed or ALLOWED_EXTENSIONS
    if extension(file.filename) not in permitidas:
        raise ApiError('Tipo de archivo no permitido. Formatos aceptados: '
                       + ', '.join(sorted(permitidas)), 400, 'extension_not_allowed')
    _check_disk()
    if user_id is not None and kind != 'avatar':
        _check_user_limits(user_id)

    cfg = current_app.config
    limite_mb = cfg.get('AVATAR_MAX_MB', 4) if kind == 'avatar' else cfg.get('MAX_UPLOAD_MB', 25)
    stored = stored_name_for(file.filename)
    tmp_dir = os.path.join(_base(), TMP_DIR)
    os.makedirs(tmp_dir, exist_ok=True)
    tmp = os.path.join(tmp_dir, stored + '.part')
    tamano = 0
    try:
        with open(tmp, 'wb') as destino:
            while True:
                bloque = file.stream.read(_CHUNK)
                if not bloque:
                    break
                tamano += len(bloque)
                if tamano > limite_mb * 1024 * 1024:
                    raise ApiError(f'El archivo supera el máximo de {limite_mb} MB.', 413, 'file_too_large')
                destino.write(bloque)
        if tamano == 0:
            raise ApiError('El archivo está vacío.', 400, 'empty_file')
        carpeta = folder_for(kind, scope_id)
        os.makedirs(carpeta, exist_ok=True)
        ruta = os.path.join(carpeta, stored)
        os.replace(tmp, ruta)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return stored, ruta, tamano


def delete_upload(kind: str, stored_name: str | None, scope_id: int | None = None) -> None:
    """Borra un archivo si existe, sin propagar errores de disco."""
    if not stored_name:
        return
    ruta = path_for(kind, stored_name, scope_id)
    try:
        if os.path.exists(ruta):
            os.remove(ruta)
    except OSError as exc:
        current_app.logger.warning('No se pudo borrar %s: %s', ruta, exc)


# --- Mantenimiento ------------------------------------------------------------

def migrate_layout() -> int:
    """Mueve los archivos de la estructura anterior a la actual. Idempotente."""
    from .models import PrivateResource

    base = _base()
    movidos = 0
    biblioteca = folder_for('public')
    os.makedirs(biblioteca, exist_ok=True)
    try:
        sueltos = [n for n in os.listdir(base) if os.path.isfile(os.path.join(base, n)) and not n.startswith('.')]
    except OSError:
        sueltos = []
    for nombre in sueltos:
        try:
            os.replace(os.path.join(base, nombre), os.path.join(biblioteca, nombre))
            movidos += 1
        except OSError as exc:
            log.warning('No se pudo mover %s a library/: %s', nombre, exc)

    privada = os.path.join(base, 'private')
    if os.path.isdir(privada):
        for nombre in os.listdir(privada):
            origen = os.path.join(privada, nombre)
            if not os.path.isfile(origen):
                continue
            nota = PrivateResource.query.filter_by(filename=nombre).first()
            if nota is None:
                continue  # huérfano: lo quitará cleanup()
            destino = folder_for('private', nota.owner_id)
            try:
                os.makedirs(destino, exist_ok=True)
                os.replace(origen, os.path.join(destino, nombre))
                movidos += 1
            except OSError as exc:
                log.warning('No se pudo mover %s a private/%s/: %s', nombre, nota.owner_id, exc)
    if movidos:
        log.info('Archivos reorganizados en la estructura nueva: %s', movidos)
    return movidos


def _referenced() -> dict[str, set[str]]:
    from .models import GroupResource, PrivateResource, Resource, User

    return {
        'library': {r.filename for r in Resource.query.with_entities(Resource.filename)},
        'private': {p.filename for p in PrivateResource.query.with_entities(PrivateResource.filename) if p.filename},
        'groups': {g.filename for g in GroupResource.query.with_entities(GroupResource.filename)},
        'profile': {u.profile_picture for u in User.query.with_entities(User.profile_picture) if u.profile_picture},
    }


def cleanup(*, dry_run: bool = False, min_age_hours: float = 24) -> dict:
    """Borra subidas a medias (tmp/) y archivos que ya no pertenecen a ningún registro.

    Sólo toca archivos con más de `min_age_hours` horas, para no borrar uno que
    se está guardando en este momento. Devuelve un informe.
    """
    base = _base()
    ahora = time.time()
    usados = _referenced()
    informe = {'removed': [], 'bytes': 0, 'dry_run': dry_run}

    def quitar(ruta: str) -> None:
        try:
            tam = os.path.getsize(ruta)
            if not dry_run:
                os.remove(ruta)
            informe['removed'].append(os.path.relpath(ruta, base))
            informe['bytes'] += tam
        except OSError as exc:
            log.warning('Limpieza: no se pudo borrar %s: %s', ruta, exc)

    tmp = os.path.join(base, TMP_DIR)
    if os.path.isdir(tmp):
        for nombre in os.listdir(tmp):
            ruta = os.path.join(tmp, nombre)
            if os.path.isfile(ruta) and ahora - os.path.getmtime(ruta) > 3600:
                quitar(ruta)

    for carpeta, nombres in usados.items():
        raiz = os.path.join(base, carpeta)
        if not os.path.isdir(raiz):
            continue
        for actual, _dirs, archivos in os.walk(raiz):
            for nombre in archivos:
                ruta = os.path.join(actual, nombre)
                if nombre.startswith('.') or nombre in nombres:
                    continue
                if ahora - os.path.getmtime(ruta) > min_age_hours * 3600:
                    quitar(ruta)
        # Carpetas de grupos o estudiantes que quedaron vacías.
        if not dry_run:
            for actual, dirs, archivos in os.walk(raiz, topdown=False):
                if actual != raiz and not dirs and not archivos:
                    try:
                        os.rmdir(actual)
                    except OSError:
                        pass
    if informe['removed']:
        log.info('Limpieza de archivos: %s huérfanos (%.1f MB)%s', len(informe['removed']),
                 informe['bytes'] / 1024 / 1024, ' [simulación]' if dry_run else '')
    return informe


def stats() -> dict:
    """Archivos y espacio por carpeta, y espacio libre en el disco."""
    base = _base()
    carpetas = {}
    for carpeta in (*CARPETAS.values(), TMP_DIR):
        raiz = os.path.join(base, carpeta)
        n = tam = 0
        if os.path.isdir(raiz):
            for actual, _dirs, archivos in os.walk(raiz):
                for nombre in archivos:
                    if not nombre.startswith('.'):
                        n += 1
                        tam += os.path.getsize(os.path.join(actual, nombre))
        carpetas[carpeta] = {'files': n, 'bytes': tam}
    try:
        libre = shutil.disk_usage(base).free
    except OSError:
        libre = None
    return {'folders': carpetas, 'free_bytes': libre, 'path': base}
