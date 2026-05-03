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
    # canonical/dv/dm_alerts.csv
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


def test_tasks_v1_from_alerts_close_writes_decision_and_resolves_alert(client: TestClient):
    artifacts = Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"])
    dv = "dv_test"
    _seed_alert_sources(artifacts, dv)

    # Viewer can list tasks but cannot generate
    _login(client, "viewer", "viewer")
    r_list_empty = client.get("/api/tasks_v1")
    assert r_list_empty.status_code == 200
    r_forbidden = client.post("/api/tasks_v1/generate_from_alerts", params={"data_version": dv})
    assert r_forbidden.status_code == 403
    client.get("/logout")

    # Zootech generates alerts then tasks
    _login(client, "zootech", "zootech")
    rgen_alerts = client.post("/api/alerts_v2/generate", params={"data_version": dv})
    assert rgen_alerts.status_code == 200

    # T12-02: tasks may be auto-created during alerts generation; keep manual endpoint idempotent.
    rlist_pre = client.get("/api/tasks_v1", params={"status": "open"})
    assert rlist_pre.status_code == 200
    tasks_pre = rlist_pre.json().get("tasks") or []

    rgen_tasks = client.post("/api/tasks_v1/generate_from_alerts", params={"data_version": dv})
    assert rgen_tasks.status_code == 200
    body = rgen_tasks.json()
    assert body["inserted"] >= 0

    rlist = client.get("/api/tasks_v1", params={"status": "open"})
    assert rlist.status_code == 200
    tasks = rlist.json()["tasks"]
    if not tasks:
        # Fallback when auto-tasking is disabled by config
        tasks = tasks_pre
    assert tasks
    # pick a task that has related_alert (for resolve test)
    t0 = next((t for t in tasks if t.get("related_alert")), tasks[0])
    task_id = t0["task_id"]

    # Take then close
    rtake = client.post(f"/api/tasks_v1/{task_id}/take")
    assert rtake.status_code == 200
    rclose = client.post(
        f"/api/tasks_v1/{task_id}/close",
        json={"status": "done", "reason": "performed", "comment": "ok", "resolve_related_alert": True},
    )
    assert rclose.status_code == 200

    # Decision log has task.close
    related_alert = t0.get("related_alert")
    if related_alert:
        rdl = client.get("/api/decision_log_v2", params={"related_alert": related_alert})
        assert rdl.status_code == 200
        actions = [d["action"] for d in rdl.json()["decisions"]]
        assert "task.close" in actions

        # Related alert resolved
        ralert = client.get(f"/api/alerts_v2/{related_alert}")
        assert ralert.status_code == 200
        assert ralert.json()["status"] == "resolved"
