"""Inicializa la base de datos de UFG Knowledge Hub.

Uso:
    python init_database.py            Crea las tablas que falten (no borra nada)
    python init_database.py --reset    Borra la base y la vuelve a crear vacía
    python init_database.py --demo     Crea las tablas y añade un usuario de prueba

Cambios respecto a la versión anterior:

- Ya NO borra la base de datos cada vez que se ejecuta. Antes, un simple
  "python init_database.py" eliminaba instance/database.db sin preguntar, con
  todos los usuarios y recursos dentro. Ahora hay que pedirlo con --reset y
  además confirmarlo por teclado.
- Ya NO crea un usuario fijo con la contraseña "123456" en cada arranque. Esa
  cuenta quedaba activa en cualquier despliegue y su contraseña estaba escrita
  en el código. Ahora sólo se crea con --demo y la contraseña se genera al
  azar y se muestra una única vez.
"""

import argparse
import os
import secrets
import sys

from app import app, db, User, bcrypt, check_and_update_db


def crear_tablas():
    """Crea las tablas que falten sin tocar los datos existentes."""
    with app.app_context():
        db.create_all()
        check_and_update_db()
        total = User.query.count()
    print('Tablas verificadas. Usuarios registrados actualmente: ' + str(total))


def reiniciar_base():
    """Borra la base de datos y la vuelve a crear vacía. Pide confirmación."""
    db_path = os.path.join(app.instance_path, 'database.db')

    if os.path.exists(db_path):
        with app.app_context():
            total = User.query.count()

        print('ATENCIÓN: se va a borrar ' + db_path)
        print('Se perderán ' + str(total) + ' usuario(s) y todos sus recursos.')
        respuesta = input('Escribe BORRAR para confirmar: ').strip()
        if respuesta != 'BORRAR':
            print('Cancelado. No se ha modificado nada.')
            return False

        with app.app_context():
            db.session.close()
            db.engine.dispose()
        try:
            os.remove(db_path)
            print('Base de datos anterior eliminada.')
        except PermissionError:
            print('No se pudo borrar: el archivo está en uso.')
            print('Cierra el servidor (python app.py) y vuelve a intentarlo.')
            return False

    os.makedirs(app.instance_path, exist_ok=True)
    with app.app_context():
        db.create_all()
    print('Base de datos creada vacía.')
    return True


def crear_usuario_demo():
    """Crea una cuenta de prueba con contraseña aleatoria."""
    correo = 'demo@ufg.edu.sv'
    with app.app_context():
        if User.query.filter_by(email=correo).first():
            print('El usuario de prueba ya existe: ' + correo)
            return

        # Contraseña aleatoria: no queda escrita en el código ni se repite entre
        # instalaciones. Se muestra una sola vez.
        password = secrets.token_urlsafe(12)
        usuario = User(
            name='Usuario Demo',
            email=correo,
            password=bcrypt.generate_password_hash(password).decode('utf-8'),
            career='Ingeniería en Sistemas',
            semester=5
        )
        db.session.add(usuario)
        db.session.commit()

    print('')
    print('Usuario de prueba creado. Apunta la contraseña, no se volverá a mostrar:')
    print('   Email:      ' + correo)
    print('   Contraseña: ' + password)
    print('')


def main():
    parser = argparse.ArgumentParser(
        description='Inicializa la base de datos de UFG Knowledge Hub.')
    parser.add_argument('--reset', action='store_true',
                        help='Borra la base de datos y la recrea vacía (pide confirmación).')
    parser.add_argument('--demo', action='store_true',
                        help='Crea un usuario de prueba con contraseña aleatoria.')
    args = parser.parse_args()

    print('UFG Knowledge Hub - inicialización de base de datos')
    print('-' * 52)

    if args.reset:
        if not reiniciar_base():
            sys.exit(1)
    else:
        crear_tablas()

    if args.demo:
        crear_usuario_demo()

    print('Listo. Arranca el servidor con: python app.py')


if __name__ == '__main__':
    main()
