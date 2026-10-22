"""Segunda barrera: el antivirus del sistema.

* Windows: Microsoft Defender (MpCmdRun.exe), que ya viene instalado.
* Linux (servidor de la universidad): ClamAV (clamdscan o clamscan).

SCAN_ANTIVIRUS=auto|defender|clamav|off  (auto = el que se encuentre).
Si no hay ninguno, el informe lo dice y el archivo sigue con las otras capas.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import time

from ..config import env_int, env_str

TIMEOUT = env_int('SCAN_ANTIVIRUS_TIMEOUT', 120)


def _defender_path() -> str | None:
    candidatos = sorted(glob.glob(r'C:\ProgramData\Microsoft\Windows Defender\Platform\*\MpCmdRun.exe'),
                        reverse=True)
    candidatos.append(r'C:\Program Files\Windows Defender\MpCmdRun.exe')
    for ruta in candidatos:
        if os.path.exists(ruta):
            return ruta
    return None


def _clamav_cmd() -> list[str] | None:
    if shutil.which('clamdscan'):
        return ['clamdscan', '--no-summary', '--fdpass']
    if shutil.which('clamscan'):
        return ['clamscan', '--no-summary']
    return None


def engine() -> tuple[str, object] | None:
    """(nombre, ejecutable/comando) del antivirus a usar, o None."""
    eleccion = env_str('SCAN_ANTIVIRUS', 'auto').lower()
    if eleccion == 'off':
        return None
    if eleccion in ('auto', 'defender') and os.name == 'nt':
        ruta = _defender_path()
        if ruta:
            return 'Microsoft Defender', ruta
    if eleccion in ('auto', 'clamav'):
        cmd = _clamav_cmd()
        if cmd:
            return 'ClamAV', cmd
    return None


def scan(path: str) -> dict:
    """Escanea un archivo. Devuelve {'engine', 'verdict': clean|infected|unavailable|error, 'detail'}."""
    motor = engine()
    if motor is None:
        return {'engine': None, 'verdict': 'unavailable', 'detail': 'No hay antivirus configurado en el servidor.'}
    nombre, ejecutable = motor
    if not os.path.exists(path):
        # Defender en tiempo real borra la amenaza en cuanto se escribe en disco.
        return {'engine': nombre, 'verdict': 'infected',
                'detail': 'El antivirus del sistema eliminó el archivo al guardarlo.'}

    if nombre == 'Microsoft Defender':
        cmd = [ejecutable, '-Scan', '-ScanType', '3', '-File', os.path.abspath(path), '-DisableRemediation']
    else:
        cmd = [*ejecutable, os.path.abspath(path)]

    inicio = time.perf_counter()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired:
        return {'engine': nombre, 'verdict': 'error', 'detail': f'El escaneo tardó más de {TIMEOUT} s.'}
    except OSError as exc:
        return {'engine': nombre, 'verdict': 'error', 'detail': f'No se pudo ejecutar el antivirus: {exc}'}
    ms = round((time.perf_counter() - inicio) * 1000)
    salida = (proc.stdout or '') + (proc.stderr or '')

    if nombre == 'Microsoft Defender':
        if proc.returncode == 0:
            return {'engine': nombre, 'verdict': 'clean', 'detail': 'Sin amenazas.', 'ms': ms}
        if proc.returncode == 2:
            amenaza = next((l.split(':', 1)[1].strip() for l in salida.splitlines()
                            if l.strip().lower().startswith('threat')), 'amenaza detectada')
            return {'engine': nombre, 'verdict': 'infected', 'detail': amenaza, 'ms': ms}
    else:
        if proc.returncode == 0:
            return {'engine': nombre, 'verdict': 'clean', 'detail': 'Sin amenazas.', 'ms': ms}
        if proc.returncode == 1:
            amenaza = salida.strip().split(':', 1)[-1].replace('FOUND', '').strip() or 'amenaza detectada'
            return {'engine': nombre, 'verdict': 'infected', 'detail': amenaza, 'ms': ms}
    if not os.path.exists(path):
        return {'engine': nombre, 'verdict': 'infected',
                'detail': 'El antivirus del sistema eliminó el archivo durante el escaneo.', 'ms': ms}
    return {'engine': nombre, 'verdict': 'error',
            'detail': f'Código {proc.returncode}: {salida.strip()[:200]}', 'ms': ms}
