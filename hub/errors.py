"""Errores de la API con formato JSON uniforme.

Toda respuesta de error tiene la forma:

    {"message": "Texto para el estudiante", "code": "slug_opcional", "details": {...}}

y el código HTTP correspondiente (400, 401, 403, 404, 409, 413, 422, 429, 500, 503).
"""

from __future__ import annotations

from flask import Flask, current_app, jsonify
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from .extensions import db, jwt


class ApiError(Exception):
    """Error controlado: se lanza desde cualquier ruta y llega al cliente tal cual."""

    def __init__(self, message: str, status: int = 400, code: str | None = None,
                 details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.details = details


def _payload(message: str, code: str | None = None, details: dict | None = None) -> dict:
    data = {'message': message}
    if code:
        data['code'] = code
    if details:
        data['details'] = details
    return data


_MENSAJES_HTTP = {
    400: 'La petición no es válida.',
    401: 'Inicia sesión para continuar.',
    403: 'No tienes permiso para hacer esto.',
    404: 'No se encontró lo que buscas.',
    405: 'Método no permitido en esta ruta.',
    409: 'La operación entra en conflicto con el estado actual.',
    429: 'Demasiadas peticiones seguidas. Espera un momento.',
}


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _api_error(err: ApiError):
        return jsonify(_payload(err.message, err.code, err.details)), err.status

    @app.errorhandler(RequestEntityTooLarge)
    def _too_large(_err):
        limite = current_app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)
        return jsonify(_payload(f'El archivo supera el límite de {limite} MB.', 'file_too_large')), 413

    @app.errorhandler(HTTPException)
    def _http_error(err: HTTPException):
        status = err.code or 500
        return jsonify(_payload(_MENSAJES_HTTP.get(status, err.description or 'Error'))), status

    @app.errorhandler(Exception)
    def _unexpected(err: Exception):
        # El detalle sólo va al registro; al cliente no se le exponen rutas ni SQL.
        db.session.rollback()
        current_app.logger.exception('Error no controlado: %s', err)
        data = _payload('Error interno del servidor. Inténtalo de nuevo.', 'internal_error')
        if current_app.config.get('DEBUG_MODE'):
            data['error'] = f'{err.__class__.__name__}: {err}'
        return jsonify(data), 500

    # Errores de Flask-JWT-Extended con el mismo formato.
    @jwt.unauthorized_loader
    def _sin_token(_reason):
        return jsonify(_payload('Inicia sesión para continuar.', 'auth_required')), 401

    @jwt.invalid_token_loader
    def _token_invalido(_reason):
        return jsonify(_payload('Tu sesión no es válida. Inicia sesión de nuevo.', 'invalid_token')), 401

    @jwt.expired_token_loader
    def _token_expirado(_header, _payload_jwt):
        return jsonify(_payload('Tu sesión expiró. Inicia sesión de nuevo.', 'token_expired')), 401
