from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    os.environ["GENOMEAI_PROJECT_ROOT"] = str(repo_root)
    os.environ["GENOMEAI_WEB_STORAGE"] = str(tmp_path / "web_storage")
    os.environ["GENOMEAI_ARTIFACTS_ROOT"] = str(tmp_path / "artifacts")
    os.environ["GENOMEAI_WEB_DISABLE_WORKER"] = "1"
    os.environ["GENOMEAI_WEB_SECRET"] = "test-secret-long-enough"
    os.environ["GENOMEAI_DEPLOY_PROFILE"] = "test"
    os.environ.pop("GENOMEAI_RUNTIME_STORAGE_BACKEND", None)
    os.environ.pop("GENOMEAI_RUNTIME_POSTGRES_DSN", None)
    os.environ.pop("GENOMEAI_RUNTIME_POSTGRES_DSN_FILE", None)

    import web_cabinet.app as appmod
    importlib.reload(appmod)

    with TestClient(appmod.app) as c:
        yield c


def _login(c: TestClient) -> None:
    resp = c.post("/login", data={"username": "viewer", "password": "viewer"}, follow_redirects=False)
    assert resp.status_code in (302, 303)


def test_readyz_reports_storage_headers(client: TestClient) -> None:
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.headers["X-GenomeAI-Storage-Backend"] == "sqlite"
    assert resp.headers["X-GenomeAI-Storage-Profile"] == "test"
    assert resp.headers["X-GenomeAI-Storage-Migration-Status"] == "sqlite_compat_runtime"


def test_observability_and_runtime_storage_endpoint_include_backend(client: TestClient) -> None:
    _login(client)
    obs = client.get("/api/observability")
    assert obs.status_code == 200
    body = obs.json()
    assert body["runtime_storage"]["backend"] == "sqlite"
    assert body["runtime_storage"]["profile"] == "test"

    storage = client.get("/api/runtime-storage")
    assert storage.status_code == 200
    payload = storage.json()
    assert payload["backend"] == "sqlite"
    assert payload["migration_status"] == "sqlite_compat_runtime"
