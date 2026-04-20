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


def _login(c: TestClient, username: str = "operator", password: str = "operator"):
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_contracts_page_shows_catalog_and_templates(client: TestClient):
    _login(client)
    resp = client.get("/contracts")
    assert resp.status_code == 200
    assert "Data Contracts 2.0" in resp.text
    assert "dm_animals" in resp.text
    assert "configs/mappings/templates/selex/animals.yaml" in resp.text
    assert "qc.cross_dataset_links" in resp.text


def test_contracts_page_filters_by_source_system(client: TestClient):
    _login(client)
    resp = client.get("/contracts?source=selex")
    assert resp.status_code == 200
    assert "configs/mappings/templates/selex/animals.yaml" in resp.text
    assert "configs/mappings/templates/1c/animals.yaml" not in resp.text


def test_contracts_api_returns_filtered_catalog(client: TestClient):
    _login(client)
    resp = client.get("/api/contracts/catalog?domain=master_data&source=СЕЛЭКС")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["filtered_count"] >= 1
    assert any(row["dataset"] == "dm_animals" for row in payload["datasets"])
    assert all(row["domain"] == "master_data" for row in payload["datasets"])
