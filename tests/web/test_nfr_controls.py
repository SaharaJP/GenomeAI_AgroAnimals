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
    # Small limits for tests
    os.environ["GENOMEAI_WEB_MAX_UPLOAD_MB"] = "1"
    os.environ["GENOMEAI_WEB_MAX_MAPPING_MB"] = "1"
    os.environ["GENOMEAI_JOB_TIMEOUT_SEC"] = "1"

    import web_cabinet.app as appmod
    importlib.reload(appmod)

    with TestClient(appmod.app) as c:
        yield c


def _login(c: TestClient, username: str, password: str):
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_healthz_readyz(client: TestClient):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.text.strip() == "ok"

    rr = client.get("/readyz")
    # With temp sqlite + writable dirs should be ready
    assert rr.status_code == 200


def test_upload_limit_returns_413(client: TestClient):
    _login(client, "operator", "operator")
    big = b"a" * (2 * 1024 * 1024)  # 2MB
    r = client.post(
        "/upload/ingest-all",
        data={
            "data_version": "dv_test",
            "farms_mapping_path": "configs/mappings/farms_example.yaml",
            "animals_mapping_path": "configs/mappings/animals_example.yaml",
            "lactations_mapping_path": "configs/mappings/lactations_example.yaml",
        },
        files={"farms_file": ("farms.csv", big, "text/csv")},
        follow_redirects=False,
    )
    assert r.status_code == 413


def test_config_limit_returns_413(client: TestClient):
    _login(client, "admin", "admin")
    big = b"b" * (2 * 1024 * 1024)
    r = client.post(
        "/configs/upload",
        data={"target_rel_path": "configs/qc_rules_v2.yaml"},
        files={"file": ("qc_rules_v2.yaml", big, "text/yaml")},
        follow_redirects=False,
    )
    assert r.status_code == 413


def test_job_timeout_marks_failed_and_creates_ops_alert(client: TestClient, tmp_path: Path):
    # Create a queued job and run worker synchronously
    from web_cabinet.db import connect, create_job, init_db
    from web_cabinet.worker import JobWorker

    # Ensure DB schema
    conn = connect(Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db")
    init_db(conn)

    logs_dir = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "job_timeout.log"

    job_id = create_job(
        conn,
        kind="sleep",
        tenant_id="default",
        user_id=1,
        user="operator",
        command="python -m genomeai",
        args={"argv": ["sleep", "--seconds", "2"]},
        log_path=log_path,
    )
    conn.close()
    jw = JobWorker()
    jw.run_once()

    conn = connect(Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db")
    row = conn.execute("SELECT status, exit_code FROM jobs WHERE id=?", (job_id,)).fetchone()
    assert row is not None
    assert row[0] == "failed"
    assert int(row[1]) == 124

    # Alert should exist
    a = conn.execute(
        "SELECT COUNT(1) FROM alerts_v2 WHERE tenant_id='default' AND alert_type='ops.job_failed'"
    ).fetchone()[0]
    assert int(a) >= 1
    conn.close()


def test_observability_endpoint_requires_login(client: TestClient):
    r = client.get("/api/observability")
    assert r.status_code in (401, 403)
    _login(client, "viewer", "viewer")
    r2 = client.get("/api/observability")
    assert r2.status_code == 200
    js = r2.json()
    assert "uptime_sec" in js
    assert "jobs" in js
