from conftest import befriend


def test_friend_request_flow(make_user):
    ana, beto = make_user('Ana'), make_user('Beto')
    r = ana.post('/api/contacts/request', {'contact_id': beto.id})
    assert r.status_code == 201
    assert ana.post('/api/contacts/request', {'contact_id': beto.id}).status_code == 409
    assert ana.post('/api/contacts/request', {'contact_id': ana.id}).status_code == 400
    assert len(ana.get('/api/contacts/requests/sent').get_json()['requests']) == 1
    recibidas = beto.get('/api/contacts/requests').get_json()['requests']
    assert recibidas[0]['user_name'] == 'Ana'
    assert beto.put(f"/api/contacts/requests/{recibidas[0]['id']}/accept").status_code == 200
    assert ana.get('/api/contacts').get_json()['contacts'][0]['name'] == 'Beto'
    tipos = [n['type'] for n in ana.get('/api/notifications').get_json()['notifications']]
    assert 'contact_accepted' in tipos


def test_reverse_request_auto_accepts(make_user):
    ana, beto = make_user('Ana'), make_user('Beto')
    ana.post('/api/contacts/request', {'contact_id': beto.id})
    r = beto.post('/api/contacts/request', {'contact_id': ana.id})
    assert r.status_code == 200 and r.get_json()['relation'] == 'accepted'


def test_cancel_reject_and_remove(make_user):
    ana, beto = make_user('Ana'), make_user('Beto')
    req = ana.post('/api/contacts/request', {'contact_id': beto.id}).get_json()['request_id']
    assert ana.delete(f'/api/contacts/requests/{req}').status_code == 200
    assert beto.get('/api/contacts/requests').get_json()['requests'] == []
    befriend(ana, beto)
    assert ana.delete(f'/api/contacts/{beto.id}').status_code == 200
    assert beto.get('/api/contacts').get_json()['contacts'] == []


def test_search_shows_relation(make_user):
    ana, beto = make_user('Ana'), make_user('Beto')
    make_user('Carla')
    ana.post('/api/contacts/request', {'contact_id': beto.id})
    usuarios = {u['name']: u for u in ana.get('/api/contacts/search?q=ufg').get_json()['users']}
    assert usuarios['Beto']['relation'] == 'pending_sent'
    assert usuarios['Carla']['relation'] == 'none'
    assert usuarios['Carla']['email'] is None
    assert beto.get('/api/contacts/search?q=ana').get_json()['users'][0]['relation'] == 'pending_received'


def test_direct_messages_only_between_friends(make_user):
    ana, beto, carla = make_user('Ana'), make_user('Beto'), make_user('Carla')
    assert ana.post('/api/direct-messages', {'receiver_id': beto.id, 'message': 'hola'}).status_code == 403
    befriend(ana, beto)
    r = ana.post('/api/direct-messages', {'receiver_id': beto.id, 'message': 'hola Beto'})
    assert r.status_code == 201
    primer_id = r.get_json()['data']['id']
    ana.post('/api/direct-messages', {'receiver_id': beto.id, 'message': '¿tienes la guía?'})
    assert carla.get(f'/api/direct-messages/{ana.id}').status_code == 403

    pulso = beto.get('/api/pulse').get_json()
    assert pulso['dm_unread'][str(ana.id)] == 2
    conv = beto.get('/api/conversations').get_json()['conversations']
    assert conv[0]['unread'] == 2 and conv[0]['last_message']['message'] == '¿tienes la guía?'

    nuevos = beto.get(f'/api/direct-messages/{ana.id}?after={primer_id}').get_json()['messages']
    assert [m['message'] for m in nuevos] == ['¿tienes la guía?']
    beto.get(f'/api/direct-messages/{ana.id}')
    assert beto.get('/api/pulse').get_json()['dm_unread_total'] == 0


def test_message_validation(make_user):
    ana, beto = make_user('Ana'), make_user('Beto')
    befriend(ana, beto)
    assert ana.post('/api/direct-messages', {'receiver_id': beto.id, 'message': '   '}).status_code == 400
    assert ana.post('/api/direct-messages', {'receiver_id': beto.id, 'message': 'x' * 2001}).status_code == 400


def test_global_chat_incremental_and_unread(make_user):
    ana, beto = make_user('Ana'), make_user('Beto')
    primero = ana.post('/api/chat/messages', {'message': 'Hola a todos'}).get_json()['data']['id']
    ana.post('/api/chat/messages', {'message': '¿Alguien tiene Bases de Datos II?'})
    assert beto.get('/api/pulse').get_json()['global_unread'] == 2
    nuevos = beto.get(f'/api/chat/messages?after={primero}').get_json()['messages']
    assert len(nuevos) == 1
    assert beto.get('/api/pulse').get_json()['global_unread'] == 0
    assert beto.delete(f'/api/chat/messages/{primero}').status_code == 403
    assert ana.delete(f'/api/chat/messages/{primero}').status_code == 200
