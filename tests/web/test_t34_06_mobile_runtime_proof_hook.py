from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


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


def test_t34_06_mobile_runtime_proof_hook_returns_current_session_evidence(client: TestClient) -> None:
    login = client.post(
        '/api/app/v1/auth/login',
        json={
            'username': 'admin',
            'password': 'admin',
            'tenant_id': 'default',
            'client_kind': 'android',
            'device': {'device_id': 'android-proof-1', 'device_label': 'Pixel', 'platform': 'android', 'app_version': '0.1.0'},
        },
    )
    assert login.status_code == 200, login.text
    body = login.json()
    access_token = body['tokens']['access_token']
    session_id = body['session']['session_id']

    proof = client.get('/api/app/v1/auth/mobile/runtime-proof', headers={'Authorization': f'Bearer {access_token}'})
    assert proof.status_code == 200, proof.text
    proof_body = proof.json()
    assert proof_body['schema'] == 'genomeai.api.auth.mobile.runtime_proof.v1'
    assert proof_body['session']['session_id'] == session_id
    assert proof_body['session']['client_kind'] == 'android'
    assert proof_body['request_auth_transport'] in ('bearer', 'hybrid')
    assert proof_body['refresh_lineage_count'] >= 1
    assert proof_body['revoke_status'] == 'active'

    refreshed = client.post(
        '/api/app/v1/auth/refresh',
        json={'refresh_token': body['tokens']['refresh_token'], 'device': {'device_id': 'android-proof-1', 'platform': 'android', 'app_version': '0.1.1'}},
    )
    assert refreshed.status_code == 200, refreshed.text
    new_access = refreshed.json()['tokens']['access_token']
    proof_after_refresh = client.get('/api/app/v1/auth/mobile/runtime-proof', headers={'Authorization': f'Bearer {new_access}'})
    assert proof_after_refresh.status_code == 200, proof_after_refresh.text
    assert proof_after_refresh.json()['refresh_lineage_count'] >= 2
