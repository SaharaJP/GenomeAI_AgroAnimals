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


def test_upload_page_shows_mapping_templates(client: TestClient):
    _login(client)
    resp = client.get("/upload")
    assert resp.status_code == 200
    assert "configs/mappings/templates/selex/animals.yaml" in resp.text
    assert "configs/mappings/templates/1c/lactations.yaml" in resp.text
    assert "configs/mappings/templates/excel/farms.yaml" in resp.text


def test_upload_blocks_invalid_contract_and_writes_audit(client: TestClient):
    from web_cabinet.db import connect

    _login(client)
    bad_animals = (
        "animals_bad.csv",
        b"AnimalID,EarTag,Breed,Sex,Birth,Alive,Status\nA1,1001,HO,X,2022-01-01,true,active\n",
        "text/csv",
    )
    resp = client.post(
        "/upload/ingest-all",
        data={
            "data_version": "dv_contract_fail_001",
            "animals_mapping_path": "configs/mappings/animals_example.yaml",
        },
        files={"animals_file": bad_animals},
    )
    assert resp.status_code == 400
    assert "Contract validation не пройдена" in resp.text
    assert "Колонка из mapping не найдена" in resp.text
    assert "allowed_values" in resp.text

    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    conn = connect(db_path)
    jobs = conn.execute("SELECT COUNT(*) AS cnt FROM jobs").fetchone()[0]
    audit = conn.execute(
        "SELECT action, status, error FROM audit_log WHERE action='contract.validate' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert jobs == 0
    assert audit[0] == "contract.validate"
    assert audit[1] == "FAIL"
    assert "FarmID" in (audit[2] or "")


def test_connector_run_marks_dataset_failed_on_contract_validation(client: TestClient, tmp_path: Path):
    from web_cabinet.db import connect, init_db
    from web_cabinet.worker import JobWorker

    repo_root = Path(os.environ["GENOMEAI_PROJECT_ROOT"])
    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    artifacts = Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"])
    inbox = tmp_path / "connector_inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    connector_id = f"contract_fail_{uuid.uuid4().hex[:8]}"
    cfg_path = repo_root / "configs" / "connectors" / f"{connector_id}.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                f"connector_id: {connector_id}",
                "kind: file",
                "enabled: true",
                f"source_dir: {inbox}",
                'schedule: "*/15 * * * *"',
                'data_version_template: "dv_contract_%Y%m%d_%H%M%S"',
                "datasets:",
                f"  - dataset_key: animals\n    pattern: 'animals.csv'\n    mapping: {repo_root / 'configs/mappings/animals_example.yaml'}",
            ]
        ),
        encoding="utf-8",
    )
    (inbox / "animals.csv").write_text(
        "AnimalID,EarTag,Breed,Sex,Birth,Alive,Status\nA1,1001,HO,X,2022-01-01,true,active\n",
        encoding="utf-8",
    )

    try:
        conn = connect(db_path)
        init_db(conn)
        conn.close()

        _login(client)
        run_now = client.post("/connectors/run", data={"config_path": str(cfg_path)}, follow_redirects=False)
        assert run_now.status_code in (302, 303)

        worker = JobWorker()
        assert worker.run_until_empty(max_jobs=5) == 1

        conn = connect(db_path)
        row = conn.execute(
            "SELECT connector_run_id, status, data_version, outputs_json FROM connector_runs WHERE connector_id=? ORDER BY id DESC LIMIT 1",
            (connector_id,),
        ).fetchone()
        conn.close()
        assert row is not None
        connector_run_id, status, data_version, outputs_json = row
        assert status == "failed"

        manifest = artifacts / str(data_version) / "connectors" / str(connector_run_id) / "manifest.json"
        assert manifest.exists()
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        dataset_result = payload["dataset_results"][0]
        assert dataset_result["error_type"] == "ContractValidationError"
        assert dataset_result["validation_error_count"] >= 1
        validation_report = Path(dataset_result["validation_errors_json"])
        assert validation_report.exists()
        report_payload = json.loads(validation_report.read_text(encoding="utf-8"))
        assert report_payload["error_count"] >= 1
        assert any("FarmID" in line or "allowed_values" in line for line in report_payload["preview"])
    finally:
        cfg_path.unlink(missing_ok=True)
