"""Índice de búsqueda del asistente: vectores (ChromaDB/HNSW) + léxico (FTS5/BM25).

    Fragmentación     ~1000 caracteres con 150 de solape, por página.
    Vectores          el modelo de embeddings del router (Gemini u Ollama).
    Búsqueda híbrida  vectorial + BM25 (SQLite FTS5), fusión RRF k=60.
    Permisos          condición sobre metadatos DENTRO de cada búsqueda.
    Catálogo          lista de documentos relevantes (para "¿qué material hay de X?").

El índice se actualiza en segundo plano al subir, editar o borrar un recurso,
y al arrancar se sincroniza con la base de datos. Si no hay modelo de
embeddings o ChromaDB falla, la búsqueda sigue funcionando sólo con BM25.

Cada modelo de embeddings vive en su propia colección de ChromaDB: si se
cambia de Ollama a Gemini, los documentos se vuelven a vectorizar solos.
"""

from __future__ import annotations

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
from typing import Callable, Iterable

from ..config import env_float, env_int
from . import llm
from .extract import extraer_paginas

log = logging.getLogger(__name__)

CHUNK_SIZE = env_int('AI_CHUNK_SIZE', 1000)
CHUNK_OVERLAP = env_int('AI_CHUNK_OVERLAP', 150)
CANDIDATOS = env_int('AI_CANDIDATES', 24)
TOP_K = env_int('AI_TOP_K', 6)
RRF_K = 60
EMBED_BATCH = 32

ACCESO = {'public': 'publico', 'private_note': 'privado', 'private_file': 'privado', 'group': 'grupo'}


def similitud_minima(firma: str) -> float:
    """Umbral de similitud coseno del mejor fragmento para considerar que los
    documentos tratan el tema. Depende del modelo de embeddings: nomic se midió
    con los datos de prueba (>= 0.72 con respuesta, <= 0.68 sin ella)."""
    explicito = os.environ.get('AI_MIN_SIMILARITY')
    if explicito:
        return env_float('AI_MIN_SIMILARITY', 0.6)
    if 'nomic' in firma:
        return 0.70
    return 0.55


@dataclass
class DocSpec:
    """Lo que el índice necesita de un recurso (lo construye hub.ai.specs)."""
    kind: str
    resource_id: int
    title: str
    owner_id: int
    origin: str
    header: str = ''
    group_id: int | None = None
    path: str | None = None
    text: str | None = None

    @property
    def key(self) -> str:
        return f'{self.kind}:{self.resource_id}'

    @property
    def access(self) -> str:
        return ACCESO[self.kind]

    def fingerprint(self, firma_embeddings: str = '') -> str:
        """Cambia si cambia el contenido, los metadatos o el modelo de vectores."""
        partes = [self.title, self.header, str(self.group_id), self.origin, firma_embeddings]
        if self.path:
            try:
                st = os.stat(self.path)
                partes += [self.path, str(st.st_size), str(int(st.st_mtime))]
            except OSError:
                partes.append('sin-archivo')
        if self.text is not None:
            partes.append(self.text)
        return hashlib.sha1('\x1f'.join(partes).encode('utf-8')).hexdigest()


