"""Anotaciones privadas: notas de texto y archivos personales."""

from __future__ import annotations

import os

from flask import Blueprint, jsonify, request, send_file

from ..ai import specs
from ..errors import ApiError
from ..extensions import db
from ..models import (SCAN_BLOCKED, SCAN_CLEAN, SCAN_PENDING, VISIBLE_STATUSES, PrivateResource,
                      display_filename, iso_utc, utcnow)
from ..security import pipeline
from ..storage import delete_upload, extension, path_for, save_upload
from ..utils import clean_text, current_user, json_body, login_required

bp = Blueprint('notes', __name__, url_prefix='/api/private-resources')

MAX_NOTE = 50_000


def note_dict(p: PrivateResource) -> dict:
    es_archivo = p.type == 'file'
    return {
        'id': p.id,
        'doc_key': f"{'private_file' if es_archivo else 'private_note'}:{p.id}",
        'title': p.title,
        'content': p.content or '',
        'type': p.type,
        'filename': p.filename,
        'original_filename': display_filename(p.filename),
        'extension': extension(p.filename) if es_archivo else None,
        'file_size': p.file_size,
        'scan_status': (p.scan_status or SCAN_CLEAN) if es_archivo else SCAN_CLEAN,
        'download_url': f'/api/private-resources/{p.id}/download' if es_archivo else None,
        'created_at': iso_utc(p.created_at),
        'updated_at': iso_utc(p.updated_at),
    }


def _own(resource_id: int) -> PrivateResource:
    p = db.session.get(PrivateResource, resource_id)
    if p is None or p.owner_id != current_user().id:
        raise ApiError('Anotación no encontrada.', 404)
    return p


@bp.get('')
@login_required
def list_notes():
    viewer = current_user()
    filas = PrivateResource.query.filter_by(owner_id=viewer.id).order_by(PrivateResource.updated_at.desc()).all()
    return jsonify({'resources': [note_dict(p) for p in filas]}), 200


@bp.post('')
@login_required
def create_note():
    viewer = current_user()
    archivo = request.files.get('file')
    if archivo and archivo.filename:
        titulo = clean_text(request.form.get('title') or archivo.filename, 'título', required=True, max_len=200)
        stored, ruta, size = save_upload(archivo, 'private')
        check = pipeline.check_upload(ruta, archivo.filename, 'private', viewer.id)
        nota = PrivateResource(title=titulo, filename=stored, file_size=size, type='file', owner_id=viewer.id,
                               scan_status=SCAN_PENDING)
        db.session.add(nota)
        db.session.commit()
        pipeline.enqueue('private', nota.id, stored, archivo.filename, viewer.id, check, title=titulo)
        db.session.refresh(nota)
    else:
        data = json_body()
        nota = PrivateResource(title=clean_text(data.get('title'), 'título', required=True, max_len=200),
                               content=clean_text(data.get('content'), 'contenido', max_len=MAX_NOTE) or '',
                               type='note', owner_id=viewer.id)
        db.session.add(nota)
        db.session.commit()
        specs.reindex(specs.spec_private(nota))
    return jsonify({'message': 'Anotación guardada.', 'id': nota.id, 'resource': note_dict(nota)}), 201


@bp.put('/<int:resource_id>')
@login_required
def update_note(resource_id: int):
    p = _own(resource_id)
    data = json_body()
    if 'title' in data:
        p.title = clean_text(data.get('title'), 'título', required=True, max_len=200)
    if 'content' in data and p.type == 'note':
        p.content = clean_text(data.get('content'), 'contenido', max_len=MAX_NOTE) or ''
    p.updated_at = utcnow()
    db.session.commit()
    if p.type == 'note' or p.scan_status in VISIBLE_STATUSES:
        specs.reindex(specs.spec_private(p))
    return jsonify({'message': 'Anotación actualizada.', 'resource': note_dict(p)}), 200


@bp.delete('/<int:resource_id>')
@login_required
def delete_note(resource_id: int):
    p = _own(resource_id)
    filename = p.filename if p.type == 'file' else None
    kind = 'private_file' if p.type == 'file' else 'private_note'
    db.session.delete(p)
    db.session.commit()
    delete_upload('private', filename)
    specs.unindex(kind, resource_id)
    return jsonify({'message': 'Anotación eliminada.'}), 200


@bp.get('/<int:resource_id>/download')
@login_required
def download(resource_id: int):
    p = _own(resource_id)
    if p.type != 'file' or not p.filename:
        raise ApiError('Esta anotación no tiene archivo.', 404)
    if p.scan_status == SCAN_BLOCKED:
        raise ApiError('El archivo fue bloqueado por seguridad.', 403, 'scan_blocked')
    ruta = path_for('private', p.filename)
    if not os.path.exists(ruta):
        raise ApiError('El archivo ya no está en el servidor.', 404)
    return send_file(ruta, as_attachment=request.args.get('inline') != '1',
                     download_name=display_filename(p.filename))
