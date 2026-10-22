"""El router de modelos cambia de proveedor cuando uno se queda sin cuota."""

import io
import json

import pytest

from hub.ai import llm


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _router(monkeypatch, comportamiento):
    proveedores = {
        'a': llm.Provider(name='a', label='A', base_url='http://a', api_key='k', chat_models=['m1', 'm2'],
                          security_models=['s1']),
        'b': llm.Provider(name='b', label='B', base_url='http://b', api_key='k', chat_models=['m3']),
    }
    router = llm.Router(providers=proveedores, chat_order=['a', 'b'], security_order=['a', 'b'],
                        embed_provider='none')
    llamadas = []

    def falso(provider, path, payload, *, stream=False):
        clave = f'{provider.name}/{payload["model"]}'
        llamadas.append(clave)
        accion = comportamiento.get(clave, 'ok')
        if accion == '429':
            raise llm._ProviderError('cuota', retry_after=30, status=429)
        if accion == '401':
            raise llm._ProviderError('clave', fatal=True, status=401)
        if stream:
            cuerpo = (f'data: {json.dumps({"choices": [{"delta": {"content": "Hola "}}]})}\n'
                      f'data: {json.dumps({"choices": [{"delta": {"content": clave}}]})}\ndata: [DONE]\n')
            return _Resp(cuerpo.encode())
        return _Resp(json.dumps({'choices': [{'message': {'content': f'respuesta de {clave}'}}]}).encode())

    monkeypatch.setattr(router, '_request', falso)
    return router, llamadas


def test_failover_on_quota(monkeypatch):
    router, llamadas = _router(monkeypatch, {'a/m1': '429'})
    r = router.chat([{'role': 'user', 'content': 'hola'}])
    assert (r.provider, r.model) == ('a', 'm2')
    # m1 queda en enfriamiento: la siguiente pregunta ni lo intenta.
    router.chat([{'role': 'user', 'content': 'otra'}])
    assert llamadas == ['a/m1', 'a/m2', 'a/m2']


def test_invalid_key_disables_provider(monkeypatch):
    router, _ = _router(monkeypatch, {'a/m1': '401'})
    r = router.chat([{'role': 'user', 'content': 'hola'}])
    assert r.provider == 'b'
    assert 'a' in router._disabled
    assert router.status()['primary']['provider'] == 'b'


def test_all_fail_raises(monkeypatch):
    router, _ = _router(monkeypatch, {'a/m1': '429', 'a/m2': '429', 'b/m3': '429'})
    with pytest.raises(llm.LLMError):
        router.chat([{'role': 'user', 'content': 'hola'}])
    assert router.status()['available'] is False


def test_stream_failover_before_first_token(monkeypatch):
    router, _ = _router(monkeypatch, {'a/m1': '429', 'a/m2': '429'})
    meta = {}
    texto = ''.join(router.chat_stream([{'role': 'user', 'content': 'hola'}], meta=meta))
    assert texto == 'Hola b/m3' and meta['provider'] == 'b'


def test_security_uses_its_own_models(monkeypatch):
    router, llamadas = _router(monkeypatch, {})
    r = router.chat([{'role': 'user', 'content': 'revisa'}], purpose='security')
    assert r.model == 's1'


def test_unconfigured_providers_are_skipped():
    router = llm.Router(providers={'x': llm.Provider(name='x', label='X', base_url='http://x', chat_models=['m'])},
                        chat_order=['x'], security_order=['x'], embed_provider='none')
    assert router.candidates() == []  # sin clave de API
