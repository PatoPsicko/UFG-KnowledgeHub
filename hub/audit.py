"""Bitácora de seguridad.

record() añade un evento a la sesión de la base de datos; lo confirma el
commit de quien llama, así el evento y el cambio que describe se guardan
juntos (o ninguno de los dos).

Acciones que se registran:

    login_ok, login_failed, login_blocked, login_2fa_failed, logout
    session_revoked, sessions_revoked_others, token_reuse, password_changed
    register, email_verified
    2fa_enabled, 2fa_disabled, 2fa_step_up, 2fa_recovery_used, 2fa_recovery_regenerated, 2fa_reset
    scan_approved, scan_rejected, scan_rescan, scan_export, hash_unblocked, role_granted, role_removed
    uploads_suspended, uploads_restored, uploads_auto_suspended
    report_dismiss, report_hide, report_remove, data_export, account_deleted, backup_created
"""

from __future__ import annotations

import json
from datetime import timedelta

from flask import current_app, has_request_context, request

from .extensions import db
from .models import AuditEvent, User, utcnow

# Grupos para los filtros del panel de Seguridad.
GROUPS = {
    'login': ('login_ok', 'logout', 'register', 'email_verified'),
    'failed': ('login_failed', 'login_blocked', 'login_2fa_failed', 'token_reuse'),
    'sessions': ('session_revoked', 'sessions_revoked_others', 'password_changed', 'token_reuse'),
    '2fa': ('2fa_enabled', '2fa_disabled', '2fa_step_up', '2fa_recovery_used', '2fa_recovery_regenerated',
            '2fa_reset', 'login_2fa_failed'),
    'admin': ('scan_approved', 'scan_rejected', 'scan_rescan', 'scan_export', 'hash_unblocked', 'role_granted',
              'role_removed', '2fa_reset', 'uploads_suspended', 'uploads_restored', 'uploads_auto_suspended',
              'report_dismiss', 'report_hide', 'report_remove', 'backup_created'),
    'privacy': ('data_export', 'account_deleted'),
    'files': ('report_dismiss', 'report_hide', 'report_remove', 'scan_approved', 'scan_rejected', 'scan_rescan', 'scan_export', 'hash_unblocked',
              'uploads_suspended', 'uploads_restored', 'uploads_auto_suspended'),
}


def record(action: str, *, user: User | None = None, user_id: int | None = None, email: str | None = None,
           target: str | None = None, **details) -> AuditEvent:
    details = {k: v for k, v in details.items() if v is not None}
    ip = device = None
    if has_request_context():
        from .sessions import device_label
        from .utils import client_ip
        ip = client_ip()[:64]
        device = device_label(request.headers.get('User-Agent', ''))
    evento = AuditEvent(
        action=action[:40],
        user_id=user.id if user else user_id,
        email=(user.email if user else email or '')[:150] or None,
        target=(target or '')[:120] or None,
        ip=ip, device=device,
        details=json.dumps(details, ensure_ascii=False)[:2000] if details else None,
    )
    db.session.add(evento)
    return evento


def purge() -> int:
    """Borra los eventos más antiguos que AUDIT_RETENTION_DAYS."""
    limite = utcnow() - timedelta(days=current_app.config['AUDIT_RETENTION_DAYS'])
    borrados = AuditEvent.query.filter(AuditEvent.created_at < limite).delete()
    db.session.commit()
    return borrados
