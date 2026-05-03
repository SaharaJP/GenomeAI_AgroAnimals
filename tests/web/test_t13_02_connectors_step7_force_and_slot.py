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


def test_force_run_and_manual_schedule_slot_queue_and_execute(client: TestClient, tmp_path: Path):
    from web_cabinet.db import connect, init_db
    from web_cabinet.worker import JobWorker

    repo_root = Path(os.environ["GENOMEAI_PROJECT_ROOT"])
    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    artifacts = Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"])
    inbox = tmp_path / "force_slot_inbox"
    _write_sources(inbox)

    connector_id = f"force_slot_{uuid.uuid4().hex[:8]}"
    cfg_path = repo_root / "configs" / "connectors" / f"{connector_id}.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                f"connector_id: {connector_id}",
                "kind: file",
                "enabled: true",
                f"source_dir: {inbox}",
                'schedule: "*/15 * * * *"',
                'data_version_template: "dv_force_slot_%Y%m%d_%H%M%S"',
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
        detail = client.get(f"/connectors/{connector_id}")
        assert detail.status_code == 200
        assert "Schedule control" in detail.text
        assert "Force run" in detail.text
        assert "Queue selected slot" in detail.text

        first = client.post(
            "/connectors/run",
            data={"config_path": str(cfg_path), "redirect_to": f"/connectors/{connector_id}"},
            follow_redirects=False,
        )
        assert first.status_code in (302, 303)
        worker = JobWorker()
        assert worker.run_until_empty(max_jobs=5) == 1

        forced = client.post(
            "/connectors/run",
            data={"config_path": str(cfg_path), "redirect_to": f"/connectors/{connector_id}", "force": "1"},
            follow_redirects=False,
        )
        assert forced.status_code in (302, 303)
        worker = JobWorker()
        assert worker.run_until_empty(max_jobs=5) == 1

        slot = "2026-03-07T10:15:00+00:00"
        queued_slot = client.post(
            "/connectors/run-slot",
            data={
                "config_path": str(cfg_path),
                "redirect_to": f"/connectors/{connector_id}",
                "scheduled_slot": slot,
                "force": "1",
            },
            follow_redirects=False,
        )
        assert queued_slot.status_code in (302, 303)

        conn = connect(db_path)
        runs = [dict(r) for r in conn.execute(
            "SELECT connector_run_id, trigger_type, status, data_version FROM connector_runs WHERE connector_id=? ORDER BY id ASC",
            (connector_id,),
        ).fetchall()]
        jobs = [dict(r) for r in conn.execute(
            "SELECT status, args_json FROM jobs WHERE kind='connector_run' ORDER BY id DESC LIMIT 1"
        ).fetchall()]
        audits = [dict(r) for r in conn.execute(
            "SELECT action, status FROM audit_log WHERE object_id=? ORDER BY id DESC",
            (connector_id,),
        ).fetchall()]
        conn.close()

        assert len(runs) >= 2
        assert runs[0]["status"] == "success"
        assert runs[1]["status"] == "success"
        assert runs[1]["trigger_type"] == "manual_force"
        assert runs[0]["data_version"] != runs[1]["data_version"]
        assert (artifacts / str(runs[1]["data_version"]) / "canonical" / "dm_animals.csv").exists()

        last_args = json.loads(jobs[0]["args_json"])
        argv = last_args.get("argv") or []
        assert "--scheduled-slot" in argv
        assert slot in argv
        assert "--force" in argv
        assert any(a["action"] == "connector.enqueue" and a["status"] == "OK" for a in audits)
    finally:
        cfg_path.unlink(missing_ok=True)
