"""Amigos (contactos), conversaciones privadas y presencia en línea."""

from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import and_, case, func, or_

from ..errors import ApiError
from ..extensions import db
from ..models import Contact, DirectMessage, User, iso_utc, utcnow
from ..utils import (are_contacts, contact_between, contact_ids, current_user, json_body, login_required,
                     message_text, notify, parse_int, query_int)

bp = Blueprint('social', __name__, url_prefix='/api')

ONLINE_WINDOW = timedelta(seconds=75)


def is_online(user: User) -> bool:
    return bool(user.last_seen and utcnow() - user.last_seen <= ONLINE_WINDOW)


def user_card(user: User) -> dict:
    return {**user.public_dict(), 'online': is_online(user)}


def dm_dict(m: DirectMessage) -> dict:
    return {
        'id': m.id,
        'sender_id': m.sender_id,
        'sender_name': m.sender.name if m.sender else 'Usuario eliminado',
        'receiver_id': m.receiver_id,
        'message': m.message,
        'timestamp': iso_utc(m.timestamp),
        'read': bool(m.read),
    }


def _relation(viewer_id: int, other_id: int) -> tuple[str, int | None]:
    c = contact_between(viewer_id, other_id)
    if c is None:
        return 'none', None
    if c.status == 'accepted':
        return 'accepted', c.id
    return ('pending_sent' if c.user_id == viewer_id else 'pending_received'), c.id


# --- Amigos ----------------------------------------------------------------------
@bp.get('/contacts')
@login_required
def list_contacts():
    viewer = current_user()
    filas = Contact.query.filter(((Contact.user_id == viewer.id) | (Contact.contact_id == viewer.id))
                                 & (Contact.status == 'accepted')).all()
    contactos = []
    for c in filas:
        otro = c.contact_user if c.user_id == viewer.id else c.user
        if otro is None:
            continue
        contactos.append({'id': c.id, 'user_id': otro.id, 'name': otro.name, 'email': otro.email,
                          'status': c.status, 'user': user_card(otro), 'since': iso_utc(c.created_at)})
    contactos.sort(key=lambda x: (not x['user']['online'], x['name'].lower()))
    return jsonify({'contacts': contactos}), 200


@bp.get('/contacts/search')
@login_required
def search_users():
    viewer = current_user()
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify({'users': []}), 200
    patron = f'%{q}%'
    usuarios = (User.query.filter(User.id != viewer.id,
                                  or_(User.name.ilike(patron), User.email.ilike(patron), User.career.ilike(patron)))
                .order_by(User.name).limit(15).all())
    resultado = []
    for u in usuarios:
        relacion, request_id = _relation(viewer.id, u.id)
        resultado.append({**user_card(u), 'email': u.email if relacion == 'accepted' else None,
                          'relation': relacion, 'request_id': request_id,
                          'is_contact': relacion == 'accepted',
                          'contact_status': None if relacion == 'none' else
                          ('accepted' if relacion == 'accepted' else 'pending')})
    return jsonify({'users': resultado}), 200


@bp.get('/contacts/suggestions')
@login_required
def suggestions():
    """Compañeros de la misma carrera o de tus grupos con los que aún no eres amigo."""
    viewer = current_user()
    ya = set(contact_ids(viewer.id)) | {viewer.id}
    pendientes = Contact.query.filter((Contact.user_id == viewer.id) | (Contact.contact_id == viewer.id)).all()
    ya |= {c.user_id for c in pendientes} | {c.contact_id for c in pendientes}
    candidatos = User.query.filter(~User.id.in_(ya))
    if viewer.career:
        candidatos = candidatos.order_by((User.career == viewer.career).desc(), User.last_seen.desc())
    else:
        candidatos = candidatos.order_by(User.last_seen.desc())
    return jsonify({'users': [{**user_card(u), 'relation': 'none'} for u in candidatos.limit(6).all()]}), 200


@bp.post('/contacts/request')
@login_required
def send_request():
    viewer = current_user()
    destino_id = parse_int(json_body().get('contact_id'), 'contacto')
    if destino_id == viewer.id:
        raise ApiError('No puedes agregarte a ti mismo.', 400)
    destino = db.session.get(User, destino_id)
    if destino is None:
        raise ApiError('Usuario no encontrado.', 404)

    existente = contact_between(viewer.id, destino_id)
    if existente:
        if existente.status == 'accepted':
            raise ApiError('Ya son amigos.', 409, 'already_contacts')
        if existente.contact_id == viewer.id:
            # La otra persona ya te había enviado una solicitud: se acepta.
            existente.status = 'accepted'
            notify(destino_id, 'contact_accepted', 'Solicitud aceptada',
                   f'{viewer.name} aceptó tu solicitud de amistad', existente.id)
            db.session.commit()
            return jsonify({'message': f'Ahora tú y {destino.name} son amigos.', 'relation': 'accepted',
                            'request_id': existente.id}), 200
        raise ApiError('Ya enviaste una solicitud a esta persona.', 409, 'already_requested')

    contacto = Contact(user_id=viewer.id, contact_id=destino_id, status='pending')
    db.session.add(contacto)
    db.session.flush()
    notify(destino_id, 'contact_request', 'Nueva solicitud de amistad',
           f'{viewer.name} quiere agregarte como amigo', contacto.id)
    db.session.commit()
    return jsonify({'message': 'Solicitud enviada.', 'relation': 'pending_sent', 'request_id': contacto.id}), 201


def _requests(received: bool) -> list[dict]:
    viewer = current_user()
    campo = Contact.contact_id if received else Contact.user_id
    filas = Contact.query.filter(campo == viewer.id, Contact.status == 'pending').order_by(Contact.id.desc()).all()
    resultado = []
    for c in filas:
        otro = c.user if received else c.contact_user
        if otro is None:
            continue
        resultado.append({'id': c.id, 'user_id': otro.id, 'user_name': otro.name, 'user': user_card(otro),
                          'created_at': iso_utc(c.created_at)})
    return resultado


