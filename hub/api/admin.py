"""Panel de seguridad para administradores (ADMIN_EMAILS en .env).

Archivos (vigilante):
    GET  /api/admin/overview                     resumen, política y estado de las tres barreras
    GET  /api/admin/scans?status=&kind=&q=&before=   registro del vigilante con búsqueda y paginación
    GET  /api/admin/scans/stats?days=14          actividad por día y motivos más frecuentes
    GET  /api/admin/scans/export.csv             registro completo en CSV
    GET  /api/admin/scans/<id>/preview           texto extraído (sin abrir el archivo original)
    GET  /api/admin/scans/<id>/image             imagen en cuarentena (sólo imágenes)
    POST /api/admin/scans/<id>/decision          {decision: approve|reject, note}
    POST /api/admin/scans/bulk                   {ids: [...], decision, note}
    POST /api/admin/scans/<id>/rescan
    GET  /api/admin/blocked-hashes               huellas vetadas
    DELETE /api/admin/blocked-hashes/<sha256>    quitar el veto
    GET  /api/admin/uploaders                    estudiantes con archivos rechazados o en cuarentena
    POST /api/admin/users/<id>/uploads           {days: 7} suspende, {days: 0} reactiva
Bitácora:
    GET  /api/admin/audit
"""

from __future__ import annotations

import csv
import io
import os
from collections import Counter
from datetime import timedelta

from flask import Blueprint, Response, current_app, jsonify, request, send_file
from sqlalchemy import func, or_

from .. import audit, backup, storage
from ..ai import index, llm
from ..ai.extract import texto_plano
from ..errors import ApiError
from ..extensions import db
from ..models import (SCAN_BLOCKED, SCAN_CLEAN, SCAN_PENDING, SCAN_REVIEW, AuditEvent, BlockedHash, FileScan,
                      GroupResource, PrivateResource, Resource, User, UserSession, iso_utc, utcnow)
from ..security import antivirus, pipeline
from ..utils import admin_required, current_user, json_body, query_int

bp = Blueprint('admin', __name__, url_prefix='/api/admin')

KINDS = ('public', 'group', 'private', 'avatar')
MAX_BULK = 100


def _quarantine_query():
    return FileScan.query.filter(FileScan.status.in_((SCAN_REVIEW, SCAN_BLOCKED)), FileScan.reviewed_by.is_(None))


def _policy() -> dict:
    cfg = current_app.config
    return {
        'extensions': sorted(storage.ALLOWED_EXTENSIONS),
        'max_upload_mb': cfg.get('MAX_UPLOAD_MB'),
        'avatar_max_mb': cfg.get('AVATAR_MAX_MB'),
        'user_quota_mb': cfg.get('USER_QUOTA_MB'),
        'uploads_per_day': cfg.get('UPLOADS_PER_DAY'),
        'require_ai': pipeline.require_ai(),
        'strikes': pipeline.UPLOAD_STRIKES,
        'strike_days': pipeline.UPLOAD_STRIKE_DAYS,
        'block_days': pipeline.UPLOAD_BLOCK_DAYS,
    }


@bp.get('/overview')
@admin_required
def overview():
    estados = dict(db.session.query(FileScan.status, func.count(FileScan.id)).group_by(FileScan.status).all())
    en_cuarentena = [s for s in _quarantine_query().all() if pipeline.awaiting_decision(s)]
    motor = antivirus.engine()
    hace_un_dia = utcnow() - timedelta(hours=24)
    return jsonify({
        'users': User.query.count(),
        'resources': Resource.query.count(),
        'group_resources': GroupResource.query.count(),
        'private_files': PrivateResource.query.filter_by(type='file').count(),
        'scans': estados,
        'scans_24h': FileScan.query.filter(FileScan.created_at >= hace_un_dia).count(),
        'blocked_hashes': BlockedHash.query.count(),
        'scan_queue': pipeline.pending_count(),
        'quarantine': len(en_cuarentena),
        'suspended_uploaders': User.query.filter(User.uploads_blocked_until > utcnow()).count(),
        'failed_logins_24h': AuditEvent.query.filter(
            AuditEvent.action.in_(('login_failed', 'login_2fa_failed')), AuditEvent.created_at >= hace_un_dia).count(),
        'active_sessions': UserSession.query.filter(UserSession.revoked_at.is_(None),
                                                    UserSession.last_seen_at >= hace_un_dia).count(),
        'storage': storage.stats(),
        'antivirus': motor[0] if motor else None,
        'ai': llm.router().status(),
        'index': index.indice().estadisticas(),
        'policy': _policy(),
        'backups': backup.list_backups()[:5],
    }), 200


