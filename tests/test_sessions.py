"""Fase 3A: sesiones por dispositivo, renovación, verificación en dos pasos y bitácora."""

from __future__ import annotations

import io
from datetime import timedelta

import samples
from conftest import PASSWORD
from hub import twofactor
from hub.extensions import db
from hub.models import User, UserSession, utcnow
from hub.sessions import REFRESH_COOKIE

CHROME_ANDROID = 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36'
SAFARI_IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Safari/604.1'


def registrar(client, email='ana@ufg.edu.sv', name='Ana'):
    r = client.post('/api/register', json={'name': name, 'email': email, 'password': PASSWORD})
    assert r.status_code == 201


def entrar(app, email='ana@ufg.edu.sv', ua=CHROME_ANDROID):
    """Inicia sesión desde un «dispositivo» nuevo (cliente con su propia cookie)."""
    c = app.test_client()
    r = c.post('/api/login', json={'email': email, 'password': PASSWORD}, headers={'User-Agent': ua})
    assert r.status_code == 200, r.get_json()
    return c, r.get_json()


def auth(token):
    return {'Authorization': f'Bearer {token}'}


def cookie(c):
    k = c.get_cookie(REFRESH_COOKIE, path='/api/auth')
    return k.value if k else None


def codigo_siguiente(secret):
    """Código válido del intervalo siguiente (el actual ya lo gastó la activación)."""
    return twofactor.code_at(secret, twofactor.current_step() + 1)


def activar_2fa(c, token):
    r = c.post('/api/auth/2fa/setup', json={'password': PASSWORD}, headers=auth(token))
    assert r.status_code == 200, r.get_json()
    datos = r.get_json()
    assert datos['qr_svg'].startswith('<?xml') or '<svg' in datos['qr_svg']
    assert datos['uri'].startswith('otpauth://totp/')
    secreto = datos['secret']
    r = c.post('/api/auth/2fa/enable', json={'code': twofactor.code_at(secreto, twofactor.current_step())},
               headers=auth(token))
    assert r.status_code == 200, r.get_json()
    return secreto, r.get_json()['recovery_codes']


def test_totp_rfc6238_vector():
    # RFC 6238, apéndice B: secreto ASCII «12345678901234567890», t = 59 s -> 94287082 (6 últimos dígitos).
    secreto = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'
    assert twofactor.code_at(secreto, 1) == '287082'
    assert twofactor.match(secreto, '287 082', now=59) == 1
    assert twofactor.match(secreto, '287082', now=59, last_step=1) is None  # no se reutiliza
    assert twofactor.match(secreto, '000000', now=59) is None


def test_login_opens_session_per_device_and_refresh_rotates(app, client):
    registrar(client)
    cel, d1 = entrar(app, ua=CHROME_ANDROID)
    pc, d2 = entrar(app, ua=SAFARI_IPHONE)
    assert cookie(cel) and cookie(pc) and cookie(cel) != cookie(pc)

    lista = cel.get('/api/auth/sessions', headers=auth(d1['token'])).get_json()['sessions']
    assert {s['device'] for s in lista} == {'Chrome en Android', 'Safari en iPhone'}
    assert [s['current'] for s in lista].count(True) == 1

    viejo = cookie(cel)
    r = cel.post('/api/auth/refresh')
    assert r.status_code == 200 and r.get_json()['token']
    assert cookie(cel) != viejo
    assert cel.get('/api/me', headers=auth(r.get_json()['token'])).status_code == 200

    # Otra pestaña que renueva con la cookie vieja en el mismo instante: vale, sin cookie nueva.
    otra = app.test_client()
    otra.set_cookie(REFRESH_COOKIE, viejo, path='/api/auth')
    assert otra.post('/api/auth/refresh').status_code == 200

    # La misma cookie vieja pasado el margen: es una copia robada y se cierra la sesión.
    with app.app_context():
        s = UserSession.query.filter_by(device='Chrome en Android').one()
        s.rotated_at = utcnow() - timedelta(minutes=5)
        db.session.commit()
    r = otra.post('/api/auth/refresh')
    assert r.status_code == 401 and r.get_json()['code'] == 'session_closed'
    assert cel.post('/api/auth/refresh').status_code == 401
    assert cel.get('/api/me', headers=auth(d1['token'])).get_json()['code'] == 'session_closed'
    # La sesión del otro dispositivo sigue abierta.
    assert pc.get('/api/me', headers=auth(d2['token'])).status_code == 200


