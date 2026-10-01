"""Punto de entrada para servidores WSGI de producción.

`python app.py` usa el servidor de desarrollo de Flask, que sirve para trabajar
en local pero no para atender a muchos usuarios a la vez. En un servidor:

    Windows:  waitress-serve --host 0.0.0.0 --port 5001 wsgi:app
    Linux:    gunicorn --bind 0.0.0.0:5001 --workers 2 --timeout 300 wsgi:app

El --timeout alto es necesario: sin GPU, el modelo puede tardar más de un
minuto en contestar y gunicorn cortaría la petición a los 30 s por defecto.
"""

from app import app, db, check_and_update_db

# Mismo arranque que `python app.py`: crea las tablas que falten (incluidas
# las del asistente de IA) sin tocar los datos existentes.
with app.app_context():
    db.create_all()
check_and_update_db()
