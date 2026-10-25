"""Configuración de la aplicación.

Todo sale de variables de entorno (archivo .env) para que el mismo código sirva
en esta PC, en el laboratorio o en el servidor de la universidad sin tocarlo.
Los valores por defecto están pensados para desarrollo local.
"""

from __future__ import annotations

import os
import secrets
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def env_str(name: str, default: str = '') -> str:
    return (os.environ.get(name) or '').strip() or default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name) or default)
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name) or default)
    except ValueError:
        return default


def env_bool(name: str, default: bool = False) -> bool:
    valor = (os.environ.get(name) or '').strip().lower()
    if not valor:
        return default
    return valor in ('1', 'true', 'yes', 'si', 'sí', 'on')


def env_list(name: str, default: str = '') -> list[str]:
    return [p.strip() for p in env_str(name, default).split(',') if p.strip()]


def _jwt_secret(instance_path: str) -> str:
    """Clave JWT estable entre reinicios.

    Se toma de JWT_SECRET_KEY y, si no existe, se genera una vez y se guarda en
    instance/.jwt_secret (fuera del control de versiones). Generarla en cada
    arranque cerraba todas las sesiones al reiniciar el servidor.
    """
    desde_env = env_str('JWT_SECRET_KEY')
    if desde_env:
        return desde_env
    ruta = os.path.join(instance_path, '.jwt_secret')
    if os.path.exists(ruta):
        with open(ruta, 'r', encoding='utf-8') as fh:
            guardada = fh.read().strip()
            if guardada:
                return guardada
    nueva = secrets.token_urlsafe(48)
    with open(ruta, 'w', encoding='utf-8') as fh:
        fh.write(nueva)
    return nueva


def build_config(instance_path: str, overrides: dict | None = None) -> dict:
    """Diccionario de configuración de Flask. `overrides` lo usan las pruebas."""
    overrides = overrides or {}
    os.makedirs(instance_path, exist_ok=True)

    db_path = overrides.get('DATABASE_PATH') or env_str('DATABASE_PATH') or os.path.join(instance_path, 'database.db')
    upload_folder = overrides.get('UPLOAD_FOLDER') or env_str('UPLOAD_FOLDER') or os.path.join(ROOT_DIR, 'uploads')

    config = {
        'DEBUG_MODE': env_bool('FLASK_DEBUG'),
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + db_path,
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        # pool_pre_ping evita usar conexiones muertas; timeout = espera máxima
        # cuando otro hilo está escribiendo (SQLite admite un escritor a la vez).
        'SQLALCHEMY_ENGINE_OPTIONS': {'pool_pre_ping': True, 'connect_args': {'timeout': 15}},
        'JWT_SECRET_KEY': overrides.get('JWT_SECRET_KEY') or _jwt_secret(instance_path),
        'JWT_ACCESS_TOKEN_EXPIRES': timedelta(hours=env_int('JWT_HOURS', 24)),
        'UPLOAD_FOLDER': upload_folder,
        # 25 MB por petición: suficiente para presentaciones y PDF de clase.
        # (+1 MB de margen para los campos del formulario multipart).
        'MAX_UPLOAD_MB': env_int('MAX_UPLOAD_MB', 25),
        'MAX_CONTENT_LENGTH': (env_int('MAX_UPLOAD_MB', 25) + 1) * 1024 * 1024,
        # Límites por estudiante para que 20 personas no llenen el disco de la PC.
        'AVATAR_MAX_MB': env_int('AVATAR_MAX_MB', 4),
        'USER_QUOTA_MB': env_int('USER_QUOTA_MB', 300),
        'UPLOADS_PER_DAY': env_int('UPLOADS_PER_DAY', 40),
        'MIN_FREE_DISK_MB': env_int('MIN_FREE_DISK_MB', 1024),
        'CORS_ORIGINS': env_list('CORS_ORIGINS'),
        # Correos que entran con rol de administrador (panel de seguridad).
        'ADMIN_EMAILS': [e.lower() for e in env_list('ADMIN_EMAILS')],
        # Dominios permitidos al registrarse. Por defecto sólo ufg.edu.sv (exacto);
        # "*.ufg.edu.sv" admitiría también subdominios. "*" = cualquiera.
        'ALLOWED_EMAIL_DOMAINS': [d.lower().lstrip('@') for d in env_list('ALLOWED_EMAIL_DOMAINS', 'ufg.edu.sv')],
        'PASSWORD_MIN_LENGTH': max(8, env_int('PASSWORD_MIN_LENGTH', 8)),
        # Bloqueo temporal de una cuenta (o de un correo inexistente, para no
        # revelar cuáles existen) tras varios intentos fallidos seguidos.
        'LOGIN_MAX_FAILURES': env_int('LOGIN_MAX_FAILURES', 5),
        'LOGIN_LOCK_MINUTES': env_int('LOGIN_LOCK_MINUTES', 15),
        # Verificación por correo: lista pero apagada hasta tener un SMTP real.
        'EMAIL_VERIFICATION': env_bool('EMAIL_VERIFICATION'),
        'SMTP_HOST': env_str('SMTP_HOST'),
        'SMTP_PORT': env_int('SMTP_PORT', 587),
        'SMTP_USER': env_str('SMTP_USER'),
        'SMTP_PASSWORD': env_str('SMTP_PASSWORD'),
        'SMTP_FROM': env_str('SMTP_FROM'),
        'SMTP_SECURITY': env_str('SMTP_SECURITY', 'starttls').lower(),  # starttls | ssl | none
        # Dirección pública para los enlaces de los correos (p. ej. la del túnel).
        'APP_PUBLIC_URL': env_str('APP_PUBLIC_URL').rstrip('/'),
        'AI_INDEX_DIR': env_str('AI_INDEX_DIR') or os.path.join(instance_path, 'ai_index'),
        # Vigilante: si la IA no pudo revisar un archivo tras todos los reintentos,
        # 1 = va a cuarentena (lo decide un admin), 0 = se publica con la nota.
        'SCAN_REQUIRE_AI': env_bool('SCAN_REQUIRE_AI', True),
        # Hilos de fondo (indexado y escáner). Las pruebas los desactivan para
        # ejecutar todo de forma síncrona y determinista.
        'BACKGROUND_WORKERS': True,
    }
    config.update(overrides)
    return config