def test_logout_and_revoking_sessions(app, client):
    registrar(client)
    cel, d1 = entrar(app)
    pc, d2 = entrar(app, ua=SAFARI_IPHONE)
    tablet, d3 = entrar(app)

    assert cel.post('/api/auth/logout').status_code == 200
    assert cookie(cel) is None
    r = cel.get('/api/me', headers=auth(d1['token']))
    assert r.status_code == 401 and r.get_json()['code'] == 'session_closed'

    # Cerrar otra sesión desde la lista.
    lista = pc.get('/api/auth/sessions', headers=auth(d2['token'])).get_json()['sessions']
    otra = next(s for s in lista if not s['current'])
    assert pc.delete(f"/api/auth/sessions/{otra['id']}", headers=auth(d2['token'])).status_code == 200
    assert tablet.get('/api/me', headers=auth(d3['token'])).status_code == 401
    assert pc.delete(f"/api/auth/sessions/{otra['id']}", headers=auth(d2['token'])).status_code == 404

    # Cerrar todas menos la actual.
    _, d4 = entrar(app)
    r = pc.post('/api/auth/sessions/revoke-others', headers=auth(d2['token']))
    assert r.get_json()['closed'] == 1
    assert pc.get('/api/me', headers=auth(d4['token'])).status_code == 401
    assert len(pc.get('/api/auth/sessions', headers=auth(d2['token'])).get_json()['sessions']) == 1


def test_sessions_of_other_users_are_untouchable(app, client):
    registrar(client)
    registrar(client, 'beto@ufg.edu.sv', 'Beto')
    _, ana = entrar(app)
    beto_c, beto = entrar(app, 'beto@ufg.edu.sv')
    sid_ana = client.get('/api/auth/sessions', headers=auth(ana['token'])).get_json()['sessions'][0]['id']
    assert beto_c.delete(f'/api/auth/sessions/{sid_ana}', headers=auth(beto['token'])).status_code == 404
    assert client.get('/api/me', headers=auth(ana['token'])).status_code == 200


def test_password_change_closes_other_sessions(app, client):
    registrar(client)
    cel, d1 = entrar(app)
    pc, d2 = entrar(app)
    r = cel.post('/api/profile/password', json={'current_password': PASSWORD, 'new_password': 'OtraClave456'},
                 headers=auth(d1['token']))
    assert r.status_code == 200 and r.get_json()['closed_sessions'] == 1
    assert cel.get('/api/me', headers=auth(d1['token'])).status_code == 200
    assert pc.get('/api/me', headers=auth(d2['token'])).status_code == 401
    assert pc.post('/api/auth/refresh').status_code == 401


def test_idle_and_expired_sessions_close(app, client):
    registrar(client)
    cel, d1 = entrar(app)
    with app.app_context():
        s = UserSession.query.one()
        s.last_seen_at = utcnow() - timedelta(days=app.config['SESSION_IDLE_DAYS'] + 1)
        db.session.commit()
    assert cel.get('/api/me', headers=auth(d1['token'])).status_code == 401
    assert cel.post('/api/auth/refresh').status_code == 401


def test_old_tokens_without_session_are_rejected(app, client):
    from flask_jwt_extended import create_access_token
    registrar(client)
    with app.app_context():
        uid = User.query.one().id
        viejo = create_access_token(identity=str(uid))
    r = client.get('/api/me', headers=auth(viejo))
    assert r.status_code == 401 and r.get_json()['code'] == 'invalid_token'


def test_download_link_stops_working_after_logout(app, client):
    registrar(client)
    c, d = entrar(app)
    r = c.post('/api/resources', data={'title': 'Apuntes', 'author': 'Ana', 'category': 'Programación',
                                       'file': (io.BytesIO(samples.pdf()), 'apuntes.pdf')},
               headers=auth(d['token']), content_type='multipart/form-data')
    assert r.status_code == 201, r.get_json()
    rid = r.get_json()['resource']['id']
    url = c.post('/api/files/link', json={'path': f'/api/resources/{rid}/file'}, headers=auth(d['token'])).get_json()['url']
    assert c.get(url).status_code == 200
    c.post('/api/auth/logout')
    r = c.get(url)
    assert r.status_code == 403 and r.get_json()['code'] == 'link_expired'


