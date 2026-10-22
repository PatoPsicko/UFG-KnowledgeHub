"""Biblioteca compartida: documentos públicos para toda la comunidad UFG."""

from __future__ import annotations

import os

from flask import Blueprint, jsonify, request, send_file
from sqlalchemy import func, or_, true

from ..ai import specs
from ..errors import ApiError
from ..extensions import db
from ..models import (SCAN_BLOCKED, SCAN_CLEAN, SCAN_PENDING, VISIBLE_STATUSES, Resource, SavedResource, User,
                      display_filename, iso_utc)
from ..security import pipeline
from ..storage import delete_upload, extension, path_for, save_upload
from ..utils import clean_text, current_user, form_or_json, login_required, query_int

bp = Blueprint('library', __name__, url_prefix='/api/resources')


def serialize(r: Resource, viewer: User, saved_ids: set[int] | None = None) -> dict:
    return {
        'id': r.id,
        'doc_key': f'public:{r.id}',
        'title': r.title,
        'author': r.author,
        'category': r.category or 'Sin categoría',
        'tags': r.tags or '',
        'description': r.description or '',
        'original_filename': display_filename(r.filename),
        'extension': extension(r.filename),
        'file_size': r.file_size,
        'downloads': r.downloads or 0,
        'owner': r.owner.public_dict() if r.owner else None,
        'owner_id': r.owner_id,
        'owner_name': r.owner.name if r.owner else 'Usuario eliminado',
        'is_owner': r.owner_id == viewer.id,
        'saved': r.id in (saved_ids or set()),
        'scan_status': r.scan_status or SCAN_CLEAN,
        'created_at': iso_utc(r.created_at),
    }


def _visible_filter(viewer: User):
    if viewer.is_admin:
        return true()
    return or_(Resource.scan_status.is_(None), Resource.scan_status == SCAN_CLEAN, Resource.owner_id == viewer.id)


def _get_visible(resource_id: int, viewer: User) -> Resource:
    r = db.session.get(Resource, resource_id)
    if r is None:
        raise ApiError('Documento no encontrado.', 404)
    if r.scan_status not in VISIBLE_STATUSES and r.owner_id != viewer.id and not viewer.is_admin:
        raise ApiError('Documento no encontrado.', 404)
    return r


def _saved_ids(user_id: int) -> set[int]:
    return {s.resource_id for s in SavedResource.query.filter_by(user_id=user_id).all()}


@bp.get('')
@login_required
def list_resources():
    viewer = current_user()
    consulta = Resource.query.filter(_visible_filter(viewer))

    q = (request.args.get('q') or '').strip()
    for termino in q.split()[:8]:
        patron = f'%{termino}%'
        consulta = consulta.filter(or_(Resource.title.ilike(patron), Resource.author.ilike(patron),
                                       Resource.tags.ilike(patron), Resource.category.ilike(patron),
                                       Resource.description.ilike(patron)))
    categoria = (request.args.get('category') or '').strip()
    if categoria:
        consulta = consulta.filter(Resource.category == categoria)

    guardados = _saved_ids(viewer.id)
    alcance = request.args.get('scope', 'all')
    if alcance == 'mine':
        consulta = consulta.filter(Resource.owner_id == viewer.id)
    elif alcance == 'saved':
        consulta = consulta.filter(Resource.id.in_(guardados or {-1}))

    orden = request.args.get('sort', 'recent')
    if orden == 'popular':
        consulta = consulta.order_by(Resource.downloads.desc(), Resource.id.desc())
    elif orden == 'title':
        consulta = consulta.order_by(func.lower(Resource.title))
    else:
        consulta = consulta.order_by(Resource.created_at.desc(), Resource.id.desc())

    total = consulta.count()
    limite = query_int('limit', 60, minimum=1, maximum=200)
    desde = query_int('offset', 0)
    filas = consulta.offset(desde).limit(limite).all()
    return jsonify({
        'resources': [serialize(r, viewer, guardados) for r in filas],
        'total': total, 'limit': limite, 'offset': desde,
        # Compatibilidad con la interfaz anterior.
        'user_id': viewer.id, 'user_name': viewer.name,
    }), 200


@bp.get('/categories')
@login_required
def categories():
    viewer = current_user()
    filas = (db.session.query(Resource.category, func.count(Resource.id))
             .filter(_visible_filter(viewer)).group_by(Resource.category).all())
    return jsonify({'categories': [{'name': c or 'Sin categoría', 'count': n} for c, n in
                                   sorted(filas, key=lambda f: -f[1])]}), 200


@bp.get('/<int:resource_id>')
@login_required
def get_resource(resource_id: int):
    viewer = current_user()
    r = _get_visible(resource_id, viewer)
    return jsonify({'resource': serialize(r, viewer, _saved_ids(viewer.id))}), 200


