"""Catálogo de carreras para el perfil y los documentos.

Agrupadas por área para que los desplegables muestren primero el área y luego
sus carreras, no la lista entera de golpe. Basado en la oferta de la UFG: se
ajusta aquí sin tocar nada más (el frontend lo pide a /api/catalog/careers).
"""

from __future__ import annotations

CAREER_GROUPS = [
    ('Ingeniería y sistemas', [
        'Ingeniería en Ciencias de la Computación',
        'Ingeniería en Sistemas y Redes Informáticas',
        'Ingeniería en Telecomunicaciones',
        'Ingeniería Industrial',
        'Ingeniería Eléctrica',
        'Ingeniería Civil',
        'Técnico en Ingeniería de Software',
    ]),
    ('Arquitectura y diseño', [
        'Arquitectura',
        'Licenciatura en Diseño Gráfico',
        'Licenciatura en Animación Digital y Videojuegos',
    ]),
    ('Ciencias económicas', [
        'Licenciatura en Administración de Empresas',
        'Licenciatura en Contaduría Pública',
        'Licenciatura en Mercadeo',
        'Licenciatura en Negocios Internacionales',
        'Licenciatura en Administración Turística',
    ]),
    ('Ciencias sociales y humanidades', [
        'Licenciatura en Psicología',
        'Licenciatura en Ciencias de la Comunicación',
        'Licenciatura en Relaciones Públicas',
        'Licenciatura en Idioma Inglés',
        'Licenciatura en Ciencias de la Educación',
    ]),
    ('Ciencias jurídicas', [
        'Licenciatura en Ciencias Jurídicas',
    ]),
]

CAREERS = {c for _, carreras in CAREER_GROUPS for c in carreras}


def careers_payload() -> list[dict]:
    return [{'name': area, 'careers': carreras} for area, carreras in CAREER_GROUPS]


def valid_career(value: str | None, current: str | None = None) -> bool:
    """Vacío, una carrera del catálogo o la que ya tenía (cuentas anteriores al catálogo)."""
    return not value or value in CAREERS or value == current
