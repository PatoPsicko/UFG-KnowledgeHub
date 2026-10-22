"""UFG Knowledge Hub — servidor de desarrollo.

    python app.py            servidor de desarrollo (sólo esta PC)
    python wsgi.py           servidor para varias personas a la vez (waitress)

El código de la aplicación está en el paquete hub/ (ver hub/__init__.py).
"""

from hub import create_app, start_background
from hub.config import env_int, env_str

app = create_app()

if __name__ == '__main__':
    from hub.ai import llm

    host = env_str('APP_HOST', '127.0.0.1')
    port = env_int('APP_PORT', 5001)
    estado = llm.router().status()
    primario = estado['primary']
    print('=' * 60)
    print('  UFG Knowledge Hub (desarrollo)')
    print(f'  Abre la app en:   http://127.0.0.1:{port}')
    print(f"  Asistente IA:     {primario['label'] + ' · ' + primario['model'] if primario else 'sin modelo disponible'}")
    print(f"  Vigilante IA:     {(estado['security'] or {}).get('model') or 'sin modelo (sólo estático + antivirus)'}")
    print('  Para 20 personas a la vez usa:  python wsgi.py')
    print('=' * 60)
    start_background(app)
    # use_reloader=False: con el recargador los hilos de fondo arrancarían dos veces.
    app.run(debug=app.config['DEBUG_MODE'], host=host, port=port, threaded=True, use_reloader=False)
