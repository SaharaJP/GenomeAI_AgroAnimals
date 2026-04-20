from __future__ import annotations

import importlib
import os
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


def _login(c: TestClient, username: str, password: str):
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_director_can_reject_whatif_scenario_with_comment_and_audit(client: TestClient):
    _login(client, "zootech", "zootech")

    r_create = client.post(
        "/api/whatif_scenarios_v1",
        json={"name": "Scenario A", "data_version": "dv_demo", "params": {"milk_price": 50}},
    )
    assert r_create.status_code == 200
    scenario_id = r_create.json()["scenario_id"]

    # zootech cannot reject (director-only)
    r_forbidden = client.post(
        f"/api/whatif_scenarios_v1/{scenario_id}/reject",
        json={"comment": "no"},
    )
    assert r_forbidden.status_code == 403

    client.get("/logout")
    _login(client, "director", "director")

    r_reject = client.post(
        f"/api/whatif_scenarios_v1/{scenario_id}/reject",
        json={"comment": "  Нужно уточнить предпосылки  "},
    )
    assert r_reject.status_code == 200

    r_get = client.get(f"/api/whatif_scenarios_v1/{scenario_id}")
    assert r_get.status_code == 200
    s = r_get.json()
    assert s["status"] == "draft"  # workflow: draft -> approved -> archived
    assert s.get("rejected_at")
    assert s.get("rejected_by_username") == "director"
    assert s.get("rejection_comment") == "Нужно уточнить предпосылки"

    # approve clears rejection metadata
    r_approve = client.post(
        f"/api/whatif_scenarios_v1/{scenario_id}/approve",
        json={"comment": "OK"},
    )
    assert r_approve.status_code == 200
    s2 = client.get(f"/api/whatif_scenarios_v1/{scenario_id}").json()
    assert s2["status"] == "approved"
    assert s2.get("rejected_at") is None
    assert s2.get("rejection_comment") is None

    ra = client.get("/api/audit", params={"action": "whatif_scenario.reject"})
    assert ra.status_code == 200
    rows = ra.json()["rows"]
    assert len(rows) >= 1
    assert rows[0]["object_id"] == scenario_id
