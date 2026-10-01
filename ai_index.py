"""Índice de búsqueda del asistente: vectores (ChromaDB/HNSW) + léxico (FTS5/BM25).

Implementa el capítulo 5 del documento "Integración de inteligencia artificial
en la plataforma UFG Knowledge Hub":

    5.1  Fragmentación     800 caracteres con 100 de solape, por página.
    5.2  Vectores          nomic-embed-text (768 dimensiones) vía Ollama.
    5.3  Similitud coseno  la colección de ChromaDB usa espacio "cosine".
    5.4  Índice HNSW       el que trae ChromaDB por defecto.
    5.5  Búsqueda híbrida  vectorial + BM25 (SQLite FTS5), fusión RRF k=60.
    5.6  Permisos          condición sobre metadatos DENTRO de cada búsqueda.
    5.7  Reordenamiento    20 candidatos por lista, se conservan los 5 mejores.

Y la etapa 4 del plan: el índice se actualiza al subir, editar o borrar un
recurso (cola en segundo plano), y al arrancar se sincroniza con la base de
datos por si algo cambió con la app apagada.

Si ChromaDB o el modelo de embeddings no están disponibles, la búsqueda sigue
funcionando sólo con BM25 (modo "léxico") en lugar de dejar al asistente caído.

Uso desde consola (comprobación de la etapa 1):

    python ai_index.py --sync                 indexa lo nuevo o modificado
    python ai_index.py --rebuild              borra el índice y lo rehace
    python ai_index.py --stats                resumen del índice
    python ai_index.py --query "pregunta" --user 1
"""

import hashlib
import logging
import os
import queue
import re
import shutil
import sqlite3
import threading
import time
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass

import ai_service

log = logging.getLogger('ai_index')

# --- Parámetros (capítulos 5.1 y 5.7) ----------------------------------------
CHUNK_SIZE = int(os.environ.get('AI_CHUNK_SIZE') or 800)
CHUNK_OVERLAP = int(os.environ.get('AI_CHUNK_OVERLAP') or 100)
CANDIDATOS = int(os.environ.get('AI_CANDIDATES') or 20)
TOP_K = int(os.environ.get('AI_TOP_K') or 5)
RRF_K = 60
EMBED_BATCH = 32
MAX_CHARS_PER_FILE = 400_000
MAX_PDF_PAGES = 300
# Un PDF con menos caracteres por página que esto se considera escaneado.
MIN_CHARS_PDF_PAGE = 25

# ChromaDB en modo servidor (para despliegues con varios procesos). Vacío =
# ChromaDB embebido, guardado en disco junto al resto del índice.
CHROMA_HOST = os.environ.get('CHROMA_HOST', '').strip()
CHROMA_PORT = int(os.environ.get('CHROMA_PORT') or 8000)

ACCESO = {
    'public': 'publico',
    'private_note': 'privado',
    'private_file': 'privado',
    'group': 'grupo',
}


@dataclass
class DocSpec:
    """Lo que el índice necesita saber de un recurso de la plataforma.

    app.py construye estos objetos; este módulo no conoce la base de datos.
    O bien `path` (archivo en disco) o bien `text` (nota) traen el contenido.
    `header` son los metadatos legibles (título, autor, etiquetas...).
    """
    kind: str
    resource_id: int
    title: str
    owner_id: int
    origin: str
    header: str = ''
    group_id: int = None
    path: str = None
    text: str = None
    version: str = ''

    @property
    def key(self):
        return f'{self.kind}:{self.resource_id}'

    @property
    def access(self):
        return ACCESO[self.kind]

    def fingerprint(self):
        """Cambia si cambia el contenido o los metadatos: evita reindexar en vano."""
        partes = [self.title, self.header, str(self.group_id), self.version]
        if self.path:
            try:
                st = os.stat(self.path)
                partes += [self.path, str(st.st_size), str(int(st.st_mtime))]
            except OSError:
                partes.append('sin-archivo')
        if self.text is not None:
            partes.append(self.text)
        return hashlib.sha1('\x1f'.join(partes).encode('utf-8')).hexdigest()


# --- Extracción de texto (etapa 1) -------------------------------------------

