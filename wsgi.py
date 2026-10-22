"""Servidor para pruebas con varias personas (y para producción).

    python wsgi.py                      waitress en 0.0.0.0:5001 con 32 hilos

waitress es un servidor WSGI en Python puro que funciona igual en Windows y en
Linux. Un solo proceso con varios hilos es lo adecuado aquí: SQLite, el índice
del asistente y el vigilante de archivos viven en ese proceso.

En Linux también se puede usar gunicorn con UN worker y varios hilos:
    gunicorn --bind 0.0.0.0:5001 --workers 1 --threads 32 --timeout 300 wsgi:app
"""

from hub import create_app, start_background
from hub.config import env_int, env_str

app = create_app()
start_background(app)

if __name__ == '__main__':
    from waitress import serve

    from hub.ai import llm

    host = env_str('APP_HOST', '0.0.0.0')
    port = env_int('APP_PORT', 5001)
    hilos = env_int('APP_THREADS', 32)
    estado = llm.router().status()
    primario = estado['primary']
    print('=' * 64)
    print('  UFG Knowledge Hub — servidor multiusuario (waitress)')
    print(f'  En esta PC:        http://127.0.0.1:{port}')
    print(f'  En la red local:   http://<IP-de-esta-PC>:{port}  (ipconfig muestra la IP)')
    print('  Desde internet:    scripts\\compartir.ps1  (Cloudflare Tunnel, gratis)')
    print(f"  Asistente IA:      {primario['label'] + ' · ' + primario['model'] if primario else 'sin modelo disponible'}")
    print(f'  Hilos:             {hilos}')
    print('=' * 64)
    # channel_timeout alto: una respuesta del asistente en streaming puede durar
    # más de un minuto con Ollama local.
    serve(app, host=host, port=port, threads=hilos, channel_timeout=300, connection_limit=500,
          ident='UFG Knowledge Hub')
