import json

import samples


def _doc(user, titulo, texto):
    r = user.upload('/api/resources', f'{titulo}.pdf', samples.pdf(texto), title=titulo, author=user.name,
                    category='Base de Datos')
    assert r.status_code == 201
    return r.get_json()['id']


def test_greeting_does_not_call_model(make_user, fake_router):
    ana = make_user('Ana')
    r = ana.post('/api/ai/chat', {'question': 'hola'})
    assert r.status_code == 200
    assert 'UFG Knowledge Hub' in r.get_json()['answer']
    assert fake_router.chat_calls == []


def test_answer_cites_documents(make_user, fake_router):
    ana = make_user('Ana')
    _doc(ana, 'Manual de normalizacion', 'La normalizacion de bases de datos evita la redundancia de datos')
    r = ana.post('/api/ai/chat', {'question': '¿Para qué sirve la normalizacion de bases de datos?'})
    datos = r.get_json()
    assert r.status_code == 200, datos
    assert '[1]' in datos['answer']
    assert datos['sources'][0]['title'] == 'Manual de normalizacion'
    prompt = fake_router.chat_calls[-1][-1]['content']
    assert 'CATÁLOGO' in prompt and 'EXTRACTOS' in prompt
    # La conversación se guarda con el modelo que respondió.
    hist = ana.get(f"/api/ai/history?conversation_id={datos['conversation_id']}").get_json()['messages']
    assert hist[1]['model'] == 'fake/fake-model'
    assert ana.get('/api/ai/conversations').get_json()['conversations'][0]['messages'] == 2


def test_private_documents_are_not_leaked(make_user, fake_router):
    ana, beto = make_user('Ana'), make_user('Beto')
    nid = ana.post('/api/private-resources', {'title': 'Clave del wifi', 'content': 'La clave secreta es zanahoria'}
                   ).get_json()['id']
    r = beto.post('/api/ai/chat', {'question': '¿Cuál es la clave secreta zanahoria?'})
    assert 'zanahoria' not in json.dumps(r.get_json()['sources'])
    assert beto.post('/api/ai/chat', {'question': 'resume', 'doc_key': f'private_note:{nid}'}).status_code == 404
    r = ana.post('/api/ai/chat', {'question': 'resume esta nota', 'doc_key': f'private_note:{nid}'})
    assert r.status_code == 200
    assert r.get_json()['search_mode'] == 'documento'


def test_general_fallback_when_no_material(make_user):
    ana = make_user('Ana')
    datos = ana.post('/api/ai/chat', {'question': 'Explícame qué es la recursividad'}).get_json()
    assert 'No encontré esto en los documentos' in datos['answer']
    assert datos['sources'] == []


def test_off_topic_is_refused(make_user):
    from hub.ai.assistant import FUERA_DE_TEMA
    ana = make_user('Ana')
    datos = ana.post('/api/ai/chat', {'question': '¿Quién ganó el mundial de 1986?'}).get_json()
    assert datos['answer'] in FUERA_DE_TEMA
    r = ana.post('/api/ai/chat/stream', {'question': '¿Y el mundial de 2010?'})
    texto = ''.join(json.loads(l).get('content', '') for l in r.data.decode().splitlines() if '"token"' in l)
    assert texto in FUERA_DE_TEMA


def test_stream_ndjson(make_user):
    ana = make_user('Ana')
    _doc(ana, 'Guia SQL', 'La normalizacion de bases de datos evita la redundancia')
    r = ana.post('/api/ai/chat/stream', {'question': 'normalizacion de bases de datos'})
    eventos = [json.loads(l) for l in r.data.decode().splitlines() if l.strip()]
    tipos = [e['type'] for e in eventos]
    assert tipos[0] == 'sources' and tipos[-1] == 'done'
    assert 'model' in tipos and 'token' in tipos
    assert eventos[-1]['conversation_id']


def test_model_unavailable_returns_503(make_user, fake_router):
    ana = make_user('Ana')
    fake_router.fail_chat = True
    r = ana.post('/api/ai/chat', {'question': 'Explica la recursividad'})
    assert r.status_code == 503 and r.get_json()['code'] == 'llm_unavailable'


def test_question_validation_and_status(make_user):
    ana = make_user('Ana')
    assert ana.post('/api/ai/chat', {'question': ''}).status_code == 400
    assert ana.post('/api/ai/chat', {'question': 'x' * 2001}).status_code == 400
    estado = ana.get('/api/ai/status').get_json()
    assert estado['available'] is True and estado['provider'] == 'fake'
