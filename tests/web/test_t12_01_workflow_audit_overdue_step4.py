from __future__ import annotations

import importlib
import json
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


def _login(c: TestClient, username: str, password: str):
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def _audit_rows(client: TestClient, action: str) -> list[dict]:
    r = client.get("/api/audit", params={"action": action})
    assert r.status_code == 200
    return list(r.json().get("rows") or [])


def test_t12_01_overdue_endpoint_and_audit(client: TestClient):
    # Use admin to have both tasks.* and audit.view
    _login(client, "admin", "admin")

    # Create an overdue task (explicit due_at in the past)
    payload = {
        "task_type": "qc_check",
        "title": "Overdue QC check",
        "domain": "qc",
        "priority": 2,
        "assignee_team": None,
        "due_at": "2000-01-01T00:00:00+00:00",
    }
    r_create = client.post("/api/tasks_v1", json=payload)
    assert r_create.status_code == 200
    task_id = r_create.json()["task_id"]

    # Overdue quick view should include it
    r_over = client.get("/api/tasks_v1/overdue", params={"limit": 50})
    assert r_over.status_code == 200
    body = r_over.json()
    assert "run_id" in body and body["run_id"]
    items = body.get("items") or []
    assert any(str(x.get("task_id")) == str(task_id) for x in items)

    # Audit should include create and overdue_view
    rows_create = _audit_rows(client, "tasks_v1.create")
    assert any(r.get("object_id") == task_id for r in rows_create)

    rows_over = _audit_rows(client, "tasks_v1.overdue_view")
    assert rows_over, "expected at least one overdue_view audit row"

    ok = False
    for rr in rows_over:
        aj = rr.get("after_json")
        if not aj:
            continue
        try:
            after = json.loads(aj)
        except Exception:
            continue
        if "count" in after:
            ok = True
            break
    assert ok, "expected overdue_view audit rows to contain after_json with 'count'"
