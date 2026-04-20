from __future__ import annotations

import importlib
import os
import threading
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


def test_create_job_infers_refs_and_jobs_page(client: TestClient):
    from web_cabinet.db import connect, create_job, init_db

    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    conn = connect(db_path)
    init_db(conn)
    job_id = create_job(
        conn,
        kind="report",
        tenant_id="default",
        user_id=1,
        user="operator",
        command="python -m genomeai",
        args={
            "argv": [
                "report",
                "--data-version",
                "dv_demo",
                "--qc-run",
                "qc_1",
                "--model-version",
                "mdl_1",
                "--scoring-run",
                "scr_1",
                "--report-version",
                "rep_1",
            ]
        },
        log_path=Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "logs" / "job_report.log",
    )
    row = conn.execute(
        "SELECT pipeline_key, data_version, qc_run, model_version, scoring_run, report_version, run_id FROM jobs WHERE id=?",
        (job_id,),
    ).fetchone()
    assert row is not None
    assert row[0] == "report"
    assert row[1] == "dv_demo"
    assert row[2] == "qc_1"
    assert row[3] == "mdl_1"
    assert row[4] == "scr_1"
    assert row[5] == "rep_1"
    assert row[6] == "rep_1"
    conn.close()

    _login(client)
    r = client.get("/jobs")
    assert r.status_code == 200
    assert "Очередь работ" in r.text
    assert "dv_demo" in r.text
    assert "rep_1" in r.text


def test_cancel_running_job_via_api(client: TestClient):
    from web_cabinet.db import connect, create_job, get_job, init_db
    from web_cabinet.worker import JobWorker

    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    conn = connect(db_path)
    init_db(conn)
    job_id = create_job(
        conn,
        kind="sleep",
        tenant_id="default",
        user_id=1,
        user="operator",
        command="python -m genomeai",
        args={"argv": ["sleep", "--seconds", "5"]},
        log_path=Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "logs" / "job_sleep.log",
    )
    conn.close()

    worker = JobWorker()
    th = threading.Thread(target=worker.run_once, daemon=True)
    th.start()
    time.sleep(1.0)

    _login(client)
    rcancel = client.post(f"/api/jobs/{job_id}/cancel")
    assert rcancel.status_code == 200, rcancel.text

    th.join(timeout=15)
    assert not th.is_alive()

    conn = connect(db_path)
    job = get_job(conn, job_id)
    conn.close()
    assert job is not None
    assert job["status"] == "cancelled"
    assert int(job["exit_code"] or 0) in (0, 130, -15)
    assert job["cancel_requested_at"]


def test_retry_failed_job_creates_new_attempt(client: TestClient):
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
        log_path=Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "logs" / "job_fail.log",
    )
    conn.close()

    worker = JobWorker()
    assert worker.run_once() is True

    _login(client)
    rretry = client.post(f"/api/jobs/{job_id}/retry")
    assert rretry.status_code == 200, rretry.text
    new_job_id = int(rretry.json()["job"]["id"])
    assert new_job_id != job_id

    conn = connect(db_path)
    new_job = get_job(conn, new_job_id)
    conn.close()
    assert new_job is not None
    assert new_job["retry_of_job_id"] == job_id
    assert int(new_job["attempt_no"] or 0) == 1
    assert new_job["status"] == "queued"
