"""Mantenimiento del esquema SQLite desde el propio código.

La idea es que nadie tenga que abrir un editor de bases de datos:

* create_all() crea las tablas nuevas.
* sync_columns() compara cada modelo con la tabla real y añade con ALTER TABLE
  las columnas que falten (SQLite permite añadir columnas, no quitarlas).
* configure_sqlite() activa WAL para que varias personas lean mientras otra
  escribe, que es lo que pasa con ~20 usuarios usando chat y biblioteca.
"""

from __future__ import annotations

import logging

from sqlalchemy import event, inspect, text
from sqlalchemy.engine import Engine

from .extensions import db

log = logging.getLogger(__name__)


def configure_sqlite(engine: Engine) -> None:
    """PRAGMAs por conexión: WAL, espera ante bloqueos y claves foráneas."""

    @event.listens_for(engine, 'connect')
    def _pragmas(dbapi_conn, _record):  # pragma: no cover - lo ejecuta SQLAlchemy
        cursor = dbapi_conn.cursor()
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA synchronous=NORMAL')
        cursor.execute('PRAGMA busy_timeout=15000')
        cursor.execute('PRAGMA temp_store=MEMORY')
        cursor.close()


def _sql_default(column) -> str:
    """Cláusula DEFAULT para ALTER TABLE a partir del default del modelo."""
    default = column.default
    if default is None or not getattr(default, 'is_scalar', False):
        return ''
    valor = default.arg
    if isinstance(valor, bool):
        return f' DEFAULT {1 if valor else 0}'
    if isinstance(valor, (int, float)):
        return f' DEFAULT {valor}'
    if isinstance(valor, str):
        return " DEFAULT '" + valor.replace("'", "''") + "'"
    return ''


def sync_columns() -> list[str]:
    """Añade a cada tabla las columnas del modelo que todavía no existen."""
    inspector = inspect(db.engine)
    existentes_tablas = set(inspector.get_table_names())
    agregadas = []
    for tabla in db.metadata.sorted_tables:
        if tabla.name not in existentes_tablas:
            continue
        actuales = {c['name'] for c in inspector.get_columns(tabla.name)}
        for columna in tabla.columns:
            if columna.name in actuales:
                continue
            tipo = columna.type.compile(dialect=db.engine.dialect)
            sql = f'ALTER TABLE "{tabla.name}" ADD COLUMN "{columna.name}" {tipo}{_sql_default(columna)}'
            try:
                db.session.execute(text(sql))
                db.session.commit()
                agregadas.append(f'{tabla.name}.{columna.name}')
            except Exception as exc:  # una columna que falla no frena a las demás
                db.session.rollback()
                log.error('No se pudo añadir %s.%s: %s', tabla.name, columna.name, exc)
    return agregadas


# Índices útiles para las consultas frecuentes (polling de chats y listados).
_INDICES = (
    'CREATE INDEX IF NOT EXISTS ix_dm_pair ON direct_message (sender_id, receiver_id, id)',
    'CREATE INDEX IF NOT EXISTS ix_dm_unread ON direct_message (receiver_id, read)',
    'CREATE INDEX IF NOT EXISTS ix_group_msg ON group_message (group_id, id)',
    'CREATE INDEX IF NOT EXISTS ix_notif_user ON notification (user_id, read)',
    'CREATE INDEX IF NOT EXISTS ix_resource_created ON resource (created_at)',
)


def ensure_schema() -> list[str]:
    """Crea tablas, añade columnas e índices. Idempotente: se llama al arrancar."""
    db.create_all()
    agregadas = sync_columns()
    for sql in _INDICES:
        try:
            db.session.execute(text(sql))
        except Exception as exc:
            log.warning('Índice no creado (%s): %s', sql, exc)
    db.session.commit()
    if agregadas:
        log.info('Columnas añadidas a la base de datos: %s', ', '.join(agregadas))
    return agregadas
