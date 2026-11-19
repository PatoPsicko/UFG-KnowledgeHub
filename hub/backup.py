"""Respaldos de la plataforma (Fase 3D).

Un respaldo es un ZIP en instance/backups con:
    database.db   copia consistente de SQLite (API de respaldo, sirve con el servidor encendido)
    uploads/      todos los archivos subidos
    respaldo.json fecha, versión y conteos para comprobarlo
El .env y la clave JWT NO se copian: son secretos y se guardan aparte.

Con el servidor encendido se hace uno al arrancar si el último tiene más de
BACKUP_EVERY_HOURS (24) y luego cada día; se conservan los BACKUP_KEEP (7)
más recientes. Restaurar: `python manage.py restore <zip>` con el servidor apagado.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone

from flask import Flask, current_app

from .config import env_int

log = logging.getLogger(__name__)

KEEP = env_int('BACKUP_KEEP', 7)
EVERY_HOURS = env_int('BACKUP_EVERY_HOURS', 24)


def backup_dir() -> str:
    carpeta = os.environ.get('BACKUP_DIR') or os.path.join(current_app.instance_path, 'backups')
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


def _db_path() -> str:
    return current_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '', 1)


def list_backups() -> list[dict]:
    carpeta = backup_dir()
    lista = []
    for nombre in sorted(os.listdir(carpeta), reverse=True):
        if nombre.startswith('respaldo_') and nombre.endswith('.zip'):
            ruta = os.path.join(carpeta, nombre)
            st = os.stat(ruta)
            lista.append({'name': nombre, 'bytes': st.st_size,
                          'created_at': datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat().replace('+00:00', 'Z')})
    return lista


def create_backup() -> dict:
    """Crea un respaldo y borra los más viejos. Devuelve sus datos."""
    marca = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    destino = os.path.join(backup_dir(), f'respaldo_{marca}.zip')
    temporal = destino + '.part'
    with tempfile.TemporaryDirectory() as tmp:
        copia = os.path.join(tmp, 'database.db')
        origen = sqlite3.connect(_db_path(), timeout=30)
        try:
            destino_db = sqlite3.connect(copia)
            with destino_db:
                origen.backup(destino_db)
            destino_db.close()
        finally:
            origen.close()
        conteo = sqlite3.connect(copia)
        try:
            tablas = {t: conteo.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                      for t in ('user', 'resource', 'group_resource', 'private_resource', 'file_scan')
                      if conteo.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()}
        finally:
            conteo.close()
        archivos = 0
        uploads = current_app.config['UPLOAD_FOLDER']
        with zipfile.ZipFile(temporal, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            z.write(copia, 'database.db')
            for raiz, _dirs, nombres in os.walk(uploads):
                if os.path.basename(raiz) == 'tmp':
                    continue
                for n in nombres:
                    ruta = os.path.join(raiz, n)
                    z.write(ruta, os.path.join('uploads', os.path.relpath(ruta, uploads)))
                    archivos += 1
            z.writestr('respaldo.json', json.dumps({'created_at': marca, 'tables': tablas, 'files': archivos},
                                                   ensure_ascii=False, indent=2))
    os.replace(temporal, destino)
    for viejo in list_backups()[KEEP:]:
        try:
            os.remove(os.path.join(backup_dir(), viejo['name']))
        except OSError:
            pass
    log.info('Respaldo creado: %s (%s archivos)', destino, archivos)
    return {'name': os.path.basename(destino), 'bytes': os.path.getsize(destino), 'files': archivos, 'tables': tablas}


def restore_backup(zip_path: str, db_path: str, uploads: str) -> dict:
    """Restaura un respaldo. Guarda primero lo actual en *.antes_de_restaurar por si acaso."""
    with zipfile.ZipFile(zip_path) as z:
        nombres = z.namelist()
        if 'database.db' not in nombres:
            raise ValueError('El ZIP no es un respaldo de UFG Knowledge Hub (falta database.db).')
        if any(n.startswith('/') or '..' in n.split('/') for n in nombres):
            raise ValueError('El ZIP trae rutas no válidas.')
        if os.path.exists(db_path):
            shutil.copy2(db_path, db_path + '.antes_de_restaurar')
        if os.path.isdir(uploads):
            previo = uploads.rstrip('/\\') + '.antes_de_restaurar'
            shutil.rmtree(previo, ignore_errors=True)
            shutil.move(uploads, previo)
        os.makedirs(uploads, exist_ok=True)
        with z.open('database.db') as src, open(db_path, 'wb') as dst:
            shutil.copyfileobj(src, dst)
        archivos = 0
        for n in nombres:
            if n.startswith('uploads/') and not n.endswith('/'):
                destino = os.path.join(uploads, *n.split('/')[1:])
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                with z.open(n) as src, open(destino, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                archivos += 1
        info = json.loads(z.read('respaldo.json')) if 'respaldo.json' in nombres else {}
    return {'files': archivos, **info}


def last_backup_age_hours() -> float | None:
    lista = list_backups()
    if not lista:
        return None
    creado = datetime.fromisoformat(lista[0]['created_at'].replace('Z', '+00:00'))
    return (datetime.now(timezone.utc) - creado).total_seconds() / 3600


def start_scheduler(app: Flask) -> None:
    """Hilo que hace un respaldo cuando el último tiene más de EVERY_HOURS."""
    import threading
    import time

    if EVERY_HOURS <= 0:
        return

    def ciclo():
        time.sleep(30)  # que el servidor termine de arrancar
        while True:
            try:
                with app.app_context():
                    edad = last_backup_age_hours()
                    if edad is None or edad >= EVERY_HOURS:
                        create_backup()
            except Exception as exc:  # nunca debe tumbar el servidor
                log.error('No se pudo crear el respaldo automático: %s', exc)
            time.sleep(3600)

    threading.Thread(target=ciclo, name='respaldos', daemon=True).start()
