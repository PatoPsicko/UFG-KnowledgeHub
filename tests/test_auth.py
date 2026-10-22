from conftest import PASSWORD


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


def test_duplicate_email_case_insensitive(client, make_user):
    make_user('Ana', 'ana@ufg.edu.sv')
    r = client.post('/api/register', json={'name': 'Otra', 'email': 'ANA@ufg.edu.sv', 'password': PASSWORD})
    assert r.status_code == 409


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