def _fields(data: dict, *, partial: bool = False) -> dict:
    campos = {
        'title': clean_text(data.get('title'), 'título', required=not partial, max_len=200),
        'author': clean_text(data.get('author'), 'autor', required=not partial, max_len=200),
        'category': clean_text(data.get('category'), 'categoría', max_len=100),
        'tags': clean_text(data.get('tags'), 'etiquetas', max_len=300),
        'description': clean_text(data.get('description'), 'descripción', max_len=2000),
    }
    if partial:
        return {k: v for k, v in campos.items() if k in data}
    return campos


@bp.post('')
@login_required
def create_resource():
    viewer = current_user()
    campos = _fields(request.form.to_dict())
    stored, ruta, size = save_upload(request.files.get('file'), 'public')
    original = request.files['file'].filename
    check = pipeline.check_upload(ruta, original, 'public', viewer.id)

    recurso = Resource(**campos, filename=stored, file_size=size, owner_id=viewer.id,
                       scan_status=SCAN_PENDING, downloads=0)
    db.session.add(recurso)
    db.session.commit()
    pipeline.enqueue('public', recurso.id, stored, original, viewer.id, check,
                     title=recurso.title, description=recurso.description or '')
    db.session.refresh(recurso)
    return jsonify({'message': 'Documento recibido. Se publicará cuando pase la revisión de seguridad.',
                    'id': recurso.id, 'resource': serialize(recurso, viewer)}), 201


@bp.put('/<int:resource_id>')
@login_required
def update_resource(resource_id: int):
    viewer = current_user()
    r = db.session.get(Resource, resource_id)
    if r is None:
        raise ApiError('Documento no encontrado.', 404)
    if r.owner_id != viewer.id and not viewer.is_admin:
        raise ApiError('Sólo quien subió el documento puede editarlo.', 403)

    for campo, valor in _fields(form_or_json(), partial=True).items():
        if campo in ('title', 'author') and not valor:
            raise ApiError(f'El campo «{campo}» no puede quedar vacío.', 400)
        setattr(r, campo, valor)

    archivo = request.files.get('file')
    nuevo = None
    if archivo and archivo.filename:
        stored, ruta, size = save_upload(archivo, 'public')
        check = pipeline.check_upload(ruta, archivo.filename, 'public', viewer.id)
        anterior = r.filename
        r.filename, r.file_size, r.scan_status = stored, size, SCAN_PENDING
        nuevo = (stored, archivo.filename, check)
        delete_upload('public', anterior)
    db.session.commit()

    if nuevo:
        specs.unindex('public', r.id)
        pipeline.enqueue('public', r.id, nuevo[0], nuevo[1], viewer.id, nuevo[2],
                         title=r.title, description=r.description or '')
    elif r.scan_status in VISIBLE_STATUSES:
        specs.reindex(specs.spec_resource(r))
    db.session.refresh(r)
    return jsonify({'message': 'Documento actualizado.', 'resource': serialize(r, viewer, _saved_ids(viewer.id))}), 200


@bp.delete('/<int:resource_id>')
@login_required
def delete_resource(resource_id: int):
    viewer = current_user()
    r = db.session.get(Resource, resource_id)
    if r is None:
        raise ApiError('Documento no encontrado.', 404)
    if r.owner_id != viewer.id and not viewer.is_admin:
        raise ApiError('Sólo quien subió el documento puede eliminarlo.', 403)
    filename = r.filename
    SavedResource.query.filter_by(resource_id=r.id).delete()
    db.session.delete(r)
    db.session.commit()
    # El archivo se borra tras confirmar el borrado en la base de datos.
    delete_upload('public', filename)
    specs.unindex('public', resource_id)
    return jsonify({'message': 'Documento eliminado.'}), 200


@bp.post('/<int:resource_id>/save')
@login_required
def toggle_save(resource_id: int):
    viewer = current_user()
    _get_visible(resource_id, viewer)
    existente = SavedResource.query.filter_by(user_id=viewer.id, resource_id=resource_id).first()
    if existente:
        db.session.delete(existente)
        guardado = False
    else:
        db.session.add(SavedResource(user_id=viewer.id, resource_id=resource_id))
        guardado = True
    db.session.commit()
    return jsonify({'saved': guardado}), 200


@bp.get('/<int:resource_id>/file')
@login_required
def download(resource_id: int):
    """Archivo del documento. ?download=1 lo descarga (y cuenta la descarga);
    sin él se devuelve para previsualizar en el navegador."""
    viewer = current_user()
    r = _get_visible(resource_id, viewer)
    if r.scan_status == SCAN_BLOCKED and not viewer.is_admin:
        raise ApiError('El documento fue bloqueado por seguridad.', 403, 'scan_blocked')
    ruta = path_for('public', r.filename)
    if not os.path.exists(ruta):
        raise ApiError('El archivo ya no está en el servidor.', 404)
    descargar = request.args.get('download') == '1'
    if descargar and r.owner_id != viewer.id:
        r.downloads = (r.downloads or 0) + 1
        db.session.commit()
    return send_file(ruta, as_attachment=descargar, download_name=display_filename(r.filename))