@bp.get('/contacts/requests')
@login_required
def received_requests():
    return jsonify({'requests': _requests(True)}), 200


@bp.get('/contacts/requests/sent')
@login_required
def sent_requests():
    return jsonify({'requests': _requests(False)}), 200


@bp.put('/contacts/requests/<int:request_id>/accept')
@login_required
def accept_request(request_id: int):
    viewer = current_user()
    c = db.session.get(Contact, request_id)
    if c is None or c.contact_id != viewer.id:
        raise ApiError('Solicitud no encontrada.', 404)
    if c.status != 'accepted':
        c.status = 'accepted'
        notify(c.user_id, 'contact_accepted', 'Solicitud aceptada',
               f'{viewer.name} aceptó tu solicitud de amistad', c.id)
        db.session.commit()
    return jsonify({'message': 'Solicitud aceptada.'}), 200


@bp.delete('/contacts/requests/<int:request_id>')
@bp.delete('/contacts/requests/<int:request_id>/reject')
@login_required
def delete_request(request_id: int):
    """Rechaza (si la recibiste) o cancela (si la enviaste) una solicitud pendiente."""
    viewer = current_user()
    c = db.session.get(Contact, request_id)
    if c is None or c.status != 'pending' or viewer.id not in (c.user_id, c.contact_id):
        raise ApiError('Solicitud no encontrada.', 404)
    db.session.delete(c)
    db.session.commit()
    return jsonify({'message': 'Solicitud eliminada.'}), 200


@bp.delete('/contacts/<int:user_id>')
@login_required
def remove_contact(user_id: int):
    viewer = current_user()
    c = contact_between(viewer.id, user_id)
    if c is None or c.status != 'accepted':
        raise ApiError('No son amigos.', 404)
    db.session.delete(c)
    db.session.commit()
    return jsonify({'message': 'Amigo eliminado.'}), 200


# --- Conversaciones privadas -------------------------------------------------------
@bp.get('/conversations')
@login_required
def conversations():
    """Amigos con su último mensaje y cuántos no has leído."""
    viewer = current_user()
    amigos = contact_ids(viewer.id)
    if not amigos:
        return jsonify({'conversations': []}), 200
    usuarios = {u.id: u for u in User.query.filter(User.id.in_(amigos)).all()}

    otro = case((DirectMessage.sender_id == viewer.id, DirectMessage.receiver_id), else_=DirectMessage.sender_id)
    ultimos = dict(db.session.query(otro, func.max(DirectMessage.id))
                   .filter(or_(DirectMessage.sender_id == viewer.id, DirectMessage.receiver_id == viewer.id))
                   .group_by(otro).all())
    mensajes = {m.id: m for m in DirectMessage.query.filter(DirectMessage.id.in_(ultimos.values() or [-1])).all()}
    no_leidos = dict(db.session.query(DirectMessage.sender_id, func.count(DirectMessage.id))
                     .filter(DirectMessage.receiver_id == viewer.id, DirectMessage.read.is_(False))
                     .group_by(DirectMessage.sender_id).all())

    resultado = []
    for uid, usuario in usuarios.items():
        ultimo = mensajes.get(ultimos.get(uid))
        resultado.append({
            'user': user_card(usuario),
            'last_message': dm_dict(ultimo) if ultimo else None,
            'unread': no_leidos.get(uid, 0),
        })
    resultado.sort(key=lambda c: (c['last_message'] or {}).get('id', 0), reverse=True)
    return jsonify({'conversations': resultado}), 200


@bp.get('/direct-messages/<int:contact_id>')
@login_required
def get_direct_messages(contact_id: int):
    viewer = current_user()
    if not are_contacts(viewer.id, contact_id):
        raise ApiError('Sólo puedes conversar con tus amigos.', 403, 'not_contacts')
    despues = query_int('after', 0)
    limite = query_int('limit', 60, minimum=1, maximum=200)
    par = or_(and_(DirectMessage.sender_id == viewer.id, DirectMessage.receiver_id == contact_id),
              and_(DirectMessage.sender_id == contact_id, DirectMessage.receiver_id == viewer.id))
    consulta = DirectMessage.query.filter(par)
    if despues:
        mensajes = consulta.filter(DirectMessage.id > despues).order_by(DirectMessage.id).limit(limite).all()
    else:
        mensajes = consulta.order_by(DirectMessage.id.desc()).limit(limite).all()[::-1]

    sin_leer = [m.id for m in mensajes if m.receiver_id == viewer.id and not m.read]
    if sin_leer:
        DirectMessage.query.filter(DirectMessage.id.in_(sin_leer)).update({'read': True}, synchronize_session=False)
        db.session.commit()
        for m in mensajes:
            if m.id in sin_leer:
                m.read = True
    otro = db.session.get(User, contact_id)
    return jsonify({'messages': [dm_dict(m) for m in mensajes], 'contact': user_card(otro) if otro else None}), 200


@bp.post('/direct-messages')
@login_required
def send_direct_message():
    viewer = current_user()
    data = json_body()
    destino = parse_int(data.get('receiver_id'), 'destinatario')
    texto = message_text(data)
    if not are_contacts(viewer.id, destino):
        raise ApiError('Sólo puedes enviar mensajes a tus amigos.', 403, 'not_contacts')
    mensaje = DirectMessage(sender_id=viewer.id, receiver_id=destino, message=texto)
    db.session.add(mensaje)
    db.session.commit()
    return jsonify({'message': 'Mensaje enviado.', 'data': dm_dict(mensaje)}), 201
