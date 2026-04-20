from __future__ import annotations

import importlib
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


def _write_sources(base: Path, *, invalid_animals: bool = False) -> None:
    base.mkdir(parents=True, exist_ok=True)
    (base / "farms.csv").write_text(
        "FarmID,Name,Reg,Country,Latitude,Longitude,Created,Active\n"
        "F1,Farm 1,MSK,RU,55.1,37.2,2025-01-01,true\n",
        encoding="utf-8",
    )
    alive = "MAYBE" if invalid_animals else "true"
    birth = "bad-date" if invalid_animals else "2022-01-01"
    (base / "animals.csv").write_text(
        "AnimalID,FarmID,EarTag,Breed,Sex,Birth,Alive,Status\n"
        f"A1,F1,1001,HO,F,{birth},{alive},active\n",
        encoding="utf-8",
    )
    (base / "lactations.csv").write_text(
        "AnimalID,LactNo,Calving,Dryoff,DIM,Milk305,Fat,Protein\n"
        "A1,1,2025-01-10,2025-11-10,305,12345,3.9,3.2\n",
        encoding="utf-8",
    )


def test_preview_shows_expected_outputs_and_run_detail_shows_error_breakdown(client: TestClient, tmp_path: Path):
    from web_cabinet.db import connect, init_db
    from web_cabinet.worker import JobWorker

    repo_root = Path(os.environ["GENOMEAI_PROJECT_ROOT"])
    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    inbox = tmp_path / "outputs_preview_inbox"
    _write_sources(inbox, invalid_animals=True)

    connector_id = f"outputs_preview_{uuid.uuid4().hex[:8]}"
    cfg_path = repo_root / "configs" / "connectors" / f"{connector_id}.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                f"connector_id: {connector_id}",
                "kind: file",
                "enabled: true",
                f"source_dir: {inbox}",
                'schedule: "*/15 * * * *"',
                'data_version_template: "dv_outputs_preview_%Y%m%d_%H%M%S"',
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
    conn.close()

    try:
        _login(client)
        preview = client.post(
            "/connectors/preview",
            data={
                "mode": "edit",
                "original_connector_id": connector_id,
                "connector_id": connector_id,
                "kind": "file",
                "enabled": "1",
                "description": "outputs preview",
                "source_dir": str(inbox),
                "schedule": "*/15 * * * *",
                "data_version_template": "dv_outputs_preview_%Y%m%d_%H%M%S",
                "row_count": "3",
                "dataset_key_0": "farms",
                "pattern_0": "farms.csv",
                "path_0": "",
                "mapping_0": str(repo_root / "configs" / "mappings" / "farms_example.yaml"),
                "required_0": "1",
                "dataset_key_1": "animals",
                "pattern_1": "animals.csv",
                "path_1": "",
                "mapping_1": str(repo_root / "configs" / "mappings" / "animals_example.yaml"),
                "required_1": "1",
                "dataset_key_2": "lactations",
                "pattern_2": "lactations.csv",
                "path_2": "",
                "mapping_2": str(repo_root / "configs" / "mappings" / "lactations_example.yaml"),
                "required_2": "1",
            },
            follow_redirects=True,
        )
        assert preview.status_code == 200
        assert "Expected canonical outputs / ingest targets" in preview.text
        assert "first_write=3" in preview.text
        assert "dm_animals.csv" in preview.text

        queued = client.post(
            "/connectors/run",
            data={"config_path": str(cfg_path), "redirect_to": f"/connectors/{connector_id}"},
            follow_redirects=False,
        )
        assert queued.status_code in (302, 303)
        worker = JobWorker()
        assert worker.run_until_empty(max_jobs=5) == 1

        conn = connect(db_path)
        run_row = dict(conn.execute(
            "SELECT connector_run_id FROM connector_runs WHERE connector_id=? ORDER BY id DESC LIMIT 1",
            (connector_id,),
        ).fetchone())
        conn.close()

        detail = client.get(f"/connectors/runs/{run_row['connector_run_id']}")
        assert detail.status_code == 200
        assert "Canonical outputs / dataset results" in detail.text
        assert "datasets_with_errors=1" in detail.text
        assert "Error breakdown by field" in detail.text
        assert "is_alive=1" in detail.text
        assert "birth_date=1" in detail.text
        assert "Failed to coerce value to type &#39;bool&#39;" in detail.text
        assert "Failed to coerce value to type &#39;date&#39;" in detail.text
    finally:
        cfg_path.unlink(missing_ok=True)
