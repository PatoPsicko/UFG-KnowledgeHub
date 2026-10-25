from datetime import timedelta

from conftest import PASSWORD

from hub import mailer
from hub.extensions import db
from hub.models import LoginThrottle, User, utcnow


def test_register_and_login(client, make_user):
    ana = make_user('Ana')
    r = ana.get('/api/verify-token')
    assert r.status_code == 200
    assert r.get_json()['user']['name'] == 'Ana'
    assert r.get_json()['user']['role'] == 'student'


def test_register_validation_errors_are_json(client):
    r = client.post('/api/register', json={'name': 'X', 'email': 'malo', 'password': PASSWORD})
    assert r.status_code == 400
    assert r.get_json()['code'] == 'invalid_email'
    r = client.post('/api/register', json={'name': 'X', 'email': 'x@ufg.edu.sv', 'password': '123'})
    assert r.status_code == 400 and r.get_json()['code'] == 'weak_password'
    r = client.post('/api/register', json={'email': 'x@ufg.edu.sv', 'password': PASSWORD})
    assert r.status_code == 400 and r.get_json()['code'] == 'missing_field'


def test_duplicate_email_does_not_reveal_account(client, make_user):
    make_user('Ana', 'ana@ufg.edu.sv')
    nuevo = client.post('/api/register', json={'name': 'Beto', 'email': 'beto@ufg.edu.sv', 'password': PASSWORD})
    repetido = client.post('/api/register', json={'name': 'Otra', 'email': ' ANA@UFG.edu.sv ', 'password': 'OtraClave987'})
    # Misma respuesta para un correo nuevo y para uno que ya tiene cuenta.
    assert repetido.status_code == nuevo.status_code == 201
    assert repetido.get_json() == nuevo.get_json()
    # La cuenta original no cambió: la contraseña nueva no sirve.
    assert client.post('/api/login', json={'email': 'ana@ufg.edu.sv', 'password': 'OtraClave987'}).status_code == 401
    assert client.post('/api/login', json={'email': 'ana@ufg.edu.sv', 'password': PASSWORD}).status_code == 200


def test_wrong_password_and_rate_limit(client, make_user):
    make_user('Ana', 'ana@ufg.edu.sv')
    codigos = [client.post('/api/login', json={'email': 'ana@ufg.edu.sv', 'password': 'incorrecta'}).status_code
               for _ in range(12)]
    assert codigos[0] == 401
    assert 429 in codigos


def test_admin_email_gets_admin_role(make_user):
    admin = make_user('Admin', 'admin@ufg.edu.sv')
    assert admin.get('/api/me').get_json()['user']['is_admin'] is True


def test_protected_routes_need_token(client):
    r = client.get('/api/resources')
    assert r.status_code == 401
    assert r.get_json()['code'] == 'auth_required'
    r = client.get('/api/resources', headers={'Authorization': 'Bearer basura'})
    assert r.status_code == 401


def test_unknown_api_route_is_json_404(client):
    r = client.get('/api/no-existe')
    assert r.status_code == 404
    assert 'message' in r.get_json()


def test_frontend_does_not_expose_source(client):
    assert client.get('/app.py').status_code == 404
    assert client.get('/instance/database.db').status_code == 404
    assert client.get('/js/../app.py').status_code == 404


def test_security_headers(client):
    r = client.get('/api/health')
    assert r.headers['X-Content-Type-Options'] == 'nosniff'
    assert "script-src 'self'" in r.headers['Content-Security-Policy']


def test_only_institutional_domain(client):
    for correo in ('ana@gmail.com', 'ana@prueba.ufg.edu.sv', 'ana@ufg.edu.sv.evil.com', 'ana@xufg.edu.sv'):
        r = client.post('/api/register', json={'name': 'Ana', 'email': correo, 'password': PASSWORD})
        assert r.status_code == 400 and r.get_json()['code'] == 'email_domain', correo
    for correo in ('ana..lopez@ufg.edu.sv', '.ana@ufg.edu.sv', 'ana lopez@ufg.edu.sv', 'ana@'):
        r = client.post('/api/register', json={'name': 'Ana', 'email': correo, 'password': PASSWORD})
        assert r.status_code == 400 and r.get_json()['code'] == 'invalid_email', correo
    assert client.get('/api/auth/policy').get_json()['domains_label'] == '@ufg.edu.sv'


