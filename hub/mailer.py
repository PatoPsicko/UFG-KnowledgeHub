"""Envío de correos (verificación de cuenta) por SMTP.

Está listo pero apagado: con EMAIL_VERIFICATION=0 (lo normal mientras no haya
un servidor de correo de la universidad) nadie llama a send(). Para activarlo
basta con rellenar en .env:

    EMAIL_VERIFICATION=1
    SMTP_HOST=smtp.ufg.edu.sv        SMTP_PORT=587   SMTP_SECURITY=starttls
    SMTP_USER=...                    SMTP_PASSWORD=...
    SMTP_FROM="UFG Knowledge Hub <no-responder@ufg.edu.sv>"
    APP_PUBLIC_URL=https://...       (dirección con la que entran los estudiantes)

Sólo usa la biblioteca estándar (smtplib).
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app

log = logging.getLogger(__name__)

# Las pruebas sustituyen esta lista para capturar los correos sin enviarlos.
outbox: list[EmailMessage] | None = None


def configured() -> bool:
    cfg = current_app.config
    return bool(cfg.get('SMTP_HOST') and cfg.get('SMTP_FROM'))


def send(to: str, subject: str, text: str) -> bool:
    """Envía un correo de texto. Devuelve False si no se pudo (nunca lanza)."""
    cfg = current_app.config
    msg = EmailMessage()
    msg['From'] = cfg.get('SMTP_FROM') or 'UFG Knowledge Hub <no-responder@localhost>'
    msg['To'] = to
    msg['Subject'] = subject
    msg.set_content(text)

    if outbox is not None:
        outbox.append(msg)
        return True
    if not configured():
        log.warning('Correo no enviado a %s: falta SMTP_HOST/SMTP_FROM en .env', to)
        return False
    try:
        seguridad = cfg.get('SMTP_SECURITY', 'starttls')
        contexto = ssl.create_default_context()
        if seguridad == 'ssl':
            servidor = smtplib.SMTP_SSL(cfg['SMTP_HOST'], cfg['SMTP_PORT'], timeout=20, context=contexto)
        else:
            servidor = smtplib.SMTP(cfg['SMTP_HOST'], cfg['SMTP_PORT'], timeout=20)
        with servidor:
            if seguridad == 'starttls':
                servidor.starttls(context=contexto)
            if cfg.get('SMTP_USER'):
                servidor.login(cfg['SMTP_USER'], cfg.get('SMTP_PASSWORD') or '')
            servidor.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException) as exc:
        log.error('No se pudo enviar el correo a %s: %s', to, exc)
        return False