def test_two_factor_login_with_code_and_recovery(app, client):
    registrar(client)
    c, d = entrar(app)
    assert c.post('/api/auth/2fa/setup', json={'password': 'mala1234'}, headers=auth(d['token'])).status_code == 400
    secreto, respaldo = activar_2fa(c, d['token'])
    assert len(respaldo) == 8 and all(len(x) == 9 and x[4] == '-' for x in respaldo)
    estado = c.get('/api/auth/2fa', headers=auth(d['token'])).get_json()
    assert estado == {'enabled': True, 'required': False, 'session_verified': True, 'recovery_left': 8}
    assert c.get('/api/me', headers=auth(d['token'])).get_json()['user']['two_factor_enabled'] is True

    # La contraseña ya no basta.
    otro = app.test_client()
    r = otro.post('/api/login', json={'email': 'ana@ufg.edu.sv', 'password': PASSWORD})
    datos = r.get_json()
    assert r.status_code == 200 and datos['two_factor_required'] and 'token' not in datos
    assert cookie(otro) is None
    reto = datos['challenge']

    r = otro.post('/api/login/2fa', json={'challenge': reto, 'code': '000000'})
    assert r.status_code == 401 and r.get_json()['code'] == 'invalid_code'
    r = otro.post('/api/login/2fa', json={'challenge': reto + 'x', 'code': codigo_siguiente(secreto)})
    assert r.status_code == 401 and r.get_json()['code'] == 'challenge_invalid'
    r = otro.post('/api/login/2fa', json={'challenge': reto, 'code': codigo_siguiente(secreto)})
    assert r.status_code == 200 and r.get_json()['token'] and cookie(otro)
    # El mismo código no sirve dos veces.
    r = app.test_client().post('/api/login/2fa', json={'challenge': reto, 'code': codigo_siguiente(secreto)})
    assert r.status_code == 401

    # Código de respaldo: vale una sola vez.
    r = app.test_client().post('/api/login/2fa', json={'challenge': reto, 'code': respaldo[0].lower()})
    assert r.status_code == 200
    r = app.test_client().post('/api/login/2fa', json={'challenge': reto, 'code': respaldo[0]})
    assert r.status_code == 401
    assert c.get('/api/auth/2fa', headers=auth(d['token'])).get_json()['recovery_left'] == 7

    # Desactivar pide contraseña y código.
    r = c.post('/api/auth/2fa/disable', json={'password': PASSWORD, 'code': '123456'}, headers=auth(d['token']))
    assert r.status_code == 400
    r = c.post('/api/auth/2fa/disable', json={'password': PASSWORD, 'code': respaldo[1]}, headers=auth(d['token']))
    assert r.status_code == 200
    assert 'token' in app.test_client().post('/api/login', json={'email': 'ana@ufg.edu.sv', 'password': PASSWORD}).get_json()


def test_two_factor_failures_count_towards_lockout(app, client):
    registrar(client)
    c, d = entrar(app)
    activar_2fa(c, d['token'])
    reto = app.test_client().post('/api/login', json={'email': 'ana@ufg.edu.sv', 'password': PASSWORD}).get_json()['challenge']
    for _ in range(app.config['LOGIN_MAX_FAILURES']):
        client.post('/api/login/2fa', json={'challenge': reto, 'code': '111111'})
    r = client.post('/api/login/2fa', json={'challenge': reto, 'code': '111111'})
    assert r.status_code == 429 and r.get_json()['code'] == 'account_locked'


def test_admin_panel_requires_two_factor(app, client):
    app.config['ADMIN_REQUIRE_2FA'] = True
    registrar(client, 'admin@ufg.edu.sv', 'Admin')
    c1, d1 = entrar(app, 'admin@ufg.edu.sv')
    c2, d2 = entrar(app, 'admin@ufg.edu.sv', ua=SAFARI_IPHONE)
    r = c1.get('/api/admin/overview', headers=auth(d1['token']))
    assert r.status_code == 403 and r.get_json()['code'] == 'two_factor_setup'

    secreto, respaldo = activar_2fa(c1, d1['token'])
    assert c1.get('/api/admin/overview', headers=auth(d1['token'])).status_code == 200
    # La otra sesión se abrió antes de activarla: tiene que confirmar con un código.
    r = c2.get('/api/admin/overview', headers=auth(d2['token']))
    assert r.status_code == 403 and r.get_json()['code'] == 'two_factor_step_up'
    assert c2.post('/api/auth/2fa/step-up', json={'code': '999999'}, headers=auth(d2['token'])).status_code == 400
    assert c2.post('/api/auth/2fa/step-up', json={'code': codigo_siguiente(secreto)},
                   headers=auth(d2['token'])).status_code == 200
    assert c2.get('/api/admin/overview', headers=auth(d2['token'])).status_code == 200
    # Un administrador no puede quitársela.
    r = c1.post('/api/auth/2fa/disable', json={'password': PASSWORD, 'code': respaldo[0]}, headers=auth(d1['token']))
    assert r.status_code == 403
    # Los estudiantes no entran aunque la tengan.
    registrar(client)
    c3, d3 = entrar(app)
    activar_2fa(c3, d3['token'])
    assert c3.get('/api/admin/overview', headers=auth(d3['token'])).get_json()['code'] == 'admin_only'


