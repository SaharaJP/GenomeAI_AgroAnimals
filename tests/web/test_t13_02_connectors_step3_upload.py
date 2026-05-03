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


def test_connector_detail_upload_and_run_flow(client: TestClient, tmp_path: Path):
    from web_cabinet.db import connect, init_db
    from web_cabinet.worker import JobWorker

    repo_root = Path(os.environ["GENOMEAI_PROJECT_ROOT"])
    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    artifacts = Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"])
    inbox = tmp_path / "connector_inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    connector_id = f"upload_flow_{uuid.uuid4().hex[:8]}"
    cfg_path = repo_root / "configs" / "connectors" / f"{connector_id}.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                f"connector_id: {connector_id}",
                "kind: file",
                "enabled: true",
                f"source_dir: {inbox}",
                'schedule: "*/15 * * * *"',
                'data_version_template: "dv_upload_%Y%m%d_%H%M%S"',
                "datasets:",
                f"  - dataset_key: farms\n    pattern: 'farms.csv'\n    mapping: {repo_root / 'configs/mappings/farms_example.yaml'}",
                f"  - dataset_key: animals\n    pattern: 'animals.csv'\n    mapping: {repo_root / 'configs/mappings/animals_example.yaml'}",
                f"  - dataset_key: lactations\n    pattern: 'lactations.csv'\n    mapping: {repo_root / 'configs/mappings/lactations_example.yaml'}",
            ]
        ),
        encoding="utf-8",
    )

    try:
        conn = connect(db_path)
        init_db(conn)
        conn.close()

        _login(client)
        page = client.get(f"/connectors/{connector_id}")
        assert page.status_code == 200
        assert connector_id in page.text
        assert "Upload" in page.text

        uploads = {
            "farms": (
                "farms.csv",
                b"FarmID,Name,Reg,Country,Latitude,Longitude,Created,Active\nF1,Farm 1,MSK,RU,55.1,37.2,2025-01-01,true\n",
            ),
            "animals": (
                "animals.csv",
                b"AnimalID,FarmID,EarTag,Breed,Sex,Birth,Alive,Status\nA1,F1,1001,HO,F,2022-01-01,true,active\n",
            ),
            "lactations": (
                "lactations.csv",
                b"AnimalID,LactNo,Calving,Dryoff,DIM,Milk305,Fat,Protein\nA1,1,2025-01-10,2025-11-10,305,12345,3.9,3.2\n",
            ),
        }
        for dataset_key, (filename, payload) in uploads.items():
            r = client.post(
                "/connectors/upload",
                data={"config_path": str(cfg_path), "dataset_key": dataset_key},
                files={"file": (filename, payload, "text/csv")},
                follow_redirects=False,
            )
            assert r.status_code in (302, 303)
            assert (inbox / filename).exists()

        detail = client.get(f"/connectors/{connector_id}")
        assert detail.status_code == 200
        assert str(inbox / "animals.csv") in detail.text
        assert "matched=1" in detail.text

        run_now = client.post("/connectors/run", data={"config_path": str(cfg_path)}, follow_redirects=False)
        assert run_now.status_code in (302, 303)

        worker = JobWorker()
        assert worker.run_until_empty(max_jobs=5) == 1

        conn = connect(db_path)
        rows = [dict(r) for r in conn.execute(
            "SELECT connector_run_id, status, data_version FROM connector_runs WHERE connector_id=? ORDER BY id DESC",
            (connector_id,),
        ).fetchall()]
        audits = [dict(r) for r in conn.execute(
            "SELECT action, status FROM audit_log WHERE action='connector.upload' ORDER BY id DESC"
        ).fetchall()]
        conn.close()
        assert rows
        assert rows[0]["status"] == "success"
        data_version = str(rows[0]["data_version"])
        assert (artifacts / data_version / "canonical" / "dm_animals.csv").exists()
        assert audits and all(a["status"] == "OK" for a in audits[:3])
    finally:
        cfg_path.unlink(missing_ok=True)
