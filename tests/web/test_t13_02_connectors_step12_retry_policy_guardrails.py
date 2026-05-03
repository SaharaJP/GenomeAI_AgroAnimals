from __future__ import annotations

import importlib
import json
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
    os.environ["GENOMEAI_CONNECTOR_RECOVERY_QUEUE_LIMIT"] = "1"

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


def test_connector_ui_editor_saves_retry_policy_and_detail_shows_analytics(client: TestClient, tmp_path: Path):
    from web_cabinet.db import connect, init_db

    repo_root = Path(os.environ["GENOMEAI_PROJECT_ROOT"])
    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    inbox = tmp_path / "ui_retry_policy_inbox"
    _write_sources(inbox)

    conn = connect(db_path)
    init_db(conn)
    conn.close()

    connector_id = f"ui_retry_policy_{uuid.uuid4().hex[:8]}"
    cfg_path = repo_root / "configs" / "connectors" / f"{connector_id}.yaml"
    try:
        _login(client)
        resp = client.post(
            "/connectors/save",
            data={
                "mode": "create",
                "original_connector_id": "",
                "connector_id": connector_id,
                "kind": "file",
                "enabled": "1",
                "description": "UI retry policy test",
                "source_dir": str(inbox),
                "schedule": "*/15 * * * *",
                "data_version_template": "dv_ui_retry_%Y%m%d_%H%M%S",
                "retry_policy_enabled": "1",
                "retry_policy_max_attempts": "2",
                "retry_policy_backoff_sec": "15",
                "retry_policy_status_partial": "1",
                "retry_policy_status_failed": "1",
                "row_count": "3",
                "dataset_key_0": "farms",
                "pattern_0": "farms.csv",
                "mapping_0": str(repo_root / "configs/mappings/farms_example.yaml"),
                "required_0": "1",
                "dataset_key_1": "animals",
                "pattern_1": "animals.csv",
                "mapping_1": str(repo_root / "configs/mappings/animals_example.yaml"),
                "required_1": "1",
                "dataset_key_2": "lactations",
                "pattern_2": "lactations.csv",
                "mapping_2": str(repo_root / "configs/mappings/lactations_example.yaml"),
                "required_2": "1",
            },
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        assert f"/connectors/{connector_id}?notice=connector_saved" in (resp.headers.get("location") or "")

        raw = cfg_path.read_text(encoding="utf-8")
        assert "retry_policy:" in raw
        assert "auto_retry_failed_datasets: true" in raw
        assert "max_attempts: 2" in raw
        assert "backoff_sec: 15" in raw
        assert "- failed" in raw and "- partial" in raw

        detail = client.get(f"/connectors/{connector_id}")
        assert detail.status_code == 200
        assert "Auto retry failed datasets: enabled" in detail.text
        assert "max_attempts=2" in detail.text
        assert "backoff_sec=15" in detail.text
        assert "statuses=failed, partial" in detail.text
        assert "Recovery analytics" in detail.text
        assert "queue_limit=1" in detail.text
    finally:
        cfg_path.unlink(missing_ok=True)


def test_duplicate_recovery_job_is_blocked_and_recovery_analytics_update(client: TestClient, tmp_path: Path):
    from web_cabinet.db import connect, init_db
    from web_cabinet.worker import JobWorker

    repo_root = Path(os.environ["GENOMEAI_PROJECT_ROOT"])
    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    inbox = tmp_path / "guardrail_recovery_inbox"
    _write_sources(inbox)

    bad_mapping = tmp_path / "animals_bad_guardrail.yaml"
    bad_mapping.write_text("foo: bar\n", encoding="utf-8")

    connector_id = f"guardrail_retry_{uuid.uuid4().hex[:8]}"
    cfg_path = repo_root / "configs" / "connectors" / f"{connector_id}.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                f"connector_id: {connector_id}",
                "kind: file",
                "enabled: true",
                f"source_dir: {inbox}",
                'schedule: "*/15 * * * *"',
                'data_version_template: "dv_guardrail_retry_%Y%m%d_%H%M%S"',
                "retry_policy:",
                "  auto_retry_failed_datasets: false",
                "  max_attempts: 0",
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
        assert worker.run_until_empty(max_jobs=5) == 1

        conn = connect(db_path)
        partial_row = dict(
            conn.execute(
                "SELECT connector_run_id, status FROM connector_runs WHERE connector_id=? ORDER BY id DESC LIMIT 1",
                (connector_id,),
            ).fetchone()
        )
        conn.close()
        assert partial_row["status"] == "partial"

        first_retry = client.post(
            "/connectors/run",
            data={
                "config_path": str(cfg_path),
                "redirect_to": f"/connectors/{connector_id}",
                "dataset_keys": "animals",
                "force": "1",
                "trigger_override": "retry_last_failed",
                "retry_parent_run_id": partial_row["connector_run_id"],
            },
            follow_redirects=False,
        )
        assert first_retry.status_code in (302, 303)
        assert "retry_last_failed_queued_1" in (first_retry.headers.get("location") or "")

        duplicate = client.post(
            "/connectors/run",
            data={
                "config_path": str(cfg_path),
                "redirect_to": f"/connectors/{connector_id}",
                "dataset_keys": "animals",
                "force": "1",
                "trigger_override": "retry_last_failed",
                "retry_parent_run_id": partial_row["connector_run_id"],
            },
            follow_redirects=False,
        )
        assert duplicate.status_code in (302, 303)
        location = unquote(duplicate.headers.get("location") or "")
        assert "error=Recovery job already queued for connector=" in location

        detail = client.get(f"/connectors/{connector_id}")
        assert detail.status_code == 200
        assert "Recovery analytics" in detail.text
        assert "pending_jobs=1" in detail.text
        assert "queue_limit=1" in detail.text

        bad_mapping.write_text((repo_root / "configs" / "mappings" / "animals_example.yaml").read_text(encoding="utf-8"), encoding="utf-8")
        assert worker.run_until_empty(max_jobs=5) == 1

        detail_after = client.get(f"/connectors/{connector_id}")
        assert detail_after.status_code == 200
        assert "manual_retry_runs=1" in detail_after.text
        assert "recovered_successes=1" in detail_after.text
        assert "success_rate=100%" in detail_after.text

        conn = connect(db_path)
        retry_row = dict(
            conn.execute(
                "SELECT connector_run_id, status, trigger_type, outputs_json FROM connector_runs WHERE connector_id=? ORDER BY id DESC LIMIT 1",
                (connector_id,),
            ).fetchone()
        )
        conn.close()
        assert retry_row["status"] == "success"
        assert retry_row["trigger_type"] == "retry_last_failed"
        outputs = json.loads(retry_row["outputs_json"])
        assert outputs.get("retry_parent_run_id") == partial_row["connector_run_id"]
    finally:
        cfg_path.unlink(missing_ok=True)
