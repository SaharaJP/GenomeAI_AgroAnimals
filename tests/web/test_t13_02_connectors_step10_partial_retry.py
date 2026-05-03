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



def test_connector_partial_failure_and_retry_failed_dataset_only(client: TestClient, tmp_path: Path):
    from web_cabinet.db import connect, init_db
    from web_cabinet.worker import JobWorker

    repo_root = Path(os.environ["GENOMEAI_PROJECT_ROOT"])
    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    inbox = tmp_path / "partial_retry_inbox"
    _write_sources(inbox)

    bad_mapping = tmp_path / "animals_bad_mapping.yaml"
    bad_mapping.write_text("foo: bar\n", encoding="utf-8")

    connector_id = f"partial_retry_{uuid.uuid4().hex[:8]}"
    cfg_path = repo_root / "configs" / "connectors" / f"{connector_id}.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                f"connector_id: {connector_id}",
                "kind: file",
                "enabled: true",
                f"source_dir: {inbox}",
                'schedule: "*/15 * * * *"',
                'data_version_template: "dv_partial_retry_%Y%m%d_%H%M%S"',
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
                "SELECT connector_run_id, status, trigger_type, data_version, selected_files_json FROM connector_runs WHERE connector_id=? ORDER BY id DESC LIMIT 1",
                (connector_id,),
            ).fetchone()
        )
        conn.close()
        assert partial_row["status"] == "partial"

        selected = json.loads(partial_row["selected_files_json"])
        assert sorted(x["dataset_key"] for x in selected) == ["animals", "farms", "lactations"]

        detail = client.get(f"/connectors/runs/{partial_row['connector_run_id']}")
        assert detail.status_code == 200
        assert "status=partial" in detail.text
        assert "failed_dataset=1" in detail.text
        assert "Retry failed datasets only" in detail.text
        assert "mapping yaml must contain" in detail.text

        # Fix only the failed dataset mapping and retry just that binding.
        bad_mapping.write_text((repo_root / "configs" / "mappings" / "animals_example.yaml").read_text(encoding="utf-8"), encoding="utf-8")
        retry = client.post(
            "/connectors/run",
            data={
                "config_path": str(cfg_path),
                "redirect_to": f"/connectors/runs/{partial_row['connector_run_id']}",
                "dataset_keys": "animals",
                "force": "1",
            },
            follow_redirects=False,
        )
        assert retry.status_code in (302, 303)
        assert "retry_failed_queued_1" in (retry.headers.get("location") or "")
        assert worker.run_until_empty(max_jobs=5) == 1

        conn = connect(db_path)
        retry_row = dict(
            conn.execute(
                "SELECT connector_run_id, status, trigger_type, data_version, selected_files_json FROM connector_runs WHERE connector_id=? ORDER BY id DESC LIMIT 1",
                (connector_id,),
            ).fetchone()
        )
        conn.close()

        assert retry_row["status"] == "success"
        assert retry_row["trigger_type"] == "retry_failed"
        retry_selected = json.loads(retry_row["selected_files_json"])
        assert [x["dataset_key"] for x in retry_selected] == ["animals"]
        assert (Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"]) / retry_row["data_version"] / "canonical" / "dm_animals.csv").exists()

        retry_detail = client.get(f"/connectors/runs/{retry_row['connector_run_id']}")
        assert retry_detail.status_code == 200
        assert "requested_dataset_keys=animals" in retry_detail.text
        assert "written=1" in retry_detail.text
    finally:
        cfg_path.unlink(missing_ok=True)