def _filtered_scans():
    consulta = FileScan.query
    estado = request.args.get('status')
    if estado == 'quarantine':
        consulta = _quarantine_query()
    elif estado == 'reviewed':
        consulta = consulta.filter(FileScan.reviewed_by.isnot(None))
    elif estado:
        consulta = consulta.filter(FileScan.status == estado)
    tipo = request.args.get('kind')
    if tipo in KINDS:
        consulta = consulta.filter(FileScan.kind == tipo)
    usuario = query_int('user', 0)
    if usuario:
        consulta = consulta.filter(FileScan.user_id == usuario)
    texto = (request.args.get('q') or '').strip()[:100]
    if texto:
        patron = f'%{texto}%'
        consulta = consulta.outerjoin(User, FileScan.user_id == User.id).filter(or_(
            FileScan.original_name.ilike(patron), FileScan.summary.ilike(patron), FileScan.sha256.ilike(patron),
            User.name.ilike(patron), User.email.ilike(patron)))
    return consulta, estado


def _scan_dict(s: FileScan) -> dict:
    datos = s.to_dict()
    if s.uploader:
        datos['user'] = {**datos['user'], 'email': s.uploader.email,
                         'uploads_blocked': pipeline.uploads_blocked(s.uploader)}
    return {**datos, 'awaiting_decision': pipeline.awaiting_decision(s)}


@bp.get('/scans')
@admin_required
def list_scans():
    consulta, estado = _filtered_scans()
    antes = query_int('before', 0)
    if antes:
        consulta = consulta.filter(FileScan.id < antes)
    limite = query_int('limit', 50, minimum=1, maximum=500)
    filas = consulta.order_by(FileScan.id.desc()).limit(limite + 1).all()
    escaneos = [_scan_dict(s) for s in filas[:limite]]
    if estado == 'quarantine':
        escaneos = [s for s in escaneos if s['awaiting_decision']]
    return jsonify({'scans': escaneos, 'next_before': filas[limite - 1].id if len(filas) > limite else None}), 200


