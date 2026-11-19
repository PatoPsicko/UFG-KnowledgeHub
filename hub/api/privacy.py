"""Privacidad de la cuenta (Fase 3C).

    GET    /api/me/export   ZIP con mis datos (datos.json) y los archivos que subí
    DELETE /api/me          {password, confirm: "BORRAR"} borra la cuenta y lo que subí

Qué se borra con la cuenta: perfil, sesiones, notas y archivos de Mi espacio,
documentos que subí a la biblioteca y a grupos (con sus archivos), mensajes de
grupo, conversaciones con Francis, guardados, notificaciones y reportes. Los
grupos que lideraba pasan al miembro más antiguo (o se eliminan si no queda
nadie). La bitácora de seguridad conserva el evento con el correo, como exige
el registro de accesos, y se purga sola según AUDIT_RETENTION_DAYS.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import zipfile

from flask import Blueprint, jsonify, send_file

from .. import audit, sessions
from ..ai import specs
from ..errors import ApiError
from ..extensions import bcrypt, db
from ..models import (AIConversation, AuditEvent, ChatMessage, Contact, DirectMessage, DocumentReport, FileScan, Group,
                      GroupMember, GroupMessage, GroupResource, GroupTask, Notification, PrivateResource, Resource,
                      SavedResource, User, UserSession, display_filename, iso_utc, utcnow)
from ..storage import delete_upload, folder_for, path_for
from ..utils import SlidingWindowLimiter, current_user, json_body, login_required, notify

bp = Blueprint('privacy', __name__, url_prefix='/api/me')

export_limiter = SlidingWindowLimiter(3, 3600)
MAX_EXPORT_FILES_MB = 200


def _datos(u: User) -> dict:
    recursos = Resource.query.filter_by(owner_id=u.id).all()
    privados = PrivateResource.query.filter_by(owner_id=u.id).all()
    de_grupo = GroupResource.query.filter_by(user_id=u.id).all()
    grupos = {m.group_id: m for m in GroupMember.query.filter_by(user_id=u.id).all()}
    nombres_grupo = dict(db.session.query(Group.id, Group.name).filter(Group.id.in_(grupos or {-1})).all())
    conversaciones = AIConversation.query.filter_by(user_id=u.id).all()
    return {
        'exportado': iso_utc(utcnow()),
        'cuenta': {**u.private_dict(), 'preferences': u.prefs()},
        'biblioteca': [{'id': r.id, 'titulo': r.title, 'autor': r.author, 'categoria': r.category, 'etiquetas': r.tags,
                        'descripcion': r.description, 'archivo': display_filename(r.filename), 'descargas': r.downloads,
                        'estado': r.scan_status or 'clean', 'subido': iso_utc(r.created_at)} for r in recursos],
        'mi_espacio': [{'id': p.id, 'tipo': p.type, 'titulo': p.title, 'contenido': p.content if p.type == 'note' else None,
                        'archivo': display_filename(p.filename) if p.filename else None,
                        'creado': iso_utc(p.created_at), 'actualizado': iso_utc(p.updated_at)} for p in privados],
        'grupos': [{'id': gid, 'nombre': nombres_grupo.get(gid), 'desde': iso_utc(m.joined_at)} for gid, m in grupos.items()],
        'archivos_en_grupos': [{'id': g.id, 'grupo': nombres_grupo.get(g.group_id), 'titulo': g.title,
                                'archivo': display_filename(g.filename), 'subido': iso_utc(g.uploaded_at)} for g in de_grupo],
        'mensajes_en_grupos': [{'grupo': nombres_grupo.get(m.group_id), 'mensaje': m.message, 'fecha': iso_utc(m.timestamp)}
                               for m in GroupMessage.query.filter_by(user_id=u.id).order_by(GroupMessage.id).all()],
        'tareas_creadas': [{'titulo': t.title, 'estado': t.status, 'grupo': nombres_grupo.get(t.group_id)}
                           for t in GroupTask.query.filter_by(created_by=u.id).all()],
        'guardados': [s.resource_id for s in SavedResource.query.filter_by(user_id=u.id).all()],
        'conversaciones_con_francis': [{'titulo': c.title, 'fecha': iso_utc(c.created_at),
                                        'mensajes': [{'rol': m.role, 'texto': m.content, 'fecha': iso_utc(m.created_at)}
                                                     for m in c.messages]} for c in conversaciones],
        'reportes_enviados': [r.to_dict() for r in DocumentReport.query.filter_by(reporter_id=u.id).all()],
        'sesiones': [{'dispositivo': s.device, 'ip': s.ip, 'abierta': iso_utc(s.created_at),
                      'ultima_actividad': iso_utc(s.last_seen_at), 'cerrada': iso_utc(s.revoked_at)}
                     for s in UserSession.query.filter_by(user_id=u.id).all()],
        'bitacora_de_seguridad': [e.to_dict() for e in AuditEvent.query.filter_by(user_id=u.id)
                                  .order_by(AuditEvent.id.desc()).limit(500).all()],
    }


@bp.get('/export')
@login_required
def export():
    u = current_user()
    if not export_limiter.allow(u.id):
        raise ApiError('Ya descargaste tus datos varias veces esta hora. Inténtalo más tarde.', 429)
    datos = _datos(u)
    salida = io.BytesIO()
    total = 0
    with zipfile.ZipFile(salida, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('datos.json', json.dumps(datos, ensure_ascii=False, indent=2))
        z.writestr('LEEME.txt', 'Datos de tu cuenta en UFG Knowledge Hub.\n\ndatos.json: perfil, documentos, notas, grupos, '
                                'mensajes de grupo, conversaciones con Francis, sesiones y bitácora.\narchivos/: los '
                                'archivos que subiste (biblioteca, grupos y Mi espacio).\n')
        archivos = [('biblioteca', 'public', r.filename, None) for r in Resource.query.filter_by(owner_id=u.id).all()]
        archivos += [('mi_espacio', 'private', p.filename, u.id) for p in
                     PrivateResource.query.filter_by(owner_id=u.id, type='file').all()]
        archivos += [('grupos', 'group', g.filename, g.group_id) for g in GroupResource.query.filter_by(user_id=u.id).all()]
        for carpeta, kind, nombre, scope in archivos:
            ruta = path_for(kind, nombre, scope)
            if not nombre or not os.path.isfile(ruta):
                continue
            total += os.path.getsize(ruta)
            if total > MAX_EXPORT_FILES_MB * 1024 * 1024:
                z.writestr('archivos/FALTAN_ARCHIVOS.txt', 'Se alcanzó el límite de la descarga; baja los demás desde la app.')
                break
            z.write(ruta, f'archivos/{carpeta}/{display_filename(nombre)}')
    audit.record('data_export', user=u)
    db.session.commit()
    salida.seek(0)
    return send_file(salida, mimetype='application/zip', as_attachment=True,
                     download_name=f'mis_datos_ufg_hub_{utcnow():%Y%m%d}.zip')


def delete_account(u: User) -> None:
    """Borra la cuenta y todo lo que el estudiante subió."""
    uid = u.id
    # Grupos que lideraba: pasan al miembro más antiguo o se eliminan.
    from .groups import _delete_group
    for grupo in Group.query.filter_by(owner_id=uid).all():
        otros = sorted((m for m in grupo.members if m.user_id != uid), key=lambda m: m.id)
        if otros:
            grupo.owner_id = otros[0].user_id
            notify(otros[0].user_id, 'group_owner', 'Ahora eres líder', f'Eres el nuevo líder del grupo «{grupo.name}».',
                   grupo.id)
        else:
            _delete_group(grupo)
    db.session.commit()

    for r in Resource.query.filter_by(owner_id=uid).all():
        delete_upload('public', r.filename)
        specs.unindex('public', r.id)
        SavedResource.query.filter_by(resource_id=r.id).delete()
        db.session.delete(r)
    for g in GroupResource.query.filter_by(user_id=uid).all():
        delete_upload('group', g.filename, g.group_id)
        specs.unindex('group', g.id)
        db.session.delete(g)
    for p in PrivateResource.query.filter_by(owner_id=uid).all():
        specs.unindex('private_file' if p.type == 'file' else 'private_note', p.id)
        db.session.delete(p)
    shutil.rmtree(folder_for('private', uid), ignore_errors=True)
    if u.profile_picture:
        delete_upload('avatar', u.profile_picture)

    GroupTask.query.filter_by(assigned_to=uid).update({'assigned_to': None})
    for modelo, campo in ((GroupMember, 'user_id'), (GroupMessage, 'user_id'), (ChatMessage, 'user_id'),
                          (SavedResource, 'user_id'), (Notification, 'user_id'), (UserSession, 'user_id'),
                          (DocumentReport, 'reporter_id')):
        modelo.query.filter(getattr(modelo, campo) == uid).delete(synchronize_session=False)
    DirectMessage.query.filter((DirectMessage.sender_id == uid) | (DirectMessage.receiver_id == uid)).delete(
        synchronize_session=False)
    Contact.query.filter((Contact.user_id == uid) | (Contact.contact_id == uid)).delete(synchronize_session=False)
    for c in AIConversation.query.filter_by(user_id=uid).all():
        db.session.delete(c)
    FileScan.query.filter_by(user_id=uid).update({'user_id': None})
    db.session.delete(u)
    db.session.commit()


@bp.delete('')
@login_required
def delete_me():
    u = current_user()
    data = json_body()
    if (data.get('confirm') or '').strip().upper() != 'BORRAR':
        raise ApiError('Escribe BORRAR para confirmar.', 400, 'confirm_required')
    if not bcrypt.check_password_hash(u.password, data.get('password') or ''):
        raise ApiError('La contraseña no es correcta.', 400, 'wrong_password')
    if u.is_admin and User.query.filter_by(role='admin').count() <= 1:
        raise ApiError('Eres el único administrador: nombra a otro antes de borrar tu cuenta.', 400, 'last_admin')
    audit.record('account_deleted', user=u)
    db.session.commit()
    delete_account(u)
    respuesta = jsonify({'message': 'Tu cuenta y tus datos se borraron.'})
    sessions.clear_cookie(respuesta)
    return respuesta, 200

