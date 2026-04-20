from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.infra.web_db import connect, create_user_v2, get_settings
from web_cabinet.auth import hash_password


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
    os.environ['GENOMEAI_DEPLOY_PROFILE'] = 'test'
    os.environ['GENOMEAI_RUNTIME_STORAGE_BACKEND'] = 'sqlite'

    import web_cabinet.app as appmod
    importlib.reload(appmod)
    with TestClient(appmod.app) as c:
        yield c


def test_t34_02_admin_auth_diagnostics_and_failed_attempts(client: TestClient) -> None:
    bad_login = client.post(
        '/api/app/v1/auth/login',
        json={'username': 'admin', 'password': 'wrong', 'tenant_id': 'default', 'client_kind': 'android'},
    )
    assert bad_login.status_code == 401

    login = client.post(
        '/api/app/v1/auth/login',
        json={'username': 'admin', 'password': 'admin', 'tenant_id': 'default', 'client_kind': 'android'},
    )
    assert login.status_code == 200, login.text
    body = login.json()
    access_token = body['tokens']['access_token']
    session_id = body['session']['session_id']

    runtime_diag = client.get('/api/app/v1/auth/admin/runtime-storage', headers={'Authorization': f'Bearer {access_token}'})
    assert runtime_diag.status_code == 200, runtime_diag.text
    assert runtime_diag.json()['backend'] == 'sqlite'

    sessions = client.get('/api/app/v1/auth/admin/sessions', headers={'Authorization': f'Bearer {access_token}'})
    assert sessions.status_code == 200, sessions.text
    sessions_body = sessions.json()
    assert sessions_body['backend'] == 'sqlite'
    assert any(item['session']['session_id'] == session_id for item in sessions_body['items'])

    detail = client.get(f'/api/app/v1/auth/admin/sessions/{session_id}', headers={'Authorization': f'Bearer {access_token}'})
    assert detail.status_code == 200, detail.text
    detail_body = detail.json()
    assert detail_body['session']['session_id'] == session_id
    assert 'refresh_lineage' in detail_body

    failed = client.get('/api/app/v1/auth/admin/failed-attempts?username=admin', headers={'Authorization': f'Bearer {access_token}'})
    assert failed.status_code == 200, failed.text
    failed_body = failed.json()
    assert failed_body['backend'] == 'sqlite'
    assert any(item['reason_code'] == 'invalid_credentials' for item in failed_body['items'])
