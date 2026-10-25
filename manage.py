"""Herramientas de consola de UFG Knowledge Hub (sin editores de base de datos).

    python manage.py db                    crea tablas y columnas que falten (no borra nada)
    python manage.py db --reset            borra la base y la recrea vacía (pide confirmación)
    python manage.py demo                  crea un usuario de prueba con contraseña aleatoria
    python manage.py admin correo@ufg.edu.sv   da rol de administrador a una cuenta
    python manage.py users                 lista las cuentas
    python manage.py ai                    estado de los proveedores de IA
    python manage.py ai --test "pregunta"  prueba el router con una pregunta
    python manage.py index --stats | --sync | --rebuild
    python manage.py index --query "pregunta" --user 1
    python manage.py scan ruta/al/archivo.pdf   pasa un archivo por el vigilante
    python manage.py storage               archivos y espacio por carpeta
    python manage.py storage --limpiar     borra subidas a medias y archivos huérfanos (--simular para ver antes)
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time


def _app(workers: bool = False):
    from hub import create_app
    return create_app({'BACKGROUND_WORKERS': workers})


def cmd_db(args) -> None:
    from hub.extensions import db
    from hub.models import User
    app = _app()
    if args.reset:
        ruta = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        with app.app_context():
            total = User.query.count()
        print(f'ATENCIÓN: se borrará {ruta} con {total} usuario(s) y todo su contenido.')
        if input('Escribe BORRAR para confirmar: ').strip() != 'BORRAR':
            print('Cancelado. No se modificó nada.')
            return
        with app.app_context():
            db.drop_all()
            db.create_all()
        print('Base de datos vacía y lista.')
        return
    from hub.schema import ensure_schema
    with app.app_context():
        nuevas = ensure_schema()
        print('Tablas verificadas.' + (f' Columnas añadidas: {", ".join(nuevas)}' if nuevas else ''))
        print(f'Usuarios registrados: {User.query.count()}')


def cmd_demo(_args) -> None:
    from hub.extensions import bcrypt, db
    from hub.models import User
    app = _app()
    with app.app_context():
        email = 'demo@ufg.edu.sv'
        if User.query.filter_by(email=email).first():
            print(f'Ya existe {email}. Si olvidaste la contraseña, bórralo con db --reset o crea otro.')
            return
        clave = secrets.token_urlsafe(9)
        db.session.add(User(name='Usuario Demo', email=email, career='Ingeniería en Sistemas',
                            password=bcrypt.generate_password_hash(clave).decode()))
        db.session.commit()
        print(f'Usuario de prueba creado:\n  correo: {email}\n  contraseña: {clave}\n(Se muestra sólo esta vez.)')


def cmd_admin(args) -> None:
    from hub.extensions import db
    from hub.models import User
    app = _app()
    with app.app_context():
        u = User.query.filter(db.func.lower(User.email) == args.email.lower()).first()
        if not u:
            sys.exit(f'No existe ninguna cuenta con el correo {args.email}.')
        u.role = 'student' if args.remove else 'admin'
        db.session.commit()
        print(f'{u.name} ({u.email}) ahora tiene rol: {u.role}')


def cmd_users(_args) -> None:
    from hub.models import User
    app = _app()
    with app.app_context():
        for u in User.query.order_by(User.id).all():
            print(f'{u.id:>4}  {u.role or "student":<8}  {u.email:<40} {u.name}')


def cmd_ai(args) -> None:
    from hub.ai import llm
    _app()
    router = llm.router()
    print(json.dumps(router.status(), ensure_ascii=False, indent=2))
    if args.test:
        t = time.perf_counter()
        r = router.chat([{'role': 'user', 'content': args.test}])
        print(f'\n[{r.provider}/{r.model} · {time.perf_counter() - t:.1f} s]\n{r.text}')
    if args.embed:
        t = time.perf_counter()
        v = router.embed([args.embed])
        print(f'\nEmbedding con {router.embed_signature()}: {len(v[0])} dimensiones ({time.perf_counter() - t:.1f} s)')


def cmd_index(args) -> None:
    from hub.ai import index, specs
    from hub.utils import user_group_ids
    app = _app()
    with app.app_context():
        idx = index.indice()
        if args.rebuild:
            idx.vaciar()
            print('Índice vaciado.')
        if args.rebuild or args.sync:
            t = time.perf_counter()
            print(f'Sincronizado en {time.perf_counter() - t:.1f} s: {idx.sincronizar(list(specs.all_specs()))}')
        if args.query:
            if args.user is None:
                sys.exit('--query necesita --user <id> para aplicar los permisos')
            fragmentos, info = idx.buscar(args.query, args.user, user_group_ids(args.user))
            print(f"Modo: {info['modo']}  candidatos: {info.get('candidatos')}  similitud máx.: "
                  f"{info.get('similitud_maxima')}  tiempos: {info['tiempos_ms']}")
            for i, f in enumerate(fragmentos, 1):
                print(f"\n[{i}] {f['title']} ({f['origin']}) score={f['score']}\n    {index.snippet(f['text'])}")
        if args.stats or not (args.sync or args.rebuild or args.query):
            print(json.dumps(idx.estadisticas(), ensure_ascii=False, indent=2))


def cmd_scan(args) -> None:
    from hub.security import ai_review, antivirus, static
    _app()
    ruta = os.path.abspath(args.path)
    if not os.path.isfile(ruta):
        sys.exit(f'No existe {ruta}')
    nombre = os.path.basename(ruta)
    print('1) Análisis estático')
    print(json.dumps(static.analyze(ruta, nombre).to_dict(), ensure_ascii=False, indent=2))
    print('\n2) Antivirus')
    print(json.dumps(antivirus.scan(ruta), ensure_ascii=False, indent=2))
    if not args.no_ai:
        print('\n3) Revisión con IA')
        print(json.dumps(ai_review.review(ruta, nombre), ensure_ascii=False, indent=2))


def cmd_storage(args) -> None:
    from hub import storage
    app = _app()
    with app.app_context():
        if args.limpiar:
            informe = storage.cleanup(dry_run=args.simular, min_age_hours=args.horas)
            accion = 'Se borrarían' if args.simular else 'Borrados'
            print(f"{accion} {len(informe['removed'])} archivos ({informe['bytes'] / 1024 / 1024:.1f} MB)")
            for ruta in informe['removed'][:50]:
                print('  ' + ruta)
            return
        st = storage.stats()
        print(f"Carpeta: {st['path']}")
        for nombre, f in st['folders'].items():
            print(f"  {nombre:<10} {f['files']:>6} archivos  {f['bytes'] / 1024 / 1024:>8.1f} MB")
        if st['free_bytes'] is not None:
            print(f"Libre en el disco: {st['free_bytes'] / 1024 ** 3:.1f} GB")


def main() -> None:
    parser = argparse.ArgumentParser(description='Herramientas de UFG Knowledge Hub')
    sub = parser.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('db', help='Crea o reinicia la base de datos')
    p.add_argument('--reset', action='store_true')
    p.set_defaults(func=cmd_db)
    sub.add_parser('demo', help='Crea un usuario de prueba').set_defaults(func=cmd_demo)
    p = sub.add_parser('admin', help='Da rol de administrador')
    p.add_argument('email')
    p.add_argument('--remove', action='store_true', help='Quita el rol de administrador')
    p.set_defaults(func=cmd_admin)
    sub.add_parser('users', help='Lista las cuentas').set_defaults(func=cmd_users)
    p = sub.add_parser('ai', help='Estado y prueba de los modelos de IA')
    p.add_argument('--test', help='Pregunta de prueba')
    p.add_argument('--embed', help='Texto para probar los embeddings')
    p.set_defaults(func=cmd_ai)
    p = sub.add_parser('index', help='Índice de búsqueda del asistente')
    p.add_argument('--stats', action='store_true')
    p.add_argument('--sync', action='store_true')
    p.add_argument('--rebuild', action='store_true')
    p.add_argument('--query')
    p.add_argument('--user', type=int)
    p.set_defaults(func=cmd_index)
    p = sub.add_parser('storage', help='Espacio de los archivos y limpieza de huérfanos')
    p.add_argument('--limpiar', action='store_true')
    p.add_argument('--simular', action='store_true', help='Con --limpiar: sólo muestra qué se borraría')
    p.add_argument('--horas', type=float, default=24, help='Antigüedad mínima de un huérfano para borrarlo')
    p.set_defaults(func=cmd_storage)
    p = sub.add_parser('scan', help='Pasa un archivo por el vigilante')
    p.add_argument('path')
    p.add_argument('--no-ai', action='store_true')
    p.set_defaults(func=cmd_scan)
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
