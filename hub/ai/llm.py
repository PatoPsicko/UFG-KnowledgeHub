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

Sólo se usa la biblioteca estándar (urllib) para no añadir dependencias.
"""

from __future__ import annotations

import json
import logging
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
            chat_models=env_list('GROQ_CHAT_MODELS', 'openai/gpt-oss-120b,qwen/qwen3.8-27b'),
            security_models=env_list('GROQ_SECURITY_MODELS', 'openai/gpt-oss-20b'),
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
        }

    # --- HTTP ---------------------------------------------------------------
    def _request(self, provider: Provider, path: str, payload: dict, *, stream: bool = False):
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
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
             max_tokens: int | None = None, json_mode: bool = False) -> ChatResult:
        errores = []
        for provider, model in self.candidates(purpose):
            if not self._available(provider, model):  # pudo desactivarse en esta misma vuelta
                continue
            payload = self._chat_payload(model, messages, temperature=temperature, max_tokens=max_tokens,
                                         stream=False, json_mode=json_mode)
            try:
                with self._request(provider, '/chat/completions', payload) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                texto = ((data.get('choices') or [{}])[0].get('message') or {}).get('content') or ''
                texto = texto.strip()
                if not texto:
                    raise _ProviderError(f'{provider.name}/{model} devolvió una respuesta vacía')
                return ChatResult(texto, provider.name, model)
            except _ProviderError as exc:
                self._handle_failure(provider, model, exc)
                errores.append(str(exc))
            except ValueError as exc:
                errores.append(f'{provider.name}: JSON inválido ({exc})')
        raise LLMError('; '.join(errores) or 'No hay ningún modelo de IA configurado o disponible.')

    def chat_stream(self, messages: list[dict], *, temperature: float = 0.2,
                    max_tokens: int | None = None, meta: dict | None = None) -> Iterator[str]:
        """Genera la respuesta trozo a trozo (Server-Sent Events del proveedor).

        Si un proveedor falla ANTES de enviar el primer trozo se pasa al
        siguiente; si falla a mitad de respuesta se lanza LLMError. `meta`
        recibe el proveedor y modelo que respondieron.
        """
        errores = []
        for provider, model in self.candidates('chat'):
            if not self._available(provider, model):
                continue
            payload = self._chat_payload(model, messages, temperature=temperature, max_tokens=max_tokens,
                                         stream=True, json_mode=False)
            enviado = False
            try:
                with self._request(provider, '/chat/completions', payload, stream=True) as resp:
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
                errores.append(str(exc))
            except (OSError, TimeoutError) as exc:
                if enviado:
                    raise LLMError(f'La respuesta se cortó: {exc}') from exc
                self._cool(provider.name, model, None)
                errores.append(f'{provider.name}: {exc}')
        raise LLMError('; '.join(errores) or 'No hay ningún modelo de IA configurado o disponible.')

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
            _router = Router()
        return _router


def set_router(nuevo: Router | None) -> None:
    """Sustituye el router (las pruebas usan uno falso)."""
    global _router
    with _router_lock:
        _router = nuevo
