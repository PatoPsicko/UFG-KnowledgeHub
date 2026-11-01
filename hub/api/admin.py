"""Panel de seguridad para administradores (ADMIN_EMAILS en .env)."""

from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import func, or_

from .. import audit, storage
from ..ai import index, llm
from ..errors import ApiError
from ..extensions import db
from ..models import (AuditEvent, BlockedHash, FileScan, GroupResource, PrivateResource, Resource, User,
                      UserSession, utcnow)
from ..security import antivirus, pipeline
from ..utils import admin_required, current_user, json_body, query_int

bp = Blueprint('admin', __name__, url_prefix='/api/admin')


@bp.get('/overview')
@admin_required
def overview():
    estados = dict(db.session.query(FileScan.status, func.count(FileScan.id)).group_by(FileScan.status).all())
    en_cuarentena = [s for s in FileScan.query.filter(FileScan.status.in_(('review', 'blocked')),
                                                      FileScan.reviewed_by.is_(None)).all()
                     if pipeline.awaiting_decision(s)]
    motor = antivirus.engine()
    hace_un_dia = utcnow() - timedelta(hours=24)
    return jsonify({
        'users': User.query.count(),
        'resources': Resource.query.count(),
        'group_resources': GroupResource.query.count(),
        'private_files': PrivateResource.query.filter_by(type='file').count(),
        'scans': estados,
        'blocked_hashes': BlockedHash.query.count(),
        'scan_queue': pipeline.pending_count(),
        'quarantine': len(en_cuarentena),
        'failed_logins_24h': AuditEvent.query.filter(
            AuditEvent.action.in_(('login_failed', 'login_2fa_failed')), AuditEvent.created_at >= hace_un_dia).count(),
        'active_sessions': UserSession.query.filter(UserSession.revoked_at.is_(None),
                                                    UserSession.last_seen_at >= hace_un_dia).count(),
        'storage': storage.stats(),
        'antivirus': motor[0] if motor else None,
        'ai': llm.router().status(),
        'index': index.indice().estadisticas(),
    }), 200


@bp.get('/scans')
@admin_required
def list_scans():
    consulta = FileScan.query
    estado = request.args.get('status')
    if estado == 'quarantine':
        consulta = consulta.filter(FileScan.status.in_(('review', 'blocked')), FileScan.reviewed_by.is_(None))
    elif estado:
        consulta = consulta.filter(FileScan.status == estado)
    limite = query_int('limit', 100, minimum=1, maximum=500)
    filas = consulta.order_by(FileScan.id.desc()).limit(limite).all()
    escaneos = [{**s.to_dict(), 'awaiting_decision': pipeline.awaiting_decision(s)} for s in filas]
    if estado == 'quarantine':
        escaneos = [s for s in escaneos if s['awaiting_decision']]
    return jsonify({'scans': escaneos}), 200


def _scan(scan_id: int) -> FileScan:
    scan = db.session.get(FileScan, scan_id)
    if scan is None:
        raise ApiError('Escaneo no encontrado.', 404)
    return scan


@bp.post('/scans/<int:scan_id>/decision')
@admin_required
def decide(scan_id: int):
    scan = _scan(scan_id)
    decision = (json_body().get('decision') or '').strip()
    pipeline.admin_decide(scan, decision, current_user().id)
    if decision in ('approve', 'reject'):
        audit.record('scan_approved' if decision == 'approve' else 'scan_rejected', user=current_user(),
                     target=f'scan:{scan.id}', file=scan.original_name)
        db.session.commit()
    return jsonify({'message': 'Decisión aplicada.',
                    'scan': {**scan.to_dict(), 'awaiting_decision': pipeline.awaiting_decision(scan)}}), 200


@bp.post('/scans/<int:scan_id>/rescan')
@admin_required
def rescan(scan_id: int):
    scan = _scan(scan_id)
    nombre = scan.original_name
    nuevo = pipeline.rescan(scan)
    audit.record('scan_rescan', user=current_user(), target=f'scan:{scan_id}', file=nombre)
    db.session.commit()
    return jsonify({'message': 'Archivo enviado de nuevo al vigilante.', 'scan_id': nuevo}), 202


@bp.get('/audit')
@admin_required
def audit_log():
    """Bitácora: ?group=login|failed|sessions|2fa|admin, ?q=correo o texto, ?before=<id> para paginar."""
    consulta = AuditEvent.query
    grupo = request.args.get('group')
    if grupo in audit.GROUPS:
        consulta = consulta.filter(AuditEvent.action.in_(audit.GROUPS[grupo]))
    texto = (request.args.get('q') or '').strip()[:100]
    if texto:
        patron = f'%{texto}%'
        consulta = consulta.filter(or_(AuditEvent.email.ilike(patron), AuditEvent.target.ilike(patron),
                                       AuditEvent.ip.ilike(patron), AuditEvent.details.ilike(patron)))
    antes = query_int('before', 0)
    if antes:
        consulta = consulta.filter(AuditEvent.id < antes)
    limite = query_int('limit', 50, minimum=1, maximum=200)
    filas = consulta.order_by(AuditEvent.id.desc()).limit(limite + 1).all()
    nombres = dict(db.session.query(User.id, User.name)
                   .filter(User.id.in_({e.user_id for e in filas if e.user_id})).all())
    eventos = [{**e.to_dict(), 'name': nombres.get(e.user_id)} for e in filas[:limite]]
    return jsonify({'events': eventos, 'next_before': filas[limite - 1].id if len(filas) > limite else None}), 200
