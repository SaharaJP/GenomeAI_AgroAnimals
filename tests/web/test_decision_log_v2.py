from __future__ import annotations

import importlib
import os
import sqlite3
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


def test_decision_log_v2_written_from_alert_lifecycle(client: TestClient, tmp_path: Path):
    artifacts = Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"])
    storage = Path(os.environ["GENOMEAI_WEB_STORAGE"])
    dv = "dv_test"
    _seed_alert_sources(artifacts, dv)

    _login(client, "zootech", "zootech")

    # Generate -> ack -> resolve
    rgen = client.post("/api/alerts_v2/generate", params={"data_version": dv})
    assert rgen.status_code == 200

    rlist = client.get("/api/alerts_v2", params={"status": "new"})
    alerts = rlist.json()["alerts"]
    assert alerts
    aid = alerts[0]["alert_id"]

    rack = client.post(f"/api/alerts_v2/{aid}/ack")
    assert rack.status_code == 200
    rres = client.post(f"/api/alerts_v2/{aid}/resolve", json={"reason": "fixed in source"})
    assert rres.status_code == 200

    # Decision log should have 2 records for this alert
    rdl = client.get("/api/decision_log_v2", params={"related_alert": aid})
    assert rdl.status_code == 200
    body = rdl.json()
    assert body["total"] >= 2
    actions = [d["action"] for d in body["decisions"]]
    assert "alert.acknowledge" in actions
    assert "alert.resolve" in actions

    # Verify trace versions are present (may be NULL for some sources)
    d0 = body["decisions"][0]
    assert "data_version" in d0
    assert "model_version" in d0
    assert "report_version" in d0

    # Append-only enforcement: UPDATE should fail
    db_path = storage / "web.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("UPDATE decision_log_v2 SET comment='x' WHERE 1=1")
        conn.commit()
        raise AssertionError("UPDATE should have been blocked by trigger")
    except sqlite3.DatabaseError:
        pass
    finally:
        conn.close()


def test_decision_log_v2_manual_append_api(client: TestClient):
    _login(client, "zootech", "zootech")
    r = client.post(
        "/api/decision_log_v2",
        json={
            "action": "recommendation.confirm",
            "recommendation_id": "rec_1",
            "object_type": "animal",
            "object_id": "A-009",
            "data_version": "dv_x",
            "model_version": "m_x",
            "report_version": "r_x",
            "reason": "ok",
            "comment": "manual confirm",
        },
    )
    assert r.status_code == 200
    did = r.json()["decision_id"]

    rget = client.get(f"/api/decision_log_v2/{did}")
    assert rget.status_code == 200
    assert rget.json()["recommendation_id"] == "rec_1"
