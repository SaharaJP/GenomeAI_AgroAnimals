from __future__ import annotations

import importlib
import os
from pathlib import Path

import pandas as pd
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


def _login(c: TestClient, username: str, password: str):
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def _seed_alert_sources(artifacts: Path, dv: str) -> None:
    # canonical/dv/dm_alerts.csv (legacy producer)
    can = artifacts / "canonical" / dv
    can.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "alert_id": "a1",
                "alert_type": "health_risk",
                "entity_type": "animal",
                "entity_id": "A-001",
                "message": "High health risk (model flag)",
                "confidence": 0.77,
                "model_version": "m1",
                "scoring_run": "s1",
            }
        ]
    ).to_csv(can / "dm_alerts.csv", index=False)

    # qc2 auto alerts
    qc_dir = artifacts / "qc2" / dv / "qc2_20990101_000000_test"
    qc_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "tenant_id": "default",
                "alert_id": "qc_a1",
                "farm_id": "F1",
                "alert_date": "2099-01-01",
                "severity": "MAJOR",
                "alert_type": "QC.PK_DUPLICATE",
                "entity_type": "dataset",
                "entity_id": "dm_animals",
                "message": "Duplicate animal_id",
                "source_rule_id": "pk_animals",
                "qc_run": "qc2_20990101_000000_test",
                "data_version": dv,
            }
        ]
    ).to_csv(qc_dir / "alerts_auto.csv", index=False)


def test_t12_02_auto_tasking_dedup_and_links(client: TestClient):
    artifacts = Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"])
    dv = "dv_test"
    _seed_alert_sources(artifacts, dv)

    _login(client, "zootech", "zootech")

    # 1) generate alerts -> auto tasks
    rgen = client.post("/api/alerts_v2/generate", params={"data_version": dv})
    assert rgen.status_code == 200
    body = rgen.json()
    assert "auto_tasks" in body
    assert body["auto_tasks"]["inserted"] >= 1

    rlist = client.get("/api/tasks_v1", params={"status": "open"})
    assert rlist.status_code == 200
    tasks = rlist.json().get("tasks") or []
    assert len(tasks) >= 1

    # Every auto-created task must keep links (alert <-> task <-> versions)
    for t in tasks:
        assert t.get("related_alert")
        assert t.get("data_version") == dv

    # At least one QC task should carry qc_run from qc2
    assert any(str(t.get("qc_run") or "").startswith("qc2_") for t in tasks)

    # 2) re-generate alerts -> should NOT create duplicate tasks for same object/reason
    count_before = len(tasks)
    rgen2 = client.post("/api/alerts_v2/generate", params={"data_version": dv})
    assert rgen2.status_code == 200
    body2 = rgen2.json()
    assert body2["auto_tasks"]["inserted"] == 0

    rlist2 = client.get("/api/tasks_v1", params={"status": "open"})
    assert rlist2.status_code == 200
    tasks2 = rlist2.json().get("tasks") or []
    assert len(tasks2) == count_before

    # 3) mutual link check: alert exists and is readable
    any_task = tasks2[0]
    aid = str(any_task.get("related_alert"))
    ralert = client.get(f"/api/alerts_v2/{aid}")
    assert ralert.status_code == 200
    alert = ralert.json()
    assert alert.get("alert_id") == aid
    assert alert.get("data_version") == dv
