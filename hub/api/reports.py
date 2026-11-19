"""Reportes de documentos (Fase 3C, moderación).

Cualquier estudiante que puede ver un documento lo puede reportar. Con
REPORT_HIDE_THRESHOLD reportes de personas distintas el documento se oculta
solo y pasa a la cuarentena del panel, donde un admin lo aprueba o rechaza.

    GET  /api/reports/reasons                    motivos disponibles
    POST /api/reports                            {kind, resource_id, reason, comment}
    GET  /api/admin/reports?status=open|closed   reportes agrupados por documento
    POST /api/admin/reports/resolve              {kind, resource_id, action: dismiss|hide|remove, note}
"""

from __future__ import annotations

import os
from collections import Counter

from flask import Blueprint, jsonify, request

from .. import audit
from ..errors import ApiError
from ..extensions import db
from ..models import (REPORT_REASONS, SCAN_BLOCKED, SCAN_REVIEW, VISIBLE_STATUSES, DocumentReport, FileScan, Group,
                      GroupResource, Resource, User, display_filename, iso_utc, utcnow)
from ..security import pipeline
from ..utils import (SlidingWindowLimiter, admin_required, clean_text, current_user, json_body, login_required,
                     membership, notify, parse_int)

bp = Blueprint('reports', __name__, url_prefix='/api')

HIDE_THRESHOLD = int(os.environ.get('REPORT_HIDE_THRESHOLD') or 3)
report_limiter = SlidingWindowLimiter(20, 86400)


def _resource(kind: str, resource_id: int):
    modelo = {'public': Resource, 'group': GroupResource}.get(kind)
    if modelo is None:
        raise ApiError('Tipo de documento no válido (public | group).', 400)
    objetivo = db.session.get(modelo, resource_id)
    if objetivo is None:
        raise ApiError('Documento no encontrado.', 404)
    return objetivo


def _owner_id(kind: str, objetivo) -> int:
    return objetivo.owner_id if kind == 'public' else objetivo.user_id


@bp.get('/reports/reasons')
@login_required
def reasons():
    return jsonify({'reasons': [{'code': k, 'label': v} for k, v in REPORT_REASONS.items()]}), 200


@bp.post('/reports')
@login_required
def create_report():
    viewer = current_user()
    data = json_body()
    kind = (data.get('kind') or 'public').strip()
    objetivo = _resource(kind, parse_int(data.get('resource_id'), 'documento'))
    if kind == 'group' and membership(objetivo.group_id, viewer.id) is None:
        raise ApiError('Documento no encontrado.', 404)
    if objetivo.scan_status not in VISIBLE_STATUSES:
        raise ApiError('Este documento ya está en revisión.', 409, 'already_hidden')
    if _owner_id(kind, objetivo) == viewer.id:
        raise ApiError('No puedes reportar un documento tuyo; puedes editarlo o borrarlo.', 400)
    motivo = (data.get('reason') or '').strip()
    if motivo not in REPORT_REASONS:
        raise ApiError('Elige un motivo del reporte.', 400, 'missing_field', {'field': 'reason'})
    comentario = clean_text(data.get('comment'), 'comentario', max_len=500)
    if DocumentReport.query.filter_by(kind=kind, resource_id=objetivo.id, reporter_id=viewer.id, status='open').first():
        raise ApiError('Ya reportaste este documento. Un administrador lo revisará.', 409, 'already_reported')
    if not report_limiter.allow(viewer.id):
        raise ApiError('Has enviado muchos reportes hoy. Inténtalo mañana.', 429)

    db.session.add(DocumentReport(kind=kind, resource_id=objetivo.id, reporter_id=viewer.id, reason=motivo,
                                  comment=comentario, group_id=objetivo.group_id if kind == 'group' else None))
    db.session.flush()
    abiertos = DocumentReport.query.filter_by(kind=kind, resource_id=objetivo.id, status='open').all()
    personas = {r.reporter_id for r in abiertos}
    oculto = False
    if len(abiertos) == 1:
        for admin in User.query.filter_by(role='admin').all():
            notify(admin.id, 'document_report', 'Documento reportado',
                   f'«{objetivo.title}»: {REPORT_REASONS[motivo]}', objetivo.id)
    if HIDE_THRESHOLD > 0 and len(personas) >= HIDE_THRESHOLD:
        conteo = Counter(r.reason for r in abiertos).most_common(2)
        resumen = f'Reportado por {len(personas)} estudiantes: ' + ', '.join(REPORT_REASONS[c].lower() for c, _ in conteo)
        db.session.commit()
        pipeline.quarantine_published(kind, objetivo, resumen)
        notify(_owner_id(kind, objetivo), 'scan_result', 'Documento en revisión',
               f'«{objetivo.title}» se ocultó mientras un administrador revisa varios reportes.', objetivo.id)
        oculto = True
    db.session.commit()
    return jsonify({'message': 'Gracias. Un administrador revisará el documento.' if not oculto else
                    'Gracias. El documento se ocultó mientras un administrador lo revisa.', 'hidden': oculto}), 201


