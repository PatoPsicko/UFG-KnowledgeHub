"""UFG Knowledge Hub: fábrica de la aplicación Flask.

    hub/
      config.py      variables de entorno (.env)
      models.py      tablas de SQLite
      schema.py      crea tablas y columnas nuevas sin editor de BD
      errors.py      errores JSON uniformes
      api/           Blueprints por dominio (auth, biblioteca, social, grupos...)
      ai/            router de modelos (Gemini/Groq/Ollama), índice y prompt
      security/      vigilante de archivos (estático + antivirus + IA)
"""

from __future__ import annotations

import logging
import os

from flask import Flask
from flask_cors import CORS

from .config import ROOT_DIR, build_config
from .errors import register_error_handlers
from .extensions import bcrypt, db, jwt, migrate


def _security_headers(app: Flask) -> None:
    csp = ("default-src 'self'; script-src 'self'; "
           "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
           "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; "
           "connect-src 'self'; frame-src 'self' blob:; object-src 'none'; base-uri 'self'; "
           "form-action 'self'; frame-ancestors 'none'")

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resp.headers.setdefault('X-Frame-Options', 'DENY')
        resp.headers.setdefault('Referrer-Policy', 'same-origin')
        resp.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        resp.headers.setdefault('Content-Security-Policy', csp)
        return resp


def create_app(overrides: dict | None = None) -> Flask:
    app = Flask(__name__, instance_path=os.path.join(ROOT_DIR, 'instance'), static_folder=None)
    app.config.update(build_config(app.instance_path, overrides))
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    if not app.debug:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')

    db.init_app(app)
    bcrypt.init_app(app)
    jwt.init_app(app)
    migrate.init_app(app, db)
    if app.config['CORS_ORIGINS']:
        CORS(app, origins=app.config['CORS_ORIGINS'], supports_credentials=False)

    register_error_handlers(app)
    _security_headers(app)

    from .api import admin, assistant, auth, chat, frontend, groups, library, notes, profile, realtime, social
    for modulo in (auth, library, social, chat, groups, notes, profile, realtime, assistant, admin, frontend):
        app.register_blueprint(modulo.bp)

    from . import storage
    from .schema import configure_sqlite, ensure_schema
    with app.app_context():
        configure_sqlite(db.engine)
        db.engine.dispose()  # las conexiones nuevas ya traen los PRAGMA
        ensure_schema()
        storage.migrate_layout()

    from .ai import index as ai_index
    from .security import pipeline
    pipeline.init_app(app)
    ai_index.iniciar(app.config['AI_INDEX_DIR'], sincrono=not app.config['BACKGROUND_WORKERS'])
    return app


def start_background(app: Flask) -> None:
    """Sincroniza el índice y revisa archivos antiguos (se llama al arrancar el servidor)."""
    from .ai import index as ai_index, specs
    from .security import pipeline

    def obtener_specs():
        with app.app_context():
            return list(specs.all_specs())

    with app.app_context():
        ai_index.encolar_sincronizacion(obtener_specs)
        pendientes = pipeline.scan_legacy_backlog()
        if pendientes:
            app.logger.info('Vigilante: %s archivos anteriores en revisión de fondo', pendientes)
        a_medias = pipeline.requeue_pending()
        if a_medias:
            app.logger.info('Vigilante: %s archivos que quedaron a medias vuelven a la cola', a_medias)

    # Si el modelo de embeddings aparece o cambia con el servidor encendido
    # (p. ej. se abre Ollama o se añade la clave de Gemini), el índice se
    # vuelve a sincronizar solo para pasar de búsqueda léxica a híbrida.
    import threading
    import time

    def vigilar_embeddings():
        firma = ai_index.indice().firma()
        while True:
            time.sleep(120)
            try:
                nueva = ai_index.indice().firma()
                if nueva != firma:
                    app.logger.info('Embeddings: %s -> %s, resincronizando el índice', firma or 'ninguno', nueva or 'ninguno')
                    firma = nueva
                    ai_index.encolar_sincronizacion(obtener_specs)
            except Exception as exc:  # nunca debe tumbar el servidor
                app.logger.warning('Vigilancia de embeddings: %s', exc)

    threading.Thread(target=vigilar_embeddings, name='vigilar-embeddings', daemon=True).start()

    # Limpieza de archivos huérfanos y subidas a medias: al arrancar y cada 6 h.
    from . import storage

    def limpiar_archivos():
        while True:
            try:
                with app.app_context():
                    storage.cleanup()
            except Exception as exc:
                app.logger.warning('Limpieza de archivos: %s', exc)
            time.sleep(6 * 3600)

    threading.Thread(target=limpiar_archivos, name='limpiar-archivos', daemon=True).start()
