from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv('GENOMEAI_PROJECT_ROOT', str(repo_root))
    monkeypatch.setenv('GENOMEAI_WEB_STORAGE', str(tmp_path / 'web_storage'))
    monkeypatch.setenv('GENOMEAI_ARTIFACTS_ROOT', str(tmp_path / 'artifacts'))
    monkeypatch.setenv('GENOMEAI_WEB_DISABLE_WORKER', '1')
    monkeypatch.setenv('GENOMEAI_WEB_SECRET', 'test-secret-ops')
    monkeypatch.setenv('GENOMEAI_DEPLOY_PROFILE', 'dev')

    import web_cabinet.app as appmod
    importlib.reload(appmod)
    with TestClient(appmod.app) as c:
        yield c


def _login(c: TestClient) -> None:
    r = c.post('/login', data={'username': 'admin', 'password': 'admin'}, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_t34_09_operability_endpoints_and_readyz_headers(client: TestClient) -> None:
    _login(client)
    ready = client.get('/readyz')
    metrics = client.get('/api/metrics-contract')
    operability = client.get('/api/operability')
    page = client.get('/admin/operability')

    assert ready.status_code == 200
    assert 'X-GenomeAI-Auth-Backend' in ready.headers
    assert 'X-GenomeAI-Auth-Mode' in ready.headers
    assert metrics.status_code == 200
    assert 'required_correlation_ids' in metrics.json()
    assert operability.status_code == 200
    payload = operability.json()
    assert 'release' in payload and 'supportability' in payload and 'observability' in payload
    assert page.status_code == 200
    assert 'Production operability' in page.text
