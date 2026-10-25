"""Router de modelos de lenguaje: Gemini, Groq, OpenRouter y Ollama.

Los cuatro proveedores exponen la misma API "compatible con OpenAI"
(/chat/completions y /embeddings), así que un único cliente basta. El router
prueba los proveedores en el orden configurado y, si uno responde 429 (cuota
gratuita agotada), 5xx o no contesta, lo deja "en enfriamiento" un rato y pasa
al siguiente. Así el asistente sigue funcionando aunque una capa gratuita se
quede sin cuota a media clase.

Configuración (.env):

    AI_PROVIDERS=gemini,groq,ollama            orden para el asistente
    SECURITY_AI_PROVIDERS=groq,gemini          orden para el vigilante de archivos
    GEMINI_API_KEY=...   GEMINI_CHAT_MODELS=gemini-3.6-flash,gemini-3.5-flash-lite
    GROQ_API_KEY=...     GROQ_CHAT_MODELS=openai/gpt-oss-120b,qwen/qwen3.8-27b
    OLLAMA_URL=http://127.0.0.1:11434   OLLAMA_MODEL=llama3.1:8b

Cuotas gratuitas (lo que más limita con 20 personas a la vez). Groq informa
en cada respuesta cuántos tokens le quedan al modelo en el minuto y cuántas
peticiones en el día (cabeceras x-ratelimit-*). El router las guarda por
modelo y, antes de enviar una pregunta, calcula si cabe: si no cabe en ningún
modelo, avisa cuánto falta (wait_time) para que la pregunta espere en cola en
lugar de chocar con un error 429. Con la cuenta gratuita de Groq (octubre de
2026) cada modelo gpt-oss admite 8.000 tokens por minuto y 1.000 peticiones al
día; una pregunta con extractos usa entre 2.500 y 4.500 tokens.

Sólo se usa la biblioteca estándar (urllib) para no añadir dependencias.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Iterator

from ..config import env_float, env_int, env_list, env_str

log = logging.getLogger(__name__)


class LLMError(Exception):
    """Ningún proveedor pudo responder."""


class CapacityError(LLMError):
    """Los modelos están bien pero sin cupo ahora mismo (cuota por minuto o por día).

    `retry_after` = segundos estimados hasta que alguno vuelva a tener cupo
    (None si no se sabe). Quien llama puede esperar y reintentar.
    """

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


_RE_DURACION = re.compile(r'(\d+(?:\.\d+)?)(ms|h|m|s)')


def _parse_duration(texto: str | None) -> float | None:
    """'607ms' -> 0.607, '1m26.4s' -> 86.4, '2h3m' -> 7380 (formato de Groq)."""
    if not texto:
        return None
    total, encontrado = 0.0, False
    for valor, unidad in _RE_DURACION.findall(texto):
        encontrado = True
        total += float(valor) * {'ms': 0.001, 's': 1, 'm': 60, 'h': 3600}[unidad]
    if encontrado:
        return total
    try:
        return float(texto)
    except ValueError:
        return None


@dataclass
class _Cupo:
    """Lo que sabemos de la cuota de un modelo según las cabeceras de su última respuesta.

    Groq usa «cubetas» que se rellenan de forma continua: los tokens por minuto
    se recuperan a razón de límite/60 por segundo.
    """
    limit_tokens: int | None = None
    tokens: float | None = None      # tokens restantes cuando se vio la cabecera
    visto: float = 0.0               # time.monotonic() de esa lectura
    lleno_en: float = 0.0            # cuándo vuelve a estar llena la cubeta de tokens
    limit_requests: int | None = None
    requests: int | None = None      # peticiones que quedan en el día
    request_en: float = 0.0          # cuándo se recupera la siguiente petición

    def tokens_now(self, ahora: float) -> float | None:
        if self.tokens is None:
            return None
        if ahora >= self.lleno_en:
            return float(self.limit_tokens or self.tokens)
        if self.limit_tokens:
            return min(float(self.limit_tokens), self.tokens + (ahora - self.visto) * self.limit_tokens / 60)
        return self.tokens

    def wait_for(self, need: float, ahora: float) -> float:
        """Segundos hasta que quepa una petición de `need` tokens (0 = ya cabe)."""
        espera = 0.0
        if self.requests is not None and self.requests <= 0 and ahora < self.request_en:
            espera = self.request_en - ahora
        disponibles = self.tokens_now(ahora)
        if disponibles is not None:
            if self.limit_tokens:
                need = min(need, self.limit_tokens)  # una petición enorme se intenta con la cubeta llena
            if disponibles < need:
                ritmo = (self.limit_tokens or 0) / 60
                faltan = (need - disponibles) / ritmo if ritmo else max(0.0, self.lleno_en - ahora)
                espera = max(espera, min(faltan, max(0.0, self.lleno_en - ahora)) if self.lleno_en > ahora
                             else faltan)
        return max(0.0, espera)

    def consume(self, need: float, ahora: float) -> None:
        disponibles = self.tokens_now(ahora)
        if disponibles is not None:
            self.tokens, self.visto = max(0.0, disponibles - need), ahora
        if self.requests is not None:
            self.requests = max(0, self.requests - 1)


class _ProviderError(Exception):
    def __init__(self, message: str, *, retry_after: float | None = None, fatal: bool = False,
                 status: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after
        self.fatal = fatal  # credenciales inválidas: no reintentar en esta sesión
        self.status = status


@dataclass
class Provider:
    name: str
    label: str
    base_url: str
    api_key: str = ''
    chat_models: list[str] = field(default_factory=list)
    security_models: list[str] = field(default_factory=list)
    embed_model: str = ''
    prompt_guard_model: str = ''
    timeout: int = 60
    local: bool = False

    @property
    def configured(self) -> bool:
        return bool(self.base_url) and (self.local or bool(self.api_key))


def _load_providers() -> dict[str, Provider]:
    timeout = env_int('AI_TIMEOUT', 60)
    ollama_url = env_str('OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/')
    return {
        'gemini': Provider(
            name='gemini', label='Google Gemini',
            base_url='https://generativelanguage.googleapis.com/v1beta/openai',
            api_key=env_str('GEMINI_API_KEY'),
            chat_models=env_list('GEMINI_CHAT_MODELS', 'gemini-3.6-flash,gemini-3.5-flash-lite'),
            security_models=env_list('GEMINI_SECURITY_MODELS', 'gemini-3.5-flash-lite'),
            embed_model=env_str('GEMINI_EMBED_MODEL', 'gemini-embedding-001'),
            timeout=timeout,
        ),
        'groq': Provider(
            name='groq', label='Groq',
            base_url='https://api.groq.com/openai/v1',
            api_key=env_str('GROQ_API_KEY'),
            chat_models=env_list('GROQ_CHAT_MODELS', 'openai/gpt-oss-120b,qwen/qwen3.8-27b,openai/gpt-oss-20b'),
            security_models=env_list('GROQ_SECURITY_MODELS', 'openai/gpt-oss-120b,openai/gpt-oss-20b'),
            prompt_guard_model=env_str('GROQ_PROMPT_GUARD_MODEL', 'meta-llama/llama-prompt-guard-2-86m'),
            timeout=timeout,
        ),
        'openrouter': Provider(
            name='openrouter', label='OpenRouter',
            base_url='https://openrouter.ai/api/v1',
            api_key=env_str('OPENROUTER_API_KEY'),
            chat_models=env_list('OPENROUTER_CHAT_MODELS'),
            security_models=env_list('OPENROUTER_SECURITY_MODELS'),
            timeout=timeout,
        ),
        'ollama': Provider(
            name='ollama', label='Ollama (local)',
            base_url=f'{ollama_url}/v1' if ollama_url else '',
            chat_models=env_list('OLLAMA_MODEL', 'llama3.1:8b'),
            security_models=env_list('OLLAMA_SECURITY_MODEL') or env_list('OLLAMA_MODEL', 'llama3.1:8b'),
            embed_model=env_str('OLLAMA_EMBED_MODEL', 'nomic-embed-text'),
            # Sin GPU, un modelo de 8B tarda bastante más que la nube.
            timeout=env_int('OLLAMA_TIMEOUT', 300),
            local=True,
        ),
    }


@dataclass
class ChatResult:
    text: str
    provider: str
    model: str


class Router:
    """Elige proveedor/modelo, aplica enfriamiento y conmuta ante fallos."""

    def __init__(self, providers: dict[str, Provider] | None = None,
                 chat_order: list[str] | None = None, security_order: list[str] | None = None,
                 embed_provider: str | None = None):
        self.providers = providers or _load_providers()
        self.chat_order = chat_order or env_list('AI_PROVIDERS', 'gemini,groq,openrouter,ollama')
        self.security_order = security_order or env_list('SECURITY_AI_PROVIDERS', 'groq,gemini,openrouter,ollama')
        self._embed_choice = embed_provider if embed_provider is not None else env_str('AI_EMBED_PROVIDER', 'auto')
        self.cooldown_default = env_float('AI_COOLDOWN_SECONDS', 60)
        # Tokens por minuto que el vigilante deja libres para el asistente cuando
        # comparten modelo: las preguntas de los estudiantes tienen prioridad.
        self.security_reserve = env_int('AI_SECURITY_RESERVE_TOKENS', 3000)
        self._cupos: dict[str, _Cupo] = {}
        self._cooldown: dict[str, float] = {}
        self._disabled: dict[str, str] = {}
        self._ollama_ok: tuple[float, bool] | None = None
        self._lock = threading.Lock()

    # --- Estado -------------------------------------------------------------
    def _key(self, provider: str, model: str) -> str:
        return f'{provider}/{model}'

    def _available(self, provider: Provider, model: str) -> bool:
        if not provider.configured or provider.name in self._disabled:
            return False
        if provider.local and not self._ollama_alive(provider):
            return False
        with self._lock:
            hasta = self._cooldown.get(self._key(provider.name, model), 0)
        return time.monotonic() >= hasta

    def _ollama_alive(self, provider: Provider) -> bool:
        """Ollama local: se comprueba con /api/tags como mucho cada 30 s."""
        ahora = time.monotonic()
        if self._ollama_ok and ahora - self._ollama_ok[0] < 30:
            return self._ollama_ok[1]
        url = provider.base_url[:-3] + '/api/tags' if provider.base_url.endswith('/v1') else provider.base_url
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                ok = resp.status == 200
        except Exception:
            ok = False
        self._ollama_ok = (ahora, ok)
        return ok

    # --- Cuotas -------------------------------------------------------------
    @staticmethod
    def estimate_tokens(messages: list[dict], max_tokens: int | None = None) -> int:
        """Estimación barata: ~3,5 caracteres por token en español, más la respuesta."""
        texto = sum(len(m['content']) if isinstance(m.get('content'), str) else 1200 for m in messages)
        return int(texto / 3.5) + 40 * len(messages) + (max_tokens or 1024)

    def _need(self, provider: Provider, model: str, need: int, purpose: str) -> int:
        if purpose == 'chat' or model not in provider.chat_models:
            return need
        return need + self.security_reserve

    def _wait(self, provider: Provider, model: str, need: int) -> float:
        """Segundos hasta que el modelo pueda atender `need` tokens (enfriamiento incluido)."""
        ahora = time.monotonic()
        with self._lock:
            espera = max(0.0, self._cooldown.get(self._key(provider.name, model), 0) - ahora)
            cupo = self._cupos.get(self._key(provider.name, model))
            if cupo:
                espera = max(espera, cupo.wait_for(need, ahora))
        return espera

    def _take(self, provider: Provider, model: str, need: int) -> bool:
        """Reserva el cupo de una petición si cabe (atómico entre hilos)."""
        ahora = time.monotonic()
        with self._lock:
            cupo = self._cupos.get(self._key(provider.name, model))
            if cupo is None:
                return True
            if cupo.wait_for(need, ahora) > 0:
                return False
            cupo.consume(need, ahora)
            return True

    def _update_quota(self, provider: Provider, model: str, headers) -> None:
        """Guarda las cabeceras x-ratelimit-* de la respuesta (Groq, OpenRouter)."""
        if not headers or not hasattr(headers, 'get'):
            return
        restantes = headers.get('x-ratelimit-remaining-tokens')
        peticiones = headers.get('x-ratelimit-remaining-requests')
        if restantes is None and peticiones is None:
            return
        ahora = time.monotonic()

        def numero(nombre):
            try:
                return int(float(headers.get(nombre)))
            except (TypeError, ValueError):
                return None

        with self._lock:
            cupo = self._cupos.setdefault(self._key(provider.name, model), _Cupo())
            cupo.limit_tokens = numero('x-ratelimit-limit-tokens') or cupo.limit_tokens
            cupo.limit_requests = numero('x-ratelimit-limit-requests') or cupo.limit_requests
            if restantes is not None:
                cupo.tokens, cupo.visto = numero('x-ratelimit-remaining-tokens'), ahora
                cupo.lleno_en = ahora + (_parse_duration(headers.get('x-ratelimit-reset-tokens')) or 0)
            if peticiones is not None:
                cupo.requests = numero('x-ratelimit-remaining-requests')
                cupo.request_en = ahora + (_parse_duration(headers.get('x-ratelimit-reset-requests')) or 0)

    def wait_time(self, purpose: str = 'chat', need: int = 0) -> float | None:
        """Segundos hasta que algún modelo del propósito tenga cupo (0 = ya). None = no hay modelos."""
        orden = self.chat_order if purpose == 'chat' else self.security_order
        esperas = []
        for nombre in orden:
            prov = self.providers.get(nombre)
            if not prov or not prov.configured or prov.name in self._disabled:
                continue
            if purpose == 'vision' and nombre not in self.VISION_PROVIDERS:
                continue
            if prov.local and not self._ollama_alive(prov):
                continue
            for modelo in (prov.chat_models if purpose == 'chat' else prov.security_models):
                esperas.append(self._wait(prov, modelo, self._need(prov, modelo, need, purpose)))
        return min(esperas) if esperas else None

    def quotas(self) -> list[dict]:
        """Cuota conocida de cada modelo (para el panel de Seguridad)."""
        ahora = time.monotonic()
        filas = []
        with self._lock:
            for clave, cupo in sorted(self._cupos.items()):
                disponibles = cupo.tokens_now(ahora)
                filas.append({'model': clave, 'tokens_limit': cupo.limit_tokens,
                              'tokens_remaining': int(disponibles) if disponibles is not None else None,
                              'requests_limit': cupo.limit_requests, 'requests_remaining': cupo.requests,
                              'cooldown_seconds': max(0, round(self._cooldown.get(clave, 0) - ahora))})
        return filas

    def _cool(self, provider: str, model: str, seconds: float | None) -> None:
        espera = seconds if seconds and seconds > 0 else self.cooldown_default
        with self._lock:
            self._cooldown[self._key(provider, model)] = time.monotonic() + min(espera, 600)
        log.warning('IA: %s/%s en enfriamiento %.0f s', provider, model, espera)

    # Proveedores cuyos modelos de seguridad aceptan imágenes.
    VISION_PROVIDERS = ('gemini', 'openrouter')

    def candidates(self, purpose: str = 'chat') -> list[tuple[Provider, str]]:
        """purpose: chat | security | vision (revisión de imágenes)."""
        orden = self.chat_order if purpose == 'chat' else self.security_order
        lista = []
        for nombre in orden:
            prov = self.providers.get(nombre)
            if not prov or (purpose == 'vision' and nombre not in self.VISION_PROVIDERS):
                continue
            modelos = prov.chat_models if purpose == 'chat' else prov.security_models
            for modelo in modelos:
                if self._available(prov, modelo):
                    lista.append((prov, modelo))
        return lista

    def status(self) -> dict:
        """Resumen para /api/ai/status y el panel de administración."""
        proveedores = []
        for nombre in dict.fromkeys(self.chat_order + self.security_order):
            prov = self.providers.get(nombre)
            if not prov:
                continue
            proveedores.append({
                'name': prov.name,
                'label': prov.label,
                'configured': prov.configured,
                'disabled': self._disabled.get(prov.name),
                'chat_models': prov.chat_models,
                'available_models': [m for m in prov.chat_models if self._available(prov, m)]
                if prov.configured else [],
            })
        chat = self.candidates('chat')
        seguridad = self.candidates('security')
        emb = self.embed_provider()
        return {
            'available': bool(chat),
            'primary': {'provider': chat[0][0].name, 'model': chat[0][1], 'label': chat[0][0].label}
            if chat else None,
            'security': {'provider': seguridad[0][0].name, 'model': seguridad[0][1]} if seguridad else None,
            'embeddings': {'provider': emb.name, 'model': emb.embed_model} if emb else None,
            'providers': proveedores,
            'quotas': self.quotas(),
        }

    # --- HTTP ---------------------------------------------------------------
    def _request(self, provider: Provider, path: str, payload: dict, *, stream: bool = False):
        # Sin User-Agent propio, Cloudflare (delante de Groq) rechaza a urllib con error 1010.
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json',
                   'User-Agent': 'UFG-KnowledgeHub/1.0 (+https://github.com/PatoPsicko/UFG-KnowledgeHub)'}
        if provider.api_key:
            headers['Authorization'] = f'Bearer {provider.api_key}'
        if provider.name == 'openrouter':
            headers['X-Title'] = 'UFG Knowledge Hub'
        req = urllib.request.Request(provider.base_url + path, data=json.dumps(payload).encode('utf-8'),
                                     headers=headers, method='POST')
        try:
            return urllib.request.urlopen(req, timeout=provider.timeout)
        except urllib.error.HTTPError as exc:
            cuerpo = exc.read().decode('utf-8', 'replace')[:400]
            retry = exc.headers.get('Retry-After') if exc.headers else None
            try:
                retry_s = float(retry) if retry else None
            except ValueError:
                retry_s = None
            fatal = exc.code in (401, 403)
            raise _ProviderError(f'{provider.name} respondió {exc.code}: {cuerpo}', retry_after=retry_s,
                                 fatal=fatal, status=exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise _ProviderError(f'No se pudo contactar con {provider.name}: {exc}') from exc

    @staticmethod
    def _chat_payload(model: str, messages: list[dict], *, temperature: float, max_tokens: int | None,
                      stream: bool, json_mode: bool) -> dict:
        payload = {'model': model, 'messages': messages, 'temperature': temperature, 'stream': stream}
        if max_tokens:
            payload['max_tokens'] = max_tokens
        if json_mode:
            payload['response_format'] = {'type': 'json_object'}
        # gpt-oss en Groq razona antes de responder; "low" basta para estas tareas
        # y responde varias veces más rápido.
        if model.startswith('openai/gpt-oss'):
            payload['reasoning_effort'] = 'low'
        elif model.startswith('qwen/qwen3'):
            # Qwen 3 en Groq: sin «pensamiento» visible (<think>...) y más rápido.
            payload['reasoning_effort'] = 'none'
        return payload

    def _handle_failure(self, provider: Provider, model: str, exc: _ProviderError) -> None:
        if exc.fatal:
            self._disabled[provider.name] = 'Clave de API rechazada'
            log.error('IA: %s desactivado (clave inválida o sin permiso): %s', provider.name, exc)
        elif exc.status == 400 or exc.status == 404:
            # Modelo inexistente o parámetro no admitido: se aparta un buen rato.
            self._cool(provider.name, model, 600)
        else:
            self._cool(provider.name, model, exc.retry_after)

    # --- API pública --------------------------------------------------------
    def chat(self, messages: list[dict], *, purpose: str = 'chat', temperature: float = 0.2,
             max_tokens: int | None = None, json_mode: bool = False, wait: float = 0) -> ChatResult:
        """Respuesta completa. Con `wait` > 0 espera hasta esos segundos a que haya cupo."""
        need = self.estimate_tokens(messages, max_tokens)
        limite = time.monotonic() + wait
        while True:
            try:
                return self._chat_once(messages, purpose, temperature, max_tokens, json_mode, need)
            except CapacityError as exc:
                espera = exc.retry_after if exc.retry_after is not None else 5
                if time.monotonic() + espera > limite:
                    raise
                time.sleep(min(max(espera, 0.5), 15))

    def _chat_once(self, messages, purpose, temperature, max_tokens, json_mode, need) -> ChatResult:
        errores = []
        solo_cupo = True  # todos los fallos fueron por cuota (429) o falta de cupo
        for provider, model in self.candidates(purpose):
            if not self._available(provider, model):  # pudo desactivarse en esta misma vuelta
                continue
            if not self._take(provider, model, self._need(provider, model, need, purpose)):
                continue
            payload = self._chat_payload(model, messages, temperature=temperature, max_tokens=max_tokens,
                                         stream=False, json_mode=json_mode)
            try:
                with self._request(provider, '/chat/completions', payload) as resp:
                    self._update_quota(provider, model, getattr(resp, 'headers', None))
                    data = json.loads(resp.read().decode('utf-8'))
                texto = ((data.get('choices') or [{}])[0].get('message') or {}).get('content') or ''
                texto = texto.strip()
                if not texto:
                    raise _ProviderError(f'{provider.name}/{model} devolvió una respuesta vacía')
                return ChatResult(texto, provider.name, model)
            except _ProviderError as exc:
                self._handle_failure(provider, model, exc)
                solo_cupo = solo_cupo and exc.status == 429
                errores.append(str(exc))
            except ValueError as exc:
                solo_cupo = False
                errores.append(f'{provider.name}: JSON inválido ({exc})')
        self._raise(purpose, need, errores, solo_cupo)

    def _raise(self, purpose: str, need: int, errores: list[str], solo_cupo: bool):
        espera = self.wait_time(purpose, need)
        if solo_cupo and espera is not None:
            raise CapacityError('; '.join(errores) or 'Todos los modelos están sin cupo en este momento.', espera)
        raise LLMError('; '.join(errores) or 'No hay ningún modelo de IA configurado o disponible.')

    def chat_stream(self, messages: list[dict], *, temperature: float = 0.2,
                    max_tokens: int | None = None, meta: dict | None = None) -> Iterator[str]:
        """Genera la respuesta trozo a trozo (Server-Sent Events del proveedor).

        Si un proveedor falla ANTES de enviar el primer trozo se pasa al
        siguiente; si falla a mitad de respuesta se lanza LLMError. `meta`
        recibe el proveedor y modelo que respondieron. Si ningún modelo tiene
        cupo se lanza CapacityError (con los segundos estimados de espera).
        """
        errores = []
        solo_cupo = True
        need = self.estimate_tokens(messages, max_tokens)
        for provider, model in self.candidates('chat'):
            if not self._available(provider, model):
                continue
            if not self._take(provider, model, need):
                continue
            payload = self._chat_payload(model, messages, temperature=temperature, max_tokens=max_tokens,
                                         stream=True, json_mode=False)
            enviado = False
            try:
                with self._request(provider, '/chat/completions', payload, stream=True) as resp:
                    self._update_quota(provider, model, getattr(resp, 'headers', None))
                    if meta is not None:
                        meta.update(provider=provider.name, model=model, label=provider.label)
                    for crudo in resp:
                        linea = crudo.decode('utf-8', 'replace').strip()
                        if not linea.startswith('data:'):
                            continue
                        dato = linea[5:].strip()
                        if dato == '[DONE]':
                            break
                        try:
                            evento = json.loads(dato)
                        except ValueError:
                            continue
                        if evento.get('error'):
                            raise _ProviderError(f"{provider.name}: {evento['error']}")
                        delta = ((evento.get('choices') or [{}])[0].get('delta') or {}).get('content')
                        if delta:
                            enviado = True
                            yield delta
                if enviado:
                    return
                raise _ProviderError(f'{provider.name}/{model} no devolvió contenido')
            except _ProviderError as exc:
                self._handle_failure(provider, model, exc)
                if enviado:
                    raise LLMError(f'La respuesta se cortó: {exc}') from exc
                solo_cupo = solo_cupo and exc.status == 429
                errores.append(str(exc))
            except (OSError, TimeoutError) as exc:
                if enviado:
                    raise LLMError(f'La respuesta se cortó: {exc}') from exc
                self._cool(provider.name, model, None)
                solo_cupo = False
                errores.append(f'{provider.name}: {exc}')
        self._raise('chat', need, errores, solo_cupo)

    # --- Embeddings ---------------------------------------------------------
    def embed_provider(self) -> Provider | None:
        if self._embed_choice in ('none', 'off'):
            return None
        orden = [self._embed_choice] if self._embed_choice not in ('', 'auto') else ['gemini', 'ollama']
        for nombre in orden:
            prov = self.providers.get(nombre)
            if prov and prov.embed_model and prov.configured and prov.name not in self._disabled:
                if prov.local and not self._ollama_alive(prov):
                    continue
                return prov
        return None

    def embed_signature(self) -> str:
        """Identifica el espacio vectorial: cambiar de modelo obliga a reindexar."""
        prov = self.embed_provider()
        return f'{prov.name}:{prov.embed_model}' if prov else ''

    def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        if not texts:
            return []
        prov = self.embed_provider()
        if prov is None:
            raise LLMError('No hay un modelo de embeddings disponible.')
        entradas = texts
        # nomic-embed-text se entrenó con estos prefijos.
        if 'nomic' in prov.embed_model:
            prefijo = 'search_query: ' if query else 'search_document: '
            entradas = [prefijo + t for t in texts]
        intentos = 3
        for intento in range(intentos):
            try:
                with self._request(prov, '/embeddings', {'model': prov.embed_model, 'input': entradas}) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                vectores = [d['embedding'] for d in sorted(data.get('data', []), key=lambda d: d.get('index', 0))]
                if len(vectores) != len(texts):
                    raise LLMError('El proveedor devolvió un número de vectores distinto al pedido.')
                return vectores
            except _ProviderError as exc:
                if exc.fatal:
                    self._disabled[prov.name] = 'Clave de API rechazada'
                    raise LLMError(str(exc)) from exc
                if exc.status == 429 and intento < intentos - 1:
                    time.sleep(min(exc.retry_after or 5 * (intento + 1), 30))
                    continue
                raise LLMError(str(exc)) from exc
        raise LLMError('No se pudieron calcular los vectores.')

    # --- Detector de inyección de instrucciones -----------------------------
    def prompt_injection_score(self, text: str) -> float | None:
        """Probabilidad (0-1) de que el texto intente manipular al asistente.

        Usa Llama Prompt Guard 2 en Groq si hay clave; None si no está disponible.
        """
        prov = self.providers.get('groq')
        if not prov or not prov.configured or not prov.prompt_guard_model or prov.name in self._disabled:
            return None
        modelo = prov.prompt_guard_model
        if not self._available(prov, modelo):
            return None
        try:
            with self._request(prov, '/chat/completions', {
                'model': modelo, 'messages': [{'role': 'user', 'content': text[:2000]}]}) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            contenido = ((data.get('choices') or [{}])[0].get('message') or {}).get('content') or ''
            return max(0.0, min(1.0, float(contenido.strip().split()[0])))
        except _ProviderError as exc:
            self._handle_failure(prov, modelo, exc)
        except (ValueError, IndexError):
            pass
        return None


_router: Router | None = None
_router_lock = threading.Lock()


def router() -> Router:
    global _router
    with _router_lock:
        if _router is None:
            from ..config import env_bool
            if env_bool('AI_SIMULATED'):
                # Pruebas de carga: misma lógica de cuotas, pero sin red ni gasto.
                from .simulado import SimulatedRouter
                _router = SimulatedRouter()
            else:
                _router = Router()
        return _router


def set_router(nuevo: Router | None) -> None:
    """Sustituye el router (las pruebas usan uno falso)."""
    global _router
    with _router_lock:
        _router = nuevo