def extraer_paginas(path):
    """Devuelve (lista de (página, texto), estado).

    estado: 'ok', 'sin_texto' (PDF escaneado), 'no_soportado' o 'error: ...'.
    Para formatos sin páginas se usa página 0.
    """
    if not path or not os.path.exists(path):
        return [], 'sin_archivo'

    ext = path.rsplit('.', 1)[-1].lower() if '.' in path else ''
    try:
        if ext in ('txt', 'md', 'csv'):
            with open(path, 'r', encoding='utf-8', errors='replace') as fh:
                return [(0, fh.read(MAX_CHARS_PER_FILE))], 'ok'

        if ext == 'pdf':
            from pypdf import PdfReader
            paginas = []
            total = 0
            lector = PdfReader(path)
            for n, pagina in enumerate(lector.pages[:MAX_PDF_PAGES], 1):
                texto = pagina.extract_text() or ''
                paginas.append((n, texto))
                total += len(texto.strip())
                if total > MAX_CHARS_PER_FILE:
                    break
            # Riesgo de la sección 9: PDF escaneado sin capa de texto. Se marca
            # para que se vea en las estadísticas; el OCR queda fuera de alcance.
            if paginas and total < MIN_CHARS_PDF_PAGE * len(paginas):
                return [], 'sin_texto'
            return paginas, 'ok'

        if ext == 'docx':
            import docx
            texto = '\n'.join(p.text for p in docx.Document(path).paragraphs)
            return [(0, texto[:MAX_CHARS_PER_FILE])], 'ok'

    except ImportError as exc:
        return [], f'error: falta la librería {exc.name}'
    except Exception as exc:
        return [], f'error: {exc.__class__.__name__}'

    return [], 'no_soportado'


