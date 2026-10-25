"""Panel de seguridad para administradores (ADMIN_EMAILS en .env)."""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from .. import storage
from ..ai import index, llm
from ..errors import ApiError
from ..extensions import db
from ..models import BlockedHash, FileScan, GroupResource, PrivateResource, Resource, User
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
    return jsonify({
        'users': User.query.count(),
        'resources': Resource.query.count(),
        'group_resources': GroupResource.query.count(),
        'private_files': PrivateResource.query.filter_by(type='file').count(),
        'scans': estados,
        'blocked_hashes': BlockedHash.query.count(),
        'scan_queue': pipeline.pending_count(),
        'quarantine': len(en_cuarentena),
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
    pipeline.admin_decide(scan, (json_body().get('decision') or '').strip(), current_user().id)
    return jsonify({'message': 'Decisión aplicada.',
                    'scan': {**scan.to_dict(), 'awaiting_decision': pipeline.awaiting_decision(scan)}}), 200


@bp.post('/scans/<int:scan_id>/rescan')
@admin_required
def rescan(scan_id: int):
    nuevo = pipeline.rescan(_scan(scan_id))
    return jsonify({'message': 'Archivo enviado de nuevo al vigilante.', 'scan_id': nuevo}), 202
