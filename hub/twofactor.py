"""Verificación en dos pasos con códigos TOTP (RFC 6238).

Es el mismo sistema de Google Authenticator, Microsoft Authenticator o
Authy: la app y el servidor comparten un secreto y cada 30 segundos calculan
el mismo código de 6 dígitos. Sólo usa la biblioteca estándar; el QR para
escanear el secreto lo dibuja `qrcode`, que ya estaba en las dependencias.

Códigos de respaldo: 8 códigos de un solo uso por si se pierde el celular.
Se guarda una huella HMAC de cada uno (con la clave del servidor), no el código.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import secrets
import struct
import time
from urllib.parse import quote

from flask import current_app

from .models import User

STEP = 30
DIGITS = 6
ISSUER = 'UFG Knowledge Hub'
# Sin 0/O ni 1/I/L para que no se confundan al copiarlos a mano.
_ALFABETO = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'


# --- TOTP ----------------------------------------------------------------------

def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode('ascii').rstrip('=')


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP)


def code_at(secret: str, step: int) -> str:
    clave = base64.b32decode(secret + '=' * (-len(secret) % 8))
    digest = hmac.new(clave, struct.pack('>Q', step), hashlib.sha1).digest()
    corte = digest[-1] & 0x0F
    numero = struct.unpack('>I', digest[corte:corte + 4])[0] & 0x7FFFFFFF
    return str(numero % 10 ** DIGITS).zfill(DIGITS)


def match(secret: str, code: str, *, last_step: int | None = None, now: float | None = None) -> int | None:
    """Intervalo que corresponde a `code` (se acepta ±1 por la hora del celular), o None.

    Un intervalo igual o anterior a `last_step` no vale: así un código que
    alguien vio por encima del hombro no se puede volver a usar.
    """
    code = ''.join(c for c in str(code or '') if c.isdigit())
    if len(code) != DIGITS or not secret:
        return None
    actual = current_step(now)
    for step in (actual - 1, actual, actual + 1):
        if hmac.compare_digest(code_at(secret, step), code) and (last_step is None or step > last_step):
            return step
    return None


def provisioning_uri(secret: str, email: str) -> str:
    return (f'otpauth://totp/{quote(ISSUER)}:{quote(email)}?secret={secret}&issuer={quote(ISSUER)}'
            f'&algorithm=SHA1&digits={DIGITS}&period={STEP}')


def qr_svg(uri: str) -> str:
    import qrcode
    import qrcode.image.svg
    imagen = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, border=2)
    salida = io.BytesIO()
    imagen.save(salida)
    return salida.getvalue().decode('utf-8')


# --- Códigos de respaldo -------------------------------------------------------

def _normalize(code: str) -> str:
    return ''.join(c for c in str(code or '').upper() if c.isalnum())


def _hash_recovery(user_id: int, code: str) -> str:
    clave = current_app.config['JWT_SECRET_KEY'].encode('utf-8')
    return hmac.new(clave, f'{user_id}:{_normalize(code)}'.encode('utf-8'), hashlib.sha256).hexdigest()


def new_recovery_codes(user: User, n: int = 8) -> list[str]:
    """Genera códigos nuevos (invalida los anteriores) y los devuelve una sola vez."""
    codigos = [''.join(secrets.choice(_ALFABETO) for _ in range(8)) for _ in range(n)]
    codigos = [f'{c[:4]}-{c[4:]}' for c in codigos]
    user.totp_recovery = json.dumps([_hash_recovery(user.id, c) for c in codigos])
    return codigos


def recovery_left(user: User) -> int:
    try:
        return len(json.loads(user.totp_recovery or '[]'))
    except ValueError:
        return 0


# --- Comprobación para una cuenta ----------------------------------------------

def check(user: User, code: str) -> str | None:
    """'totp' o 'recovery' si el código vale (y lo consume), None si no.

    No hace commit: lo hace quien llama junto con el resto de cambios.
    """
    if not user.totp_enabled or not user.totp_secret:
        return None
    paso = match(user.totp_secret, code, last_step=user.totp_last_step)
    if paso is not None:
        user.totp_last_step = paso
        return 'totp'
    limpio = _normalize(code)
    if len(limpio) != 8:
        return None
    try:
        huellas = json.loads(user.totp_recovery or '[]')
    except ValueError:
        huellas = []
    huella = _hash_recovery(user.id, limpio)
    for h in huellas:
        if hmac.compare_digest(h, huella):
            huellas.remove(h)
            user.totp_recovery = json.dumps(huellas)
            return 'recovery'
    return None


def disable(user: User) -> None:
    user.totp_enabled = False
    user.totp_secret = None
    user.totp_last_step = None
    user.totp_recovery = None
