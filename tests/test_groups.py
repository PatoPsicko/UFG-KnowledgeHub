import samples
from conftest import befriend


def _grupo(owner, **extra):
    r = owner.post('/api/groups', {'name': 'Proyecto BD', 'subject': 'Bases de Datos II', **extra})
    assert r.status_code == 201, r.get_json()
    return r.get_json()['group_id']


def test_create_with_friends_and_detail(make_user):
    ana, beto, carla = make_user('Ana'), make_user('Beto'), make_user('Carla')
    befriend(ana, beto)
    gid = _grupo(ana, member_ids=[beto.id, carla.id])  # Carla no es amiga: se ignora
    detalle = beto.get(f'/api/groups/{gid}').get_json()
    assert {m['name'] for m in detalle['members']} == {'Ana', 'Beto'}
    assert carla.get(f'/api/groups/{gid}').status_code == 403
    assert any(n['type'] == 'group_invite' for n in beto.get('/api/notifications').get_json()['notifications'])


def test_invite_rules(make_user):
    ana, beto, carla, dani = (make_user(n) for n in ('Ana', 'Beto', 'Carla', 'Dani'))
    befriend(ana, beto)
    gid = _grupo(ana, member_ids=[beto.id])
    # Cualquier miembro puede sumar a otro estudiante; un externo no.
    assert beto.post(f'/api/groups/{gid}/invite', {'user_id': carla.id}).status_code == 201
    assert ana.post(f'/api/groups/{gid}/invite', {'user_id': carla.id}).status_code == 409
    assert dani.post(f'/api/groups/{gid}/invite', {'user_id': dani.id}).status_code == 403


def test_tasks_lifecycle(make_user):
    ana, beto = make_user('Ana'), make_user('Beto')
    befriend(ana, beto)
    gid = _grupo(ana, member_ids=[beto.id])
    r = beto.post(f'/api/groups/{gid}/tasks', {'title': 'Diagrama ER', 'assigned_to': ana.id, 'due_date': '2026-11-05'})
    assert r.status_code == 201
    tarea = r.get_json()['task']
    assert tarea['assigned_to'] == 'Ana' and tarea['due_date'] == '2026-11-05'
    assert any(n['type'] == 'group_task' for n in ana.get('/api/notifications').get_json()['notifications'])
    assert ana.put(f"/api/groups/{gid}/tasks/{tarea['id']}", {'status': 'in_progress'}).status_code == 200
    assert ana.put(f"/api/groups/{gid}/tasks/{tarea['id']}", {'status': 'hecho'}).status_code == 400
    assert ana.post(f'/api/groups/{gid}/tasks', {'title': 'x', 'assigned_to': 999}).status_code == 400
    assert ana.get('/api/groups').get_json()['groups'][0]['open_tasks'] == 1
    assert ana.delete(f"/api/groups/{gid}/tasks/{tarea['id']}").status_code == 200  # el líder puede


def test_group_chat_unread(make_user):
    ana, beto = make_user('Ana'), make_user('Beto')
    befriend(ana, beto)
    gid = _grupo(ana, member_ids=[beto.id])
    ana.post(f'/api/groups/{gid}/messages', {'message': 'Reunión mañana 6 pm'})
    assert beto.get('/api/pulse').get_json()['groups_unread'][str(gid)] == 1
    assert beto.get('/api/groups').get_json()['groups'][0]['unread'] == 1
    beto.get(f'/api/groups/{gid}/messages')
    assert beto.get('/api/pulse').get_json()['groups_unread_total'] == 0


def test_group_files(make_user):
    ana, beto = make_user('Ana'), make_user('Beto')
    befriend(ana, beto)
    gid = _grupo(ana, member_ids=[beto.id])
    r = beto.upload(f'/api/groups/{gid}/resources', 'avance.pdf', samples.pdf(), title='Avance 1')
    assert r.status_code == 201
    rid = r.get_json()['id']
    assert ana.get(f'/api/groups/{gid}/resources/{rid}/download').status_code == 200
    assert beto.upload(f'/api/groups/{gid}/resources', 'x.pdf', samples.fake_exe(), title='X').status_code == 422
    assert ana.delete(f'/api/groups/{gid}/resources/{rid}').status_code == 200


def test_leave_transfers_ownership_and_owner_actions(make_user):
    ana, beto, carla = make_user('Ana'), make_user('Beto'), make_user('Carla')
    befriend(ana, beto)
    befriend(ana, carla)
    gid = _grupo(ana, member_ids=[beto.id, carla.id])
    assert beto.put(f'/api/groups/{gid}', {'name': 'Hack'}).status_code == 403
    assert ana.put(f'/api/groups/{gid}', {'name': 'Proyecto BD final'}).status_code == 200
    assert ana.delete(f'/api/groups/{gid}/members/{carla.id}').status_code == 200
    assert ana.post(f'/api/groups/{gid}/leave').status_code == 200
    assert beto.get(f'/api/groups/{gid}').get_json()['group']['is_owner'] is True
    assert beto.delete(f'/api/groups/{gid}').status_code == 200
    assert beto.get('/api/groups').get_json()['groups'] == []
