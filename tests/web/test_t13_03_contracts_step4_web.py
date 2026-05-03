from __future__ import annotations

import importlib
import os
import re
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


def test_upload_contract_error_has_report_and_contract_links(client: TestClient):
    _login(client)
    bad_animals = (
        "animals_bad.csv",
        b"AnimalID,EarTag,Breed,Sex,Birth,Alive,Status\nA1,1001,HO,X,2022-01-01,true,active\n",
        "text/csv",
    )
    resp = client.post(
        "/upload/ingest-all",
        data={
            "data_version": "dv_contract_links_001",
            "animals_mapping_path": "configs/mappings/animals_example.yaml",
        },
        files={"animals_file": bad_animals},
    )
    assert resp.status_code == 400
    assert "Открыть контракт" in resp.text
    assert "Открыть validation report" in resp.text
    assert "/contracts?focus=dm_animals#dm_animals" in resp.text

    match = re.search(r'href="(/contracts/validation-report\?path=[^"]+)"', resp.text)
    assert match, resp.text
    report_href = match.group(1)
    report_page = client.get(report_href)
    assert report_page.status_code == 200
    assert "Contract validation report" in report_page.text
    assert "dm_animals" in report_page.text
    assert "FarmID" in report_page.text

    api_href = report_href.replace("/contracts/validation-report", "/api/contracts/validation-report")
    api_resp = client.get(api_href)
    assert api_resp.status_code == 200
    payload = api_resp.json()
    assert payload["dataset_name"] == "dm_animals"
    assert payload["report"]["error_count"] >= 1


def test_connector_run_detail_shows_validation_report_link(client: TestClient, tmp_path: Path):
    from web_cabinet.db import connect, init_db
    from web_cabinet.worker import JobWorker

    repo_root = Path(os.environ["GENOMEAI_PROJECT_ROOT"])
    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    inbox = tmp_path / "connector_inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    connector_id = f"contract_detail_{uuid.uuid4().hex[:8]}"
    cfg_path = repo_root / "configs" / "connectors" / f"{connector_id}.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                f"connector_id: {connector_id}",
                "kind: file",
                "enabled: true",
                f"source_dir: {inbox}",
                'schedule: "*/15 * * * *"',
                'data_version_template: "dv_contract_detail_%Y%m%d_%H%M%S"',
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
            "SELECT connector_run_id FROM connector_runs WHERE connector_id=? ORDER BY id DESC LIMIT 1",
            (connector_id,),
        ).fetchone()
        conn.close()
        assert row is not None

        detail = client.get(f"/connectors/runs/{row[0]}")
        assert detail.status_code == 200
        assert "Открыть validation report" in detail.text
        assert "/contracts?focus=dm_animals#dm_animals" in detail.text
    finally:
        cfg_path.unlink(missing_ok=True)
