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
    monkeypatch.setenv('GENOMEAI_WEB_SECRET', 'test-secret-123456')
    monkeypatch.setenv('GENOMEAI_DEPLOY_PROFILE', 'dev')
    monkeypatch.delenv('GENOMEAI_INTERNAL_WEB_LOGIN_MODE', raising=False)

    import web_cabinet.app as appmod
    importlib.reload(appmod)
    with TestClient(appmod.app) as c:
        yield c


def _login(c: TestClient, username: str, password: str) -> None:
    r = c.post('/login', data={'username': username, 'password': password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_t34_07_readyz_and_observability_expose_lockdown_snapshot(client: TestClient) -> None:
    _login(client, 'admin', 'admin')
    ready = client.get('/readyz')
    obs = client.get('/api/observability')
    profile = client.get('/api/production-profile')
    page = client.get('/admin/production-profile')

    assert ready.headers['X-GenomeAI-Production-Lockdown'] in {'0', '1'}
    assert 'X-GenomeAI-Internal-Web-Login' in ready.headers
    assert obs.status_code == 200
    assert 'production_lockdown' in obs.json()
    assert profile.status_code == 200
    payload = profile.json()
    assert 'forbidden_tails_status' in payload
    assert 'compatibility_flags' in payload
    assert page.status_code == 200
    assert 'Production profile diagnostics' in page.text


def test_t34_07_login_page_respects_explicit_lockdown_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv('GENOMEAI_PROJECT_ROOT', str(repo_root))
    monkeypatch.setenv('GENOMEAI_WEB_STORAGE', str(tmp_path / 'web_storage'))
    monkeypatch.setenv('GENOMEAI_ARTIFACTS_ROOT', str(tmp_path / 'artifacts'))
    monkeypatch.setenv('GENOMEAI_WEB_DISABLE_WORKER', '1')
    monkeypatch.setenv('GENOMEAI_WEB_SECRET', 'adult-secret-123456')
    monkeypatch.setenv('GENOMEAI_DEPLOY_PROFILE', 'dev')
    monkeypatch.setenv('GENOMEAI_INTERNAL_WEB_LOGIN_MODE', 'disabled')

    import web_cabinet.app as appmod
    importlib.reload(appmod)
    with TestClient(appmod.app) as c:
        resp = c.get('/login')
        assert resp.status_code == 404
        assert 'auth.internal_web_login_disabled' in resp.text
