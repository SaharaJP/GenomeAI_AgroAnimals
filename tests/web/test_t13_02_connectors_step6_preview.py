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


def test_connector_preview_shows_selected_files_and_does_not_save_config(client: TestClient, tmp_path: Path):
    from web_cabinet.db import connect, init_db

    repo_root = Path(os.environ["GENOMEAI_PROJECT_ROOT"])
    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    inbox = tmp_path / "preview_inbox"
    _write_sources(inbox)

    conn = connect(db_path)
    init_db(conn)
    conn.close()

    connector_id = f"preview_{uuid.uuid4().hex[:8]}"
    cfg_path = repo_root / "configs" / "connectors" / f"{connector_id}.yaml"
    cfg_path.unlink(missing_ok=True)

    _login(client)
    res = client.post(
        "/connectors/preview",
        data={
            "mode": "create",
            "original_connector_id": "",
            "connector_id": connector_id,
            "kind": "file",
            "enabled": "1",
            "description": "Preview only connector",
            "source_dir": str(inbox),
            "schedule": "*/15 * * * *",
            "data_version_template": "dv_preview_%Y%m%d_%H%M%S",
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
    assert res.status_code == 200
    assert "Preview result" in res.text
    assert "Predicted run status: success" in res.text
    assert "Selected files" in res.text
    assert "animals.csv" in res.text
    assert cfg_path.exists() is False

    conn = connect(db_path)
    audits = [dict(r) for r in conn.execute(
        "SELECT action, status FROM audit_log WHERE object_id=? ORDER BY id DESC",
        (connector_id,),
    ).fetchall()]
    conn.close()
    assert any(a["action"] == "connector.config_preview" and a["status"] == "OK" for a in audits)


def test_connector_preview_shows_human_readable_error(client: TestClient):
    _login(client)
    res = client.post(
        "/connectors/preview",
        data={
            "mode": "create",
            "original_connector_id": "",
            "connector_id": f"bad_preview_{uuid.uuid4().hex[:6]}",
            "kind": "file",
            "enabled": "1",
            "description": "Broken preview",
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
    assert res.status_code == 200
    assert "must have 5 cron fields" in res.text or "Invalid cron" in res.text
