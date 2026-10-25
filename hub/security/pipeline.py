"""El vigilante de archivos: une las tres barreras y decide.

    subida ──► 1. análisis estático (en el momento)  ── block ──► 422, el archivo se borra
                     │ ok / review
                     ▼
               recurso guardado con scan_status = 'pending' (nadie más lo ve)
                     │  (hilo en segundo plano)
                     ▼
               2. antivirus del sistema ── infectado ──► 'blocked', se borra, huella vetada
               3. revisión con IA       ── block ─────► 'blocked' ─┐ cuarentena: el archivo se
                                        ── review ────► 'review' ──┘ guarda y un admin decide
                                        ── sin cuota ─► sigue 'pending' y se reintenta más tarde
                     ▼
               'clean' ──► se publica solo y entra al índice del asistente

El administrador NO revisa a mano lo que sale limpio: sólo ve en el panel de
Seguridad lo que quedó en cuarentena (dudoso o peligroso), con el motivo, y lo
aprueba o lo rechaza. Rechazar borra el archivo y veta su huella SHA-256.

Si la IA no responde (sin cuota o sin red) el archivo no se publica a ciegas:
se reintenta con esperas crecientes (SCAN_AI_RETRY_MINUTES). Si tras todos
los intentos sigue sin respuesta, va a cuarentena (SCAN_REQUIRE_AI=1, lo
normal) o se publica con la nota «sin revisión IA» (SCAN_REQUIRE_AI=0).

Los archivos privados (Mi espacio) sólo pasan por las barreras 1 y 2: nadie
más los ve, así que no hace falta gastar cuota de IA en ellos.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
from dataclasses import dataclass

from flask import Flask, current_app

from ..ai import specs
from ..config import env_list
from ..errors import ApiError
from ..extensions import db
from ..models import (SCAN_BLOCKED, SCAN_CLEAN, SCAN_PENDING, SCAN_REVIEW, BlockedHash, FileScan,
                      GroupResource, PrivateResource, Resource, User, display_filename, utcnow)
from ..storage import delete_upload, path_for
from ..utils import notify
from . import ai_review, antivirus, static

log = logging.getLogger(__name__)

# Minutos de espera antes de cada reintento de la revisión con IA.
RETRY_MINUTES = [float(m) for m in env_list('SCAN_AI_RETRY_MINUTES', '1,5,15,30,60')]

KIND_LABEL = {'public': 'la biblioteca', 'group': 'tu grupo', 'private': 'Mi espacio', 'avatar': 'tu perfil'}


def require_ai() -> bool:
    """¿Un archivo sin revisión de IA espera a un admin (True) o se publica (False)?"""
    return bool(current_app.config.get('SCAN_REQUIRE_AI', True))


@dataclass
class UploadCheck:
    report: static.StaticReport
    initial_status: str


def check_upload(path: str, original_name: str, kind: str, user_id: int) -> UploadCheck:
    """Barrera 1. Si el archivo se rechaza, lo borra, lo registra y lanza ApiError 422."""
    report = static.analyze(path, original_name)
    vetado = db.session.get(BlockedHash, report.sha256)
    if vetado:
        report.add('block', 'blocked_hash', f'Este archivo ya fue bloqueado antes: {vetado.reason or "contenido peligroso"}.')

    if report.verdict == 'block':
        try:
            os.remove(path)
        except OSError:
            pass
        db.session.add(FileScan(
            kind=kind, user_id=user_id, original_name=original_name[:300], sha256=report.sha256,
            size=report.size, detected_type=report.detected_type, status=SCAN_BLOCKED,
            summary='; '.join(report.reasons('block'))[:500],
            static_report=json.dumps(report.to_dict(), ensure_ascii=False), finished_at=utcnow()))
        db.session.commit()
        raise ApiError('El archivo no pasó la revisión de seguridad: ' + ' '.join(report.reasons('block')),
                       422, 'file_rejected', {'findings': [f.to_dict() for f in report.findings]})
    return UploadCheck(report=report, initial_status=SCAN_PENDING)


# --- Cola en segundo plano -------------------------------------------------------
_cola: queue.Queue = queue.Queue()
_hilo: threading.Thread | None = None
_hilo_lock = threading.Lock()
_app: Flask | None = None


def init_app(app: Flask) -> None:
    global _app
    _app = app


def enqueue(kind: str, resource_id: int, stored_name: str, original_name: str, user_id: int,
            check: UploadCheck | None, *, group_id: int | None = None, title: str = '',
            description: str = '', legacy: bool = False) -> int:
    """Registra el escaneo y lo encola. Devuelve el id de FileScan."""
    registro = FileScan(
        kind=kind, resource_id=resource_id, group_id=group_id, user_id=user_id,
        original_name=original_name[:300], stored_name=stored_name, status=SCAN_PENDING,
        sha256=check.report.sha256 if check else None, size=check.report.size if check else None,
        detected_type=check.report.detected_type if check else None,
        static_report=json.dumps(check.report.to_dict(), ensure_ascii=False) if check else None)
    db.session.add(registro)
    db.session.commit()
    trabajo = {'scan_id': registro.id, 'title': title, 'description': description, 'legacy': legacy}
    if not current_app.config.get('BACKGROUND_WORKERS', True):
        _run(trabajo)
        return registro.id
    _asegurar_hilo()
    _cola.put(trabajo)
    return registro.id


def _asegurar_hilo() -> None:
    global _hilo
    with _hilo_lock:
        if _hilo is None or not _hilo.is_alive():
            _hilo = threading.Thread(target=_trabajador, name='vigilante-archivos', daemon=True)
            _hilo.start()


def _trabajador() -> None:
    while True:
        trabajo = _cola.get()
        try:
            with _app.app_context():
                _run(trabajo)
        except Exception as exc:
            log.exception('Fallo del vigilante con %s: %s', trabajo, exc)
        finally:
            _cola.task_done()


def wait_idle() -> None:
    _cola.join()


def _schedule_retry(trabajo: dict, minutos: float) -> None:
    """Vuelve a encolar el trabajo dentro de `minutos` (temporizador en segundo plano)."""
    def reencolar():
        _asegurar_hilo()
        _cola.put(trabajo)
    temporizador = threading.Timer(minutos * 60, reencolar)
    temporizador.daemon = True
    temporizador.start()


def requeue_pending() -> int:
    """Al arrancar: vuelve a encolar los escaneos que quedaron a medias al apagar el servidor."""
    filas = FileScan.query.filter(FileScan.status == SCAN_PENDING, FileScan.resource_id.isnot(None)).all()
    for scan in filas:
        if not current_app.config.get('BACKGROUND_WORKERS', True):
            _run({'scan_id': scan.id})
        else:
            _asegurar_hilo()
            _cola.put({'scan_id': scan.id})
    return len(filas)


def pending_count() -> int:
    return _cola.qsize()


# --- Ejecución de un escaneo -------------------------------------------------
def _target(scan: FileScan):
    modelo = {'public': Resource, 'group': GroupResource, 'private': PrivateResource, 'avatar': User}[scan.kind]
    return db.session.get(modelo, scan.resource_id)


def _scope(scan: FileScan) -> int | None:
    """Subcarpeta del archivo: el grupo, o el dueño en Mi espacio."""
    return scan.group_id if scan.kind == 'group' else scan.user_id if scan.kind == 'private' else None


def _file_path(scan: FileScan) -> str:
    return path_for(scan.kind, scan.stored_name, _scope(scan))


def _run(trabajo: dict) -> None:
    scan = db.session.get(FileScan, trabajo['scan_id'])
    if scan is None:
        return
    objetivo = _target(scan)
    if objetivo is None:
        scan.status, scan.summary, scan.finished_at = SCAN_BLOCKED, 'El recurso se borró antes de revisarlo.', utcnow()
        db.session.commit()
        return
    ruta = _file_path(scan)

    # Archivos anteriores al vigilante: se hace también el análisis estático.
    if not scan.static_report and os.path.exists(ruta):
        rep = static.analyze(ruta, scan.original_name or scan.stored_name)
        scan.static_report = json.dumps(rep.to_dict(), ensure_ascii=False)
        scan.sha256, scan.size, scan.detected_type = rep.sha256, rep.size, rep.detected_type
        estatico = rep.to_dict()
    else:
        estatico = json.loads(scan.static_report) if scan.static_report else {'verdict': 'ok', 'findings': []}

    motivos_block: list[str] = [f['message'] for f in estatico.get('findings', []) if f['severity'] == 'block']
    motivos_review: list[str] = [f['message'] for f in estatico.get('findings', []) if f['severity'] == 'review']

    # Barrera 2: antivirus.
    av = antivirus.scan(ruta) if not motivos_block else {'verdict': 'skipped'}
    scan.antivirus_report = json.dumps(av, ensure_ascii=False)
    if av.get('verdict') == 'infected':
        motivos_block.append(f"Antivirus ({av.get('engine')}): {av.get('detail')}")

    # Barrera 3: revisión con IA. No se aplica a archivos privados ni a la
    # revisión inicial de los archivos antiguos (gastaría la cuota gratuita en
    # material que ya estaba publicado).
    ia = None
    sin_ia = False
    if not motivos_block and scan.kind != 'private' and not trabajo.get('legacy') and os.path.exists(ruta):
        titulo, descripcion = trabajo.get('title'), trabajo.get('description')
        if titulo is None:  # reintento tras reiniciar: se recuperan del recurso
            titulo = getattr(objetivo, 'title', '') or ''
            descripcion = getattr(objetivo, 'description', '') or ''
        ia = ai_review.review(ruta, scan.original_name or '', titulo, descripcion or '')
        scan.ai_report = json.dumps(ia, ensure_ascii=False)
        if ia['verdict'] == 'block':
            motivos_block.append(f"Revisión IA: {ia.get('reason') or 'contenido no permitido'}")
        elif ia['verdict'] == 'review':
            motivos_review.append(f"Revisión IA: {ia.get('reason') or 'requiere revisión'}")
        elif ia['verdict'] == 'unavailable':
            intentos = (scan.ai_attempts or 0) + 1
            scan.ai_attempts = intentos
            if current_app.config.get('BACKGROUND_WORKERS', True) and intentos <= len(RETRY_MINUTES):
                # Sin cuota o sin red: el archivo sigue «en revisión» y se reintenta.
                espera = RETRY_MINUTES[intentos - 1]
                scan.summary = (f'Esperando a la revisión con IA (intento {intentos} de '
                                f'{len(RETRY_MINUTES) + 1}): {ia.get("reason") or ""}')[:500]
                db.session.commit()
                _schedule_retry({**trabajo, 'scan_id': scan.id}, espera)
                log.warning('Vigilante: IA no disponible para el escaneo %s, reintento en %s min', scan.id, espera)
                return
            if require_ai():
                motivos_review.append('La revisión con IA no estuvo disponible después de varios intentos.')
            else:
                sin_ia = True

    if motivos_block:
        estado, resumen = SCAN_BLOCKED, '; '.join(motivos_block)
    elif motivos_review:
        estado, resumen = SCAN_REVIEW, '; '.join(motivos_review)
    else:
        estado = SCAN_CLEAN
        partes = ['Sin amenazas']
        if av.get('engine'):
            partes.append(f"antivirus: {av['engine']}")
        if ia and ia.get('model'):
            partes.append(f"IA: {ia['model']}")
        if sin_ia:
            partes.append('sin revisión IA (no estuvo disponible)')
        if ia and ia.get('verdict') == 'skipped':
            partes.append('imagen sin revisión IA (no hay modelo con visión)')
        resumen = ' · '.join(partes)

    _apply(scan, objetivo, estado, resumen[:500], legacy=trabajo.get('legacy', False),
           malware=av.get('verdict') == 'infected')


def _apply(scan: FileScan, objetivo, estado: str, resumen: str, *, legacy: bool = False,
           malware: bool = False, by_admin: int | None = None) -> None:
    """Aplica el veredicto al recurso, al índice y avisa al estudiante."""
    scan.status, scan.summary, scan.finished_at = estado, resumen, utcnow()
    if by_admin:
        scan.reviewed_by = by_admin
    nombre = scan.original_name or display_filename(scan.stored_name)

    if scan.kind == 'avatar':
        if estado != SCAN_CLEAN and objetivo.profile_picture == scan.stored_name:
            objetivo.profile_picture = None
            delete_upload('avatar', scan.stored_name)
    else:
        objetivo.scan_status = estado

    if estado == SCAN_BLOCKED and (malware or by_admin):
        # Malware confirmado o bloqueo manual: se borra el archivo y se veta su huella.
        if scan.kind != 'avatar':
            delete_upload(scan.kind, scan.stored_name, _scope(scan))
        if scan.sha256 and not db.session.get(BlockedHash, scan.sha256):
            db.session.add(BlockedHash(sha256=scan.sha256, reason=resumen[:300]))

    if scan.user_id and not (legacy and estado == SCAN_CLEAN):
        if estado == SCAN_CLEAN and scan.kind in ('public', 'group'):
            notify(scan.user_id, 'scan_result', 'Archivo publicado',
                   f'«{nombre}» pasó la revisión de seguridad y ya está en {KIND_LABEL[scan.kind]}.', scan.resource_id)
        elif estado == SCAN_REVIEW or (estado == SCAN_BLOCKED and not malware and not by_admin):
            notify(scan.user_id, 'scan_result', 'Archivo en cuarentena',
                   f'«{nombre}» todavía no se publicó: un administrador lo revisará. Motivo: {resumen}',
                   scan.resource_id)
        elif estado == SCAN_BLOCKED:
            notify(scan.user_id, 'scan_result', 'Archivo rechazado',
                   f'«{nombre}» no se publicó por seguridad: {resumen}', scan.resource_id)
    if estado != SCAN_CLEAN and not by_admin:
        titulo = ('Archivo dudoso en cuarentena' if estado == SCAN_REVIEW else
                  'Malware bloqueado' if malware else 'Archivo peligroso en cuarentena')
        for admin in User.query.filter_by(role='admin').all():
            notify(admin.id, 'security_alert', titulo, f'«{nombre}»: {resumen}', scan.id)
    db.session.commit()

    if scan.kind == 'avatar':
        return
    if estado == SCAN_CLEAN:
        # Un archivo antiguo que resulta limpio ya estaba en el índice.
        if not legacy:
            _reindex(scan.kind, objetivo)
    else:
        specs.unindex({'public': 'public', 'group': 'group',
                       'private': 'private_file'}[scan.kind], scan.resource_id)


def _reindex(kind: str, objetivo) -> None:
    if kind == 'public':
        specs.reindex(specs.spec_resource(objetivo))
    elif kind == 'group':
        specs.reindex(specs.spec_group_resource(objetivo))
    elif kind == 'private':
        specs.reindex(specs.spec_private(objetivo))


# --- Acciones del administrador --------------------------------------------------
def admin_decide(scan: FileScan, decision: str, admin_id: int) -> None:
    objetivo = _target(scan)
    if objetivo is None:
        raise ApiError('El recurso de este escaneo ya no existe.', 404)
    if decision == 'approve':
        if not os.path.exists(_file_path(scan)):
            raise ApiError('El archivo ya no está en el servidor; no se puede aprobar.', 409)
        _apply(scan, objetivo, SCAN_CLEAN, 'Aprobado por un administrador.', by_admin=admin_id)
    elif decision in ('block', 'reject'):
        _apply(scan, objetivo, SCAN_BLOCKED, 'Rechazado por un administrador.', by_admin=admin_id)
    else:
        raise ApiError('Decisión no válida (approve | reject).', 400)


def awaiting_decision(scan: FileScan) -> bool:
    """En cuarentena: dudoso o peligroso, con el archivo guardado y sin decisión de un admin."""
    return (scan.status in (SCAN_REVIEW, SCAN_BLOCKED) and not scan.reviewed_by and bool(scan.resource_id)
            and bool(scan.stored_name) and os.path.exists(_file_path(scan)))


def rescan(scan: FileScan) -> int:
    objetivo = _target(scan)
    if objetivo is None or not os.path.exists(_file_path(scan)):
        raise ApiError('El archivo ya no está disponible para volver a revisarlo.', 409)
    if scan.kind != 'avatar':
        objetivo.scan_status = SCAN_PENDING
    db.session.commit()
    return enqueue(scan.kind, scan.resource_id, scan.stored_name, scan.original_name or '', scan.user_id,
                   None, group_id=scan.group_id, title=getattr(objetivo, 'title', ''))


def scan_legacy_backlog(limit: int = 500) -> int:
    """Encola la revisión de archivos subidos antes de que existiera el vigilante."""
    total = 0
    for r in Resource.query.filter(Resource.scan_status.is_(None)).limit(limit).all():
        enqueue('public', r.id, r.filename, display_filename(r.filename), r.owner_id, None,
                title=r.title, description=r.description or '', legacy=True)
        total += 1
    for g in GroupResource.query.filter(GroupResource.scan_status.is_(None)).limit(limit).all():
        enqueue('group', g.id, g.filename, display_filename(g.filename), g.user_id, None,
                group_id=g.group_id, title=g.title, legacy=True)
        total += 1
    for p in PrivateResource.query.filter(PrivateResource.type == 'file',
                                          PrivateResource.scan_status.is_(None)).limit(limit).all():
        enqueue('private', p.id, p.filename, display_filename(p.filename), p.owner_id, None,
                title=p.title, legacy=True)
        total += 1
    return total
