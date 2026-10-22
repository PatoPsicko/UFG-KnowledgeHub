import samples


def _subir(user, titulo='Normalización', **extra):
    campos = {'title': titulo, 'author': user.name, 'category': 'Base de Datos', 'tags': 'sql,3fn', **extra}
    r = user.upload('/api/resources', f'{titulo}.pdf', samples.pdf(f'Contenido de {titulo}'), **campos)
    assert r.status_code == 201, r.get_json()
    return r.get_json()['id']


def test_list_search_filter_and_sort(make_user):
    ana = make_user('Ana')
    _subir(ana, 'Normalización')
    _subir(ana, 'Cálculo integral', category='Cálculo', tags='integrales')
    datos = ana.get('/api/resources').get_json()
    assert datos['total'] == 2
    assert ana.get('/api/resources?q=integral').get_json()['total'] == 1
    assert ana.get('/api/resources?category=Cálculo').get_json()['total'] == 1
    titulos = [r['title'] for r in ana.get('/api/resources?sort=title').get_json()['resources']]
    assert titulos == sorted(titulos, key=str.lower)
    cats = ana.get('/api/resources/categories').get_json()['categories']
    assert {c['name'] for c in cats} == {'Base de Datos', 'Cálculo'}


def test_save_and_saved_scope(make_user):
    ana, beto = make_user('Ana'), make_user('Beto')
    rid = _subir(ana)
    assert beto.post(f'/api/resources/{rid}/save').get_json()['saved'] is True
    assert beto.get('/api/resources?scope=saved').get_json()['total'] == 1
    assert beto.post(f'/api/resources/{rid}/save').get_json()['saved'] is False
    assert beto.get('/api/resources?scope=saved').get_json()['total'] == 0


def test_download_counts_only_other_users(make_user):
    ana, beto = make_user('Ana'), make_user('Beto')
    rid = _subir(ana)
    assert ana.get(f'/api/resources/{rid}/file?download=1').status_code == 200
    r = beto.get(f'/api/resources/{rid}/file?download=1')
    assert r.status_code == 200 and r.data.startswith(b'%PDF')
    assert 'attachment' in r.headers['Content-Disposition']
    assert ana.get(f'/api/resources/{rid}').get_json()['resource']['downloads'] == 1
    assert 'inline' in beto.get(f'/api/resources/{rid}/file').headers['Content-Disposition']


def test_only_owner_edits_and_deletes(make_user):
    ana, beto = make_user('Ana'), make_user('Beto')
    rid = _subir(ana)
    assert beto.put(f'/api/resources/{rid}', {'title': 'Hack'}).status_code == 403
    r = ana.put(f'/api/resources/{rid}', {'title': 'Normalización (v2)', 'description': 'Con ejemplos'})
    assert r.status_code == 200
    assert r.get_json()['resource']['title'] == 'Normalización (v2)'
    assert beto.delete(f'/api/resources/{rid}').status_code == 403
    assert ana.delete(f'/api/resources/{rid}').status_code == 200
    assert ana.get(f'/api/resources/{rid}').status_code == 404


def test_missing_fields_and_extension(make_user):
    ana = make_user('Ana')
    r = ana.upload('/api/resources', 'a.pdf', samples.pdf(), title='', author='Ana')
    assert r.status_code == 400
    r = ana.upload('/api/resources', 'pagina.html', b'<script>alert(1)</script>', title='X', author='Ana')
    assert r.status_code == 400 and r.get_json()['code'] == 'extension_not_allowed'


def test_notes_crud_and_privacy(make_user):
    ana, beto = make_user('Ana'), make_user('Beto')
    nid = ana.post('/api/private-resources', {'title': 'Ideas', 'content': 'Repasar SQL'}).get_json()['id']
    assert ana.put(f'/api/private-resources/{nid}', {'content': 'Repasar SQL y 3FN'}).status_code == 200
    assert beto.put(f'/api/private-resources/{nid}', {'content': 'x'}).status_code == 404
    assert beto.get('/api/private-resources').get_json()['resources'] == []
    fid = ana.upload('/api/private-resources', 'mio.pdf', samples.pdf(), title='Mío').get_json()['id']
    assert ana.get(f'/api/private-resources/{fid}/download').status_code == 200
    assert beto.get(f'/api/private-resources/{fid}/download').status_code == 404
    assert ana.delete(f'/api/private-resources/{nid}').status_code == 200


def test_profile_update_and_stats(make_user):
    ana = make_user('Ana')
    r = ana.put('/api/profile', {'career': 'Ingeniería en Sistemas', 'semester': 5, 'bio': 'Me gusta SQL'})
    assert r.status_code == 200 and r.get_json()['user']['semester'] == 5
    assert ana.put('/api/profile', {'semester': 40}).status_code == 400
    assert ana.put('/api/profile', {'profile_color': 'rojo'}).status_code == 400
    _subir(ana)
    assert ana.get('/api/user/stats').get_json()['resources_count'] == 1


def test_profile_picture_is_scanned_and_served(make_user, client):
    ana = make_user('Ana')
    r = ana.upload('/api/profile/picture', 'yo.png', samples.png())
    assert r.status_code == 200
    url = r.get_json()['user']['avatar_url']
    assert client.get(url).status_code == 200
    assert ana.upload('/api/profile/picture', 'yo.pdf', samples.pdf()).status_code == 400


def test_change_password(make_user, client):
    ana = make_user('Ana', 'ana@ufg.edu.sv')
    assert ana.post('/api/profile/password', {'current_password': 'mala', 'new_password': 'NuevaClave99'}).status_code == 400
    from conftest import PASSWORD
    assert ana.post('/api/profile/password', {'current_password': PASSWORD, 'new_password': 'NuevaClave99'}).status_code == 200
    assert client.post('/api/login', json={'email': 'ana@ufg.edu.sv', 'password': 'NuevaClave99'}).status_code == 200
