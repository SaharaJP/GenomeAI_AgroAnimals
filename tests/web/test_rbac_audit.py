from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path):
    # Set env BEFORE importing web app (settings are evaluated at import time)
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


def _login(c: TestClient, username: str, password: str):
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_viewer_forbidden_on_pipeline_run(client: TestClient):
    _login(client, "viewer", "viewer")
    r = client.post("/qc/run", data={"data_version": "dv_test"}, follow_redirects=False)
    assert r.status_code == 403


def test_operator_can_enqueue_and_audit_records(client: TestClient, tmp_path: Path):
    _login(client, "operator", "operator")
    r = client.post("/qc/run", data={"data_version": "dv_test"}, follow_redirects=False)
    assert r.status_code in (302, 303)

    # create dummy artifact to download
    art = Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"]) / "dummy.txt"
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text("hello", encoding="utf-8")

    r2 = client.get("/download", params={"path": "artifacts/dummy.txt"})
    assert r2.status_code == 200

    # audit view requires admin, so login as admin in same client (new session)
    client.get("/logout")
    _login(client, "admin", "admin")

    ra = client.get("/api/audit")
    assert ra.status_code == 200
    rows = ra.json()["rows"]
    actions = [x["action"] for x in rows]
    assert "pipeline.enqueue" in actions
    assert "export.download" in actions


def test_admin_can_upload_config_and_is_audited(client: TestClient, tmp_path: Path):
    _login(client, "admin", "admin")

    # upload override
    r = client.post(
        "/configs/upload",
        data={"target_rel_path": "configs/qc_rules_v2.yaml"},
        files={"file": ("qc_rules_v2.yaml", b"rules: []\n", "text/yaml")},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    ra = client.get("/api/audit", params={"action": "configs.upload"})
    assert ra.status_code == 200
    rows = ra.json()["rows"]
    assert len(rows) >= 1
    assert rows[0]["object_id"] == "configs/qc_rules_v2.yaml"
