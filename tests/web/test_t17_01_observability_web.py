from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    storage = tmp_path / "web_storage"
    artifacts = tmp_path / "artifacts"
    os.environ["GENOMEAI_PROJECT_ROOT"] = str(repo_root)
    os.environ["GENOMEAI_WEB_STORAGE"] = str(storage)
    os.environ["GENOMEAI_ARTIFACTS_ROOT"] = str(artifacts)
    os.environ["GENOMEAI_WEB_DISABLE_WORKER"] = "1"
    os.environ["GENOMEAI_WEB_SECRET"] = "test-secret"

    import web_cabinet.app as appmod
    importlib.reload(appmod)

    with TestClient(appmod.app) as c:
        yield c



def test_t17_01_login_audit_inherits_request_id(client: TestClient) -> None:
    request_id = "REQ-LOGIN-T17"
    response = client.post(
        "/login",
        data={"username": "viewer", "password": "viewer"},
        headers={"X-Request-ID": request_id},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)
    assert response.headers["x-request-id"] == request_id

    from web_cabinet.db import connect, get_settings

    conn = connect(get_settings().db_path)
    try:
        row = conn.execute(
            "SELECT action, request_id FROM audit_log WHERE action='auth.login' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["request_id"] == request_id



def test_t17_01_observability_snapshot_exposes_requests_and_jobs(client: TestClient) -> None:
    login = client.post("/login", data={"username": "viewer", "password": "viewer"}, follow_redirects=False)
    assert login.status_code in (302, 303)

    first = client.get("/api/observability", headers={"X-Request-ID": "REQ-OBS-T17"})
    assert first.status_code == 200
    assert first.headers["x-request-id"] == "REQ-OBS-T17"

    response = client.get("/api/observability", headers={"X-Request-ID": "REQ-OBS-T17-2"})
    assert response.status_code == 200
    payload = response.json()
    assert "uptime_sec" in payload
    assert "jobs" in payload
    assert "requests" in payload
    assert "routes" in payload["requests"]
    assert payload["requests"]["routes"]["GET /api/observability"]["total"] >= 1
    assert response.headers["x-request-id"] == "REQ-OBS-T17-2"