def fragmentar(texto, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Bloques de `size` caracteres con `overlap` de solape (sección 5.1).

    Corta en un espacio para no partir palabras.
    """
    texto = re.sub(r'\s+', ' ', texto or '').strip()
    if not texto:
        return []

    fragmentos = []
    inicio = 0
    while inicio < len(texto):
        fin = min(len(texto), inicio + size)
        if fin < len(texto):
            corte = texto.rfind(' ', inicio + size // 2, fin)
            if corte > inicio:
                fin = corte
        fragmentos.append(texto[inicio:fin].strip())
        if fin >= len(texto):
            break
        inicio = max(fin - overlap, inicio + 1)
    return fragmentos


# --- Consulta FTS5 -----------------------------------------------------------
_STOPWORDS = {
    'que', 'para', 'por', 'con', 'una', 'uno', 'unos', 'unas', 'los', 'las',
    'del', 'como', 'mas', 'pero', 'sus', 'este', 'esta', 'estos', 'estas',
    'ese', 'esa', 'esos', 'esas', 'hay', 'son', 'sobre', 'entre', 'cual',
    'cuales', 'donde', 'cuando', 'quien', 'tiene', 'tienen', 'tengo', 'puedo',
    'puede', 'algo', 'algun', 'alguna', 'dime', 'explica', 'explicame',
    'cual', 'qué', 'cómo', 'the', 'and', 'for', 'with', 'what',
}


def consulta_fts(pregunta):
    """Convierte la pregunta en una consulta FTS5: término1* OR término2* ...

    El asterisco busca por prefijo, así "base" encuentra "bases" y "básico"
    no; es un sustituto barato de la lematización que FTS5 no trae en español.
    """
    norm = unicodedata.normalize('NFKD', pregunta.lower())
    norm = ''.join(c for c in norm if not unicodedata.combining(c))
    terminos = []
    for t in re.findall(r'[a-z0-9]+', norm):
        if len(t) < 3 or t in _STOPWORDS:
            continue
        if len(t) > 4 and t.endswith('s'):
            t = t[:-1]
        if t not in terminos:
            terminos.append(t)
    return ' OR '.join(f'"{t}"*' for t in terminos)


# --- Índice ------------------------------------------------------------------

class Indice:
    """ChromaDB (vectores) + SQLite FTS5 (texto) con los mismos fragmentos."""

    def __init__(self, directorio):
        self.directorio = directorio
        os.makedirs(directorio, exist_ok=True)
        self.db_path = os.path.join(directorio, 'fts.sqlite3')
        self._lock = threading.RLock()
        self._coleccion = None
        self.error_vectorial = None
        self._crear_tablas()

    # SQLite ------------------------------------------------------------------
    @contextmanager
    def _conn(self):
        """Conexión que confirma al salir sin error y siempre se cierra."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _crear_tablas(self):
        with self._conn() as c:
            c.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS fragmentos USING fts5(
                    title, body,
                    chunk_id UNINDEXED, doc_key UNINDEXED, kind UNINDEXED,
                    resource_id UNINDEXED, access UNINDEXED, owner_id UNINDEXED,
                    group_id UNINDEXED, page UNINDEXED, origin UNINDEXED,
                    tokenize = 'unicode61 remove_diacritics 2'
                )""")
            c.execute("""
                CREATE TABLE IF NOT EXISTS documentos (
                    doc_key TEXT PRIMARY KEY, kind TEXT, resource_id INTEGER,
                    title TEXT, access TEXT, owner_id INTEGER, group_id INTEGER,
                    origin TEXT, fingerprint TEXT, chunks INTEGER, vectors INTEGER,
                    status TEXT, indexed_at REAL
                )""")

    # ChromaDB ----------------------------------------------------------------
    def coleccion(self):
        """Colección de ChromaDB, o None si no está disponible (modo léxico)."""
        if self._coleccion is not None:
            return self._coleccion
        try:
            import chromadb
            if CHROMA_HOST:
                cliente = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
            else:
                cliente = chromadb.PersistentClient(path=os.path.join(self.directorio, 'chroma'))
            # Espacio coseno (sección 5.3); el índice es HNSW (sección 5.4).
            # Los vectores los calcula Ollama, por eso no hay embedding_function.
            self._coleccion = cliente.get_or_create_collection(
                name='fragmentos',
                metadata={'hnsw:space': 'cosine'},
                embedding_function=None,
            )
            self.error_vectorial = None
        except Exception as exc:
            self.error_vectorial = f'{exc.__class__.__name__}: {exc}'
            log.warning('ChromaDB no disponible, se usará sólo BM25: %s', self.error_vectorial)
            self._coleccion = None
        return self._coleccion

    # Escritura ---------------------------------------------------------------
    def indexar(self, spec):
        """(Re)indexa un documento en FTS5 y en ChromaDB. Devuelve el estado."""
        if spec.text is not None:
            paginas, estado = [(0, spec.text)], 'ok'
        else:
            paginas, estado = extraer_paginas(spec.path)

        trozos = []  # (página, texto)
        for pagina, texto in paginas:
            trozos += [(pagina, t) for t in fragmentar(texto)]

        # Sin contenido legible (imagen, zip, PDF escaneado...) el recurso se
        # indexa igualmente por sus metadatos, para que se pueda encontrar.
        if not trozos:
            trozos = [(0, spec.header or spec.title)]
            if estado == 'ok':
                estado = 'solo_metadatos'

        ids = [f'{spec.key}:{i}' for i in range(len(trozos))]
        group_id = spec.group_id if spec.group_id is not None else -1

        with self._lock:
            self._borrar(spec.key)

            with self._conn() as c:
                c.executemany(
                    'INSERT INTO fragmentos (title, body, chunk_id, doc_key, kind, resource_id, access, '
                    'owner_id, group_id, page, origin) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                    [(f'{spec.title} {spec.header}', texto, cid, spec.key, spec.kind, spec.resource_id,
                      spec.access, spec.owner_id, group_id, pagina, spec.origin)
                     for cid, (pagina, texto) in zip(ids, trozos)])

            vectores = 0
            coleccion = self.coleccion()
            if coleccion is not None:
                try:
                    for i in range(0, len(trozos), EMBED_BATCH):
                        lote = trozos[i:i + EMBED_BATCH]
                        lote_ids = ids[i:i + EMBED_BATCH]
                        # El título va delante: el vector sabe de qué documento es el fragmento.
                        embeddings = ai_service.embed([f'{spec.title}\n{t}' for _, t in lote])
                        coleccion.add(
                            ids=lote_ids,
                            embeddings=embeddings,
                            documents=[t for _, t in lote],
                            metadatas=[{
                                'doc_key': spec.key, 'kind': spec.kind,
                                'resource_id': spec.resource_id, 'title': spec.title,
                                'access': spec.access, 'owner_id': spec.owner_id,
                                'group_id': group_id, 'page': pagina, 'origin': spec.origin,
                            } for pagina, _ in lote],
                        )
                        vectores += len(lote)
                except Exception as exc:
                    # Sin vectores el documento sigue siendo encontrable por BM25.
                    log.warning('No se generaron vectores para %s: %s', spec.key, exc)
                    self._borrar_vectores(spec.key)
                    vectores = 0

            with self._conn() as c:
                c.execute(
                    'INSERT OR REPLACE INTO documentos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (spec.key, spec.kind, spec.resource_id, spec.title, spec.access, spec.owner_id,
                     group_id, spec.origin, spec.fingerprint(), len(trozos), vectores, estado, time.time()))
        return estado

    def _borrar_vectores(self, doc_key):
        coleccion = self.coleccion()
        if coleccion is not None:
            try:
                coleccion.delete(where={'doc_key': doc_key})
            except Exception as exc:
                log.warning('No se pudieron borrar los vectores de %s: %s', doc_key, exc)

    def _borrar(self, doc_key):
        with self._conn() as c:
            c.execute('DELETE FROM fragmentos WHERE doc_key = ?', (doc_key,))
            c.execute('DELETE FROM documentos WHERE doc_key = ?', (doc_key,))
        self._borrar_vectores(doc_key)

    def borrar(self, doc_key):
        with self._lock:
            self._borrar(doc_key)

    def sincronizar(self, specs):
        """Deja el índice igual que la base de datos. Devuelve un resumen."""
        resumen = {'indexados': 0, 'sin_cambios': 0, 'eliminados': 0}
        with self._conn() as c:
            actuales = {r['doc_key']: r['fingerprint'] for r in c.execute(
                'SELECT doc_key, fingerprint FROM documentos')}

        vistos = set()
        for spec in specs:
            vistos.add(spec.key)
            if actuales.get(spec.key) == spec.fingerprint():
                resumen['sin_cambios'] += 1
                continue
            self.indexar(spec)
            resumen['indexados'] += 1

        for doc_key in set(actuales) - vistos:
            self.borrar(doc_key)
            resumen['eliminados'] += 1
        return resumen

    def vaciar(self):
        """Borra el índice completo (para --rebuild)."""
        with self._lock:
            self._coleccion = None
            with self._conn() as c:
                c.execute('DELETE FROM fragmentos')
                c.execute('DELETE FROM documentos')
            if CHROMA_HOST:
                try:
                    import chromadb
                    chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT).delete_collection('fragmentos')
                except Exception:
                    pass
            else:
                shutil.rmtree(os.path.join(self.directorio, 'chroma'), ignore_errors=True)

    # Lectura -----------------------------------------------------------------
    @staticmethod
    def _filtro_sql(user_id, group_ids):
        """Condición de permisos de la sección 5.6 en SQL."""
        sql = "(access = 'publico' OR (access = 'privado' AND owner_id = ?)"
        params = [user_id]
        if group_ids:
            sql += f" OR (access = 'grupo' AND group_id IN ({','.join('?' * len(group_ids))}))"
            params += list(group_ids)
        return sql + ')', params

    @staticmethod
    def _filtro_chroma(user_id, group_ids):
        """La misma condición en el formato de filtros de ChromaDB."""
        condiciones = [
            {'access': 'publico'},
            {'$and': [{'access': 'privado'}, {'owner_id': user_id}]},
        ]
        if group_ids:
            condiciones.append({'$and': [{'access': 'grupo'}, {'group_id': {'$in': list(group_ids)}}]})
        return {'$or': condiciones}

    def contar_accesibles(self, user_id, group_ids):
        filtro, params = self._filtro_sql(user_id, group_ids)
        with self._conn() as c:
            return c.execute(f'SELECT COUNT(*) FROM documentos WHERE {filtro}', params).fetchone()[0]

    def buscar_lexico(self, pregunta, user_id, group_ids, limite=CANDIDATOS):
        consulta = consulta_fts(pregunta)
        if not consulta:
            return []
        filtro, params = self._filtro_sql(user_id, group_ids)
        with self._conn() as c:
            filas = c.execute(
                # bm25(): menor = más relevante. El título pesa el doble.
                f'SELECT chunk_id, body, doc_key, kind, resource_id, page, origin, '
                f'       (SELECT title FROM documentos d WHERE d.doc_key = fragmentos.doc_key) AS doc_title, '
                f'       bm25(fragmentos, 2.0, 1.0) AS rank '
                f'FROM fragmentos WHERE fragmentos MATCH ? AND {filtro} '
                f'ORDER BY rank LIMIT ?',
                [consulta, *params, limite]).fetchall()
        return [{
            'chunk_id': f['chunk_id'], 'text': f['body'], 'doc_key': f['doc_key'],
            'kind': f['kind'], 'resource_id': f['resource_id'], 'title': f['doc_title'] or '',
            'page': f['page'], 'origin': f['origin'],
        } for f in filas]

    def buscar_vectorial(self, pregunta, user_id, group_ids, limite=CANDIDATOS):
        coleccion = self.coleccion()
        if coleccion is None or coleccion.count() == 0:
            return []
        vector = ai_service.embed([pregunta], prefijo=ai_service.PREFIJO_PREGUNTA)[0]
        r = coleccion.query(
            query_embeddings=[vector],
            n_results=limite,
            # El filtro va DENTRO de la consulta: los fragmentos ajenos ni
            # siquiera se recorren en el grafo HNSW (sección 5.6).
            where=self._filtro_chroma(user_id, group_ids),
            include=['documents', 'metadatas', 'distances'],
        )
        resultados = []
        for cid, texto, meta, dist in zip(r['ids'][0], r['documents'][0], r['metadatas'][0], r['distances'][0]):
            resultados.append({
                'chunk_id': cid, 'text': texto, 'doc_key': meta['doc_key'],
                'kind': meta['kind'], 'resource_id': meta['resource_id'], 'title': meta['title'],
                'page': meta.get('page') or 0, 'origin': meta['origin'],
                'similarity': round(1 - dist, 3),   # distancia coseno -> similitud
            })
        return resultados

    def buscar(self, pregunta, user_id, group_ids, top_k=TOP_K):
        """Búsqueda híbrida completa (secciones 5.5 a 5.7).

        Devuelve (fragmentos, info) donde info trae el modo usado y los tiempos.
        """
        info = {'modo': 'hibrido', 'tiempos_ms': {}}

        t0 = time.perf_counter()
        try:
            vectorial = self.buscar_vectorial(pregunta, user_id, group_ids)
        except Exception as exc:
            log.warning('Búsqueda vectorial no disponible: %s', exc)
            vectorial = []
            info['modo'] = 'lexico'
        if self.coleccion() is None:
            info['modo'] = 'lexico'
        t1 = time.perf_counter()
        lexico = self.buscar_lexico(pregunta, user_id, group_ids)
        t2 = time.perf_counter()

        # Fusión por rango recíproco: puntaje = Σ 1 / (k + posición).
        fusion = {}
        for lista, nombre in ((vectorial, 'vectorial'), (lexico, 'bm25')):
            for posicion, frag in enumerate(lista, 1):
                actual = fusion.setdefault(frag['chunk_id'], {**frag, 'rrf': 0.0, 'posiciones': {}})
                actual['rrf'] += 1 / (RRF_K + posicion)
                actual['posiciones'][nombre] = posicion
                if 'similarity' in frag:
                    actual['similarity'] = frag['similarity']

        mejores = sorted(fusion.values(), key=lambda f: f['rrf'], reverse=True)[:top_k]
        maximo = mejores[0]['rrf'] if mejores else 1
        for f in mejores:
            f['score'] = round(f['rrf'] / maximo, 3)

        info['tiempos_ms'] = {
            'vectorial': round((t1 - t0) * 1000, 1),
            'bm25': round((t2 - t1) * 1000, 1),
        }
        info['candidatos'] = {'vectorial': len(vectorial), 'bm25': len(lexico)}
        return mejores, info

    def estadisticas(self):
        with self._conn() as c:
            fila = c.execute('SELECT COUNT(*), COALESCE(SUM(chunks),0), COALESCE(SUM(vectors),0) '
                             'FROM documentos').fetchone()
            estados = {r[0]: r[1] for r in c.execute(
                'SELECT status, COUNT(*) FROM documentos GROUP BY status')}
        return {
            'documentos': fila[0], 'fragmentos': fila[1], 'vectores': fila[2],
            'estados': estados,
            'vectorial': self.coleccion() is not None,
            'error_vectorial': self.error_vectorial,
        }


# --- Instancia global y cola de indexado (etapa 4) ---------------------------
_indice = None
_cola = queue.Queue()
_hilo = None
_hilo_lock = threading.Lock()


def iniciar(directorio):
    """Crea (una vez) el índice en `directorio`."""
    global _indice
    if _indice is None or _indice.directorio != directorio:
        _indice = Indice(directorio)
    return _indice


def indice():
    if _indice is None:
        raise RuntimeError('ai_index.iniciar() no se ha llamado')
    return _indice


def _trabajador():
    while True:
        accion, dato = _cola.get()
        try:
            if accion == 'indexar':
                estado = indice().indexar(dato)
                log.info('Indexado %s (%s)', dato.key, estado)
            elif accion == 'borrar':
                indice().borrar(dato)
                log.info('Eliminado del índice %s', dato)
            elif accion == 'sincronizar':
                resumen = indice().sincronizar(dato())
                log.info('Índice sincronizado: %s', resumen)
        except Exception as exc:
            log.error('Fallo en el indexado (%s): %s', accion, exc)
        finally:
            _cola.task_done()


def _asegurar_trabajador():
    global _hilo
    with _hilo_lock:
        if _hilo is None or not _hilo.is_alive():
            _hilo = threading.Thread(target=_trabajador, name='ai-indexador', daemon=True)
            _hilo.start()


def encolar_indexado(spec):
    """Indexa en segundo plano: la subida del archivo no espera a los vectores."""
    _asegurar_trabajador()
    _cola.put(('indexar', spec))


def encolar_borrado(doc_key):
    _asegurar_trabajador()
    _cola.put(('borrar', doc_key))


def encolar_sincronizacion(obtener_specs):
    """`obtener_specs` es una función: se evalúa dentro del hilo trabajador."""
    _asegurar_trabajador()
    _cola.put(('sincronizar', obtener_specs))


def esperar_cola():
    """Bloquea hasta que no quede trabajo pendiente (útil en pruebas y en la CLI)."""
    _cola.join()


# --- Consola -----------------------------------------------------------------
def _main():
    import argparse
    import json

    parser = argparse.ArgumentParser(description='Índice de búsqueda del asistente de IA.')
    parser.add_argument('--sync', action='store_true', help='Indexa lo nuevo o modificado y quita lo borrado.')
    parser.add_argument('--rebuild', action='store_true', help='Borra el índice y lo rehace completo.')
    parser.add_argument('--stats', action='store_true', help='Muestra un resumen del índice.')
    parser.add_argument('--query', help='Pregunta de prueba.')
    parser.add_argument('--user', type=int, help='ID del usuario que pregunta (para el filtro de permisos).')
    args = parser.parse_args()

    from app import app, ai_doc_specs, ai_user_group_ids, ai_index_dir  # import tardío: evita ciclo

    with app.app_context():
        idx = iniciar(ai_index_dir())

        if args.rebuild:
            idx.vaciar()
            print('Índice vaciado.')
        if args.rebuild or args.sync:
            t = time.perf_counter()
            resumen = idx.sincronizar(list(ai_doc_specs()))
            print(f'Sincronizado en {time.perf_counter() - t:.1f} s: {resumen}')
        if args.stats or not (args.sync or args.rebuild or args.query):
            print(json.dumps(idx.estadisticas(), ensure_ascii=False, indent=2))
        if args.query:
            if args.user is None:
                parser.error('--query necesita --user <id> para aplicar los permisos')
            fragmentos, info = idx.buscar(args.query, args.user, ai_user_group_ids(args.user))
            print(f"Modo: {info['modo']}  Candidatos: {info['candidatos']}  Tiempos: {info['tiempos_ms']} ms")
            for i, f in enumerate(fragmentos, 1):
                pagina = f" p.{f['page']}" if f.get('page') else ''
                print(f"\n{i}. [{f['score']}] {f['title']}{pagina} ({f['origin']}) posiciones={f['posiciones']}")
                print('   ' + snippet(f['text']))


def snippet(texto, longitud=220):
    """Extracto corto de un fragmento para mostrarlo como fuente."""
    texto = re.sub(r'\s+', ' ', texto or '').strip()
    return texto if len(texto) <= longitud else texto[:longitud].rsplit(' ', 1)[0] + '…'


if __name__ == '__main__':
    _main()
