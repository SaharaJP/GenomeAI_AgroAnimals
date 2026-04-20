from __future__ import annotations

import importlib
import os
import uuid
from pathlib import Path
from urllib.parse import quote

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


def test_connector_run_detail_and_status_summary(client: TestClient, tmp_path: Path):
    from web_cabinet.connectors_v1 import finish_connector_run, start_connector_run
    from web_cabinet.db import connect, init_db
    from web_cabinet.worker import JobWorker

    repo_root = Path(os.environ["GENOMEAI_PROJECT_ROOT"])
    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    artifacts = Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"])
    inbox = tmp_path / "detail_inbox"
    _write_sources(inbox, milk_305=12345)

    connector_id = f"detail_flow_{uuid.uuid4().hex[:8]}"
    cfg_path = repo_root / "configs" / "connectors" / f"{connector_id}.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                f"connector_id: {connector_id}",
                "kind: file",
                "enabled: true",
                f"source_dir: {inbox}",
                'schedule: "*/15 * * * *"',
                'data_version_template: "dv_detail_%Y%m%d_%H%M%S"',
                "datasets:",
                f"  - dataset_key: farms\n    pattern: 'farms.csv'\n    mapping: {repo_root / 'configs/mappings/farms_example.yaml'}",
                f"  - dataset_key: animals\n    pattern: 'animals.csv'\n    mapping: {repo_root / 'configs/mappings/animals_example.yaml'}",
                f"  - dataset_key: lactations\n    pattern: 'lactations.csv'\n    mapping: {repo_root / 'configs/mappings/lactations_example.yaml'}",
            ]
        ),
        encoding="utf-8",
    )

    failed_run_id = f"connrun_failed_{uuid.uuid4().hex[:8]}"
    try:
        conn = connect(db_path)
        init_db(conn)
        conn.close()

        _login(client)

        # 1) success
        r1 = client.post("/connectors/run", data={"config_path": str(cfg_path)}, follow_redirects=False)
        assert r1.status_code in (302, 303)
        worker = JobWorker()
        assert worker.run_until_empty(max_jobs=5) == 1

        # 2) noop on same files
        r2 = client.post("/connectors/run", data={"config_path": str(cfg_path)}, follow_redirects=False)
        assert r2.status_code in (302, 303)
        assert worker.run_until_empty(max_jobs=5) == 1

        # 3) manual failed row for summary/error visibility
        conn = connect(db_path)
        start_connector_run(
            conn,
            tenant_id="default",
            connector_run_id=failed_run_id,
            connector_id=connector_id,
            kind="file",
            trigger_type="manual",
            schedule_slot=None,
            config_path=str(cfg_path),
        )
        finish_connector_run(
            conn,
            tenant_id="default",
            connector_run_id=failed_run_id,
            status="failed",
            data_version=None,
            message="Required dataset file is missing",
            outputs={},
            selected_files=[],
            ingest_summaries=[],
            error_text="No files matched pattern='animals.csv' for connector detail test",
        )
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT connector_run_id, status, data_version FROM connector_runs WHERE connector_id=? ORDER BY id DESC",
                (connector_id,),
            ).fetchall()
        ]
        conn.close()
        assert len(rows) >= 3
        success_run_id = next(r["connector_run_id"] for r in rows if r["status"] == "success")
        noop_run_id = next(r["connector_run_id"] for r in rows if r["status"] == "noop")
        success_dv = next(str(r["data_version"]) for r in rows if r["status"] == "success")

        detail = client.get(f"/connectors/{connector_id}")
        assert detail.status_code == 200
        assert f"Last success: {success_run_id}" in detail.text
        assert f"Last noop: {noop_run_id}" in detail.text
        assert f"Last failure: {failed_run_id}" in detail.text

        run_page = client.get(f"/connectors/runs/{success_run_id}")
        assert run_page.status_code == 200
        assert success_run_id in run_page.text
        assert "increment_reason=first_pull" in run_page.text
        assert str(inbox / "animals.csv") in run_page.text
        assert "dm_animals.csv" in run_page.text
        assert "Download manifest.json" in run_page.text

        manifest_rel = f"artifacts/{success_dv}/connectors/{success_run_id}/manifest.json"
        dl = client.get(f"/download?path={quote(manifest_rel, safe='/')}")
        assert dl.status_code == 200
        assert b'"connector_run_id":' in dl.content

        failed_page = client.get(f"/connectors/runs/{failed_run_id}")
        assert failed_page.status_code == 200
        assert "Required dataset file is missing" in failed_page.text
        assert "animals.csv" in failed_page.text
        assert "connector detail test" in failed_page.text
        assert "No selected files recorded for this run." in failed_page.text
    finally:
        cfg_path.unlink(missing_ok=True)
