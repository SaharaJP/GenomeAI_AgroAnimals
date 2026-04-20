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


def test_log_stream_incremental_and_active_filter(client: TestClient):
    from web_cabinet.db import connect, create_job, init_db, mark_job_finished

    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    logs_dir = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    conn = connect(db_path)
    init_db(conn)

    stream_log = logs_dir / "job_stream.log"
    stream_job_id = create_job(
        conn,
        kind="report",
        tenant_id="default",
        user_id=1,
        user="operator",
        command="python -m genomeai",
        args={"argv": ["report", "--data-version", "dv_stream", "--report-version", "rep_stream"]},
        log_path=stream_log,
    )
    stream_log.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    mark_job_finished(
        conn,
        stream_job_id,
        status="done",
        exit_code=0,
        result={"kv": {"data_version": "dv_stream", "report_version": "rep_stream"}},
        artifacts=[],
        error_text=None,
    )

    queued_id = create_job(
        conn,
        kind="ingest",
        tenant_id="default",
        user_id=1,
        user="operator",
        command="python -m genomeai",
        args={"argv": ["ingest", "--data-version", "dv_active_q"]},
        log_path=logs_dir / "job_active_q.log",
    )
    running_id = create_job(
        conn,
        kind="train",
        tenant_id="default",
        user_id=1,
        user="operator",
        command="python -m genomeai",
        args={"argv": ["train", "--data-version", "dv_active_r", "--model-version", "mdl_active"]},
        log_path=logs_dir / "job_active_r.log",
    )
    cancel_requested_id = create_job(
        conn,
        kind="score",
        tenant_id="default",
        user_id=1,
        user="operator",
        command="python -m genomeai",
        args={"argv": ["score", "--data-version", "dv_active_c", "--scoring-run", "scr_active"]},
        log_path=logs_dir / "job_active_c.log",
    )
    failed_id = create_job(
        conn,
        kind="qc",
        tenant_id="default",
        user_id=1,
        user="operator",
        command="python -m genomeai",
        args={"argv": ["qc2", "--data-version", "dv_failed"]},
        log_path=logs_dir / "job_failed.log",
    )
    conn.execute("UPDATE jobs SET status='running', started_at=? WHERE id=?", ("2026-03-06T10:00:00+00:00", running_id))
    conn.execute(
        "UPDATE jobs SET status='cancel_requested', started_at=?, cancel_requested_at=?, retry_source='manual' WHERE id=?",
        ("2026-03-06T10:01:00+00:00", "2026-03-06T10:02:00+00:00", cancel_requested_id),
    )
    conn.execute(
        "UPDATE jobs SET status='failed', finished_at=?, error_text=?, retry_source='auto' WHERE id=?",
        ("2026-03-06T10:03:00+00:00", "report stage exploded", failed_id),
    )
    conn.commit()
    conn.close()

    _login(client)

    s1 = client.get(f"/api/jobs/{stream_job_id}/log/stream", params={"cursor": 0, "max_bytes": 6})
    assert s1.status_code == 200
    js1 = s1.json()
    assert js1["text"] == "alpha\n"
    assert js1["next_cursor"] == 6
    assert js1["status"] == "done"

    s2 = client.get(f"/api/jobs/{stream_job_id}/log/stream", params={"cursor": js1["next_cursor"], "max_bytes": 5})
    assert s2.status_code == 200
    js2 = s2.json()
    assert js2["text"] == "beta\n"
    assert js2["next_cursor"] == 11

    s3 = client.get(f"/api/jobs/{stream_job_id}/log/stream", params={"cursor": js2["next_cursor"], "max_bytes": 1024})
    assert s3.status_code == 200
    js3 = s3.json()
    assert js3["text"] == "gamma\n"
    assert js3["is_eof"] is True

    active_api = client.get("/api/jobs", params={"status": "active"})
    assert active_api.status_code == 200
    active_jobs = active_api.json()["jobs"]
    active_ids = {int(j["id"]) for j in active_jobs}
    assert {queued_id, running_id, cancel_requested_id}.issubset(active_ids)
    assert failed_id not in active_ids
    assert stream_job_id not in active_ids

    search_api = client.get("/api/jobs", params={"q": "rep_stream"})
    assert search_api.status_code == 200
    assert any(int(j["id"]) == stream_job_id for j in search_api.json()["jobs"])

    search_retry = client.get("/api/jobs", params={"q": "report stage exploded"})
    assert search_retry.status_code == 200
    assert any(int(j["id"]) == failed_id for j in search_retry.json()["jobs"])

    page = client.get("/jobs", params={"status": "active", "auto_refresh": 1})
    assert page.status_code == 200
    assert "auto refresh" in page.text
    assert "Только active" in page.text


def test_cancel_retry_still_visible_after_live_tail_changes(client: TestClient):
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
        log_path=Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "logs" / "job_sleep_step4.log",
    )
    fail_job_id = create_job(
        conn,
        kind="qc",
        tenant_id="default",
        user_id=1,
        user="operator",
        command="python -m genomeai",
        args={"argv": ["qc2", "--data-version", "missing_step4", "--artifacts", os.environ["GENOMEAI_ARTIFACTS_ROOT"]]},
        log_path=Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "logs" / "job_fail_step4.log",
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

    conn = connect(db_path)
    try:
        cancelled = get_job(conn, sleep_job_id)
        retried = get_job(conn, retry_job_id)
    finally:
        conn.close()
    assert cancelled is not None and cancelled["status"] == "cancelled"
    assert retried is not None and retried["retry_of_job_id"] == fail_job_id

    detail = client.get(f"/jobs/{retry_job_id}")
    assert detail.status_code == 200
    assert "Live tail" in detail.text
    assert "Log stream API" in detail.text
    assert "Семейство попыток" in detail.text
    assert f">{fail_job_id}<" in detail.text
    assert f">{retry_job_id}<" in detail.text


def test_report_artifacts_preview_and_stream_api(client: TestClient):
    from web_cabinet.db import connect, create_job, init_db, mark_job_finished

    artifacts_root = Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"])
    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    dv = "dv_t13_step4"
    report_version = "report_t13_step4"
    report_dir = artifacts_root / dv / "reports" / report_version
    exports_dir = report_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "fact_pack.json").write_text('{"data_version":"%s","report_version":"%s"}' % (dv, report_version), encoding="utf-8")
    (report_dir / "report_summary.json").write_text('{"data_version":"%s","report_version":"%s"}' % (dv, report_version), encoding="utf-8")
    (exports_dir / "report.html").write_text(f"<html><body>{report_version}</body></html>", encoding="utf-8")

    conn = connect(db_path)
    init_db(conn)
    log_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "logs" / "job_report_step4.log"
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
        f"[job {job_id}] START\ndata_version={dv}\nreport_version={report_version}\nline=one\nline=two\n[job {job_id}] END status=done exit_code=0\n",
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

    log_stream = client.get(f"/api/jobs/{job_id}/log/stream", params={"cursor": 0, "max_bytes": 32})
    assert log_stream.status_code == 200
    assert "START" in log_stream.json()["text"]
    assert log_stream.json()["next_cursor"] > 0

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
    assert "Live tail" in page.text
    assert "Artifacts API" in page.text
    assert "Log stream API" in page.text
