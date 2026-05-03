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
    os.environ["GENOMEAI_JOB_TIMEOUT_SEC"] = "15"

    import web_cabinet.app as appmod
    importlib.reload(appmod)

    with TestClient(appmod.app) as c:
        yield c


def _login(c: TestClient, username: str = "operator", password: str = "operator"):
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def _run_jobs(max_jobs: int = 50) -> int:
    from web_cabinet.worker import JobWorker

    worker = JobWorker()
    return worker.run_until_empty(max_jobs=max_jobs)


def _latest_job_id(db_path: Path, *, kind: str) -> int:
    from web_cabinet.db import connect

    conn = connect(db_path)
    try:
        row = conn.execute("SELECT id FROM jobs WHERE kind=? ORDER BY id DESC LIMIT 1", (kind,)).fetchone()
        assert row is not None, f"job not found for kind={kind}"
        return int(row[0])
    finally:
        conn.close()


def test_report_job_artifacts_and_log_api_e2e(client: TestClient):
    from web_cabinet.db import connect, create_job, init_db, mark_job_finished

    artifacts_root = Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"])
    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    dv = "dv_t13_step3"
    report_version = "report_t13_step3"
    report_dir = artifacts_root / dv / "reports" / report_version
    exports_dir = report_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "fact_pack.json").write_text('{"data_version":"%s","report_version":"%s"}' % (dv, report_version), encoding="utf-8")
    (report_dir / "report_summary.json").write_text('{"data_version":"%s","report_version":"%s"}' % (dv, report_version), encoding="utf-8")
    (exports_dir / "report.html").write_text(f"<html><body>{report_version}</body></html>", encoding="utf-8")

    conn = connect(db_path)
    init_db(conn)
    log_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "logs" / "job_report_step3.log"
    job_id = create_job(
        conn,
        kind="report",
        tenant_id="default",
        user_id=1,
        user="operator",
        command="python -m genomeai",
        args={"argv": ["report", "--data-version", dv, "--report-version", report_version]},
        log_path=log_path,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        f"[job {job_id}] START\ndata_version={dv}\nreport_version={report_version}\n[job {job_id}] END status=done exit_code=0\n",
        encoding="utf-8",
    )
    mark_job_finished(
        conn,
        job_id,
        status="done",
        exit_code=0,
        result={"kv": {"data_version": dv, "report_version": report_version}},
        artifacts=[],
        error_text=None,
    )
    conn.close()

    _login(client)
    report = client.get(f"/api/jobs/{job_id}")
    assert report.status_code == 200
    report_payload = report.json()
    assert report_payload["status"] == "done"
    assert report_payload["report_version"] == report_version
    assert int(report_payload["artifacts_count"] or 0) >= 3

    log_api = client.get(f"/api/jobs/{job_id}/log")
    assert log_api.status_code == 200
    assert "END status=done" in log_api.json()["text"]

    arts_api = client.get(f"/api/jobs/{job_id}/artifacts")
    assert arts_api.status_code == 200
    artifacts = arts_api.json()["artifacts"]
    assert artifacts
    previewable = next((a for a in artifacts if a.get("previewable")), None)
    assert previewable is not None

    preview = client.get(previewable["preview_href"])
    assert preview.status_code == 200
    assert "report_version" in preview.text or report_version in preview.text

    page = client.get(f"/jobs/{job_id}")
    assert page.status_code == 200
    assert "Artifacts API" in page.text
    assert "preview" in page.text


def test_cancel_and_retry_flow_visible_in_queue(client: TestClient):
    from web_cabinet.db import connect, create_job, get_job, init_db
    from web_cabinet.worker import JobWorker

    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    conn = connect(db_path)
    init_db(conn)
    sleep_job_id = create_job(
        conn,
        kind="sleep",
        tenant_id="default",
        user_id=1,
        user="operator",
        command="python -m genomeai",
        args={"argv": ["sleep", "--seconds", "5"]},
        log_path=Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "logs" / "job_sleep_step3.log",
    )
    fail_job_id = create_job(
        conn,
        kind="qc",
        tenant_id="default",
        user_id=1,
        user="operator",
        command="python -m genomeai",
        args={"argv": ["qc2", "--data-version", "missing_step3", "--artifacts", os.environ["GENOMEAI_ARTIFACTS_ROOT"]]},
        log_path=Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "logs" / "job_fail_step3.log",
        max_attempts=2,
    )
    conn.close()

    _login(client)

    worker = JobWorker()
    th = threading.Thread(target=worker.run_once, daemon=True)
    th.start()
    time.sleep(1.0)
    rcancel = client.post(f"/api/jobs/{sleep_job_id}/cancel")
    assert rcancel.status_code == 200
    th.join(timeout=15)
    assert not th.is_alive()

    assert worker.run_once() is True
    rretry = client.post(f"/api/jobs/{fail_job_id}/retry")
    assert rretry.status_code == 200
    retry_job_id = int(rretry.json()["job"]["id"])
    assert worker.run_once() is True

    conn = connect(db_path)
    try:
        cancelled = get_job(conn, sleep_job_id)
        retried = get_job(conn, retry_job_id)
    finally:
        conn.close()
    assert cancelled is not None and cancelled["status"] == "cancelled"
    assert retried is not None and retried["retry_of_job_id"] == fail_job_id

    queue = client.get("/jobs", params={"q": "missing_step3"})
    assert queue.status_code == 200
    assert "cancelled" in queue.text or "Cancel" in queue.text
    assert "Retry" in queue.text or "retry" in queue.text

    detail = client.get(f"/jobs/{retry_job_id}")
    assert detail.status_code == 200
    assert "Семейство попыток" in detail.text
    assert f">{fail_job_id}<" in detail.text
    assert f">{retry_job_id}<" in detail.text
