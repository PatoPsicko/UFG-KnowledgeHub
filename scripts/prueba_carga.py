"""Prueba de carga: simula N estudiantes usando el sitio al mismo tiempo.

    python scripts/prueba_carga.py                    20 usuarios, 2 minutos, contra http://127.0.0.1:5001
    python scripts/prueba_carga.py --usuarios 30 --minutos 5
    python scripts/prueba_carga.py --url https://xxxx.trycloudflare.com
    python scripts/prueba_carga.py --con-ia           además cada usuario hace 2 preguntas al asistente
    python scripts/prueba_carga.py --limpiar          borra las cuentas de prueba (@carga.test) y lo que crearon

Cada usuario virtual hace lo mismo que un estudiante con la pestaña abierta:
pide el «pulso» cada 4 s, abre la biblioteca, busca, escribe en el chat global,
abre sus conversaciones y su grupo. Al final se muestra la latencia (p50/p95)
y los errores por tipo de petición.

Las cuentas se crean directamente en la base de datos (no por /api/register,
que limita los registros por IP), con el dominio reservado @carga.test.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DOMINIO = 'carga.test'
CLAVE = 'CargaUFG2026'
BUSQUEDAS = ['base de datos', 'calculo', 'derecho', 'sql', 'ingles', 'contabilidad', 'anatomia', 'redes']


def preparar_cuentas(n: int) -> list[str]:
    from hub import create_app
    from hub.extensions import bcrypt, db
    from hub.models import Contact, Group, GroupMember, User

    app = create_app({'BACKGROUND_WORKERS': False})
    with app.app_context():
        clave = bcrypt.generate_password_hash(CLAVE).decode()
        correos = []
        usuarios = []
        for i in range(1, n + 1):
            correo = f'estudiante{i:02d}@{DOMINIO}'
            u = User.query.filter_by(email=correo).first()
            if not u:
                u = User(name=f'Estudiante {i:02d}', email=correo, password=clave,
                         career=random.choice(['Ingeniería en Sistemas', 'Derecho', 'Medicina', 'Arquitectura']))
                db.session.add(u)
            usuarios.append(u)
            correos.append(correo)
        db.session.flush()
        # Cada uno es amigo del siguiente y todos comparten un grupo.
        for a, b in zip(usuarios, usuarios[1:]):
            if not Contact.query.filter_by(user_id=a.id, contact_id=b.id).first():
                db.session.add(Contact(user_id=a.id, contact_id=b.id, status='accepted'))
        grupo = Group.query.filter_by(name='Grupo de prueba de carga').first()
        if not grupo:
            grupo = Group(name='Grupo de prueba de carga', description='Creado por scripts/prueba_carga.py',
                          owner_id=usuarios[0].id)
            db.session.add(grupo)
            db.session.flush()
        for u in usuarios:
            if not GroupMember.query.filter_by(group_id=grupo.id, user_id=u.id).first():
                db.session.add(GroupMember(group_id=grupo.id, user_id=u.id))
        db.session.commit()
    return correos


def limpiar() -> None:
    from hub import create_app
    from hub.extensions import db
    from hub.models import (AIConversation, ChatMessage, Contact, DirectMessage, Group, GroupMember, GroupMessage,
                            Notification, User)

    app = create_app({'BACKGROUND_WORKERS': False})
    with app.app_context():
        ids = [u.id for u in User.query.filter(User.email.like(f'%@{DOMINIO}')).all()]
        if not ids:
            print('No hay cuentas de prueba que borrar.')
            return
        for g in Group.query.filter_by(name='Grupo de prueba de carga').all():
            db.session.delete(g)
        ChatMessage.query.filter(ChatMessage.user_id.in_(ids)).delete(synchronize_session=False)
        DirectMessage.query.filter(DirectMessage.sender_id.in_(ids) | DirectMessage.receiver_id.in_(ids)).delete(synchronize_session=False)
        GroupMessage.query.filter(GroupMessage.user_id.in_(ids)).delete(synchronize_session=False)
        GroupMember.query.filter(GroupMember.user_id.in_(ids)).delete(synchronize_session=False)
        Contact.query.filter(Contact.user_id.in_(ids) | Contact.contact_id.in_(ids)).delete(synchronize_session=False)
        Notification.query.filter(Notification.user_id.in_(ids)).delete(synchronize_session=False)
        for c in AIConversation.query.filter(AIConversation.user_id.in_(ids)).all():
            db.session.delete(c)
        User.query.filter(User.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        print(f'Borradas {len(ids)} cuentas de prueba y su actividad.')


class Metricas:
    def __init__(self):
        self.tiempos = defaultdict(list)
        self.errores = defaultdict(int)
        self.lock = threading.Lock()

    def registrar(self, nombre: str, ms: float, ok: bool, detalle: str = '') -> None:
        with self.lock:
            self.tiempos[nombre].append(ms)
            if not ok:
                self.errores[f'{nombre}: {detalle}'] += 1


def peticion(base: str, metodo: str, ruta: str, token: str | None, cuerpo: dict | None, metricas: Metricas,
             nombre: str, timeout: int = 60) -> dict | None:
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(base + ruta, data=datos, headers=headers, method=metodo)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            contenido = resp.read()
        metricas.registrar(nombre, (time.perf_counter() - t0) * 1000, True)
        try:
            return json.loads(contenido)
        except ValueError:
            return {}
    except urllib.error.HTTPError as exc:
        metricas.registrar(nombre, (time.perf_counter() - t0) * 1000, False, str(exc.code))
    except Exception as exc:
        metricas.registrar(nombre, (time.perf_counter() - t0) * 1000, False, exc.__class__.__name__)
    return None


def estudiante(base: str, correo: str, fin: float, metricas: Metricas, con_ia: bool, indice: int) -> None:
    time.sleep(random.uniform(0, 3))  # que no entren todos en el mismo milisegundo
    r = peticion(base, 'POST', '/api/login', None, {'email': correo, 'password': CLAVE}, metricas, 'login')
    if not r or 'token' not in r:
        return
    token = r['token']
    peticion(base, 'GET', '/api/me', token, None, metricas, 'me')
    grupos = (peticion(base, 'GET', '/api/groups', token, None, metricas, 'grupos') or {}).get('groups', [])
    gid = grupos[0]['id'] if grupos else None
    preguntas = 2 if con_ia else 0
    ultimo_chat = 0
    siguiente = {'biblio': 0, 'chat': time.time() + random.uniform(5, 30), 'dm': time.time() + random.uniform(10, 40),
                 'grupo': time.time() + random.uniform(10, 40), 'ia': time.time() + random.uniform(5, 60)}
    while time.time() < fin:
        ahora = time.time()
        pulso = peticion(base, 'GET', '/api/pulse', token, None, metricas, 'pulso') or {}
        if pulso.get('global_last_id', 0) > ultimo_chat:
            msgs = (peticion(base, 'GET', f'/api/chat/messages?after={ultimo_chat}', token, None, metricas,
                             'chat leer') or {}).get('messages', [])
            if msgs:
                ultimo_chat = msgs[-1]['id']
        if ahora >= siguiente['biblio']:
            peticion(base, 'GET', '/api/resources?limit=60', token, None, metricas, 'biblioteca')
            peticion(base, 'GET', f'/api/resources?q={urllib.parse.quote(random.choice(BUSQUEDAS))}', token, None,
                     metricas, 'buscar')
            siguiente['biblio'] = ahora + random.uniform(15, 30)
        if ahora >= siguiente['chat']:
            peticion(base, 'POST', '/api/chat/messages', token, {'message': f'Hola desde la prueba de carga ({indice})'},
                     metricas, 'chat enviar')
            siguiente['chat'] = ahora + random.uniform(25, 50)
        if ahora >= siguiente['dm']:
            convs = (peticion(base, 'GET', '/api/conversations', token, None, metricas, 'conversaciones') or {}).get('conversations', [])
            if convs:
                otro = random.choice(convs)['user']['id']
                peticion(base, 'POST', '/api/direct-messages', token, {'receiver_id': otro, 'message': '¿Estudiamos hoy?'},
                         metricas, 'dm enviar')
                peticion(base, 'GET', f'/api/direct-messages/{otro}', token, None, metricas, 'dm leer')
            siguiente['dm'] = ahora + random.uniform(30, 60)
        if gid and ahora >= siguiente['grupo']:
            peticion(base, 'GET', f'/api/groups/{gid}', token, None, metricas, 'grupo detalle')
            peticion(base, 'POST', f'/api/groups/{gid}/messages', token, {'message': 'Avance listo'}, metricas, 'grupo enviar')
            siguiente['grupo'] = ahora + random.uniform(30, 60)
        if preguntas and ahora >= siguiente['ia']:
            peticion(base, 'POST', '/api/ai/chat', token, {'question': random.choice(
                ['¿Qué material hay sobre bases de datos?', 'Explícame la tercera forma normal',
                 '¿Qué es una derivada?', 'Resume el material de contabilidad'])}, metricas, 'asistente', timeout=180)
            preguntas -= 1
            siguiente['ia'] = ahora + random.uniform(20, 40)
        time.sleep(4)


def percentil(valores: list[float], p: float) -> float:
    if not valores:
        return 0
    orden = sorted(valores)
    return orden[min(len(orden) - 1, int(round(p / 100 * (len(orden) - 1))))]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--url', default='http://127.0.0.1:5001')
    parser.add_argument('--usuarios', type=int, default=20)
    parser.add_argument('--minutos', type=float, default=2)
    parser.add_argument('--con-ia', action='store_true', help='Incluye preguntas al asistente (gasta cuota de IA)')
    parser.add_argument('--limpiar', action='store_true', help='Borra las cuentas de prueba y termina')
    args = parser.parse_args()

    if args.limpiar:
        return limpiar()

    correos = preparar_cuentas(args.usuarios)
    base = args.url.rstrip('/')
    metricas = Metricas()
    fin = time.time() + args.minutos * 60
    print(f'Simulando {args.usuarios} estudiantes durante {args.minutos} min contra {base} ...')
    hilos = [threading.Thread(target=estudiante, args=(base, c, fin, metricas, args.con_ia, i), daemon=True)
             for i, c in enumerate(correos, 1)]
    t0 = time.time()
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=args.minutos * 60 + 240)
    duracion = time.time() - t0

    total = sum(len(v) for v in metricas.tiempos.values())
    errores = sum(metricas.errores.values())
    print(f'\n{total} peticiones en {duracion:.0f} s ({total / duracion:.1f} por segundo), {errores} errores\n')
    print(f'{"Petición":<16}{"n":>6}{"p50 ms":>10}{"p95 ms":>10}{"máx ms":>10}')
    for nombre in sorted(metricas.tiempos):
        v = metricas.tiempos[nombre]
        print(f'{nombre:<16}{len(v):>6}{statistics.median(v):>10.0f}{percentil(v, 95):>10.0f}{max(v):>10.0f}')
    if metricas.errores:
        print('\nErrores:')
        for k, n in sorted(metricas.errores.items(), key=lambda x: -x[1]):
            print(f'  {k}: {n}')
    print('\nPara borrar las cuentas de prueba: python scripts/prueba_carga.py --limpiar')


if __name__ == '__main__':
    main()
