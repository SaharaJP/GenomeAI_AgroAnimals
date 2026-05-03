from __future__ import annotations

import csv
import importlib
import io
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


def test_t12_01_tasks_export_csv_and_audit(client: TestClient):
    # Use admin to have both tasks.view and audit.view
    _login(client, "admin", "admin")

    # Create 2 tasks of different domains
    r1 = client.post(
        "/api/tasks_v1",
        json={"task_type": "qc_followup", "title": "QC followup", "domain": "qc", "priority": 2},
    )
    assert r1.status_code == 200
    qc_id = r1.json()["task_id"]
    r2 = client.post(
        "/api/tasks_v1",
        json={"task_type": "mastitis_control", "title": "Health followup", "domain": "health", "priority": 3},
    )
    assert r2.status_code == 200

    # Export only qc domain
    r = client.get("/api/tasks_v1/export", params={"domain": "qc", "limit": 500})
    assert r.status_code == 200
    assert "attachment" in (r.headers.get("content-disposition") or "").lower()
    assert (r.headers.get("x-run-id") or "").strip(), "expected X-Run-Id header"

    # Parse CSV
    text = r.content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    assert rows, "expected at least one row in export"
    assert all((row.get("domain") == "qc") for row in rows)
    assert any(row.get("task_id") == qc_id for row in rows)

    # Audit log should include tasks_v1.export
    rows_a = _audit_rows(client, "tasks_v1.export")
    assert rows_a, "expected at least one tasks_v1.export audit row"
    ok = False
    for rr in rows_a:
        aj = rr.get("after_json")
        if not aj:
            continue
        try:
            after = json.loads(aj)
        except Exception:
            continue
        if after.get("count") is not None:
            ok = True
            break
    assert ok, "expected tasks_v1.export audit rows to contain after_json with 'count'"
