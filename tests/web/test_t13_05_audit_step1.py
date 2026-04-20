from __future__ import annotations

import csv
import importlib
import io
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


def _login(c: TestClient, username: str = "admin", password: str = "admin"):
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def _seed_audit_rows():
    import web_cabinet.app as appmod
    from web_cabinet.audit import write_audit
    from web_cabinet.db import connect

    conn = connect(appmod.settings.db_path)
    try:
        write_audit(
            conn,
            tenant_id="default",
            user_id=1,
            username="admin",
            role="Admin",
            action="pipeline.enqueue",
            object_type="job",
            object_id="JOB-001",
            data_version="dv_seed",
            run_id="run_seed_001",
            before={"status": "queued"},
            after={"status": "running"},
            status="OK",
        )
        write_audit(
            conn,
            tenant_id="default",
            user_id=1,
            username="admin",
            role="Admin",
            action="report.approve",
            object_type="report",
            object_id="rp_001",
            data_version="dv_seed",
            run_id="run_seed_approve",
            before={"status": "draft"},
            after={"status": "approved"},
            status="OK",
        )
    finally:
        conn.close()


def test_t13_05_api_audit_returns_canonical_schema_and_filters_by_group(client: TestClient):
    _login(client)
    _seed_audit_rows()

    r = client.get(
        "/api/audit",
        params={"action_group": "run", "run_id": "run_seed_001", "limit": 50},
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["schema_version"] == 2
    rows = payload["rows"]
    assert rows, "expected filtered audit rows"
    row = rows[0]
    assert row["action"] == "pipeline.enqueue"
    assert row["action_group"] == "run"
    assert row["schema_version"] == 2
    assert row["when"]
    assert row["who"]["username"] == "admin"
    assert row["what"]["action"] == "pipeline.enqueue"
    assert row["object"]["ref"] == "job:JOB-001"
    assert row["before"]["status"] == "queued"
    assert row["after"]["status"] == "running"


def test_t13_05_audit_export_csv_respects_filters(client: TestClient):
    _login(client)
    _seed_audit_rows()

    r = client.get("/api/audit/export.csv", params={"action_group": "approve", "limit": 50})
    assert r.status_code == 200, r.text
    assert "attachment" in (r.headers.get("content-disposition") or "").lower()

    reader = csv.DictReader(io.StringIO(r.text))
    rows = list(reader)
    assert rows, "expected csv rows"
    assert all(row["action_group"] == "approve" for row in rows)
    assert any(row["action"] == "report.approve" for row in rows)
    assert {"schema_version", "before_json", "after_json", "object_ref", "run_id"}.issubset(reader.fieldnames or [])


def test_t13_05_invalid_audit_limit_returns_human_readable_error(client: TestClient):
    _login(client)
    r = client.get("/api/audit", params={"limit": "oops"})
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["error"] == "invalid_audit_limit"
    assert "limit должен быть целым числом" in body["detail"]["detail"]