def test_audit_log(app, client):
    registrar(client, 'admin@ufg.edu.sv', 'Admin')
    registrar(client)
    client.post('/api/login', json={'email': 'nadie@ufg.edu.sv', 'password': 'Cualquiera1'})
    client.post('/api/login', json={'email': 'ana@ufg.edu.sv', 'password': 'Incorrecta1'})
    c, d = entrar(app)
    assert c.get('/api/admin/audit', headers=auth(d['token'])).status_code == 403  # sólo administradores
    c.post('/api/auth/sessions/revoke-others', headers=auth(d['token']))
    c.post('/api/auth/logout')
    ac, ad = entrar(app, 'admin@ufg.edu.sv')

    eventos = ac.get('/api/admin/audit', headers=auth(ad['token'])).get_json()['events']
    acciones = [e['action'] for e in eventos]
    for accion in ('register', 'login_failed', 'login_ok', 'sessions_revoked_others', 'logout'):
        assert accion in acciones, accion
    fallo = next(e for e in eventos if e['action'] == 'login_failed' and e['email'] == 'nadie@ufg.edu.sv')
    assert fallo['user_id'] is None and fallo['details']['reason'] == 'unknown_email'
    assert next(e for e in eventos if e['action'] == 'login_ok' and e['email'] == 'ana@ufg.edu.sv')['device'] == 'Chrome en Android'

    fallidos = ac.get('/api/admin/audit?group=failed', headers=auth(ad['token'])).get_json()['events']
    assert {e['action'] for e in fallidos} == {'login_failed'} and len(fallidos) == 2
    solo_ana = ac.get('/api/admin/audit?q=ana@', headers=auth(ad['token'])).get_json()['events']
    assert solo_ana and all(e['email'] == 'ana@ufg.edu.sv' for e in solo_ana)

    pagina = ac.get('/api/admin/audit?limit=2', headers=auth(ad['token'])).get_json()
    assert len(pagina['events']) == 2 and pagina['next_before']
    resto = ac.get(f"/api/admin/audit?limit=200&before={pagina['next_before']}", headers=auth(ad['token'])).get_json()
    assert resto['events'][0]['id'] < pagina['events'][-1]['id'] and resto['next_before'] is None

    resumen = ac.get('/api/admin/overview', headers=auth(ad['token'])).get_json()
    assert resumen['failed_logins_24h'] == 2 and resumen['active_sessions'] >= 1


def test_mobile_client_gets_refresh_token_in_body(client, make_user):
    make_user('Movil', 'movil@ufg.edu.sv')
    from conftest import PASSWORD
    h = {'X-Client': 'mobile'}
    r = client.post('/api/login', json={'email': 'movil@ufg.edu.sv', 'password': PASSWORD}, headers=h)
    assert r.status_code == 200
    datos = r.get_json()
    assert datos['refresh_token'] and 'hub_refresh' not in r.headers.get('Set-Cookie', '')
    r2 = client.post('/api/auth/refresh', json={'refresh_token': datos['refresh_token']}, headers=h)
    assert r2.status_code == 200 and r2.get_json()['refresh_token'] != datos['refresh_token']
    # Reintento con el mismo token dentro del periodo de gracia: recibe otro válido.
    r3 = client.post('/api/auth/refresh', json={'refresh_token': datos['refresh_token']}, headers=h)
    nuevo = r3.get_json()['refresh_token']
    assert r3.status_code == 200 and nuevo
    r4 = client.post('/api/auth/refresh', json={'refresh_token': nuevo}, headers=h)
    assert r4.status_code == 200
    assert client.post('/api/auth/logout', json={'refresh_token': r4.get_json()['refresh_token']}, headers=h).status_code == 200
    assert client.post('/api/auth/refresh', json={'refresh_token': r4.get_json()['refresh_token']}, headers=h).status_code == 401
