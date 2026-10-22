"""Chat global de la comunidad UFG (ahora vive dentro de Mensajes)."""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..errors import ApiError
from ..extensions import db
from ..models import ChatMessage, iso_utc
from ..utils import SlidingWindowLimiter, current_user, json_body, login_required, message_text, query_int

bp = Blueprint('chat', __name__, url_prefix='/api/chat')

# Evita que alguien inunde el chat global: 20 mensajes por minuto y usuario.
flood_limiter = SlidingWindowLimiter(20, 60)


def chat_dict(m: ChatMessage) -> dict:
    return {
        'id': m.id,
        'user_id': m.user_id,
        'user_name': m.user.name if m.user else 'Usuario eliminado',
        'user': m.user.public_dict() if m.user else None,
        'message': m.message,
        'timestamp': iso_utc(m.timestamp),
    }


@bp.get('/messages')
@login_required
def get_messages():
    """?after=<id> devuelve sólo los nuevos (para el sondeo); sin él, los últimos 60."""
    viewer = current_user()
    despues = query_int('after', 0)
    limite = query_int('limit', 60, minimum=1, maximum=200)
    if despues:
        mensajes = ChatMessage.query.filter(ChatMessage.id > despues).order_by(ChatMessage.id).limit(limite).all()
    else:
        # Los más recientes, mostrados en orden cronológico. El desempate por id
        # es necesario porque la marca de tiempo tiene precisión de segundos.
        mensajes = ChatMessage.query.order_by(ChatMessage.id.desc()).limit(limite).all()[::-1]
    if mensajes and mensajes[-1].id > (viewer.chat_last_read_id or 0):
        viewer.chat_last_read_id = mensajes[-1].id
        db.session.commit()
    return jsonify({'messages': [chat_dict(m) for m in mensajes]}), 200


@bp.post('/messages')
@login_required
def send_message():
    viewer = current_user()
    texto = message_text(json_body())
    if not flood_limiter.allow(viewer.id):
        raise ApiError('Vas muy rápido. Espera unos segundos antes de seguir escribiendo.', 429)
    mensaje = ChatMessage(user_id=viewer.id, message=texto)
    db.session.add(mensaje)
    db.session.flush()
    viewer.chat_last_read_id = mensaje.id
    db.session.commit()
    return jsonify({'message': 'Mensaje enviado.', 'data': chat_dict(mensaje)}), 201


@bp.delete('/messages/<int:message_id>')
@login_required
def delete_message(message_id: int):
    viewer = current_user()
    m = db.session.get(ChatMessage, message_id)
    if m is None:
        raise ApiError('Mensaje no encontrado.', 404)
    if m.user_id != viewer.id and not viewer.is_admin:
        raise ApiError('Sólo puedes borrar tus propios mensajes.', 403)
    db.session.delete(m)
    db.session.commit()
    return jsonify({'message': 'Mensaje eliminado.'}), 200
