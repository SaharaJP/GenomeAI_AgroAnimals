from __future__ import annotations

import importlib
import os
import uuid
from pathlib import Path
from urllib.parse import unquote

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


def _write_sources(base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    (base / "farms.csv").write_text(
        "FarmID,Name,Reg,Country,Latitude,Longitude,Created,Active\n"
        "F1,Farm 1,MSK,RU,55.1,37.2,2025-01-01,true\n",
        encoding="utf-8",
    )
    (base / "animals.csv").write_text(
        "AnimalID,FarmID,EarTag,Breed,Sex,Birth,Alive,Status\n"
        "A1,F1,1001,HO,F,2022-01-01,true,active\n",
        encoding="utf-8",
    )
    (base / "lactations.csv").write_text(
        "AnimalID,LactNo,Calving,Dryoff,DIM,Milk305,Fat,Protein\n"
        "A1,1,2025-01-10,2025-11-10,305,12345,3.9,3.2\n",
        encoding="utf-8",
    )


def test_connector_recovery_queue_cancel_and_clear_are_visible_and_audited(client: TestClient, tmp_path: Path):
    from web_cabinet.db import connect, init_db
    from web_cabinet.worker import JobWorker

    repo_root = Path(os.environ["GENOMEAI_PROJECT_ROOT"])
    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    inbox = tmp_path / "recovery_cancel_inbox"
    _write_sources(inbox)

    bad_mapping = tmp_path / "animals_bad_recovery_cancel.yaml"
    bad_mapping.write_text("foo: bar\n", encoding="utf-8")

    connector_id = f"recovery_cancel_{uuid.uuid4().hex[:8]}"
    cfg_path = repo_root / "configs" / "connectors" / f"{connector_id}.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                f"connector_id: {connector_id}",
                "kind: file",
                "enabled: true",
                f"source_dir: {inbox}",
                'schedule: "*/15 * * * *"',
                'data_version_template: "dv_recovery_cancel_%Y%m%d_%H%M%S"',
                "retry_policy:",
                "  auto_retry_failed_datasets: true",
                "  max_attempts: 1",
                "  backoff_sec: 0",
                "  retry_on_statuses: [partial]",
                "datasets:",
                f"  - dataset_key: farms\n    pattern: 'farms.csv'\n    mapping: {repo_root / 'configs/mappings/farms_example.yaml'}",
                f"  - dataset_key: animals\n    pattern: 'animals.csv'\n    mapping: {bad_mapping}",
                f"  - dataset_key: lactations\n    pattern: 'lactations.csv'\n    mapping: {repo_root / 'configs/mappings/lactations_example.yaml'}",
            ]
        ),
        encoding="utf-8",
    )

    conn = connect(db_path)
    init_db(conn)
    conn.close()

    try:
        _login(client)
        queued = client.post(
            "/connectors/run",
            data={"config_path": str(cfg_path), "redirect_to": f"/connectors/{connector_id}"},
            follow_redirects=False,
        )
        assert queued.status_code in (302, 303)

        worker = JobWorker()
        assert worker.run_once() is True

        conn = connect(db_path)
        queued_job = dict(
            conn.execute(
                "SELECT id, status FROM jobs WHERE kind='connector_run' AND status='queued' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        )
        partial_run = dict(
            conn.execute(
                "SELECT connector_run_id, status FROM connector_runs WHERE connector_id=? ORDER BY id DESC LIMIT 1",
                (connector_id,),
            ).fetchone()
        )
        conn.close()
        assert partial_run['status'] == 'partial'

        detail = client.get(f"/connectors/{connector_id}")
        assert detail.status_code == 200
        assert "Recovery queue" in detail.text
        assert "Cancel all queued recovery jobs" in detail.text
        assert "Last recovery decision:" in detail.text
        assert "failed dataset subset retry was scheduled" in detail.text

        cancel_resp = client.post(
            "/connectors/recovery/cancel",
            data={
                "config_path": str(cfg_path),
                "job_id": str(queued_job["id"]),
                "redirect_to": f"/connectors/{connector_id}",
            },
            follow_redirects=False,
        )
        assert cancel_resp.status_code in (302, 303)
        assert f"recovery_job_cancelled_{queued_job['id']}" in unquote(cancel_resp.headers.get("location") or "")

        conn = connect(db_path)
        cancelled = dict(conn.execute("SELECT status FROM jobs WHERE id=?", (int(queued_job["id"]),)).fetchone())
        audits = [
            dict(r)
            for r in conn.execute(
                "SELECT action, status FROM audit_log WHERE object_id=? AND action LIKE 'connector.recovery_%' ORDER BY id ASC",
                (connector_id,),
            ).fetchall()
        ]
        conn.close()
        assert cancelled["status"] == "cancelled"
        assert any(a["action"] == "connector.recovery_cancel" and a["status"] == "OK" for a in audits)

        detail_after = client.get(f"/connectors/{connector_id}")
        assert detail_after.status_code == 200
        assert "No queued recovery jobs for this connector." in detail_after.text
        assert "pending_jobs=0" in detail_after.text

        requeue = client.post(
            "/connectors/run",
            data={
                "config_path": str(cfg_path),
                "redirect_to": f"/connectors/{connector_id}",
                "dataset_keys": "animals",
                "force": "1",
                "trigger_override": "retry_last_failed",
                "retry_parent_run_id": partial_run["connector_run_id"],
            },
            follow_redirects=False,
        )
        assert requeue.status_code in (302, 303)
        assert "retry_last_failed_queued_1" in unquote(requeue.headers.get("location") or "")

        clear_resp = client.post(
            "/connectors/recovery/clear",
            data={"config_path": str(cfg_path), "redirect_to": f"/connectors/{connector_id}"},
            follow_redirects=False,
        )
        assert clear_resp.status_code in (302, 303)
        assert "recovery_queue_cleared_1" in unquote(clear_resp.headers.get("location") or "")

        conn = connect(db_path)
        cleared_statuses = [
            str(r[0])
            for r in conn.execute(
                "SELECT status FROM jobs WHERE kind='connector_run' AND status='cancelled' ORDER BY id ASC"
            ).fetchall()
        ]
        audits2 = [
            dict(r)
            for r in conn.execute(
                "SELECT action, status FROM audit_log WHERE object_id=? AND action LIKE 'connector.recovery_%' ORDER BY id ASC",
                (connector_id,),
            ).fetchall()
        ]
        conn.close()
        assert len(cleared_statuses) >= 2
        assert any(a["action"] == "connector.recovery_clear" and a["status"] == "OK" for a in audits2)
    finally:
        cfg_path.unlink(missing_ok=True)
