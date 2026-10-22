"""Grupos de trabajo: miembros, chat, tareas y archivos compartidos."""

from __future__ import annotations

import os
import shutil
from datetime import datetime

from flask import Blueprint, jsonify, request, send_file
from sqlalchemy import func

from ..ai import specs
from ..errors import ApiError
from ..extensions import db
from ..models import (SCAN_BLOCKED, SCAN_CLEAN, SCAN_PENDING, VISIBLE_STATUSES, Group, GroupMember, GroupMessage, GroupResource,
                      GroupTask, User, display_filename, iso_utc)
from ..security import pipeline
from ..storage import delete_upload, extension, folder_for, path_for, save_upload
from ..utils import (are_contacts, clean_text, current_user, json_body, login_required, membership,
                     message_text, notify, parse_int, query_int)
from .social import user_card

bp = Blueprint('groups', __name__, url_prefix='/api/groups')

TASK_STATUSES = ('pending', 'in_progress', 'completed')


# --- Ayudantes ---------------------------------------------------------------------
def _group_or_404(group_id: int) -> Group:
    grupo = db.session.get(Group, group_id)
    if grupo is None:
        raise ApiError('Grupo no encontrado.', 404)
    return grupo


def _member_or_403(group_id: int) -> tuple[Group, GroupMember]:
    grupo = _group_or_404(group_id)
    m = membership(group_id, current_user().id)
    if m is None:
        raise ApiError('No eres miembro de este grupo.', 403, 'not_member')
    return grupo, m


def _owner_or_403(group_id: int) -> Group:
    grupo = _group_or_404(group_id)
    if grupo.owner_id != current_user().id:
        raise ApiError('Sólo el líder del grupo puede hacer esto.', 403, 'not_owner')
    return grupo


def group_summary(g: Group, viewer_id: int, m: GroupMember | None = None) -> dict:
    ultimo = GroupMessage.query.filter_by(group_id=g.id).order_by(GroupMessage.id.desc()).first()
    leido = (m.last_read_message_id or 0) if m else 0
    no_leidos = GroupMessage.query.filter(GroupMessage.group_id == g.id, GroupMessage.id > leido,
                                          GroupMessage.user_id != viewer_id).count() if m else 0
    return {
        'id': g.id,
        'name': g.name,
        'description': g.description or '',
        'subject': g.subject or '',
        'owner_id': g.owner_id,
        'owner_name': g.owner.name if g.owner else 'Usuario eliminado',
        'is_owner': g.owner_id == viewer_id,
        'member_count': len(g.members),
        'open_tasks': GroupTask.query.filter(GroupTask.group_id == g.id, GroupTask.status != 'completed').count(),
        'resource_count': GroupResource.query.filter(GroupResource.group_id == g.id).count(),
        'unread': no_leidos,
        'last_message': message_dict(ultimo) if ultimo else None,
        'created_at': iso_utc(g.created_at),
    }


def member_dict(m: GroupMember, grupo: Group) -> dict:
    return {**user_card(m.user), 'email': m.user.email, 'is_owner': m.user_id == grupo.owner_id,
            'joined_at': iso_utc(m.joined_at)}


def message_dict(m: GroupMessage) -> dict:
    return {'id': m.id, 'user_id': m.user_id, 'user_name': m.author.name if m.author else 'Usuario eliminado',
            'user': m.author.public_dict() if m.author else None, 'message': m.message,
            'timestamp': iso_utc(m.timestamp)}


def task_dict(t: GroupTask) -> dict:
    return {
        'id': t.id, 'title': t.title, 'description': t.description or '', 'status': t.status or 'pending',
        'due_date': t.due_date.date().isoformat() if t.due_date else None,
        'assigned_to': t.assignee.name if t.assignee else None,
        'assigned_to_id': t.assigned_to,
        'created_by': t.creator.name if t.creator else 'Usuario eliminado',
        'created_by_id': t.created_by,
        'created_at': iso_utc(t.created_at),
    }


