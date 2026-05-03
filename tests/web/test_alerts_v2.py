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

    # canonical/dv/dm_treatments.csv
    pd.DataFrame(
        [
            {
                "treatment_id": "t1",
                "animal_id": "A-002",
                "drug_code": "ABX1",
                "withdrawal_end_date": "2099-01-10",
            }
        ]
    ).to_csv(can / "dm_treatments.csv", index=False)

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


def test_alerts_v2_lifecycle_and_rbac(client: TestClient):
    artifacts = Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"])
    dv = "dv_test"
    _seed_alert_sources(artifacts, dv)

    # Viewer: can list, cannot generate
    _login(client, "viewer", "viewer")
    r0 = client.get("/api/alerts_v2")
    assert r0.status_code == 200

    rgen_forbidden = client.post("/api/alerts_v2/generate", params={"data_version": dv})
    assert rgen_forbidden.status_code == 403

    client.get("/logout")

    # Zootech: can generate
    _login(client, "zootech", "zootech")
    rgen = client.post("/api/alerts_v2/generate", params={"data_version": dv})
    assert rgen.status_code == 200
    body = rgen.json()
    assert body["candidates"] >= 3
    assert body["inserted"] >= 3

    rlist = client.get("/api/alerts_v2", params={"status": "new"})
    assert rlist.status_code == 200
    alerts = rlist.json()["alerts"]
    assert len(alerts) >= 1
    aid = alerts[0]["alert_id"]

    # ack
    rack = client.post(f"/api/alerts_v2/{aid}/ack")
    assert rack.status_code == 200

    # resolve requires reason
    rbad = client.post(f"/api/alerts_v2/{aid}/resolve", json={})
    assert rbad.status_code == 400

    rres = client.post(f"/api/alerts_v2/{aid}/resolve", json={"reason": "fixed in source"})
    assert rres.status_code == 200

    # status updated
    rget = client.get(f"/api/alerts_v2/{aid}")
    assert rget.status_code == 200
    assert rget.json()["status"] == "resolved"
