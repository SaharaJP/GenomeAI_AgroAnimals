from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web_cabinet.auth import hash_password
from core.infra.web_db import connect, create_user_v2, get_settings


@pytest.fixture()
def client(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    storage = tmp_path / 'web_storage'
    artifacts = tmp_path / 'artifacts'
    os.environ['GENOMEAI_PROJECT_ROOT'] = str(repo_root)
    os.environ['GENOMEAI_WEB_STORAGE'] = str(storage)
    os.environ['GENOMEAI_ARTIFACTS_ROOT'] = str(artifacts)
    os.environ['GENOMEAI_WEB_DISABLE_WORKER'] = '1'
    os.environ['GENOMEAI_WEB_SECRET'] = 'test-secret'

    import web_cabinet.app as appmod
    importlib.reload(appmod)

    with TestClient(appmod.app) as c:
        yield c


def test_t32_03_android_bearer_and_refresh_flow(client: TestClient) -> None:
    login = client.post(
        '/api/app/v1/auth/login',
        json={
            'username': 'admin',
            'password': 'admin',
            'tenant_id': 'default',
            'client_kind': 'android',
            'device': {'device_id': 'android-1', 'device_label': 'Pixel', 'platform': 'android', 'app_version': '1.0.0'},
        },
    )
    assert login.status_code == 200, login.text
    body = login.json()
    assert body['schema'] == 'genomeai.api.auth.login.v1'
    access_token = body['tokens']['access_token']
    refresh_token = body['tokens']['refresh_token']
    assert body['session']['client_kind'] == 'android'
    assert body['session']['device']['device_id'] == 'android-1'

    me = client.get('/api/app/v1/auth/me', headers={'Authorization': f'Bearer {access_token}'})
    assert me.status_code == 200, me.text
    me_body = me.json()
    assert me_body['schema'] == 'genomeai.api.auth.me.v1'
    assert me_body['user']['role'] == 'Admin'
    assert me_body['session']['auth_transport'] in ('bearer', 'hybrid')

    alerts = client.get('/api/app/v1/alerts', headers={'Authorization': f'Bearer {access_token}'})
    assert alerts.status_code == 200, alerts.text

    sessions = client.get('/api/app/v1/auth/sessions', headers={'Authorization': f'Bearer {access_token}'})
    assert sessions.status_code == 200, sessions.text
    sessions_body = sessions.json()
    assert sessions_body['schema'] == 'genomeai.api.auth.sessions.list.v1'
    assert any(item['device']['device_id'] == 'android-1' for item in sessions_body['items'])

    refreshed = client.post(
        '/api/app/v1/auth/refresh',
        json={'refresh_token': refresh_token, 'device': {'app_version': '1.0.1'}},
    )
    assert refreshed.status_code == 200, refreshed.text
    refreshed_body = refreshed.json()
    assert refreshed_body['schema'] == 'genomeai.api.auth.refresh.v1'
    new_access = refreshed_body['tokens']['access_token']
    assert new_access != access_token

    old_me = client.get('/api/app/v1/auth/me', headers={'Authorization': f'Bearer {access_token}'})
    assert old_me.status_code == 401

    logout = client.post('/api/app/v1/auth/logout', headers={'Authorization': f'Bearer {new_access}'}, json={'all_devices': False})
    assert logout.status_code == 200, logout.text
    logout_body = logout.json()
    assert logout_body['schema'] == 'genomeai.api.auth.logout.v1'
    assert len(logout_body['revoked_session_ids']) == 1

    after_logout = client.get('/api/app/v1/auth/me', headers={'Authorization': f'Bearer {new_access}'})
    assert after_logout.status_code == 401


def test_t32_03_scope_boundaries_and_web_cookie_session(client: TestClient) -> None:
    settings = get_settings()
    conn = connect(settings.db_path)
    try:
        create_user_v2(
            conn,
            tenant_id='default',
            username='scoped_user',
            password_hash=hash_password('scoped_user'),
            role='Operator',
            allowed_farm_ids_json='["farm_allowed"]',
            allowed_site_ids_json='["site_allowed"]',
        )
    finally:
        conn.close()

    login = client.post(
        '/api/app/v1/auth/login',
        json={
            'username': 'scoped_user',
            'password': 'scoped_user',
            'tenant_id': 'default',
            'client_kind': 'web',
            'issue_web_session_cookie': True,
            'active_farm_id': 'farm_allowed',
            'active_site_id': 'site_allowed',
            'device': {'device_label': 'Chrome', 'platform': 'browser'},
        },
    )
    assert login.status_code == 200, login.text
    login_body = login.json()
    assert login_body['scope']['active_farm_id'] == 'farm_allowed'
    assert login_body['session']['client_kind'] == 'web'

    me_cookie = client.get('/api/app/v1/auth/me')
    assert me_cookie.status_code == 200, me_cookie.text
    me_cookie_body = me_cookie.json()
    assert me_cookie_body['session']['current'] is True
    assert me_cookie_body['scope']['allowed_farm_ids'] == ['farm_allowed']

    forbidden_scope = client.get('/api/app/v1/auth/me', headers={'X-Farm-ID': 'farm_denied'})
    assert forbidden_scope.status_code == 403


def test_t32_03_legacy_login_uses_same_server_session_model(client: TestClient) -> None:
    login = client.post('/login', data={'username': 'viewer', 'password': 'viewer'}, follow_redirects=False)
    assert login.status_code in (302, 303)

    me_cookie = client.get('/api/app/v1/auth/me')
    assert me_cookie.status_code == 200, me_cookie.text
    body = me_cookie.json()
    assert body['user']['username'] == 'viewer'
    assert body['session']['session_id']
    assert body['session']['client_kind'] == 'web'