def resource_dict(r: GroupResource, viewer_id: int, owner_id: int) -> dict:
    return {
        'id': r.id, 'doc_key': f'group:{r.id}', 'title': r.title, 'description': r.description or '',
        'original_filename': display_filename(r.filename), 'extension': extension(r.filename),
        'file_size': r.file_size, 'uploaded_by': r.uploader.name if r.uploader else 'Usuario eliminado',
        'uploaded_by_id': r.user_id, 'can_delete': viewer_id in (r.user_id, owner_id),
        'scan_status': r.scan_status or SCAN_CLEAN,
        'download_url': f'/api/groups/{r.group_id}/resources/{r.id}/download',
        'uploaded_at': iso_utc(r.uploaded_at),
    }


def _visible_resources(grupo: Group, viewer_id: int) -> list[GroupResource]:
    filas = GroupResource.query.filter_by(group_id=grupo.id).order_by(GroupResource.id.desc()).all()
    return [r for r in filas if r.scan_status in VISIBLE_STATUSES or viewer_id in (r.user_id, grupo.owner_id)]


def _parse_due(valor) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor).replace('Z', '+00:00')[:19]).replace(tzinfo=None)
    except ValueError:
        try:
            return datetime.strptime(str(valor)[:10], '%Y-%m-%d')
        except ValueError:
            raise ApiError('La fecha de entrega no es válida (usa AAAA-MM-DD).', 400)


# --- Grupos ------------------------------------------------------------------------
@bp.get('')
@login_required
def list_groups():
    viewer = current_user()
    membresias = GroupMember.query.filter_by(user_id=viewer.id).all()
    grupos = [group_summary(m.group, viewer.id, m) for m in membresias if m.group]
    grupos.sort(key=lambda g: (g['last_message'] or {}).get('id', 0), reverse=True)
    return jsonify({'groups': grupos}), 200


@bp.post('')
@login_required
def create_group():
    viewer = current_user()
    data = json_body()
    grupo = Group(name=clean_text(data.get('name'), 'nombre', required=True, max_len=200),
                  description=clean_text(data.get('description'), 'descripción', max_len=2000),
                  subject=clean_text(data.get('subject'), 'materia', max_len=120), owner_id=viewer.id)
    db.session.add(grupo)
    db.session.flush()
    db.session.add(GroupMember(group_id=grupo.id, user_id=viewer.id))
    invitados = 0
    for uid in data.get('member_ids') or []:
        try:
            uid = int(uid)
        except (TypeError, ValueError):
            continue
        if uid != viewer.id and are_contacts(viewer.id, uid):
            db.session.add(GroupMember(group_id=grupo.id, user_id=uid))
            notify(uid, 'group_invite', 'Te agregaron a un grupo',
                   f'{viewer.name} te agregó al grupo «{grupo.name}»', grupo.id)
            invitados += 1
    db.session.commit()
    return jsonify({'message': 'Grupo creado.', 'group_id': grupo.id, 'invited': invitados,
                    'group': group_summary(grupo, viewer.id, membership(grupo.id, viewer.id))}), 201


@bp.get('/<int:group_id>')
@login_required
def get_group(group_id: int):
    viewer = current_user()
    grupo, m = _member_or_403(group_id)
    miembros = GroupMember.query.filter_by(group_id=group_id).all()
    tareas = GroupTask.query.filter_by(group_id=group_id).order_by(GroupTask.id.desc()).all()
    return jsonify({
        'group': group_summary(grupo, viewer.id, m),
        'members': sorted([member_dict(x, grupo) for x in miembros if x.user],
                          key=lambda x: (not x['is_owner'], x['name'].lower())),
        'resources': [resource_dict(r, viewer.id, grupo.owner_id) for r in _visible_resources(grupo, viewer.id)],
        'tasks': [task_dict(t) for t in tareas],
    }), 200


@bp.put('/<int:group_id>')
@login_required
def update_group(group_id: int):
    grupo = _owner_or_403(group_id)
    data = json_body()
    if 'name' in data:
        grupo.name = clean_text(data.get('name'), 'nombre', required=True, max_len=200)
    if 'description' in data:
        grupo.description = clean_text(data.get('description'), 'descripción', max_len=2000)
    if 'subject' in data:
        grupo.subject = clean_text(data.get('subject'), 'materia', max_len=120)
    db.session.commit()
    return jsonify({'message': 'Grupo actualizado.'}), 200


