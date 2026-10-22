"""Perfil propio, perfiles de otros estudiantes, fotos y estadísticas."""

from __future__ import annotations

import os
import re

from flask import Blueprint, jsonify, request, send_from_directory

from ..errors import ApiError
from ..extensions import bcrypt, db
from ..models import Contact, GroupMember, PrivateResource, Resource, SavedResource, User
from ..security import pipeline
from ..storage import IMAGE_EXTENSIONS, delete_upload, folder_for, save_upload
from ..utils import are_contacts, clean_text, current_user, form_or_json, json_body, login_required, user_group_ids
from .social import _relation, is_online, user_card

bp = Blueprint('profile', __name__, url_prefix='/api')

_RE_COLOR = re.compile(r'#[0-9A-Fa-f]{6}')


@bp.get('/user/stats')
@login_required
def stats():
    viewer = current_user()
    contactos = Contact.query.filter(((Contact.user_id == viewer.id) | (Contact.contact_id == viewer.id))
                                     & (Contact.status == 'accepted')).count()
    descargas = db.session.query(db.func.coalesce(db.func.sum(Resource.downloads), 0)) \
        .filter(Resource.owner_id == viewer.id).scalar()
    return jsonify({
        'resources_count': Resource.query.filter_by(owner_id=viewer.id).count(),
        'downloads_received': int(descargas or 0),
        'saved_count': SavedResource.query.filter_by(user_id=viewer.id).count(),
        'groups_count': GroupMember.query.filter_by(user_id=viewer.id).count(),
        'contacts_count': contactos,
        'notes_count': PrivateResource.query.filter_by(owner_id=viewer.id, type='note').count(),
        'files_count': PrivateResource.query.filter_by(owner_id=viewer.id, type='file').count(),
        'registered_users': User.query.count(),
        'library_size': Resource.query.count(),
    }), 200


@bp.post('/profile')
@bp.put('/profile')
@login_required
def update_profile():
    user = current_user()
    data = form_or_json()
    if 'name' in data:
        user.name = clean_text(data.get('name'), 'nombre', required=True, max_len=150)
    if 'career' in data:
        user.career = clean_text(data.get('career'), 'carrera', max_len=100)
    if 'bio' in data:
        user.bio = clean_text(data.get('bio'), 'presentación', max_len=280)
    if 'semester' in data:
        semestre = data.get('semester')
        if semestre in ('', None):
            user.semester = None
        else:
            try:
                semestre = int(semestre)
            except (TypeError, ValueError):
                raise ApiError('El ciclo debe ser un número.', 400)
            if not 1 <= semestre <= 12:
                raise ApiError('El ciclo debe estar entre 1 y 12.', 400)
            user.semester = semestre
    if 'profile_color' in data:
        color = (data.get('profile_color') or '').strip()
        if not _RE_COLOR.fullmatch(color):
            raise ApiError('El color debe tener formato #RRGGBB.', 400)
        user.profile_color = color
    db.session.commit()
    return jsonify({'message': 'Perfil actualizado.', 'user': user.private_dict()}), 200


@bp.post('/profile/password')
@login_required
def change_password():
    user = current_user()
    data = json_body()
    if not bcrypt.check_password_hash(user.password, data.get('current_password') or ''):
        raise ApiError('La contraseña actual no es correcta.', 400, 'wrong_password')
    nueva = data.get('new_password') or ''
    if len(nueva) < 8:
        raise ApiError('La nueva contraseña debe tener al menos 8 caracteres.', 400, 'weak_password')
    user.password = bcrypt.generate_password_hash(nueva).decode('utf-8')
    db.session.commit()
    return jsonify({'message': 'Contraseña actualizada.'}), 200


@bp.post('/profile/picture')
@login_required
def upload_picture():
    user = current_user()
    archivo = request.files.get('file')
    stored, ruta, _ = save_upload(archivo, 'avatar', allowed=IMAGE_EXTENSIONS)
    if os.path.getsize(ruta) > 4 * 1024 * 1024:
        os.remove(ruta)
        raise ApiError('La foto no puede superar los 4 MB.', 400)
    check = pipeline.check_upload(ruta, archivo.filename, 'avatar', user.id)
    anterior = user.profile_picture
    user.profile_picture = stored
    db.session.commit()
    delete_upload('avatar', anterior)
    pipeline.enqueue('avatar', user.id, stored, archivo.filename, user.id, check)
    db.session.refresh(user)
    return jsonify({'message': 'Foto actualizada.', 'profile_picture': user.profile_picture,
                    'user': user.private_dict()}), 200


@bp.delete('/profile/picture')
@login_required
def delete_picture():
    user = current_user()
    anterior = user.profile_picture
    user.profile_picture = None
    db.session.commit()
    delete_upload('avatar', anterior)
    return jsonify({'message': 'Foto eliminada.', 'user': user.private_dict()}), 200


@bp.get('/avatars/<filename>')
def avatar(filename: str):
    """Fotos de perfil. Son públicas (una <img> no puede enviar el token), pero el
    nombre lleva un prefijo aleatorio imposible de adivinar y pasan por el vigilante."""
    if '/' in filename or '\\' in filename or not db.session.query(
            User.query.filter_by(profile_picture=filename).exists()).scalar():
        raise ApiError('Imagen no encontrada.', 404)
    respuesta = send_from_directory(folder_for('avatar'), filename, max_age=86400)
    respuesta.headers['Content-Security-Policy'] = "default-src 'none'"
    return respuesta


@bp.get('/users/<int:user_id>/profile')
@login_required
def user_profile(user_id: int):
    viewer = current_user()
    target = db.session.get(User, user_id)
    if target is None:
        raise ApiError('Usuario no encontrado.', 404)
    relacion, request_id = _relation(viewer.id, user_id) if viewer.id != user_id else ('self', None)
    amigos = relacion in ('accepted', 'self')
    comunes = set(user_group_ids(viewer.id)) & set(user_group_ids(user_id))
    return jsonify({'user': {
        **user_card(target),
        'email': target.email if amigos else None,
        'semester': target.semester,
        'bio': target.bio,
        'created_at': target.private_dict()['created_at'],
        'resources_count': Resource.query.filter_by(owner_id=target.id).count(),
        'groups_in_common': len(comunes),
        'relation': relacion,
        'request_id': request_id,
        'online': is_online(target),
        'can_message': are_contacts(viewer.id, user_id),
    }}), 200
