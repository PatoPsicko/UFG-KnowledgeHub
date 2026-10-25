"""Almacenamiento de archivos: carpetas, límites, migración y limpieza."""

import os
import time

import samples

from hub import storage
from hub.extensions import db
from hub.models import Resource


def _subir(user, nombre='apuntes.pdf', contenido=None, url='/api/resources'):
    return user.upload(url, nombre, contenido or samples.pdf(f'Apuntes {nombre}'), title=nombre, author=user.name)


def test_layout_by_kind_and_owner(app, make_user):
    ana = make_user('Ana')
    base = app.config['UPLOAD_FOLDER']
    assert _subir(ana).status_code == 201
    assert _subir(ana, 'mio.pdf', url='/api/private-resources').status_code == 201
    assert os.listdir(os.path.join(base, 'library'))[0].endswith('_apuntes.pdf')
    assert os.listdir(os.path.join(base, 'private', str(ana.id)))[0].endswith('_mio.pdf')
    # Ningún archivo queda suelto en la raíz ni a medias en tmp/.
    assert not [n for n in os.listdir(base) if os.path.isfile(os.path.join(base, n))]
    assert os.listdir(os.path.join(base, 'tmp')) == []


def test_long_and_accented_names_are_safe(app, make_user):
    ana = make_user('Ana')
    r = ana.upload('/api/resources', 'Cálculo ' + 'x' * 200 + '.pdf', samples.pdf(), title='Largo', author='Ana')
    assert r.status_code == 201, r.get_json()
    nombre = r.get_json()['resource']['original_filename']
    assert nombre.startswith('Calculo_x') and nombre.endswith('.pdf') and len(nombre) <= storage.MAX_NOMBRE + 4


def test_size_quota_and_daily_limits(app, make_user):
    ana = make_user('Ana')
    app.config['MAX_UPLOAD_MB'] = 1
    r = _subir(ana, 'grande.pdf', samples.pdf('x', extra=b'0' * (1024 * 1024 + 10)))
    assert r.status_code == 413 and r.get_json()['code'] == 'file_too_large'
    assert os.listdir(os.path.join(app.config['UPLOAD_FOLDER'], 'tmp')) == []

    app.config['UPLOADS_PER_DAY'] = 2
    assert _subir(ana, 'uno.pdf').status_code == 201
    assert _subir(ana, 'dos.pdf').status_code == 201
    r = _subir(ana, 'tres.pdf')
    assert r.status_code == 429 and r.get_json()['code'] == 'upload_limit'

    app.config['UPLOADS_PER_DAY'] = 100
    app.config['USER_QUOTA_MB'] = 0
    r = _subir(ana, 'cuatro.pdf')
    assert r.status_code == 413 and r.get_json()['code'] == 'quota_exceeded'


def test_empty_file_is_rejected(make_user):
    ana = make_user('Ana')
    r = _subir(ana, 'vacio.txt', b'')
    assert r.status_code in (400, 422)


def test_legacy_files_are_moved_and_still_served(app, make_user):
    ana = make_user('Ana')
    rid = _subir(ana).get_json()['id']
    base = app.config['UPLOAD_FOLDER']
    with app.app_context():
        nombre = db.session.get(Resource, rid).filename
        # Simula la estructura anterior: la biblioteca en la raíz de uploads/.
        os.replace(os.path.join(base, 'library', nombre), os.path.join(base, nombre))
        assert storage.path_for('public', nombre) == os.path.join(base, nombre)
        assert ana.get(f'/api/resources/{rid}/file').status_code == 200
        assert storage.migrate_layout() == 1
        assert os.path.exists(os.path.join(base, 'library', nombre))
    assert ana.get(f'/api/resources/{rid}/file').status_code == 200


def test_cleanup_removes_only_old_orphans(app, make_user):
    ana = make_user('Ana')
    _subir(ana)
    base = app.config['UPLOAD_FOLDER']
    huerfano = os.path.join(base, 'library', 'f' * 32 + '_huerfano.pdf')
    reciente = os.path.join(base, 'library', 'e' * 32 + '_reciente.pdf')
    a_medias = os.path.join(base, 'tmp', 'x.part')
    for ruta in (huerfano, reciente, a_medias):
        with open(ruta, 'wb') as fh:
            fh.write(b'datos')
    viejo = time.time() - 3 * 86400
    os.utime(huerfano, (viejo, viejo))
    os.utime(a_medias, (viejo, viejo))
    with app.app_context():
        assert len(storage.cleanup(dry_run=True)['removed']) == 2
        assert os.path.exists(huerfano)
        informe = storage.cleanup()
        assert sorted(os.path.basename(r) for r in informe['removed']) == ['f' * 32 + '_huerfano.pdf', 'x.part']
        assert os.path.exists(reciente)
        assert len(os.listdir(os.path.join(base, 'library'))) == 2  # el subido y el reciente
        assert storage.stats()['folders']['library']['files'] == 2
