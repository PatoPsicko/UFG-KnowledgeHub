"""IA simulada para pruebas de carga (AI_SIMULATED=1 en el entorno).

Usa el router de verdad (orden de modelos, cupos, enfriamiento, cola y
conmutación) y sólo sustituye la llamada HTTP: cada modelo simulado imita la
cuenta gratuita de Groq con su cubeta de tokens por minuto y de peticiones por
día, devuelve las mismas cabeceras x-ratelimit-* y responde 429 cuando se
agota. La latencia también se imita (primer trozo en ~1 s y ~150 tokens/s),
así la prueba mide el sistema completo sin gastar cuota ni depender de la red.

Variables opcionales:
    AI_SIM_TPM=8000         tokens por minuto de cada modelo simulado
    AI_SIM_RPD=1000         peticiones por día de cada modelo simulado
    AI_SIM_LATENCY=1.0      segundos hasta el primer trozo de la respuesta
"""

from __future__ import annotations

import io
import json
import random
import threading
import time

from ..config import env_float, env_int, env_list
from . import llm

RESPUESTA_RAG = ('📚 Según el material, la normalización organiza las tablas para evitar datos repetidos [1]. '
                 'La tercera forma normal elimina las dependencias transitivas entre columnas [2]. '
                 'Te recomiendo repasar los ejemplos del documento y practicar con un caso propio. 🧠')
RESPUESTA_GENERAL = ('📚 No encontré esto en los documentos de la plataforma, así que te lo explico con '
                     'conocimiento general: una derivada mide cómo cambia una función cuando cambia su variable.')


class _Cubeta:
    """Cubeta de tokens que se rellena de forma continua (como la de Groq)."""

    def __init__(self, tpm: int, rpd: int):
        self.tpm, self.rpd = tpm, rpd
        self.tokens, self.peticiones = float(tpm), float(rpd)
        self.t = time.monotonic()
        self.lock = threading.Lock()

    def _rellenar(self, ahora: float) -> None:
        self.tokens = min(self.tpm, self.tokens + (ahora - self.t) * self.tpm / 60)
        self.peticiones = min(self.rpd, self.peticiones + (ahora - self.t) * self.rpd / 86400)
        self.t = ahora

    def gastar(self, n: int) -> tuple[bool, float, dict]:
        with self.lock:
            ahora = time.monotonic()
            self._rellenar(ahora)
            if self.peticiones < 1 or self.tokens < n:
                falta = max(0.0, (min(n, self.tpm) - self.tokens) * 60 / self.tpm)
                return False, max(falta, 1.0), self._cabeceras()
            self.tokens -= n
            self.peticiones -= 1
            return True, 0.0, self._cabeceras()

    def _cabeceras(self) -> dict:
        lleno = (self.tpm - self.tokens) * 60 / self.tpm
        return {'x-ratelimit-limit-tokens': str(self.tpm), 'x-ratelimit-remaining-tokens': str(int(self.tokens)),
                'x-ratelimit-reset-tokens': f'{lleno:.2f}s', 'x-ratelimit-limit-requests': str(self.rpd),
                'x-ratelimit-remaining-requests': str(int(self.peticiones)),
                'x-ratelimit-reset-requests': f'{86400 / self.rpd:.1f}s'}


class _Respuesta(io.BytesIO):
    """Lo justo de http.client.HTTPResponse: read(), iteración por líneas y headers."""

    def __init__(self, cuerpo: bytes, headers: dict, pausa_linea: float = 0.0):
        super().__init__(cuerpo)
        self.headers = headers
        self.pausa_linea = pausa_linea

    def __iter__(self):
        for linea in self.getvalue().splitlines(keepends=True):
            if self.pausa_linea:
                time.sleep(self.pausa_linea)
            yield linea

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class SimulatedRouter(llm.Router):
    """Router con proveedores «groq» simulados: mismos modelos que .env, sin red."""

    def __init__(self):
        chat = env_list('GROQ_CHAT_MODELS', 'openai/gpt-oss-120b,qwen/qwen3.8-27b')
        seguridad = env_list('GROQ_SECURITY_MODELS', 'openai/gpt-oss-120b,openai/gpt-oss-20b')
        proveedor = llm.Provider(name='groq', label='Groq (simulado)', base_url='http://simulado', api_key='simulada',
                                 chat_models=chat, security_models=seguridad)
        super().__init__(providers={'groq': proveedor}, chat_order=['groq'], security_order=['groq'],
                         embed_provider='none')
        tpm, rpd = env_int('AI_SIM_TPM', 8000), env_int('AI_SIM_RPD', 1000)
        self._cubetas = {m: _Cubeta(tpm, rpd) for m in dict.fromkeys(chat + seguridad)}
        self.latencia = env_float('AI_SIM_LATENCY', 1.0)

    def prompt_injection_score(self, text: str) -> float | None:
        return 0.01

    def _request(self, provider, path, payload, *, stream=False):
        modelo = payload.get('model')
        cubeta = self._cubetas.get(modelo)
        if cubeta is None:
            raise llm._ProviderError(f'modelo {modelo} no existe', status=404)
        tokens = self.estimate_tokens(payload.get('messages') or [], payload.get('max_tokens'))
        ok, espera, cabeceras = cubeta.gastar(tokens)
        if not ok:
            raise llm._ProviderError(f'groq (simulado) respondió 429: límite de tokens por minuto de {modelo}',
                                     retry_after=espera, status=429)
        time.sleep(self.latencia * random.uniform(0.6, 1.4))
        contenido = str((payload.get('messages') or [{}])[-1].get('content', ''))
        if payload.get('response_format'):
            texto = json.dumps({'verdict': 'ok', 'categories': [], 'reason': 'Material académico (simulado).'})
        elif 'EXTRACTOS:' in contenido and '[1]' in contenido:
            texto = RESPUESTA_RAG
        else:
            texto = RESPUESTA_GENERAL
        if not stream:
            return _Respuesta(json.dumps({'choices': [{'message': {'content': texto}}]}).encode(), cabeceras)
        palabras = texto.split(' ')
        lineas = [f'data: {json.dumps({"choices": [{"delta": {"content": p + " "}}]})}\n' for p in palabras]
        lineas.append('data: [DONE]\n')
        # ~150 tokens/s: unas 0,02 s por palabra.
        return _Respuesta(''.join(lineas).encode(), cabeceras, pausa_linea=0.02)
