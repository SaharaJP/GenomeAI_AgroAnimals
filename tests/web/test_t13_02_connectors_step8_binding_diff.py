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


def test_connector_detail_and_preview_show_binding_deltas_and_history(client: TestClient, tmp_path: Path):
    from web_cabinet.db import connect, init_db
    from web_cabinet.worker import JobWorker

    repo_root = Path(os.environ["GENOMEAI_PROJECT_ROOT"])
    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    inbox = tmp_path / "binding_delta_inbox"
    _write_sources(inbox)

    connector_id = f"binding_delta_{uuid.uuid4().hex[:8]}"
    cfg_path = repo_root / "configs" / "connectors" / f"{connector_id}.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                f"connector_id: {connector_id}",
                "kind: file",
                "enabled: true",
                f"source_dir: {inbox}",
                'schedule: "*/15 * * * *"',
                'data_version_template: "dv_binding_delta_%Y%m%d_%H%M%S"',
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
        queued = client.post(
            "/connectors/run",
            data={"config_path": str(cfg_path), "redirect_to": f"/connectors/{connector_id}"},
            follow_redirects=False,
        )
        assert queued.status_code in (302, 303)
        worker = JobWorker()
        assert worker.run_until_empty(max_jobs=5) == 1

        conn = connect(db_path)
        success_row = dict(conn.execute(
            "SELECT connector_run_id, data_version FROM connector_runs WHERE connector_id=? ORDER BY id DESC LIMIT 1",
            (connector_id,),
        ).fetchone())
        conn.close()

        # Change one bound source to trigger a visible delta in detail/preview.
        (inbox / "animals.csv").write_text(
            "AnimalID,FarmID,EarTag,Breed,Sex,Birth,Alive,Status\n"
            "A1,F1,1001,JER,F,2022-01-01,true,active\n",
            encoding="utf-8",
        )

        detail = client.get(f"/connectors/{connector_id}")
        assert detail.status_code == 200
        assert "Source bindings / upload inbox / delta vs last pulled" in detail.text
        assert "Binding delta: changed=1" in detail.text
        assert "Last success" in detail.text
        assert success_row["connector_run_id"] in detail.text
        assert "source file content changed since last pull" in detail.text

        preview = client.post(
            "/connectors/preview",
            data={
                "mode": "edit",
                "original_connector_id": connector_id,
                "connector_id": connector_id,
                "kind": "file",
                "enabled": "1",
                "description": "binding delta preview",
                "source_dir": str(inbox),
                "schedule": "*/15 * * * *",
                "data_version_template": "dv_binding_delta_%Y%m%d_%H%M%S",
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
        assert "Binding diff vs last pulled" in preview.text
        assert "changed=1" in preview.text
        assert "unchanged=2" in preview.text
        assert "source file content changed since last pull" in preview.text
    finally:
        cfg_path.unlink(missing_ok=True)