def fragmentar(texto: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Bloques de `size` caracteres con `overlap` de solape, cortando en espacios."""
    texto = re.sub(r'\s+', ' ', texto or '').strip()
    if not texto:
        return []
    fragmentos = []
    inicio = 0
    while inicio < len(texto):
        fin = min(len(texto), inicio + size)
        if fin < len(texto):
            # Se prefiere cortar al final de una frase; si no, en un espacio.
            corte = texto.rfind('. ', inicio + size // 2, fin)
            if corte <= inicio:
                corte = texto.rfind(' ', inicio + size // 2, fin)
            if corte > inicio:
                fin = corte + 1
        fragmentos.append(texto[inicio:fin].strip())
        if fin >= len(texto):
            break
        inicio = max(fin - overlap, inicio + 1)
    return [f for f in fragmentos if f]


_STOPWORDS = {
    'que', 'para', 'por', 'con', 'una', 'uno', 'unos', 'unas', 'los', 'las',
    'del', 'como', 'mas', 'pero', 'sus', 'este', 'esta', 'estos', 'estas',
    'ese', 'esa', 'esos', 'esas', 'hay', 'son', 'sobre', 'entre', 'cual',
    'cuales', 'donde', 'cuando', 'quien', 'tiene', 'tienen', 'tengo', 'puedo',
    'puede', 'algo', 'algun', 'alguna', 'dime', 'explica', 'explicame', 'material',
    'materiales', 'documento', 'documentos', 'archivo', 'archivos', 'informacion',
    'the', 'and', 'for', 'with', 'what', 'busca', 'buscar', 'encuentra', 'quiero',
}


def consulta_fts(pregunta: str) -> str:
    """Pregunta -> consulta FTS5 «término1* OR término2* ...».

    El asterisco busca por prefijo: sustituto barato de la lematización.
    """
    norm = unicodedata.normalize('NFKD', (pregunta or '').lower())
    norm = ''.join(c for c in norm if not unicodedata.combining(c))
    terminos = []
    for t in re.findall(r'[a-z0-9]+', norm):
        if len(t) < 3 or t in _STOPWORDS:
            continue
        if len(t) > 4 and t.endswith('s'):
            t = t[:-1]
        if t not in terminos:
            terminos.append(t)
    return ' OR '.join(f'"{t}"*' for t in terminos[:16])


def snippet(texto: str, longitud: int = 220) -> str:
    texto = re.sub(r'\s+', ' ', texto or '').strip()
    return texto if len(texto) <= longitud else texto[:longitud].rsplit(' ', 1)[0] + '…'


def _nombre_coleccion(firma: str) -> str:
    # La colección original (Ollama + nomic) se llamaba "fragmentos": se conserva.
    if not firma or firma == 'ollama:nomic-embed-text':
        return 'fragmentos'
    return 'fragmentos_' + re.sub(r'[^a-zA-Z0-9]+', '_', firma).strip('_')[:50]


class Indice:
    """ChromaDB (vectores) + SQLite FTS5 (texto) con los mismos fragmentos."""

    def __init__(self, directorio: str):
        self.directorio = directorio
        os.makedirs(directorio, exist_ok=True)
        self.db_path = os.path.join(directorio, 'fts.sqlite3')
        self._lock = threading.RLock()
        self._colecciones: dict[str, object] = {}
        self._cliente = None
        self.error_vectorial: str | None = None
        self._crear_tablas()

    # SQLite ------------------------------------------------------------------
    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _crear_tablas(self) -> None:
        with self._conn() as c:
            c.execute('PRAGMA journal_mode=WAL')
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
            columnas = {r[1] for r in c.execute('PRAGMA table_info(documentos)')}
            for col, tipo in (('header', 'TEXT'), ('summary', 'TEXT')):
                if col not in columnas:
                    c.execute(f'ALTER TABLE documentos ADD COLUMN {col} {tipo}')

    # ChromaDB ----------------------------------------------------------------
    def firma(self) -> str:
        return llm.router().embed_signature()

    def coleccion(self):
        """Colección del modelo de embeddings actual, o None (modo léxico)."""
        firma = self.firma()
        if not firma:
            return None
        if firma in self._colecciones:
            return self._colecciones[firma]
        try:
            import chromadb
            if self._cliente is None:
                host = os.environ.get('CHROMA_HOST', '').strip()
                if host:
                    self._cliente = chromadb.HttpClient(host=host, port=env_int('CHROMA_PORT', 8000))
                else:
                    self._cliente = chromadb.PersistentClient(path=os.path.join(self.directorio, 'chroma'))
            col = self._cliente.get_or_create_collection(
                name=_nombre_coleccion(firma), metadata={'hnsw:space': 'cosine'}, embedding_function=None)
            self._colecciones[firma] = col
            self.error_vectorial = None
            return col
        except Exception as exc:
            self.error_vectorial = f'{exc.__class__.__name__}: {exc}'
            log.warning('ChromaDB no disponible, se usará sólo BM25: %s', self.error_vectorial)
            return None

    # Escritura ---------------------------------------------------------------
    def indexar(self, spec: DocSpec) -> str:
        if spec.text is not None:
            paginas, estado = [(0, spec.text)], 'ok'
        else:
            paginas, estado = extraer_paginas(spec.path)

        trozos: list[tuple[int, str]] = []
        for pagina, texto in paginas:
            trozos += [(pagina, t) for t in fragmentar(texto)]
        # Sin texto legible (imagen, zip, PDF escaneado) se indexa por metadatos.
        if not trozos:
            trozos = [(0, f'{spec.title}. {spec.header}'.strip())]
            if estado == 'ok':
                estado = 'solo_metadatos'

        ids = [f'{spec.key}:{i}' for i in range(len(trozos))]
        group_id = spec.group_id if spec.group_id is not None else -1
        firma = self.firma()
        resumen = snippet(' '.join(t for _, t in trozos[:2]), 400)

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
                        # El título va delante: el vector sabe de qué documento es el fragmento.
                        embeddings = llm.router().embed([f'{spec.title}\n{t}' for _, t in lote])
                        coleccion.add(
                            ids=ids[i:i + EMBED_BATCH],
                            embeddings=embeddings,
                            documents=[t for _, t in lote],
                            metadatas=[{
                                'doc_key': spec.key, 'kind': spec.kind, 'resource_id': spec.resource_id,
                                'title': spec.title, 'access': spec.access, 'owner_id': spec.owner_id,
                                'group_id': group_id, 'page': pagina, 'origin': spec.origin,
                            } for pagina, _ in lote])
                        vectores += len(lote)
                except Exception as exc:
                    log.warning('No se generaron vectores para %s: %s', spec.key, exc)
                    self._borrar_vectores(spec.key)
                    vectores = 0
                    firma = ''  # sin vectores: la próxima sincronización lo reintenta

            with self._conn() as c:
                c.execute(
                    'INSERT OR REPLACE INTO documentos (doc_key, kind, resource_id, title, access, owner_id, '
                    'group_id, origin, fingerprint, chunks, vectors, status, indexed_at, header, summary) '
                    'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (spec.key, spec.kind, spec.resource_id, spec.title, spec.access, spec.owner_id,
                     group_id, spec.origin, spec.fingerprint(firma), len(trozos), vectores, estado,
                     time.time(), spec.header, resumen))
        return estado

    def _borrar_vectores(self, doc_key: str) -> None:
        for col in list(self._colecciones.values()):
            try:
                col.delete(where={'doc_key': doc_key})
            except Exception as exc:
                log.warning('No se pudieron borrar los vectores de %s: %s', doc_key, exc)

    def _borrar(self, doc_key: str) -> None:
        with self._conn() as c:
            c.execute('DELETE FROM fragmentos WHERE doc_key = ?', (doc_key,))
            c.execute('DELETE FROM documentos WHERE doc_key = ?', (doc_key,))
        self.coleccion()
        self._borrar_vectores(doc_key)

    def borrar(self, doc_key: str) -> None:
        with self._lock:
            self._borrar(doc_key)

    def sincronizar(self, specs: Iterable[DocSpec]) -> dict:
        resumen = {'indexados': 0, 'sin_cambios': 0, 'eliminados': 0}
        firma = self.firma() if self.coleccion() is not None else ''
        with self._conn() as c:
            actuales = {r['doc_key']: r['fingerprint'] for r in c.execute('SELECT doc_key, fingerprint FROM documentos')}
        vistos = set()
        for spec in specs:
            vistos.add(spec.key)
            if actuales.get(spec.key) == spec.fingerprint(firma):
                resumen['sin_cambios'] += 1
                continue
            self.indexar(spec)
            resumen['indexados'] += 1
        for doc_key in set(actuales) - vistos:
            self.borrar(doc_key)
            resumen['eliminados'] += 1
        return resumen

    def vaciar(self) -> None:
        with self._lock:
            self._colecciones.clear()
            self._cliente = None
            with self._conn() as c:
                c.execute('DELETE FROM fragmentos')
                c.execute('DELETE FROM documentos')
            shutil.rmtree(os.path.join(self.directorio, 'chroma'), ignore_errors=True)

    # Lectura -----------------------------------------------------------------
    @staticmethod
    def _filtro_sql(user_id: int, group_ids: list[int], doc_key: str | None = None) -> tuple[str, list]:
        sql = "(access = 'publico' OR (access = 'privado' AND owner_id = ?)"
        params: list = [user_id]
        if group_ids:
            sql += f" OR (access = 'grupo' AND group_id IN ({','.join('?' * len(group_ids))}))"
            params += list(group_ids)
        sql += ')'
        if doc_key:
            sql += ' AND doc_key = ?'
            params.append(doc_key)
        return sql, params

    @staticmethod
    def _filtro_chroma(user_id: int, group_ids: list[int], doc_key: str | None = None) -> dict:
        condiciones = [
            {'access': 'publico'},
            {'$and': [{'access': 'privado'}, {'owner_id': user_id}]},
        ]
        if group_ids:
            condiciones.append({'$and': [{'access': 'grupo'}, {'group_id': {'$in': list(group_ids)}}]})
        filtro = {'$or': condiciones}
        if doc_key:
            filtro = {'$and': [filtro, {'doc_key': doc_key}]}
        return filtro

    def contar_accesibles(self, user_id: int, group_ids: list[int]) -> int:
        filtro, params = self._filtro_sql(user_id, group_ids)
        with self._conn() as c:
            return c.execute(f'SELECT COUNT(*) FROM documentos WHERE {filtro}', params).fetchone()[0]

    def documento(self, doc_key: str) -> dict | None:
        with self._conn() as c:
            fila = c.execute('SELECT * FROM documentos WHERE doc_key = ?', (doc_key,)).fetchone()
        return dict(fila) if fila else None

    def buscar_lexico(self, pregunta: str, user_id: int, group_ids: list[int], limite: int = CANDIDATOS,
                      doc_key: str | None = None) -> list[dict]:
        consulta = consulta_fts(pregunta)
        if not consulta:
            return []
        filtro, params = self._filtro_sql(user_id, group_ids, doc_key)
        with self._conn() as c:
            try:
                filas = c.execute(
                    f'SELECT chunk_id, body, doc_key, kind, resource_id, page, origin, '
                    f'       (SELECT title FROM documentos d WHERE d.doc_key = fragmentos.doc_key) AS doc_title, '
                    f'       bm25(fragmentos, 2.0, 1.0) AS rank '
                    f'FROM fragmentos WHERE fragmentos MATCH ? AND {filtro} ORDER BY rank LIMIT ?',
                    [consulta, *params, limite]).fetchall()
            except sqlite3.OperationalError as exc:
                log.warning('Consulta FTS no válida (%s): %s', consulta, exc)
                return []
        return [{
            'chunk_id': f['chunk_id'], 'text': f['body'], 'doc_key': f['doc_key'], 'kind': f['kind'],
            'resource_id': f['resource_id'], 'title': f['doc_title'] or '', 'page': f['page'],
            'origin': f['origin'], 'bm25': f['rank'],
        } for f in filas]

    def buscar_vectorial(self, pregunta: str, user_id: int, group_ids: list[int], limite: int = CANDIDATOS,
                         doc_key: str | None = None) -> list[dict]:
        coleccion = self.coleccion()
        if coleccion is None or coleccion.count() == 0:
            return []
        vector = llm.router().embed([pregunta], query=True)[0]
        r = coleccion.query(query_embeddings=[vector], n_results=min(limite, coleccion.count()),
                            where=self._filtro_chroma(user_id, group_ids, doc_key),
                            include=['documents', 'metadatas', 'distances'])
        resultados = []
        for cid, texto, meta, dist in zip(r['ids'][0], r['documents'][0], r['metadatas'][0], r['distances'][0]):
            resultados.append({
                'chunk_id': cid, 'text': texto, 'doc_key': meta['doc_key'], 'kind': meta['kind'],
                'resource_id': meta['resource_id'], 'title': meta['title'], 'page': meta.get('page') or 0,
                'origin': meta['origin'], 'similarity': round(1 - dist, 3),
            })
        return resultados

    def buscar(self, pregunta: str, user_id: int, group_ids: list[int], top_k: int = TOP_K,
               doc_key: str | None = None) -> tuple[list[dict], dict]:
        """Búsqueda híbrida. Devuelve (fragmentos, info con modo y tiempos)."""
        info: dict = {'modo': 'hibrido', 'tiempos_ms': {}}
        t0 = time.perf_counter()
        try:
            vectorial = self.buscar_vectorial(pregunta, user_id, group_ids, doc_key=doc_key)
        except Exception as exc:
            log.warning('Búsqueda vectorial no disponible: %s', exc)
            vectorial = []
            info['modo'] = 'lexico'
        if self.coleccion() is None:
            info['modo'] = 'lexico'
        t1 = time.perf_counter()
        lexico = self.buscar_lexico(pregunta, user_id, group_ids, doc_key=doc_key)
        t2 = time.perf_counter()

        fusion: dict[str, dict] = {}
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

        info['tiempos_ms'] = {'vectorial': round((t1 - t0) * 1000, 1), 'bm25': round((t2 - t1) * 1000, 1)}
        info['candidatos'] = {'vectorial': len(vectorial), 'bm25': len(lexico)}

        # La búsqueda vectorial siempre devuelve "los más parecidos" aunque no
        # tengan nada que ver. Si ni el mejor llega al umbral no hay material del
        # tema (salvo que se pregunte por un documento concreto).
        if vectorial and not doc_key:
            mejor = max(f['similarity'] for f in vectorial)
            info['similitud_maxima'] = mejor
            if mejor < similitud_minima(self.firma()):
                return [], info
        return mejores, info

    def buscar_documentos(self, pregunta: str, user_id: int, group_ids: list[int], limite: int = 8,
                          extra: list[dict] | None = None) -> list[dict]:
        """Documentos (no fragmentos) relacionados con la pregunta, para el catálogo."""
        puntaje: dict[str, float] = {}
        for posicion, frag in enumerate(extra or [], 1):
            puntaje[frag['doc_key']] = puntaje.get(frag['doc_key'], 0) + 1 / (RRF_K + posicion)
        for posicion, frag in enumerate(self.buscar_lexico(pregunta, user_id, group_ids, limite=60), 1):
            puntaje[frag['doc_key']] = puntaje.get(frag['doc_key'], 0) + 1 / (RRF_K + posicion)
        claves = sorted(puntaje, key=puntaje.get, reverse=True)[:limite]
        if not claves:
            return []
        with self._conn() as c:
            filas = {r['doc_key']: dict(r) for r in c.execute(
                f'SELECT doc_key, kind, resource_id, title, origin, header, summary FROM documentos '
                f'WHERE doc_key IN ({",".join("?" * len(claves))})', claves)}
        return [filas[k] for k in claves if k in filas]

    def estadisticas(self) -> dict:
        with self._conn() as c:
            fila = c.execute('SELECT COUNT(*), COALESCE(SUM(chunks),0), COALESCE(SUM(vectors),0) '
                             'FROM documentos').fetchone()
            estados = {r[0]: r[1] for r in c.execute('SELECT status, COUNT(*) FROM documentos GROUP BY status')}
        return {
            'documentos': fila[0], 'fragmentos': fila[1], 'vectores': fila[2], 'estados': estados,
            'embeddings': self.firma() or None, 'vectorial': self.coleccion() is not None,
            'error_vectorial': self.error_vectorial,
        }


# --- Instancia global y cola de indexado --------------------------------------
_indice: Indice | None = None
_cola: queue.Queue = queue.Queue()
_hilo: threading.Thread | None = None
_hilo_lock = threading.Lock()
_sincrono = False


def iniciar(directorio: str, *, sincrono: bool = False) -> Indice:
    """Crea (una vez) el índice. `sincrono` ejecuta el trabajo en el mismo hilo (pruebas)."""
    global _indice, _sincrono
    _sincrono = sincrono
    if _indice is None or _indice.directorio != directorio:
        _indice = Indice(directorio)
    return _indice


def indice() -> Indice:
    if _indice is None:
        raise RuntimeError('hub.ai.index.iniciar() no se ha llamado')
    return _indice


def _procesar(accion: str, dato) -> None:
    if accion == 'indexar':
        estado = indice().indexar(dato)
        log.info('Indexado %s (%s)', dato.key, estado)
    elif accion == 'borrar':
        indice().borrar(dato)
    elif accion == 'sincronizar':
        log.info('Índice sincronizado: %s', indice().sincronizar(dato()))


def _trabajador() -> None:
    while True:
        accion, dato = _cola.get()
        try:
            _procesar(accion, dato)
        except Exception as exc:
            log.error('Fallo en el indexado (%s): %s', accion, exc)
        finally:
            _cola.task_done()


def _encolar(accion: str, dato) -> None:
    global _hilo
    if _sincrono:
        try:
            _procesar(accion, dato)
        except Exception as exc:
            log.error('Fallo en el indexado (%s): %s', accion, exc)
        return
    with _hilo_lock:
        if _hilo is None or not _hilo.is_alive():
            _hilo = threading.Thread(target=_trabajador, name='ai-indexador', daemon=True)
            _hilo.start()
    _cola.put((accion, dato))


def encolar_indexado(spec: DocSpec) -> None:
    _encolar('indexar', spec)


def encolar_borrado(doc_key: str) -> None:
    _encolar('borrar', doc_key)


def encolar_sincronizacion(obtener_specs: Callable[[], list[DocSpec]]) -> None:
    _encolar('sincronizar', obtener_specs)


def esperar_cola() -> None:
    _cola.join()