def _delete_group(grupo: Group) -> None:
    ids = [r.id for r in grupo.resources]
    carpeta = folder_for('group', grupo.id)
    db.session.delete(grupo)
    db.session.commit()
    shutil.rmtree(carpeta, ignore_errors=True)
    for rid in ids:
        specs.unindex('group', rid)


@bp.delete('/<int:group_id>')
@login_required
def delete_group(group_id: int):
    grupo = _owner_or_403(group_id)
    nombre = grupo.name
    for m in grupo.members:
        if m.user_id != grupo.owner_id:
            notify(m.user_id, 'group_deleted', 'Grupo eliminado', f'El grupo «{nombre}» fue eliminado por su líder.')
    _delete_group(grupo)
    return jsonify({'message': 'Grupo eliminado.'}), 200


@bp.post('/<int:group_id>/leave')
@login_required
def leave_group(group_id: int):
    viewer = current_user()
    grupo, m = _member_or_403(group_id)
    otros = [x for x in grupo.members if x.user_id != viewer.id]
    if not otros:
        _delete_group(grupo)
        return jsonify({'message': 'Saliste del grupo y, como no quedaba nadie, se eliminó.'}), 200
    if grupo.owner_id == viewer.id:
        # El liderazgo pasa al miembro más antiguo.
        nuevo = min(otros, key=lambda x: x.id)
        grupo.owner_id = nuevo.user_id
        notify(nuevo.user_id, 'group_owner', 'Ahora eres líder', f'Eres el nuevo líder del grupo «{grupo.name}».',
               grupo.id)
    db.session.delete(m)
    db.session.commit()
    return jsonify({'message': 'Saliste del grupo.'}), 200


# --- Miembros ----------------------------------------------------------------------
@bp.get('/<int:group_id>/members')
@login_required
def list_members(group_id: int):
    grupo, _ = _member_or_403(group_id)
    return jsonify({'members': [member_dict(x, grupo) for x in grupo.members if x.user]}), 200


@bp.post('/<int:group_id>/invite')
@login_required
def invite(group_id: int):
    """Cualquier miembro puede sumar a sus amigos; el líder, a cualquier usuario."""
    viewer = current_user()
    grupo, _ = _member_or_403(group_id)
    invitado_id = parse_int(json_body().get('user_id'), 'usuario')
    invitado = db.session.get(User, invitado_id)
    if invitado is None:
        raise ApiError('Usuario no encontrado.', 404)
    if membership(group_id, invitado_id):
        raise ApiError(f'{invitado.name} ya es miembro del grupo.', 409)
    if grupo.owner_id != viewer.id and not are_contacts(viewer.id, invitado_id):
        raise ApiError('Sólo puedes agregar a tus amigos.', 403)
    db.session.add(GroupMember(group_id=group_id, user_id=invitado_id))
    notify(invitado_id, 'group_invite', 'Te agregaron a un grupo',
           f'{viewer.name} te agregó al grupo «{grupo.name}»', group_id)
    db.session.commit()
    return jsonify({'message': f'{invitado.name} se unió al grupo.'}), 201


@bp.delete('/<int:group_id>/members/<int:user_id>')
@login_required
def remove_member(group_id: int, user_id: int):
    grupo = _owner_or_403(group_id)
    if user_id == grupo.owner_id:
        raise ApiError('El líder no puede expulsarse; usa «Salir del grupo».', 400)
    m = membership(group_id, user_id)
    if m is None:
        raise ApiError('Esa persona no es miembro del grupo.', 404)
    db.session.delete(m)
    notify(user_id, 'group_removed', 'Saliste de un grupo', f'Ya no formas parte del grupo «{grupo.name}».')
    db.session.commit()
    return jsonify({'message': 'Miembro retirado del grupo.'}), 200


# --- Chat del grupo -----------------------------------------------------------------
@bp.get('/<int:group_id>/messages')
@login_required
def get_messages(group_id: int):
    _, m = _member_or_403(group_id)
    despues = query_int('after', 0)
    limite = query_int('limit', 60, minimum=1, maximum=200)
    consulta = GroupMessage.query.filter_by(group_id=group_id)
    if despues:
        mensajes = consulta.filter(GroupMessage.id > despues).order_by(GroupMessage.id).limit(limite).all()
    else:
        mensajes = consulta.order_by(GroupMessage.id.desc()).limit(limite).all()[::-1]
    if mensajes and mensajes[-1].id > (m.last_read_message_id or 0):
        m.last_read_message_id = mensajes[-1].id
        db.session.commit()
    return jsonify({'messages': [message_dict(x) for x in mensajes]}), 200


