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


def test_connector_ui_editor_create_run_and_disable(client: TestClient, tmp_path: Path):
    from web_cabinet.db import connect, init_db
    from web_cabinet.worker import JobWorker

    repo_root = Path(os.environ["GENOMEAI_PROJECT_ROOT"])
    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    artifacts = Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"])
    inbox = tmp_path / "ui_editor_inbox"
    _write_sources(inbox)

    connector_id = f"ui_editor_{uuid.uuid4().hex[:8]}"
    cfg_path = repo_root / "configs" / "connectors" / f"{connector_id}.yaml"
    conn = connect(db_path)
    init_db(conn)
    conn.close()

    try:
        _login(client)
        create_page = client.get("/connectors/new")
        assert create_page.status_code == 200
        assert "Create connector" in create_page.text

        payload = {
            "mode": "create",
            "original_connector_id": "",
            "connector_id": connector_id,
            "kind": "file",
            "enabled": "1",
            "description": "UI-created connector",
            "source_dir": str(inbox),
            "schedule": "*/15 * * * *",
            "data_version_template": "dv_ui_editor_%Y%m%d_%H%M%S",
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
        }
        saved = client.post("/connectors/save", data=payload, follow_redirects=False)
        assert saved.status_code in (302, 303)
        assert saved.headers["location"].startswith(f"/connectors/{connector_id}")
        assert cfg_path.exists()

        detail = client.get(f"/connectors/{connector_id}")
        assert detail.status_code == 200
        assert "Edit config" in detail.text
        assert "Health=ready" in detail.text
        assert "Upcoming:" in detail.text
        assert str(inbox) in detail.text

        catalog = client.get("/connectors")
        assert catalog.status_code == 200
        assert connector_id in catalog.text
        assert "Create connector" in catalog.text
        assert "ready" in catalog.text

        run_now = client.post("/connectors/run", data={"config_path": str(cfg_path)}, follow_redirects=False)
        assert run_now.status_code in (302, 303)
        worker = JobWorker()
        assert worker.run_until_empty(max_jobs=5) == 1

        conn = connect(db_path)
        run_row = dict(conn.execute(
            "SELECT connector_run_id, status, data_version FROM connector_runs WHERE connector_id=? ORDER BY id DESC LIMIT 1",
            (connector_id,),
        ).fetchone())
        audits = [dict(r) for r in conn.execute(
            "SELECT action, status FROM audit_log WHERE object_id=? ORDER BY id DESC",
            (connector_id,),
        ).fetchall()]
        conn.close()
        assert run_row["status"] == "success"
        dv = str(run_row["data_version"])
        assert (artifacts / dv / "canonical" / "dm_animals.csv").exists()
        assert any(a["action"] == "connector.config_save" and a["status"] == "OK" for a in audits)

        edit_payload = dict(payload)
        edit_payload.update({
            "mode": "edit",
            "original_connector_id": connector_id,
        })
        edit_payload.pop("enabled", None)
        edited = client.post("/connectors/save", data=edit_payload, follow_redirects=False)
        assert edited.status_code in (302, 303)

        detail_after = client.get(f"/connectors/{connector_id}")
        assert detail_after.status_code == 200
        assert "enabled=no" in detail_after.text
        assert "Health=disabled" in detail_after.text
    finally:
        cfg_path.unlink(missing_ok=True)



def test_connector_ui_editor_shows_human_readable_validation_error(client: TestClient):
    _login(client)
    bad = client.post(
        "/connectors/save",
        data={
            "mode": "create",
            "original_connector_id": "",
            "connector_id": f"bad_ui_{uuid.uuid4().hex[:6]}",
            "kind": "file",
            "enabled": "1",
            "description": "Broken connector",
            "source_dir": "data/examples/external",
            "schedule": "bad cron expr",
            "row_count": "1",
            "dataset_key_0": "animals",
            "pattern_0": "animals.csv",
            "path_0": "",
            "mapping_0": "configs/mappings/animals_example.yaml",
            "required_0": "1",
        },
        follow_redirects=True,
    )
    assert bad.status_code == 200
    assert "must have 5 cron fields" in bad.text or "Invalid cron" in bad.text