# --- Administración --------------------------------------------------------------
def _documento(kind: str, resource_id: int) -> dict:
    objetivo = db.session.get(Resource if kind == 'public' else GroupResource, resource_id)
    if objetivo is None:
        return {'exists': False, 'title': 'Documento eliminado'}
    dueno = db.session.get(User, _owner_id(kind, objetivo))
    datos = {'exists': True, 'title': objetivo.title, 'filename': display_filename(objetivo.filename),
             'scan_status': objetivo.scan_status or 'clean', 'owner': dueno.public_dict() if dueno else None,
             'owner_email': dueno.email if dueno else None}
    if kind == 'group':
        grupo = db.session.get(Group, objetivo.group_id)
        datos['group'] = grupo.name if grupo else None
    return datos


@bp.get('/admin/reports')
@admin_required
def admin_reports():
    estado = request.args.get('status', 'open')
    consulta = DocumentReport.query.filter(DocumentReport.status == 'open') if estado == 'open' else \
        DocumentReport.query.filter(DocumentReport.status != 'open')
    filas = consulta.order_by(DocumentReport.id.desc()).limit(500).all()
    grupos: dict[tuple, dict] = {}
    for r in filas:
        clave = (r.kind, r.resource_id)
        if clave not in grupos:
            grupos[clave] = {'kind': r.kind, 'resource_id': r.resource_id, 'document': _documento(*clave),
                             'reports': [], 'reasons': Counter(), 'last_at': iso_utc(r.created_at)}
        grupos[clave]['reports'].append(r.to_dict())
        grupos[clave]['reasons'][r.reason] += 1
    lista = []
    for g in grupos.values():
        g['reasons'] = [{'code': c, 'label': REPORT_REASONS.get(c, c), 'count': n} for c, n in g['reasons'].most_common()]
        g['count'] = len(g['reports'])
        lista.append(g)
    lista.sort(key=lambda g: -g['count'])
    return jsonify({'documents': lista, 'open': DocumentReport.query.filter_by(status='open').count(),
                    'hide_threshold': HIDE_THRESHOLD}), 200


@bp.post('/admin/reports/resolve')
@admin_required
def resolve_reports():
    admin = current_user()
    data = json_body()
    kind = (data.get('kind') or '').strip()
    resource_id = parse_int(data.get('resource_id'), 'documento')
    accion = (data.get('action') or '').strip()
    nota = (data.get('note') or '').strip()[:300]
    if accion not in ('dismiss', 'hide', 'remove'):
        raise ApiError('Acción no válida (dismiss | hide | remove).', 400)
    abiertos = DocumentReport.query.filter_by(kind=kind, resource_id=resource_id, status='open').all()
    if not abiertos:
        raise ApiError('No hay reportes abiertos de este documento.', 404)

    objetivo = db.session.get(Resource if kind == 'public' else GroupResource, resource_id)
    mensaje = 'Reportes cerrados.'
    if objetivo is not None:
        if accion == 'dismiss':
            # Si los reportes lo habían ocultado, vuelve a publicarse.
            scan = FileScan.query.filter(FileScan.kind == kind, FileScan.resource_id == resource_id,
                                         FileScan.status == SCAN_REVIEW, FileScan.reviewed_by.is_(None)).first()
            if scan and pipeline.awaiting_decision(scan):
                pipeline.admin_decide(scan, 'approve', admin.id, 'Reportes revisados: el documento se mantiene.')
            mensaje = 'Reportes descartados: el documento sigue publicado.'
        else:
            scan = pipeline.quarantine_published(kind, objetivo, f'Reportado: {abiertos[0].to_dict()["reason_label"]}')
            if accion == 'remove':
                pipeline.admin_decide(scan, 'reject', admin.id, nota or 'Eliminado tras revisar los reportes.')
                mensaje = 'Documento eliminado y su huella vetada.'
            else:
                mensaje = 'Documento oculto: queda en la cuarentena para decidir con calma.'
    estado = 'dismissed' if accion == 'dismiss' else 'resolved'
    for r in abiertos:
        r.status, r.resolution, r.resolved_by, r.resolved_at = estado, (nota or mensaje)[:300], admin.id, utcnow()
        if r.reporter_id:
            notify(r.reporter_id, 'report_result', 'Revisamos tu reporte',
                   'Gracias: el documento que reportaste se mantiene publicado.' if accion == 'dismiss'
                   else 'Gracias: el documento que reportaste fue retirado para revisión.', resource_id)
    audit.record('report_' + accion, user=admin, target=f'{kind}:{resource_id}', reports=len(abiertos),
                 note=nota or None)
    db.session.commit()
    return jsonify({'message': mensaje}), 200
