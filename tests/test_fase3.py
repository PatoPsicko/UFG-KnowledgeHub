"""Fase 3C y 3D: reportes de documentos, privacidad de la cuenta y respaldos."""

import io
import json
import os
import zipfile

import samples
from conftest import PASSWORD, befriend
from hub.extensions import db
from hub.models import DocumentReport, User


def _doc(user, titulo='Apuntes'):
    r = user.upload('/api/resources', f'{titulo}.pdf', samples.pdf(f'Contenido de {titulo}'), title=titulo, author=user.name)
    assert r.status_code == 201, r.get_json()
    return r.get_json()['id']


def test_report_flow_and_dismiss(make_user):
    ana, beto = make_user('Ana'), make_user('Beto')
    admin = make_user('Admin', 'admin@ufg.edu.sv')
    rid = _doc(ana)
    assert ana.post('/api/reports', {'kind': 'public', 'resource_id': rid, 'reason': 'spam'}).status_code == 400
    r = beto.post('/api/reports', {'kind': 'public', 'resource_id': rid, 'reason': 'copyright', 'comment': 'Libro completo'})
    assert r.status_code == 201 and r.get_json()['hidden'] is False
    assert beto.post('/api/reports', {'kind': 'public', 'resource_id': rid, 'reason': 'spam'}).status_code == 409
    assert any(n['type'] == 'document_report' for n in admin.get('/api/notifications').get_json()['notifications'])
    docs = admin.get('/api/admin/reports').get_json()['documents']
    assert docs[0]['resource_id'] == rid and docs[0]['reasons'][0]['code'] == 'copyright'
    assert admin.post('/api/admin/reports/resolve', {'kind': 'public', 'resource_id': rid, 'action': 'dismiss'}).status_code == 200
    assert admin.get('/api/admin/reports').get_json()['documents'] == []
    assert beto.get(f'/api/resources/{rid}').status_code == 200


def test_reports_hide_document_after_threshold(make_user):
    ana = make_user('Ana')
    admin = make_user('Admin', 'admin@ufg.edu.sv')
    otros = [make_user(n) for n in ('Beto', 'Carla', 'Dani')]
    rid = _doc(ana)
    for u in otros:
        r = u.post('/api/reports', {'kind': 'public', 'resource_id': rid, 'reason': 'inappropriate'})
    assert r.get_json()['hidden'] is True
    assert otros[0].get(f'/api/resources/{rid}').status_code == 404
    cuarentena = admin.get('/api/admin/scans?status=quarantine').get_json()['scans']
    assert cuarentena and cuarentena[0]['resource_id'] == rid
    # Descartar los reportes lo vuelve a publicar.
    admin.post('/api/admin/reports/resolve', {'kind': 'public', 'resource_id': rid, 'action': 'dismiss'})
    assert otros[0].get(f'/api/resources/{rid}').status_code == 200


def test_report_remove_deletes_and_bans(make_user):
    ana, beto = make_user('Ana'), make_user('Beto')
    admin = make_user('Admin', 'admin@ufg.edu.sv')
    rid = _doc(ana)
    beto.post('/api/reports', {'kind': 'public', 'resource_id': rid, 'reason': 'malicious'})
    r = admin.post('/api/admin/reports/resolve', {'kind': 'public', 'resource_id': rid, 'action': 'remove', 'note': 'Phishing'})
    assert r.status_code == 200
    assert beto.get(f'/api/resources/{rid}').status_code == 404
    assert admin.get('/api/admin/blocked-hashes').get_json()['hashes']
    assert any(n['type'] == 'report_result' for n in beto.get('/api/notifications').get_json()['notifications'])


def test_group_document_report_requires_membership(make_user):
    ana, beto, carla = make_user('Ana'), make_user('Beto'), make_user('Carla')
    befriend(ana, beto)
    gid = ana.post('/api/groups', {'name': 'G', 'member_ids': [beto.id]}).get_json()['group_id']
    rid = ana.upload(f'/api/groups/{gid}/resources', 'a.pdf', samples.pdf(), title='Avance').get_json()['id']
    assert carla.post('/api/reports', {'kind': 'group', 'resource_id': rid, 'reason': 'spam'}).status_code == 404
    assert beto.post('/api/reports', {'kind': 'group', 'resource_id': rid, 'reason': 'spam'}).status_code == 201