@bp.post('/<int:group_id>/messages')
@login_required
def send_message(group_id: int):
    viewer = current_user()
    _, m = _member_or_403(group_id)
    mensaje = GroupMessage(group_id=group_id, user_id=viewer.id, message=message_text(json_body()))
    db.session.add(mensaje)
    db.session.flush()
    m.last_read_message_id = mensaje.id
    db.session.commit()
    return jsonify({'message': 'Mensaje enviado.', 'data': message_dict(mensaje)}), 201


# --- Tareas ------------------------------------------------------------------------
@bp.get('/<int:group_id>/tasks')
@login_required
def list_tasks(group_id: int):
    _member_or_403(group_id)
    tareas = GroupTask.query.filter_by(group_id=group_id).order_by(GroupTask.id.desc()).all()
    return jsonify({'tasks': [task_dict(t) for t in tareas]}), 200


def _assignee(group_id: int, valor) -> int | None:
    if valor in (None, '', 0, '0'):
        return None
    uid = parse_int(valor, 'responsable')
    if membership(group_id, uid) is None:
        raise ApiError('La tarea sólo se puede asignar a miembros del grupo.', 400)
    return uid


@bp.post('/<int:group_id>/tasks')
@login_required
def create_task(group_id: int):
    viewer = current_user()
    grupo, _ = _member_or_403(group_id)
    data = json_body()
    tarea = GroupTask(group_id=group_id, created_by=viewer.id,
                      title=clean_text(data.get('title'), 'título', required=True, max_len=200),
                      description=clean_text(data.get('description'), 'descripción', max_len=2000),
                      assigned_to=_assignee(group_id, data.get('assigned_to')),
                      status='pending', due_date=_parse_due(data.get('due_date')))
    db.session.add(tarea)
    db.session.flush()
    if tarea.assigned_to and tarea.assigned_to != viewer.id:
        notify(tarea.assigned_to, 'group_task', 'Tienes una tarea nueva',
               f'{viewer.name} te asignó «{tarea.title}» en {grupo.name}', group_id)
    db.session.commit()
    return jsonify({'message': 'Tarea creada.', 'task': task_dict(tarea)}), 201


@bp.put('/<int:group_id>/tasks/<int:task_id>')
@login_required
def update_task(group_id: int, task_id: int):
    viewer = current_user()
    grupo, _ = _member_or_403(group_id)
    tarea = db.session.get(GroupTask, task_id)
    if tarea is None or tarea.group_id != group_id:
        raise ApiError('Tarea no encontrada.', 404)
    data = json_body()
    if 'status' in data:
        if data['status'] not in TASK_STATUSES:
            raise ApiError('Estado no válido (pending, in_progress o completed).', 400)
        tarea.status = data['status']
    if 'title' in data:
        tarea.title = clean_text(data.get('title'), 'título', required=True, max_len=200)
    if 'description' in data:
        tarea.description = clean_text(data.get('description'), 'descripción', max_len=2000)
    if 'due_date' in data:
        tarea.due_date = _parse_due(data.get('due_date'))
    if 'assigned_to' in data:
        anterior = tarea.assigned_to
        tarea.assigned_to = _assignee(group_id, data.get('assigned_to'))
        if tarea.assigned_to and tarea.assigned_to not in (anterior, viewer.id):
            notify(tarea.assigned_to, 'group_task', 'Tienes una tarea nueva',
                   f'{viewer.name} te asignó «{tarea.title}» en {grupo.name}', group_id)
    db.session.commit()
    return jsonify({'message': 'Tarea actualizada.', 'task': task_dict(tarea)}), 200


