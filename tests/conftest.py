"""Fixtures: una app con base de datos y carpetas temporales y un modelo de IA falso.

Las pruebas no llaman a ninguna API externa ni al antivirus: el router de IA
se sustituye por FakeRouter y SCAN_ANTIVIRUS=off.
"""

from __future__ import annotations

import hashlib
import io
import math
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['SCAN_ANTIVIRUS'] = 'off'

from hub import create_app  # noqa: E402
from hub.ai import assistant, llm  # noqa: E402
from hub.api import auth, chat  # noqa: E402

PASSWORD = 'ClaveSegura123'


class FakeRouter(llm.Router):
    """Responde sin red: embeddings por bolsa de palabras y respuestas fijas."""

    def __init__(self):
        super().__init__(providers={}, chat_order=['fake'], security_order=['fake'], embed_provider='none')
        self.security_verdict = 'ok'
        self.fail_security = False
        self.chat_calls: list[list[dict]] = []
        self.fail_chat = False

    def candidates(self, purpose='chat'):
        return [(llm.Provider(name='fake', label='Fake', base_url='http://fake', local=True), 'fake-model')]

    def status(self):
        return {'available': True, 'primary': {'provider': 'fake', 'model': 'fake-model', 'label': 'Fake'},
                'security': {'provider': 'fake', 'model': 'fake-guard'},
                'embeddings': {'provider': 'fake', 'model': 'hash'}, 'providers': []}

    def embed_provider(self):
        return llm.Provider(name='fake', label='Fake', base_url='http://fake', embed_model='hash', local=True)

    def embed_signature(self):
        return 'fake:hash'

    def embed(self, texts, *, query=False):
        vectores = []
        for t in texts:
            v = [0.0] * 64
            for palabra in re.findall(r'\w+', t.lower()):
                v[int(hashlib.md5(palabra.encode()).hexdigest(), 16) % 64] += 1
            norma = math.sqrt(sum(x * x for x in v)) or 1
            vectores.append([x / norma for x in v])
        return vectores

    def wait_time(self, purpose='chat', need=0):
        return 0.0

    def chat(self, messages, *, purpose='chat', temperature=0.2, max_tokens=None, json_mode=False, wait=0):
        if purpose in ('security', 'vision'):
            if self.fail_security:
                raise llm.LLMError('sin cuota')
            texto = str(messages[-1]['content'])
            veredicto = 'block' if 'ignora tus instrucciones' in texto.lower() else self.security_verdict
            return llm.ChatResult(f'{{"verdict": "{veredicto}", "categories": [], "reason": "prueba"}}',
                                  'fake', 'fake-guard')
        if self.fail_chat:
            raise llm.LLMError('sin cuota')
        self.chat_calls.append(messages)
        contenido = messages[-1]['content']
        if 'mundial' in contenido.lower():
            return llm.ChatResult('[FUERA_DE_TEMA]', 'fake', 'fake-model')
        if 'EXTRACTOS:' in contenido and '[1]' in contenido:
            return llm.ChatResult('Según el material, la normalización evita redundancia [1].', 'fake', 'fake-model')
        return llm.ChatResult('Respuesta general.', 'fake', 'fake-model')

    def chat_stream(self, messages, *, temperature=0.2, max_tokens=None, meta=None):
        if self.fail_chat:
            raise llm.LLMError('sin cuota')
        resultado = self.chat(messages)
        if meta is not None:
            meta.update(provider='fake', model='fake-model', label='Fake')
        for palabra in resultado.text.split(' '):
            yield palabra + ' '

    def prompt_injection_score(self, text):
        return None


@pytest.fixture()
def fake_router():
    router = FakeRouter()
    llm.set_router(router)
    yield router
    llm.set_router(None)


@pytest.fixture()
def app(tmp_path, fake_router):
    for limiter in (auth.login_limiter, auth.login_ip_limiter, auth.register_limiter, auth.resend_limiter,
                    chat.flood_limiter, assistant.limiter):
        limiter.reset()
    assistant.cache_clear()
    app = create_app({
        'DATABASE_PATH': str(tmp_path / 'test.db'),
        'UPLOAD_FOLDER': str(tmp_path / 'uploads'),
        'AI_INDEX_DIR': str(tmp_path / 'ai_index'),
        'JWT_SECRET_KEY': 'clave-de-pruebas-suficientemente-larga-para-hs256',
        'BACKGROUND_WORKERS': False,
        'ADMIN_EMAILS': ['admin@ufg.edu.sv'],
        # Valores fijos: las pruebas no dependen de lo que haya en .env.
        'ALLOWED_EMAIL_DOMAINS': ['ufg.edu.sv'],
        'EMAIL_VERIFICATION': False,
        'SCAN_REQUIRE_AI': True,
        'MAX_UPLOAD_MB': 25,
        'USER_QUOTA_MB': 300,
        'UPLOADS_PER_DAY': 40,
        'MIN_FREE_DISK_MB': 0,
        'TESTING': True,
    })
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


class User:
    def __init__(self, client, uid, token, name):
        self.client, self.id, self.token, self.name = client, uid, token, name

    @property
    def h(self):
        return {'Authorization': f'Bearer {self.token}'}

    def get(self, url, **kw):
        return self.client.get(url, headers=self.h, **kw)

    def post(self, url, json=None, **kw):
        return self.client.post(url, json=json, headers=self.h, **kw)

    def put(self, url, json=None, **kw):
        return self.client.put(url, json=json, headers=self.h, **kw)

    def delete(self, url, **kw):
        return self.client.delete(url, headers=self.h, **kw)

    def upload(self, url, filename, content: bytes, **fields):
        data = {**fields, 'file': (io.BytesIO(content), filename)}
        return self.client.post(url, data=data, headers=self.h, content_type='multipart/form-data')


@pytest.fixture()
def make_user(client):
    def _make(name='Ana', email=None):
        email = email or f'{name.lower()}@ufg.edu.sv'
        r = client.post('/api/register', json={'name': name, 'email': email, 'password': PASSWORD})
        assert r.status_code == 201, r.get_json()
        r = client.post('/api/login', json={'email': email, 'password': PASSWORD})
        assert r.status_code == 200, r.get_json()
        data = r.get_json()
        return User(client, data['user']['id'], data['token'], name)
    return _make


def befriend(a: User, b: User) -> None:
    r = a.post('/api/contacts/request', {'contact_id': b.id})
    assert r.status_code == 201
    req_id = r.get_json()['request_id']
    assert b.put(f'/api/contacts/requests/{req_id}/accept').status_code == 200
