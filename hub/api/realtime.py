"""Notificaciones y «pulso»: el resumen que el navegador pide cada pocos segundos.

En lugar de que cada pantalla consulte por su cuenta mensajes, notificaciones
y grupos, el frontend pide /api/pulse (una consulta ligera) y sólo descarga
el detalle de lo que cambió. Con ~20 personas conectadas son unas 5 peticiones
por segundo de respuesta pequeña, algo que SQLite atiende sin esfuerzo.
"""

from __future__ import annotations

from flask import Blueprint, jsonify
from sqlalchemy import func

from ..errors import ApiError
from ..extensions import db
from ..models import ChatMessage, DirectMessage, Notification, utcnow
from ..utils import current_user, login_required, query_int
from .groups import unread_counts

bp = Blueprint('realtime', __name__, url_prefix='/api')



@bp.get('/notifications')
@login_required
def list_notifications():
    viewer = current_user()
    limite = query_int('limit', 20, minimum=1, maximum=100)
    filas = (Notification.query.filter_by(user_id=viewer.id)
             .order_by(Notification.id.desc()).limit(limite).all())
    no_leidas = Notification.query.filter_by(user_id=viewer.id, read=False).count()
    return jsonify({'notifications': [n.to_dict() for n in filas], 'unread': no_leidas}), 200


@bp.put('/notifications/<int:notification_id>/read')
@login_required
def mark_read(notification_id: int):
    n = db.session.get(Notification, notification_id)
    if n is None or n.user_id != current_user().id:
        raise ApiError('Notificación no encontrada.', 404)
    n.read = True
    db.session.commit()
    return jsonify({'message': 'Notificación leída.'}), 200


@bp.put('/notifications/read-all')
@login_required
def mark_all_read():
    Notification.query.filter_by(user_id=current_user().id, read=False).update({'read': True})
    db.session.commit()
    return jsonify({'message': 'Todas las notificaciones están leídas.'}), 200


@bp.get('/pulse')
@login_required
def pulse():
    viewer = current_user()
    ahora = utcnow()
    dm = dict(db.session.query(DirectMessage.sender_id, func.count(DirectMessage.id))
              .filter(DirectMessage.receiver_id == viewer.id, DirectMessage.read.is_(False))
              .group_by(DirectMessage.sender_id).all())
    ultimo_global = db.session.query(func.max(ChatMessage.id)).scalar() or 0
    global_sin_leer = ChatMessage.query.filter(ChatMessage.id > (viewer.chat_last_read_id or 0),
                                               ChatMessage.user_id != viewer.id).count()
    grupos = unread_counts(viewer.id)

    return jsonify({
        'notifications_unread': Notification.query.filter_by(user_id=viewer.id, read=False).count(),
        'dm_unread': {str(k): v for k, v in dm.items()},
        'dm_unread_total': sum(dm.values()),
        'global_last_id': ultimo_global,
        'global_unread': global_sin_leer,
        'groups_unread': {str(k): v for k, v in grupos.items()},
        'groups_unread_total': sum(grupos.values()),
        'server_time': ahora.isoformat() + 'Z',
    }), 200