@bp.delete('/<int:group_id>/tasks/<int:task_id>')
@login_required
def delete_task(group_id: int, task_id: int):
    viewer = current_user()
    grupo, _ = _member_or_403(group_id)
    tarea = db.session.get(GroupTask, task_id)
    if tarea is None or tarea.group_id != group_id:
        raise ApiError('Tarea no encontrada.', 404)
    if viewer.id not in (tarea.created_by, grupo.owner_id):
        raise ApiError('Sólo quien creó la tarea o el líder pueden borrarla.', 403)
    db.session.delete(tarea)
    db.session.commit()
    return jsonify({'message': 'Tarea eliminada.'}), 200


# --- Archivos del grupo --------------------------------------------------------------
@bp.get('/<int:group_id>/resources')
@login_required
def list_resources(group_id: int):
    viewer = current_user()
    grupo, _ = _member_or_403(group_id)
    return jsonify({'resources': [resource_dict(r, viewer.id, grupo.owner_id)
                                  for r in _visible_resources(grupo, viewer.id)]}), 200


@bp.post('/<int:group_id>/resources')
@login_required
def upload_resource(group_id: int):
    viewer = current_user()
    grupo, _ = _member_or_403(group_id)
    titulo = clean_text(request.form.get('title'), 'título', required=True, max_len=200)
    descripcion = clean_text(request.form.get('description'), 'descripción', max_len=2000)
    stored, ruta, size = save_upload(request.files.get('file'), 'group', group_id)
    original = request.files['file'].filename
    check = pipeline.check_upload(ruta, original, 'group', viewer.id)
    recurso = GroupResource(group_id=group_id, user_id=viewer.id, title=titulo, description=descripcion,
                            filename=stored, file_size=size, scan_status=SCAN_PENDING)
    db.session.add(recurso)
    db.session.commit()
    pipeline.enqueue('group', recurso.id, stored, original, viewer.id, check, group_id=group_id,
                     title=titulo, description=descripcion or '')
    db.session.refresh(recurso)
    return jsonify({'message': 'Archivo recibido. Estará disponible cuando pase la revisión de seguridad.',
                    'id': recurso.id, 'resource': resource_dict(recurso, viewer.id, grupo.owner_id)}), 201


@bp.delete('/<int:group_id>/resources/<int:resource_id>')
@login_required
def delete_resource(group_id: int, resource_id: int):
    viewer = current_user()
    grupo, _ = _member_or_403(group_id)
    r = db.session.get(GroupResource, resource_id)
    if r is None or r.group_id != group_id:
        raise ApiError('Archivo no encontrado.', 404)
    if viewer.id not in (r.user_id, grupo.owner_id):
        raise ApiError('Sólo quien lo subió o el líder pueden borrarlo.', 403)
    filename = r.filename
    db.session.delete(r)
    db.session.commit()
    delete_upload('group', filename, group_id)
    specs.unindex('group', resource_id)
    return jsonify({'message': 'Archivo eliminado.'}), 200


@bp.get('/<int:group_id>/resources/<int:resource_id>/download')
@login_required
def download_resource(group_id: int, resource_id: int):
    viewer = current_user()
    grupo, _ = _member_or_403(group_id)
    r = db.session.get(GroupResource, resource_id)
    if r is None or r.group_id != group_id:
        raise ApiError('Archivo no encontrado.', 404)
    if r.scan_status == SCAN_BLOCKED and not viewer.is_admin:
        raise ApiError('El archivo fue bloqueado por seguridad.', 403, 'scan_blocked')
    if r.scan_status not in VISIBLE_STATUSES and viewer.id != r.user_id and not viewer.is_admin:
        raise ApiError('El archivo todavía está en revisión de seguridad.', 409, 'scan_pending')
    ruta = path_for('group', r.filename, group_id)
    if not os.path.exists(ruta):
        raise ApiError('El archivo ya no está en el servidor.', 404)
    return send_file(ruta, as_attachment=request.args.get('inline') != '1',
                     download_name=display_filename(r.filename))


def unread_counts(user_id: int) -> dict[int, int]:
    """Mensajes de grupo sin leer por grupo (para el sondeo)."""
    resultado = {}
    for m in GroupMember.query.filter_by(user_id=user_id).all():
        n = (db.session.query(func.count(GroupMessage.id))
             .filter(GroupMessage.group_id == m.group_id, GroupMessage.id > (m.last_read_message_id or 0),
                     GroupMessage.user_id != user_id).scalar())
        if n:
            resultado[m.group_id] = n
    return resultado
