from __future__ import annotations

import importlib
import os
import time
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
    os.environ["GENOMEAI_JOB_TIMEOUT_SEC"] = "10"

    import web_cabinet.app as appmod
    importlib.reload(appmod)

    with TestClient(appmod.app) as c:
        yield c


def _login(c: TestClient, username: str = "operator", password: str = "operator"):
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_auto_retry_is_scheduled_and_visible_in_api_and_ui(client: TestClient):
    from web_cabinet.db import connect, create_job, get_job, init_db
    from web_cabinet.worker import JobWorker

    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    conn = connect(db_path)
    init_db(conn)
    job_id = create_job(
        conn,
        kind="qc",
        tenant_id="default",
        user_id=1,
        user="operator",
        command="python -m genomeai",
        args={"argv": ["qc2", "--data-version", "missing_dv", "--artifacts", os.environ["GENOMEAI_ARTIFACTS_ROOT"]]},
        log_path=Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "logs" / "job_auto_retry.log",
        max_attempts=2,
    )
    conn.close()

    worker = JobWorker()
    assert worker.run_once() is True

    conn = connect(db_path)
    jobs = [dict(r) for r in conn.execute("SELECT * FROM jobs ORDER BY id ASC").fetchall()]
    assert len(jobs) == 2
    first, second = jobs
    assert first["id"] == job_id
    assert first["status"] == "failed"
    assert second["retry_of_job_id"] == job_id
    assert second["retry_source"] == "auto"
    assert second["status"] == "queued"
    assert second["next_attempt_at"]

    audit = conn.execute(
        "SELECT action, object_id FROM audit_log WHERE action='pipeline.auto_retry_scheduled' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert audit is not None
    assert audit[1] == str(second["id"])

    _login(client)
    r_api = client.get("/api/jobs", params={"status": "queued", "pipeline": "qc", "q": "missing_dv"})
    assert r_api.status_code == 200
    payload = r_api.json()
    assert len(payload["jobs"]) == 1
    assert payload["jobs"][0]["id"] == second["id"]
    assert payload["jobs"][0]["retry_source"] == "auto"

    r_ui = client.get("/jobs", params={"status": "queued", "pipeline": "qc", "q": "missing_dv"})
    assert r_ui.status_code == 200
    assert "retry" in r_ui.text.lower()
    assert "auto" in r_ui.text


def test_retry_family_and_delayed_attempt_execution(client: TestClient):
    from web_cabinet.db import connect, create_job, get_job, init_db
    from web_cabinet.worker import JobWorker

    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    conn = connect(db_path)
    init_db(conn)
    job_id = create_job(
        conn,
        kind="qc",
        tenant_id="default",
        user_id=1,
        user="operator",
        command="python -m genomeai",
        args={"argv": ["qc2", "--data-version", "missing_dv_2", "--artifacts", os.environ["GENOMEAI_ARTIFACTS_ROOT"]]},
        log_path=Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "logs" / "job_auto_retry_family.log",
        max_attempts=2,
    )
    conn.close()

    worker = JobWorker()
    assert worker.run_once() is True
    time.sleep(1.1)
    assert worker.run_once() is True

    conn = connect(db_path)
    jobs = [dict(r) for r in conn.execute("SELECT * FROM jobs ORDER BY id ASC").fetchall()]
    conn.close()
    assert len(jobs) == 2
    assert jobs[0]["status"] == "failed"
    assert jobs[1]["status"] == "failed"
    assert jobs[1]["retry_source"] == "auto"

    _login(client)
    r = client.get(f"/jobs/{jobs[1]['id']}")
    assert r.status_code == 200
    assert "Семейство попыток" in r.text
    assert f">{jobs[0]['id']}<" in r.text
    assert f">{jobs[1]['id']}<" in r.text
    assert "retry_source" in r.text
