"""Genera los íconos de la app instalable (PWA) a partir de img/logo_hub.png.

    python scripts/generar_iconos.py

Crea en img/icons/: icon-192.png, icon-512.png, icon-maskable-512.png (con
margen para Android, que recorta en círculo o en gota), apple-touch-icon.png
(180 px, iPhone) y favicon-32.png. Las letras «UFG» van debajo de la pila de
libros, sobre fondo blanco, como en el logotipo.
"""

from __future__ import annotations

import os

from PIL import Image

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGEN = os.path.join(RAIZ, 'img', 'logo_hub.png')
DESTINO = os.path.join(RAIZ, 'img', 'icons')
CORTE_X = 795  # columna (en el original de 2048 px) que separa «UFG» de los libros


def _recortar(img: Image.Image) -> Image.Image:
    caja = img.getchannel('A').point(lambda a: 255 if a > 24 else 0).getbbox()
    return img.crop(caja) if caja else img


def _marca(lado: int, relleno: float) -> Image.Image:
    """Libros arriba y «UFG» abajo, centrados en un cuadrado blanco de `lado` px."""
    logo = Image.open(ORIGEN).convert('RGBA')
    letras = _recortar(logo.crop((0, 0, CORTE_X, logo.height)))
    libros = _recortar(logo.crop((CORTE_X, 0, logo.width, logo.height)))
    util = lado * (1 - 2 * relleno)
    hueco = util * 0.04
    # Ambos bloques al mismo ancho; se reduce todo si no cabe en altura.
    ancho = util * 0.86
    alto_libros = libros.height * ancho * 0.62 / libros.width
    alto_letras = letras.height * ancho / letras.width
    escala = min(1.0, util / (alto_libros + hueco + alto_letras))
    libros = libros.resize((round(ancho * 0.62 * escala), round(alto_libros * escala)), Image.LANCZOS)
    letras = letras.resize((round(ancho * escala), round(alto_letras * escala)), Image.LANCZOS)
    lienzo = Image.new('RGBA', (lado, lado), (255, 255, 255, 255))
    total = libros.height + hueco * escala + letras.height
    y = round((lado - total) / 2)
    lienzo.alpha_composite(libros, (round((lado - libros.width) / 2), y))
    lienzo.alpha_composite(letras, (round((lado - letras.width) / 2), round(y + libros.height + hueco * escala)))
    return lienzo


def main() -> None:
    os.makedirs(DESTINO, exist_ok=True)
    grande = _marca(1024, 0.08)
    mascara = _marca(1024, 0.17)  # zona segura de Android: el 80 % central
    salidas = {
        'icon-512.png': grande.resize((512, 512), Image.LANCZOS),
        'icon-192.png': grande.resize((192, 192), Image.LANCZOS),
        'icon-maskable-512.png': mascara.resize((512, 512), Image.LANCZOS),
        'apple-touch-icon.png': mascara.resize((180, 180), Image.LANCZOS),
        'favicon-32.png': grande.resize((32, 32), Image.LANCZOS),
    }
    for nombre, img in salidas.items():
        img.convert('RGB').save(os.path.join(DESTINO, nombre), optimize=True)
        print('img/icons/' + nombre)


if __name__ == '__main__':
    main()