@bp.get('/scans/stats')
@admin_required
def scan_stats():
    dias = query_int('days', 14, minimum=1, maximum=90)
    desde = (utcnow() - timedelta(days=dias - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    filas = FileScan.query.filter(FileScan.created_at >= desde).all()
    por_dia: dict[str, Counter] = {}
    motivos: Counter = Counter()
    for s in filas:
        dia = s.created_at.date().isoformat()
        grupo = 'clean' if s.status == SCAN_CLEAN else 'pending' if s.status == SCAN_PENDING else 'flagged'
        por_dia.setdefault(dia, Counter())[grupo] += 1
        if s.status in (SCAN_REVIEW, SCAN_BLOCKED):
            datos = s.to_dict()
            for f in (datos.get('static') or {}).get('findings', []):
                if f.get('severity') in ('block', 'review'):
                    motivos[f.get('code') or 'estatico'] += 1
            if (datos.get('antivirus') or {}).get('verdict') == 'infected':
                motivos['antivirus'] += 1
            if (datos.get('ai') or {}).get('verdict') in ('block', 'review'):
                motivos['ia_' + datos['ai']['verdict']] += 1
    serie = []
    for i in range(dias):
        dia = (desde + timedelta(days=i)).date().isoformat()
        c = por_dia.get(dia, Counter())
        serie.append({'date': dia, 'clean': c['clean'], 'flagged': c['flagged'], 'pending': c['pending']})
    return jsonify({'days': serie, 'reasons': [{'code': k, 'count': n} for k, n in motivos.most_common(8)]}), 200


@bp.get('/scans/export.csv')
@admin_required
def export_scans():
    consulta, _ = _filtered_scans()
    filas = consulta.order_by(FileScan.id.desc()).limit(5000).all()
    admins = dict(db.session.query(User.id, User.name).filter(User.role == 'admin').all())
    salida = io.StringIO()
    salida.write('﻿')  # Excel abre bien las tildes
    w = csv.writer(salida)
    w.writerow(['id', 'fecha_utc', 'donde', 'archivo', 'estudiante', 'correo', 'estado', 'motivo', 'tamano_bytes',
                'tipo_real', 'sha256', 'revisado_por', 'revisado_utc', 'nota_admin'])
    for s in filas:
        w.writerow([s.id, iso_utc(s.created_at), s.kind, s.original_name, s.uploader.name if s.uploader else '',
                    s.uploader.email if s.uploader else '', s.status, s.summary, s.size, s.detected_type, s.sha256,
                    admins.get(s.reviewed_by, s.reviewed_by or ''), iso_utc(s.reviewed_at), s.admin_note or ''])
    audit.record('scan_export', user=current_user(), rows=len(filas))
    db.session.commit()
    return Response(salida.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="vigilante_ufg_hub.csv"'})


def _scan(scan_id: int) -> FileScan:
    scan = db.session.get(FileScan, scan_id)
    if scan is None:
        raise ApiError('Escaneo no encontrado.', 404)
    return scan


def _existing_path(scan: FileScan) -> str:
    if not scan.stored_name:
        raise ApiError('Este archivo se rechazó al subirlo y no se guardó.', 404, 'no_file')
    ruta = pipeline._file_path(scan)
    if not os.path.exists(ruta):
        raise ApiError('El archivo ya no está en el servidor.', 404, 'no_file')
    return ruta


@bp.get('/scans/<int:scan_id>/preview')
@admin_required
def preview(scan_id: int):
    """Texto extraído del archivo: sirve para decidir sin abrir el original."""
    scan = _scan(scan_id)
    ruta = _existing_path(scan)
    ext = storage.extension(scan.original_name or scan.stored_name)
    if ext in storage.IMAGE_EXTENSIONS:
        return jsonify({'image': True, 'text': '', 'status': 'imagen'}), 200
    texto, estado = texto_plano(ruta, limite=6000)
    return jsonify({'image': False, 'text': texto, 'status': estado}), 200


@bp.get('/scans/<int:scan_id>/image')
@admin_required
def preview_image(scan_id: int):
    scan = _scan(scan_id)
    ruta = _existing_path(scan)
    ext = storage.extension(scan.original_name or scan.stored_name)
    if ext not in storage.IMAGE_EXTENSIONS:
        raise ApiError('Sólo se pueden previsualizar imágenes.', 400)
    respuesta = send_file(ruta, mimetype='image/jpeg' if ext in ('jpg', 'jpeg') else f'image/{ext}')
    respuesta.headers['Content-Security-Policy'] = "default-src 'none'"
    respuesta.headers['Cache-Control'] = 'no-store'
    return respuesta


def _decide_one(scan: FileScan, decision: str, note: str, admin: User) -> bool:
    suspendido = pipeline.admin_decide(scan, decision, admin.id, note)
    audit.record('scan_approved' if decision == 'approve' else 'scan_rejected', user=admin,
                 target=f'scan:{scan.id}', file=scan.original_name, note=note[:120] if note else None)
    if suspendido:
        audit.record('uploads_auto_suspended', user=admin, target=f'user:{scan.user_id}', file=scan.original_name)
    db.session.commit()
    return suspendido


@bp.post('/scans/<int:scan_id>/decision')
@admin_required
def decide(scan_id: int):
    scan = _scan(scan_id)
    data = json_body()
    decision = (data.get('decision') or '').strip()
    if decision == 'block':
        decision = 'reject'
    suspendido = _decide_one(scan, decision, (data.get('note') or '').strip(), current_user())
    return jsonify({'message': 'Decisión aplicada.', 'uploader_suspended': suspendido,
                    'scan': _scan_dict(scan)}), 200


@bp.post('/scans/bulk')
@admin_required
def decide_bulk():
    data = json_body()
    decision = (data.get('decision') or '').strip()
    if decision not in ('approve', 'reject'):
        raise ApiError('Decisión no válida (approve | reject).', 400)
    ids = [int(i) for i in (data.get('ids') or []) if str(i).isdigit()][:MAX_BULK]
    if not ids:
        raise ApiError('Selecciona al menos un archivo.', 400)
    nota = (data.get('note') or '').strip()
    admin = current_user()
    hechos, fallidos, suspendidos = 0, [], 0
    for scan in FileScan.query.filter(FileScan.id.in_(ids)).all():
        if not pipeline.awaiting_decision(scan):
            fallidos.append({'id': scan.id, 'message': 'Ya no está en cuarentena.'})
            continue
        try:
            suspendidos += _decide_one(scan, decision, nota, admin)
            hechos += 1
        except ApiError as exc:
            db.session.rollback()
            fallidos.append({'id': scan.id, 'message': exc.message})
    return jsonify({'message': f'{hechos} archivos procesados.', 'done': hechos, 'failed': fallidos,
                    'uploaders_suspended': suspendidos}), 200


@bp.post('/scans/<int:scan_id>/rescan')
@admin_required
def rescan(scan_id: int):
    scan = _scan(scan_id)
    nombre = scan.original_name
    nuevo = pipeline.rescan(scan)
    audit.record('scan_rescan', user=current_user(), target=f'scan:{scan_id}', file=nombre)
    db.session.commit()
    return jsonify({'message': 'Archivo enviado de nuevo al vigilante.', 'scan_id': nuevo}), 202


# --- Huellas vetadas ------------------------------------------------------------
@bp.get('/blocked-hashes')
@admin_required
def blocked_hashes():
    filas = BlockedHash.query.order_by(BlockedHash.created_at.desc()).limit(500).all()
    nombres = dict(db.session.query(User.id, User.name).filter(User.id.in_({b.created_by for b in filas
                                                                             if b.created_by})).all())
    return jsonify({'hashes': [{**b.to_dict(), 'created_by_name': nombres.get(b.created_by)} for b in filas]}), 200


@bp.delete('/blocked-hashes/<sha256>')
@admin_required
def unblock_hash(sha256: str):
    veto = db.session.get(BlockedHash, sha256.lower())
    if veto is None:
        raise ApiError('Esa huella no está vetada.', 404)
    db.session.delete(veto)
    audit.record('hash_unblocked', user=current_user(), target=f'sha256:{sha256[:16]}', file=veto.original_name)
    db.session.commit()
    return jsonify({'message': 'Huella liberada: ese archivo se podrá volver a subir (y pasará otra vez por el vigilante).'}), 200


# --- Estudiantes que suben archivos ----------------------------------------------
@bp.get('/uploaders')
@admin_required
def uploaders():
    """Quién tiene archivos rechazados, en cuarentena o las subidas suspendidas."""
    desde = utcnow() - timedelta(days=pipeline.UPLOAD_STRIKE_DAYS)
    marcados = dict(db.session.query(FileScan.user_id, func.count(FileScan.id))
                    .filter(FileScan.status.in_((SCAN_REVIEW, SCAN_BLOCKED)), FileScan.created_at >= desde)
                    .group_by(FileScan.user_id).all())
    totales = dict(db.session.query(FileScan.user_id, func.count(FileScan.id))
                   .filter(FileScan.created_at >= desde).group_by(FileScan.user_id).all())
    ids = set(marcados) | {u.id for u in User.query.filter(User.uploads_blocked_until > utcnow()).all()}
    ids.discard(None)
    lista = []
    for u in User.query.filter(User.id.in_(ids or {-1})).all():
        lista.append({**u.public_dict(), 'email': u.email, 'flagged': marcados.get(u.id, 0),
                      'uploads': totales.get(u.id, 0), 'strikes': pipeline.strikes(u.id),
                      'blocked_until': iso_utc(u.uploads_blocked_until) if pipeline.uploads_blocked(u) else None,
                      'block_reason': u.uploads_block_reason if pipeline.uploads_blocked(u) else None})
    lista.sort(key=lambda x: (x['blocked_until'] is None, -x['strikes'], -x['flagged']))
    return jsonify({'uploaders': lista, 'policy': _policy()}), 200


@bp.post('/users/<int:user_id>/uploads')
@admin_required
def set_uploads(user_id: int):
    usuario = db.session.get(User, user_id)
    if usuario is None:
        raise ApiError('Usuario no encontrado.', 404)
    if usuario.is_admin:
        raise ApiError('No se pueden suspender las subidas de un administrador.', 400)
    data = json_body()
    try:
        dias = int(data.get('days', 0))
    except (TypeError, ValueError):
        raise ApiError('Indica los días de suspensión.', 400)
    if dias < 0 or dias > 365:
        raise ApiError('La suspensión va de 1 a 365 días (0 la quita).', 400)
    admin = current_user()
    if dias == 0:
        pipeline.lift_suspension(usuario)
        audit.record('uploads_restored', user=admin, target=f'user:{usuario.id}', email=usuario.email)
        mensaje = f'{usuario.name} ya puede volver a subir archivos.'
    else:
        motivo = (data.get('reason') or '').strip() or 'decisión de un administrador'
        pipeline.suspend_uploads(usuario, dias, motivo)
        audit.record('uploads_suspended', user=admin, target=f'user:{usuario.id}', email=usuario.email,
                     days=dias, reason=motivo[:120])
        mensaje = f'Subidas de {usuario.name} suspendidas {dias} días.'
    db.session.commit()
    return jsonify({'message': mensaje, 'blocked_until': iso_utc(usuario.uploads_blocked_until)}), 200


@bp.post('/backups')
@admin_required
def run_backup():
    info = backup.create_backup()
    audit.record('backup_created', user=current_user(), file=info['name'], files=info['files'])
    db.session.commit()
    return jsonify({'message': f"Respaldo creado: {info['name']}", 'backup': info, 'backups': backup.list_backups()[:5]}), 201


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
