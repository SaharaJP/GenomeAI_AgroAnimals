from __future__ import annotations

import importlib
import json
import os
import uuid
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



def test_connector_detail_retry_last_failed_button_runs_subset_only(client: TestClient, tmp_path: Path):
    from web_cabinet.db import connect, init_db
    from web_cabinet.worker import JobWorker

    repo_root = Path(os.environ["GENOMEAI_PROJECT_ROOT"])
    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    inbox = tmp_path / "detail_retry_inbox"
    _write_sources(inbox)

    bad_mapping = tmp_path / "animals_bad_detail_retry.yaml"
    bad_mapping.write_text("foo: bar\n", encoding="utf-8")

    connector_id = f"detail_retry_{uuid.uuid4().hex[:8]}"
    cfg_path = repo_root / "configs" / "connectors" / f"{connector_id}.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                f"connector_id: {connector_id}",
                "kind: file",
                "enabled: true",
                f"source_dir: {inbox}",
                'schedule: "*/15 * * * *"',
                'data_version_template: "dv_detail_retry_%Y%m%d_%H%M%S"',
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

        detail = client.get(f"/connectors/{connector_id}")
        assert detail.status_code == 200
        assert "Retry last failed datasets" in detail.text

        bad_mapping.write_text((repo_root / "configs" / "mappings" / "animals_example.yaml").read_text(encoding="utf-8"), encoding="utf-8")
        retry = client.post(
            "/connectors/run",
            data={
                "config_path": str(cfg_path),
                "redirect_to": f"/connectors/{connector_id}",
                "dataset_keys": "animals",
                "force": "1",
                "trigger_override": "retry_last_failed",
            },
            follow_redirects=False,
        )
        assert retry.status_code in (302, 303)
        assert "retry_last_failed_queued_1" in (retry.headers.get("location") or "")
        assert worker.run_until_empty(max_jobs=5) == 1

        conn = connect(db_path)
        retry_row = dict(
            conn.execute(
                "SELECT connector_run_id, status, trigger_type, selected_files_json FROM connector_runs WHERE connector_id=? ORDER BY id DESC LIMIT 1",
                (connector_id,),
            ).fetchone()
        )
        conn.close()
        assert retry_row["status"] == "success"
        assert retry_row["trigger_type"] == "retry_last_failed"
        selected = json.loads(retry_row["selected_files_json"])
        assert [x["dataset_key"] for x in selected] == ["animals"]
    finally:
        cfg_path.unlink(missing_ok=True)



def test_connector_auto_retry_failed_datasets_schedules_subset_and_executes(client: TestClient, tmp_path: Path):
    from web_cabinet.db import connect, init_db
    from web_cabinet.worker import JobWorker

    repo_root = Path(os.environ["GENOMEAI_PROJECT_ROOT"])
    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    artifacts = Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"])
    inbox = tmp_path / "auto_retry_inbox"
    _write_sources(inbox)

    bad_mapping = tmp_path / "animals_bad_auto_retry.yaml"
    bad_mapping.write_text("foo: bar\n", encoding="utf-8")

    connector_id = f"auto_retry_{uuid.uuid4().hex[:8]}"
    cfg_path = repo_root / "configs" / "connectors" / f"{connector_id}.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                f"connector_id: {connector_id}",
                "kind: file",
                "enabled: true",
                f"source_dir: {inbox}",
                'schedule: "*/15 * * * *"',
                'data_version_template: "dv_auto_retry_%Y%m%d_%H%M%S"',
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
        runs = [
            dict(r)
            for r in conn.execute(
                "SELECT connector_run_id, status, trigger_type, outputs_json FROM connector_runs WHERE connector_id=? ORDER BY id ASC",
                (connector_id,),
            ).fetchall()
        ]
        jobs = [
            dict(r)
            for r in conn.execute(
                "SELECT id, status, next_attempt_at, retry_source, args_json FROM jobs WHERE kind='connector_run' ORDER BY id ASC",
            ).fetchall()
        ]
        audits = [
            dict(r)
            for r in conn.execute(
                "SELECT action, status FROM audit_log WHERE object_id=? ORDER BY id ASC",
                (connector_id,),
            ).fetchall()
        ]
        conn.close()

        assert len(runs) == 1
        assert runs[0]["status"] == "partial"
        outputs = json.loads(runs[0]["outputs_json"])
        auto_retry = outputs.get("connector_auto_retry") or {}
        assert auto_retry.get("status") == "scheduled"
        assert auto_retry.get("failed_dataset_keys") == ["animals"]

        queued_jobs = [j for j in jobs if j["status"] == "queued"]
        assert len(queued_jobs) == 1
        queued_args = json.loads(queued_jobs[0]["args_json"])
        argv = queued_args.get("argv") or []
        assert "--trigger" in argv and "auto_retry_failed" in argv
        assert "--datasets" in argv and "animals" in argv
        assert "--retry-parent-run-id" in argv and runs[0]["connector_run_id"] in argv
        assert queued_jobs[0]["retry_source"] == "connector_auto_failed_datasets"
        assert any(a["action"] == "connector.auto_retry_scheduled" and a["status"] == "OK" for a in audits)

        detail = client.get(f"/connectors/{connector_id}")
        assert detail.status_code == 200
        assert "Auto retry failed datasets: enabled" in detail.text
        assert "Recovery queue" in detail.text
        assert "auto_retry_failed" in detail.text
        assert "animals" in detail.text

        bad_mapping.write_text((repo_root / "configs" / "mappings" / "animals_example.yaml").read_text(encoding="utf-8"), encoding="utf-8")
        assert worker.run_until_empty(max_jobs=5) == 1

        conn = connect(db_path)
        final_runs = [
            dict(r)
            for r in conn.execute(
                "SELECT connector_run_id, status, trigger_type, data_version, outputs_json, selected_files_json FROM connector_runs WHERE connector_id=? ORDER BY id ASC",
                (connector_id,),
            ).fetchall()
        ]
        conn.close()

        assert len(final_runs) == 2
        assert final_runs[1]["status"] == "success"
        assert final_runs[1]["trigger_type"] == "auto_retry_failed"
        final_outputs = json.loads(final_runs[1]["outputs_json"])
        assert final_outputs.get("retry_attempt_no") == 1
        assert final_outputs.get("retry_parent_run_id") == final_runs[0]["connector_run_id"]
        selected = json.loads(final_runs[1]["selected_files_json"])
        assert [x["dataset_key"] for x in selected] == ["animals"]
        assert (artifacts / str(final_runs[1]["data_version"]) / "canonical" / "dm_animals.csv").exists()

        retry_detail = client.get(f"/connectors/runs/{final_runs[0]['connector_run_id']}")
        assert retry_detail.status_code == 200
        assert "Auto retry scheduled" in retry_detail.text
        assert "datasets=animals" in retry_detail.text
    finally:
        cfg_path.unlink(missing_ok=True)