def test_export_my_data(make_user):
    ana = make_user('Ana')
    _doc(ana, 'Calculo')
    ana.post('/api/private-resources', {'title': 'Idea', 'content': 'Repasar derivadas'})
    r = ana.get('/api/me/export')
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.data))
    datos = json.loads(z.read('datos.json'))
    assert datos['cuenta']['email'] == 'ana@ufg.edu.sv'
    assert datos['biblioteca'][0]['titulo'] == 'Calculo'
    assert datos['mi_espacio'][0]['contenido'] == 'Repasar derivadas'
    assert any(n.startswith('archivos/biblioteca/') for n in z.namelist())


def test_delete_account(app, make_user, client):
    ana, beto = make_user('Ana'), make_user('Beto')
    befriend(ana, beto)
    gid = ana.post('/api/groups', {'name': 'Proyecto', 'member_ids': [beto.id]}).get_json()['group_id']
    rid = _doc(ana)
    assert ana.delete('/api/me', json={'password': PASSWORD}).status_code == 400
    assert ana.delete('/api/me', json={'password': 'mala', 'confirm': 'BORRAR'}).status_code == 400
    assert ana.delete('/api/me', json={'password': PASSWORD, 'confirm': 'BORRAR'}).status_code == 200
    assert beto.get(f'/api/resources/{rid}').status_code == 404
    assert beto.get(f'/api/groups/{gid}').get_json()['group']['is_owner'] is True
    assert client.post('/api/login', json={'email': 'ana@ufg.edu.sv', 'password': PASSWORD}).status_code == 401
    with app.app_context():
        assert db.session.query(User).filter_by(email='ana@ufg.edu.sv').count() == 0


def test_last_admin_cannot_delete_account(make_user):
    admin = make_user('Admin', 'admin@ufg.edu.sv')
    r = admin.delete('/api/me', json={'password': PASSWORD, 'confirm': 'BORRAR'})
    assert r.status_code == 400 and r.get_json()['code'] == 'last_admin'


def test_backup_and_restore(app, make_user, tmp_path, monkeypatch):
    from hub import backup
    monkeypatch.setenv('BACKUP_DIR', str(tmp_path / 'respaldos'))
    ana = make_user('Ana')
    admin = make_user('Admin', 'admin@ufg.edu.sv')
    rid = _doc(ana)
    r = admin.post('/api/admin/backups')
    assert r.status_code == 201
    nombre = r.get_json()['backup']['name']
    assert admin.get('/api/admin/overview').get_json()['backups'][0]['name'] == nombre
    with app.app_context():
        db.engine.dispose()
        destino = tmp_path / 'restaurado'
        info = backup.restore_backup(str(tmp_path / 'respaldos' / nombre), str(destino / 'db.sqlite'), str(destino / 'uploads'))
    assert info['files'] >= 1 and os.path.exists(destino / 'db.sqlite')
    assert info['tables']['resource'] >= 1
    assert rid


def test_hsts_only_over_https(client):
    assert 'Strict-Transport-Security' not in client.get('/api/health').headers
    r = client.get('/api/health', headers={'X-Forwarded-Proto': 'https'})
    assert r.headers['Strict-Transport-Security'].startswith('max-age=')


def test_reports_are_cleaned_with_reporter(app, make_user):
    ana, beto = make_user('Ana'), make_user('Beto')
    rid = _doc(ana)
    beto.post('/api/reports', {'kind': 'public', 'resource_id': rid, 'reason': 'spam'})
    beto.delete('/api/me', json={'password': PASSWORD, 'confirm': 'BORRAR'})
    with app.app_context():
        assert db.session.query(DocumentReport).count() == 0
