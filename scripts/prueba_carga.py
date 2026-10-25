"""Prueba de carga: simula N estudiantes usando todo el sistema al mismo tiempo.

    python scripts/prueba_carga.py --aislado              recomendado: 20 usuarios, 3 min, IA simulada
    python scripts/prueba_carga.py --aislado --usuarios 30 --minutos 5
    python scripts/prueba_carga.py --url http://127.0.0.1:5001          contra un servidor ya encendido
    python scripts/prueba_carga.py --url https://xxxx.trycloudflare.com --preguntas 1   (gasta cuota real)
    python scripts/prueba_carga.py --limpiar              borra las cuentas de prueba (@carga.test)

Cada usuario virtual hace lo mismo que un estudiante con la app abierta:
pide el «pulso» cada 4 s, abre y busca en la biblioteca, abre un documento,
lo previsualiza y lo descarga (con enlace firmado, como en el celular), sube
un documento a la biblioteca, otro a Mi espacio y otro al grupo (los tres
pasan por el vigilante), escribe en el chat del grupo y le hace preguntas al
asistente por streaming, igual que la interfaz.

--aislado arranca su propio servidor (python wsgi.py en el puerto 5001) con
una base de datos y una carpeta de archivos temporales y la IA simulada
(AI_SIMULATED=1): mismos límites que la cuenta gratuita de Groq, sin gastar
cuota ni tocar los datos reales. Al terminar lo apaga (la carpeta temporal
queda con el registro del servidor por si hay que revisarlo).

Al final se muestra la latencia (p50/p95/máx) por tipo de petición, los
errores, cómo le fue al asistente (cola, primera palabra, respuestas sin IA)
y al vigilante (publicados solos, en cuarentena, pendientes).

Las cuentas se crean directamente en la base de datos (no por /api/register,
que limita los registros por IP), con el dominio reservado @carga.test.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import defaultdict

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

DOMINIO = 'carga.test'
CLAVE = 'CargaUFG2026'
GRUPO = 'Grupo de prueba de carga'
BUSQUEDAS = ['base de datos', 'calculo', 'derecho', 'sql', 'ingles', 'contabilidad', 'anatomia', 'redes']
PREGUNTAS = ['¿Qué material hay sobre bases de datos?', 'Explícame la tercera forma normal',
             '¿Qué es una derivada?', 'Resume el material de contabilidad', '¿Cómo funciona el modelo OSI?']
TEMAS = {
    'Normalización de bases de datos': 'La normalización organiza las tablas de una base de datos para evitar datos '
                                       'repetidos. La primera forma normal pide valores atómicos; la segunda elimina '
                                       'dependencias parciales y la tercera forma normal elimina dependencias transitivas.',
    'Derivadas básicas': 'La derivada mide la razón de cambio de una función. La derivada de x al cuadrado es 2x y la '
                         'de una constante es cero. Se usa para encontrar máximos, mínimos y pendientes.',
    'Modelo OSI': 'El modelo OSI tiene siete capas: física, enlace, red, transporte, sesión, presentación y '
                  'aplicación. TCP/IP agrupa esas funciones en cuatro capas.',
    'Contabilidad general': 'El balance general muestra activos, pasivos y patrimonio. La ecuación contable dice que '
                            'el activo es igual al pasivo más el capital.',
    'Consultas SQL': 'SELECT obtiene columnas, WHERE filtra filas, GROUP BY agrupa y JOIN combina tablas por una '
                     'clave común. ORDER BY ordena el resultado.',
}


# --- Cuentas ---------------------------------------------------------------------

def preparar_cuentas(n: int) -> list[str]:
    from hub import create_app
    from hub.extensions import bcrypt, db
    from hub.models import Group, GroupMember, User

    app = create_app({'BACKGROUND_WORKERS': False})
    with app.app_context():
        clave = bcrypt.generate_password_hash(CLAVE).decode()
        correos, usuarios = [], []
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
        grupo = Group.query.filter_by(name=GRUPO).first()
        if not grupo:
            grupo = Group(name=GRUPO, description='Creado por scripts/prueba_carga.py', owner_id=usuarios[0].id)
            db.session.add(grupo)
            db.session.flush()
        for u in usuarios:
            if not GroupMember.query.filter_by(group_id=grupo.id, user_id=u.id).first():
                db.session.add(GroupMember(group_id=grupo.id, user_id=u.id))
        db.session.commit()
    return correos


def limpiar() -> None:
    from hub import create_app, storage
    from hub.extensions import db
    from hub.models import (AIConversation, FileScan, Group, GroupMember, GroupMessage, Notification,
                            PrivateResource, Resource, SavedResource, User)

    app = create_app({'BACKGROUND_WORKERS': False})
    with app.app_context():
        ids = [u.id for u in User.query.filter(User.email.like(f'%@{DOMINIO}')).all()]
        if not ids:
            print('No hay cuentas de prueba que borrar.')
            return
        for g in Group.query.filter_by(name=GRUPO).all():
            shutil.rmtree(storage.folder_for('group', g.id), ignore_errors=True)
            db.session.delete(g)
        for r in Resource.query.filter(Resource.owner_id.in_(ids)).all():
            storage.delete_upload('public', r.filename)
            SavedResource.query.filter_by(resource_id=r.id).delete()
            db.session.delete(r)
        for p in PrivateResource.query.filter(PrivateResource.owner_id.in_(ids)).all():
            storage.delete_upload('private', p.filename, p.owner_id)
            db.session.delete(p)
        GroupMessage.query.filter(GroupMessage.user_id.in_(ids)).delete(synchronize_session=False)
        GroupMember.query.filter(GroupMember.user_id.in_(ids)).delete(synchronize_session=False)
        Notification.query.filter(Notification.user_id.in_(ids)).delete(synchronize_session=False)
        FileScan.query.filter(FileScan.user_id.in_(ids)).delete(synchronize_session=False)
        for c in AIConversation.query.filter(AIConversation.user_id.in_(ids)).all():
            db.session.delete(c)
        User.query.filter(User.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        print(f'Borradas {len(ids)} cuentas de prueba, sus archivos y su actividad.')


# --- Peticiones --------------------------------------------------------------------

class Metricas:
    def __init__(self):
        self.tiempos = defaultdict(list)
        self.errores = defaultdict(int)
        self.ia = defaultdict(list)    # primera_palabra, total, cola_s
        self.ia_cuenta = defaultdict(int)
        self.lock = threading.Lock()

    def registrar(self, nombre: str, ms: float, ok: bool, detalle: str = '') -> None:
        with self.lock:
            self.tiempos[nombre].append(ms)
            if not ok:
                self.errores[f'{nombre}: {detalle}'] += 1


def _abrir(base, metodo, ruta, token, datos, tipo, timeout):
    headers = {'Content-Type': tipo} if tipo else {}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(base + ruta, data=datos, headers=headers, method=metodo)
    return urllib.request.urlopen(req, timeout=timeout)


def peticion(base: str, metodo: str, ruta: str, token: str | None, cuerpo, metricas: Metricas, nombre: str,
             timeout: int = 60, tipo: str = 'application/json', binario: bool = False):
    datos = json.dumps(cuerpo).encode() if isinstance(cuerpo, dict) else cuerpo
    t0 = time.perf_counter()
    try:
        with _abrir(base, metodo, ruta, token, datos, tipo if datos is not None else None, timeout) as resp:
            contenido = resp.read()
        metricas.registrar(nombre, (time.perf_counter() - t0) * 1000, True)
        if binario:
            return contenido
        try:
            return json.loads(contenido)
        except ValueError:
            return {}
    except urllib.error.HTTPError as exc:
        metricas.registrar(nombre, (time.perf_counter() - t0) * 1000, False, str(exc.code))
    except Exception as exc:
        metricas.registrar(nombre, (time.perf_counter() - t0) * 1000, False, exc.__class__.__name__)
    return None


def multipart(campos: dict, nombre_archivo: str, contenido: bytes) -> tuple[bytes, str]:
    limite = uuid.uuid4().hex
    partes = []
    for k, v in campos.items():
        partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="file"; filename="{nombre_archivo}"\r\n'
                  f'Content-Type: application/octet-stream\r\n\r\n'.encode() + contenido + b'\r\n')
    partes.append(f'--{limite}--\r\n'.encode())
    return b''.join(partes), f'multipart/form-data; boundary={limite}'


def documento(indice: int) -> tuple[str, bytes, str]:
    titulo, texto = random.choice(list(TEMAS.items()))
    cuerpo = f'{titulo}\n\n' + ' '.join([texto] * random.randint(3, 12)) + f'\n\nCopia de la prueba de carga {indice}.'
    return f'{titulo} {indice}', cuerpo.encode(), titulo.split()[0]


def subir(base, token, ruta, metricas, nombre, indice, extra=None) -> dict | None:
    titulo, contenido, tema = documento(indice)
    campos = {'title': titulo, 'author': f'Estudiante {indice:02d}', 'category': 'Base de Datos',
              'tags': tema.lower(), **(extra or {})}
    datos, tipo = multipart(campos, f'apuntes-{indice}-{uuid.uuid4().hex[:6]}.txt', contenido)
    return peticion(base, 'POST', ruta, token, datos, metricas, nombre, tipo=tipo, timeout=120)


def preguntar(base: str, token: str, pregunta: str, metricas: Metricas) -> None:
    """Pregunta por /api/ai/chat/stream (como la interfaz) y mide cola y primera palabra."""
    datos = json.dumps({'question': pregunta}).encode()
    t0 = time.perf_counter()
    primera = cola = None
    tipo_final = 'error'
    try:
        with _abrir(base, 'POST', '/api/ai/chat/stream', token, datos, 'application/json', 300) as resp:
            for crudo in resp:
                linea = crudo.decode('utf-8', 'replace').strip()
                if not linea:
                    continue
                ev = json.loads(linea)
                if ev['type'] == 'queue' and cola is None:
                    cola = time.perf_counter()
                elif ev['type'] == 'token' and primera is None:
                    primera = time.perf_counter()
                elif ev['type'] == 'done':
                    tipo_final = 'sin IA' if ev.get('degraded') else 'caché' if ev.get('cached') else 'IA'
                elif ev['type'] == 'error':
                    tipo_final = 'error'
        total = (time.perf_counter() - t0) * 1000
        metricas.registrar('asistente', total, tipo_final != 'error', 'respuesta con error')
        with metricas.lock:
            metricas.ia_cuenta[tipo_final] += 1
            metricas.ia_cuenta['en cola'] += 1 if cola else 0
            if primera:
                metricas.ia['primera palabra'].append((primera - t0) * 1000)
            metricas.ia['respuesta completa'].append(total)
    except Exception as exc:
        metricas.registrar('asistente', (time.perf_counter() - t0) * 1000, False, exc.__class__.__name__)


PREGUNTAS_UNICAS = False


def estudiante(base: str, correo: str, fin: float, metricas: Metricas, preguntas: int, indice: int) -> None:
    time.sleep(random.uniform(0, 3))  # que no entren todos en el mismo milisegundo
    r = peticion(base, 'POST', '/api/login', None, {'email': correo, 'password': CLAVE}, metricas, 'login')
    if not r or 'token' not in r:
        return
    token = r['token']
    peticion(base, 'GET', '/api/me', token, None, metricas, 'me')
    grupos = (peticion(base, 'GET', '/api/groups', token, None, metricas, 'grupos') or {}).get('groups', [])
    gid = next((g['id'] for g in grupos if g['name'] == GRUPO), None)
    ahora = time.time()
    siguiente = {'biblio': ahora, 'doc': ahora + random.uniform(5, 20), 'subir': ahora + random.uniform(5, 40),
                 'privado': ahora + random.uniform(20, 80), 'grupo_archivo': ahora + random.uniform(20, 80),
                 'grupo': ahora + random.uniform(10, 40), 'ia': ahora + random.uniform(5, 30)}
    hechos = {'subir': False, 'privado': False, 'grupo_archivo': False}
    restantes = preguntas
    while time.time() < fin:
        ahora = time.time()
        peticion(base, 'GET', '/api/pulse', token, None, metricas, 'pulso')
        if ahora >= siguiente['biblio']:
            peticion(base, 'GET', '/api/resources?limit=60', token, None, metricas, 'biblioteca')
            peticion(base, 'GET', f'/api/resources?q={urllib.parse.quote(random.choice(BUSQUEDAS))}', token, None,
                     metricas, 'buscar')
            siguiente['biblio'] = ahora + random.uniform(20, 40)
        if ahora >= siguiente['doc']:
            docs = (peticion(base, 'GET', '/api/resources?limit=30', token, None, metricas, 'biblioteca') or {}).get('resources', [])
            if docs:
                d = random.choice(docs)
                peticion(base, 'GET', f"/api/resources/{d['id']}", token, None, metricas, 'documento')
                peticion(base, 'GET', f"/api/resources/{d['id']}/file", token, None, metricas, 'vista previa', binario=True)
                enlace = peticion(base, 'POST', '/api/files/link', token,
                                  {'path': f"/api/resources/{d['id']}/file?download=1"}, metricas, 'enlace firmado')
                if enlace:
                    peticion(base, 'GET', enlace['url'], None, None, metricas, 'descarga', binario=True)
            siguiente['doc'] = ahora + random.uniform(25, 50)
        if not hechos['subir'] and ahora >= siguiente['subir']:
            subir(base, token, '/api/resources', metricas, 'subir biblioteca', indice)
            hechos['subir'] = True
        if not hechos['privado'] and ahora >= siguiente['privado']:
            subir(base, token, '/api/private-resources', metricas, 'subir Mi espacio', indice)
            hechos['privado'] = True
        if gid and not hechos['grupo_archivo'] and ahora >= siguiente['grupo_archivo']:
            subir(base, token, f'/api/groups/{gid}/resources', metricas, 'subir grupo', indice)
            hechos['grupo_archivo'] = True
        if gid and ahora >= siguiente['grupo']:
            peticion(base, 'GET', f'/api/groups/{gid}', token, None, metricas, 'grupo detalle')
            peticion(base, 'POST', f'/api/groups/{gid}/messages', token, {'message': 'Avance listo'}, metricas,
                     'grupo enviar')
            siguiente['grupo'] = ahora + random.uniform(30, 60)
        if restantes and ahora >= siguiente['ia']:
            pregunta = random.choice(PREGUNTAS)
            if PREGUNTAS_UNICAS:  # misma idea, distinta redacción: no sale de la caché
                pregunta += f' (lo pregunta el estudiante {indice}, intento {preguntas - restantes + 1})'
            preguntar(base, token, pregunta, metricas)
            restantes -= 1
            siguiente['ia'] = time.time() + random.uniform(15, 40)
        time.sleep(4)


# --- Servidor aislado ------------------------------------------------------------

def servidor_aislado(carpeta: str, antivirus: bool) -> subprocess.Popen:
    """Arranca wsgi.py con datos temporales y la IA simulada."""
    env = {**os.environ, 'AI_SIMULATED': '1', 'AI_EMBED_PROVIDER': 'none',
           'DATABASE_PATH': os.path.join(carpeta, 'carga.db'), 'UPLOAD_FOLDER': os.path.join(carpeta, 'uploads'),
           'AI_INDEX_DIR': os.path.join(carpeta, 'ai_index'), 'APP_PORT': '5001', 'PYTHONIOENCODING': 'utf-8'}
    if not antivirus:
        env['SCAN_ANTIVIRUS'] = 'off'
    os.environ.update({k: env[k] for k in ('AI_SIMULATED', 'AI_EMBED_PROVIDER', 'DATABASE_PATH', 'UPLOAD_FOLDER',
                                           'AI_INDEX_DIR')})
    registro = open(os.path.join(carpeta, 'servidor.log'), 'w', encoding='utf-8')
    proceso = subprocess.Popen([sys.executable, os.path.join(RAIZ, 'wsgi.py')], cwd=RAIZ, env=env,
                               stdout=registro, stderr=subprocess.STDOUT)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:5001/api/health', timeout=2)
            return proceso
        except Exception:
            if proceso.poll() is not None:
                break
            time.sleep(1)
    proceso.terminate()
    raise SystemExit(f'El servidor de prueba no arrancó. Mira {registro.name} (¿el puerto 5001 está ocupado?).')


def sembrar_biblioteca(base: str, correo: str, n: int = 12) -> None:
    """Unos documentos iniciales para que haya qué buscar, descargar y preguntar."""
    m = Metricas()
    token = peticion(base, 'POST', '/api/login', None, {'email': correo, 'password': CLAVE}, m, 'login')['token']
    for i in range(n):
        subir(base, token, '/api/resources', m, 'semilla', 100 + i)


def informe_vigilante() -> dict:
    from hub import create_app
    from hub.models import FileScan

    app = create_app({'BACKGROUND_WORKERS': False})
    with app.app_context():
        filas = FileScan.query.all()
        cuenta = defaultdict(int)
        for f in filas:
            cuenta[f.status] += 1
        return dict(cuenta)


def memoria_mb(pid: int) -> float | None:
    """RAM del servidor (Windows: el proceso y sus hijos, porque el python del
    entorno virtual lanza al intérprete real como hijo; Linux: /proc)."""
    try:
        if os.name == 'nt':
            orden = (f'(Get-CimInstance Win32_Process | Where-Object {{ $_.ProcessId -eq {pid} -or '
                     f'$_.ParentProcessId -eq {pid} }} | Measure-Object WorkingSetSize -Sum).Sum')
            salida = subprocess.run(['powershell', '-NoProfile', '-Command', orden], capture_output=True,
                                    text=True, timeout=30).stdout
            return int(salida.strip()) / 1024 / 1024
        with open(f'/proc/{pid}/status', encoding='utf-8') as fh:
            for linea in fh:
                if linea.startswith('VmRSS:'):
                    return int(linea.split()[1]) / 1024
    except Exception:
        return None
    return None


# --- Informe -----------------------------------------------------------------------

def percentil(valores: list[float], p: float) -> float:
    if not valores:
        return 0
    orden = sorted(valores)
    return orden[min(len(orden) - 1, int(round(p / 100 * (len(orden) - 1))))]


def imprimir(metricas: Metricas, duracion: float, usuarios: int) -> None:
    total = sum(len(v) for v in metricas.tiempos.values())
    errores = sum(metricas.errores.values())
    print(f'\n{usuarios} estudiantes · {total} peticiones en {duracion:.0f} s '
          f'({total / duracion:.1f} por segundo) · {errores} errores\n')
    print(f'{"Petición":<18}{"n":>6}{"p50 ms":>10}{"p95 ms":>10}{"máx ms":>10}')
    for nombre in sorted(metricas.tiempos):
        v = metricas.tiempos[nombre]
        print(f'{nombre:<18}{len(v):>6}{statistics.median(v):>10.0f}{percentil(v, 95):>10.0f}{max(v):>10.0f}')
    if metricas.ia['respuesta completa']:
        c = metricas.ia_cuenta
        print(f"\nAsistente: {c['IA']} con IA, {c['caché']} de caché, {c['sin IA']} sin IA (cuota agotada), "
              f"{c['error']} con error; {c['en cola']} esperaron en cola.")
        for nombre, v in metricas.ia.items():
            print(f'  {nombre:<20} p50 {statistics.median(v) / 1000:5.1f} s   p95 {percentil(v, 95) / 1000:5.1f} s   '
                  f'máx {max(v) / 1000:5.1f} s')
    if metricas.errores:
        print('\nErrores:')
        for k, n in sorted(metricas.errores.items(), key=lambda x: -x[1]):
            print(f'  {k}: {n}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--url', default='http://127.0.0.1:5001')
    parser.add_argument('--usuarios', type=int, default=20)
    parser.add_argument('--minutos', type=float, default=3)
    parser.add_argument('--preguntas', type=int, default=None,
                        help='Preguntas al asistente por usuario (por defecto 3 en --aislado y 0 contra un servidor real)')
    parser.add_argument('--aislado', action='store_true', help='Servidor propio con datos temporales e IA simulada')
    parser.add_argument('--sin-antivirus', action='store_true', help='Con --aislado: no pasa los archivos por Defender')
    parser.add_argument('--preguntas-distintas', action='store_true',
                        help='Cada pregunta es única (sin caché): el peor caso para la cuota de IA')
    parser.add_argument('--limpiar', action='store_true', help='Borra las cuentas de prueba y termina')
    args = parser.parse_args()

    if args.limpiar:
        return limpiar()
    global PREGUNTAS_UNICAS
    PREGUNTAS_UNICAS = args.preguntas_distintas

    carpeta = proceso = None
    preguntas = args.preguntas if args.preguntas is not None else (3 if args.aislado else 0)
    if args.aislado:
        carpeta = tempfile.mkdtemp(prefix='ufg-carga-')
        proceso = servidor_aislado(carpeta, antivirus=not args.sin_antivirus)
        args.url = 'http://127.0.0.1:5001'
        print(f'Servidor de prueba con IA simulada en {args.url} (datos en {carpeta})')
    try:
        correos = preparar_cuentas(args.usuarios)
        base = args.url.rstrip('/')
        if args.aislado:
            sembrar_biblioteca(base, correos[0])
        metricas = Metricas()
        fin = time.time() + args.minutos * 60
        print(f'Simulando {args.usuarios} estudiantes durante {args.minutos} min contra {base} '
              f'({preguntas} preguntas al asistente por estudiante) ...')
        hilos = [threading.Thread(target=estudiante, args=(base, c, fin, metricas, preguntas, i), daemon=True)
                 for i, c in enumerate(correos, 1)]
        t0 = time.time()
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(timeout=args.minutos * 60 + 400)
        imprimir(metricas, time.time() - t0, args.usuarios)
        if args.aislado:
            ram = memoria_mb(proceso.pid)
            if ram:
                print(f'\nMemoria del servidor al terminar: {ram:.0f} MB')
            # El vigilante sigue revisando lo último que recibió: se espera a que vacíe su cola.
            t_fin = time.time()
            estados = informe_vigilante()
            while estados.get('pending') and time.time() - t_fin < 600:
                time.sleep(5)
                estados = informe_vigilante()
            print(f"Vigilante: {estados.get('clean', 0)} publicados solos, {estados.get('review', 0)} en cuarentena, "
                  f"{estados.get('blocked', 0)} bloqueados, {estados.get('pending', 0)} aún en revisión "
                  f"(cola vaciada {time.time() - t_fin:.0f} s después de terminar la prueba).")
        else:
            print('\nPara borrar las cuentas de prueba: python scripts/prueba_carga.py --limpiar')
    finally:
        if proceso:
            proceso.terminate()
            try:
                proceso.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proceso.kill()
            print(f'Registro del servidor: {os.path.join(carpeta, "servidor.log")}')


if __name__ == '__main__':
    main()
