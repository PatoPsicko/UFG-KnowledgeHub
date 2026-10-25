"""Cuotas gratuitas: cupo por modelo, cola, caché y respuesta sin IA."""

import io
import json

import pytest

import samples
from hub.ai import llm
from hub.ai.simulado import SimulatedRouter


class _Resp(io.BytesIO):
    def __init__(self, cuerpo: bytes, headers: dict):
        super().__init__(cuerpo)
        self.headers = headers

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _router(monkeypatch, restantes: int):
    prov = llm.Provider(name='groq', label='Groq', base_url='http://g', api_key='k', chat_models=['m1', 'm2'],
                        security_models=['m1'])
    router = llm.Router(providers={'groq': prov}, chat_order=['groq'], security_order=['groq'], embed_provider='none')
    llamadas = []

    def falso(provider, path, payload, *, stream=False):
        llamadas.append(payload['model'])
        cabeceras = {'x-ratelimit-limit-tokens': '8000', 'x-ratelimit-remaining-tokens': str(restantes),
                     'x-ratelimit-reset-tokens': '45s', 'x-ratelimit-limit-requests': '1000',
                     'x-ratelimit-remaining-requests': '998', 'x-ratelimit-reset-requests': '1m26.4s'}
        return _Resp(json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode(), cabeceras)

    monkeypatch.setattr(router, '_request', falso)
    return router, llamadas


def test_parse_duration():
    assert llm._parse_duration('607ms') == pytest.approx(0.607)
    assert llm._parse_duration('1m26.4s') == pytest.approx(86.4)
    assert llm._parse_duration('2h3m') == pytest.approx(7380)
    assert llm._parse_duration(None) is None


def test_quota_headers_route_to_the_model_with_room(monkeypatch):
    router, llamadas = _router(monkeypatch, restantes=100)
    pregunta = [{'role': 'user', 'content': 'x' * 7000}]  # ~3.000 tokens con la respuesta
    router.chat(pregunta)                                   # m1 responde y avisa: le quedan 100 tokens
    router.chat(pregunta)                                   # m1 no tiene cupo: va directo a m2
    assert llamadas == ['m1', 'm2']
    cuotas = {c['model']: c for c in router.quotas()}
    assert cuotas['groq/m1']['tokens_limit'] == 8000 and cuotas['groq/m1']['requests_remaining'] == 998
    # Sin cupo en ningún modelo: no se llama a la API y se sabe cuánto esperar.
    with pytest.raises(llm.CapacityError) as exc:
        router.chat(pregunta)
    assert llamadas == ['m1', 'm2'] and exc.value.retry_after > 0
    assert router.wait_time('chat', router.estimate_tokens(pregunta)) > 0


def test_security_leaves_room_for_the_assistant(monkeypatch):
    router, _ = _router(monkeypatch, restantes=4000)
    router.chat([{'role': 'user', 'content': 'hola'}])
    pregunta = [{'role': 'user', 'content': 'y' * 3000}]  # ~2.000 tokens
    # Al asistente le cabe; al vigilante no, porque deja 3.000 de reserva.
    assert router.wait_time('chat', router.estimate_tokens(pregunta)) == 0
    assert router.wait_time('security', router.estimate_tokens(pregunta)) > 0


def test_simulated_router_returns_429_like_groq(monkeypatch):
    monkeypatch.setenv('AI_SIM_TPM', '2000')
    monkeypatch.setenv('AI_SIM_LATENCY', '0')
    monkeypatch.setenv('GROQ_CHAT_MODELS', 'openai/gpt-oss-120b')
    router = SimulatedRouter()
    pregunta = [{'role': 'user', 'content': 'EXTRACTOS: [1] algo\nPREGUNTA: ¿qué es?'}]
    assert '[1]' in router.chat(pregunta, max_tokens=1200).text
    with pytest.raises(llm.CapacityError):
        router.chat(pregunta, max_tokens=1200)
    assert router.quotas()[0]['tokens_limit'] == 2000


def _con_documento(ana):
    r = ana.upload('/api/resources', 'normalizacion.pdf', samples.pdf(), title='Normalización',
                   author='Ana', category='Base de Datos')
    assert r.status_code == 201


def test_repeated_question_uses_cache(make_user, fake_router):
    ana, beto = make_user('Ana'), make_user('Beto')
    _con_documento(ana)
    primera = ana.post('/api/ai/chat', {'question': '¿Qué es la normalización de bases de datos?'}).get_json()
    segunda = beto.post('/api/ai/chat', {'question': '¿qué es la normalización de bases de datos'}).get_json()
    assert primera['cached'] is False and segunda['cached'] is True
    assert segunda['answer'] == primera['answer']
    assert len(fake_router.chat_calls) == 1


def test_without_quota_the_student_still_gets_documents(make_user, fake_router, monkeypatch):
    ana = make_user('Ana')
    _con_documento(ana)

    def sin_cupo(*a, **kw):
        raise llm.CapacityError('sin cupo', retry_after=120)

    monkeypatch.setattr(fake_router, 'chat', sin_cupo)
    datos = ana.post('/api/ai/chat', {'question': '¿Qué es la normalización de bases de datos?'}).get_json()
    assert datos['degraded'] is True
    assert 'Normalización' in datos['answer'] and datos['sources']


def test_stream_announces_queue_and_then_answers(make_user, fake_router, monkeypatch):
    ana = make_user('Ana')
    _con_documento(ana)
    esperas = iter([0.6, 0.0])
    monkeypatch.setattr(fake_router, 'wait_time', lambda *a, **kw: next(esperas, 0.0))
    r = ana.post('/api/ai/chat/stream', {'question': 'Explica la normalización de bases de datos'})
    eventos = [json.loads(linea) for linea in r.data.decode().splitlines() if linea.strip()]
    tipos = [e['type'] for e in eventos]
    assert 'queue' in tipos and tipos.index('queue') < tipos.index('token') and tipos[-1] == 'done'
