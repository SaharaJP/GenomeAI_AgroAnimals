from __future__ import annotations

import importlib
import os
from datetime import datetime, timezone
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



def _write_sources(base: Path, *, milk_305: int = 10000) -> None:
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
        f"A1,1,2025-01-10,2025-11-10,305,{milk_305},3.9,3.2\n",
        encoding="utf-8",
    )



def test_scheduler_enqueues_once_per_slot_and_worker_executes(client: TestClient, tmp_path: Path):
    from web_cabinet.connectors_v1 import list_connector_runs, schedule_due_connector_jobs
    from web_cabinet.db import connect, init_db
    from web_cabinet.worker import JobWorker

    repo_root = Path(os.environ["GENOMEAI_PROJECT_ROOT"])
    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    artifacts = Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"])

    inbox = tmp_path / "inbox"
    _write_sources(inbox, milk_305=12345)
    cfg_dir = tmp_path / "configs" / "connectors"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = cfg_dir / "scheduled_file.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                "connector_id: scheduled_file",
                "kind: file",
                "enabled: true",
                f"source_dir: {inbox}",
                'schedule: "*/15 * * * *"',
                'data_version_template: "dv_scheduled_%Y%m%d_%H%M%S"',
                "datasets:",
                f"  - dataset_key: farms\n    pattern: 'farms.csv'\n    mapping: {repo_root / 'configs/mappings/farms_example.yaml'}",
                f"  - dataset_key: animals\n    pattern: 'animals.csv'\n    mapping: {repo_root / 'configs/mappings/animals_example.yaml'}",
                f"  - dataset_key: lactations\n    pattern: 'lactations.csv'\n    mapping: {repo_root / 'configs/mappings/lactations_example.yaml'}",
            ]
        ),
        encoding="utf-8",
    )

    conn = connect(db_path)
    init_db(conn)
    at = datetime(2026, 3, 7, 10, 15, tzinfo=timezone.utc)
    first = schedule_due_connector_jobs(conn, tenant_id="default", user_id=1, username="operator", configs_dir=cfg_dir, when=at)
    second = schedule_due_connector_jobs(conn, tenant_id="default", user_id=1, username="operator", configs_dir=cfg_dir, when=at)
    assert len(first["enqueued"]) == 1
    assert len(second["enqueued"]) == 0
    assert any(x[0] == "queued" for x in conn.execute("SELECT status FROM jobs").fetchall())
    conn.close()

    worker = JobWorker()
    assert worker.run_until_empty(max_jobs=5) == 1

    conn = connect(db_path)
    runs = list_connector_runs(conn, tenant_id="default", connector_id="scheduled_file", limit=10)
    conn.close()
    assert runs
    assert runs[0]["status"] == "success"
    dv = str(runs[0]["data_version"])
    assert (artifacts / dv / "canonical" / "dm_animals.csv").exists()
    assert (artifacts / dv / "connectors" / runs[0]["connector_run_id"] / "manifest.json").exists()



def test_connectors_page_and_manual_run_queue_visible(client: TestClient):
    from web_cabinet.connectors_v1 import finish_connector_run, start_connector_run
    from web_cabinet.db import connect, init_db

    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    repo_root = Path(os.environ["GENOMEAI_PROJECT_ROOT"])
    demo_cfg = repo_root / "configs" / "connectors" / "file_demo.yaml"

    conn = connect(db_path)
    init_db(conn)
    start_connector_run(
        conn,
        tenant_id="default",
        connector_run_id="connrun_demo_visible",
        connector_id="demo_file_pull",
        kind="file",
        trigger_type="manual",
        schedule_slot=None,
        config_path=str(demo_cfg),
    )
    finish_connector_run(
        conn,
        tenant_id="default",
        connector_run_id="connrun_demo_visible",
        status="noop",
        data_version="dv_demo_prev",
        message="No new files detected",
        outputs={},
        selected_files=[],
        ingest_summaries=[],
        error_text=None,
    )
    conn.close()

    _login(client)
    page = client.get("/connectors")
    assert page.status_code == 200
    assert "Connectors" in page.text
    assert "demo_file_pull" in page.text
    assert "connrun_demo_visible" in page.text
    assert "Run scheduler tick" in page.text

    r = client.post("/connectors/run", data={"config_path": str(demo_cfg)}, follow_redirects=False)
    assert r.status_code in (302, 303)

    conn = connect(db_path)
    jobs = [dict(r) for r in conn.execute("SELECT * FROM jobs WHERE kind='connector_run' ORDER BY id DESC").fetchall()]
    conn.close()
    assert jobs
    assert jobs[0]["status"] == "queued"