def test_email_is_normalized(client):
    # Mayúsculas, espacios y un carácter invisible (U+200B) se normalizan.
    r = client.post('/api/register', json={'name': 'Ana', 'email': '  Ana.Lopez\u200b@UFG.edu.SV ', 'password': PASSWORD})
    assert r.status_code == 201
    r = client.post('/api/login', json={'email': 'ana.lopez@ufg.edu.sv', 'password': PASSWORD})
    assert r.status_code == 200 and r.get_json()['user']['email'] == 'ana.lopez@ufg.edu.sv'


def test_password_policy(client):
    for clave in ('solofrases', '12345678901', 'password1', 'ana.lopez2026', 'a1' * 40):
        r = client.post('/api/register', json={'name': 'Ana', 'email': 'ana.lopez@ufg.edu.sv', 'password': clave})
        assert r.status_code == 400 and r.get_json()['code'] == 'weak_password', clave


def test_lockout_after_failures_and_same_answer_for_unknown_emails(app, client, make_user):
    make_user('Ana', 'ana@ufg.edu.sv')
    real = [client.post('/api/login', json={'email': 'ana@ufg.edu.sv', 'password': 'mala'}) for _ in range(5)]
    falso = [client.post('/api/login', json={'email': 'nadie@ufg.edu.sv', 'password': 'mala'}) for _ in range(5)]
    assert [r.status_code for r in real] == [r.status_code for r in falso] == [401] * 5
    assert real[0].get_json() == falso[0].get_json()
    # Bloqueado: ni con la contraseña correcta, y lo mismo para un correo inexistente.
    r = client.post('/api/login', json={'email': 'ana@ufg.edu.sv', 'password': PASSWORD})
    f = client.post('/api/login', json={'email': 'nadie@ufg.edu.sv', 'password': PASSWORD})
    assert r.status_code == f.status_code == 429
    assert r.get_json()['code'] == f.get_json()['code'] == 'account_locked'
    # Pasado el bloqueo se puede entrar y el contador se borra.
    with app.app_context():
        fila = db.session.get(LoginThrottle, 'ana@ufg.edu.sv')
        fila.locked_until = utcnow() - timedelta(seconds=1)
        db.session.commit()
    assert client.post('/api/login', json={'email': 'ana@ufg.edu.sv', 'password': PASSWORD}).status_code == 200
    with app.app_context():
        assert db.session.get(LoginThrottle, 'ana@ufg.edu.sv') is None


def test_email_verification_when_enabled(app, client):
    app.config['EMAIL_VERIFICATION'] = True
    mailer.outbox = []
    try:
        r = client.post('/api/register', json={'name': 'Admin', 'email': 'admin@ufg.edu.sv', 'password': PASSWORD})
        assert r.status_code == 201 and r.get_json()['verification_required'] is True
        assert len(mailer.outbox) == 1
        r = client.post('/api/login', json={'email': 'admin@ufg.edu.sv', 'password': PASSWORD})
        assert r.status_code == 403 and r.get_json()['code'] == 'email_unverified'
        with app.app_context():
            assert User.query.filter_by(email='admin@ufg.edu.sv').one().role == 'student'
        enlace = [p for p in mailer.outbox[0].get_content().split() if '/api/verify-email?token=' in p][0]
        r = client.get(enlace[enlace.index('/api/'):])
        assert r.status_code == 302 and 'verificacion=ok' in r.headers['Location']
        r = client.post('/api/login', json={'email': 'admin@ufg.edu.sv', 'password': PASSWORD})
        assert r.status_code == 200 and r.get_json()['user']['is_admin'] is True
        assert client.get('/api/verify-email?token=basura').headers['Location'].endswith('verificacion=invalida')
    finally:
        mailer.outbox = None


def test_preferences_are_saved_per_user(make_user):
    ana, beto = make_user('Ana'), make_user('Beto')
    assert ana.get('/api/profile/preferences').get_json()['preferences']['theme'] == 'system'
    r = ana.put('/api/profile/preferences', {'theme': 'dark', 'motion': 'reduced'})
    assert r.status_code == 200 and r.get_json()['preferences']['theme'] == 'dark'
    assert ana.get('/api/me').get_json()['user']['preferences']['motion'] == 'reduced'
    assert beto.get('/api/profile/preferences').get_json()['preferences']['theme'] == 'system'
    assert ana.put('/api/profile/preferences', {'theme': 'rosa'}).status_code == 400
    assert ana.put('/api/profile/preferences', {'color_fondo': 'x'}).status_code == 400
