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


def test_whatif_scenarios_rbac_create_and_approve(client: TestClient):
    # viewer: can list, cannot create
    _login(client, "viewer", "viewer")
    r_list = client.get("/api/whatif_scenarios_v1")
    assert r_list.status_code == 200
    r_forbidden = client.post(
        "/api/whatif_scenarios_v1",
        json={"name": "S1", "data_version": "dv_test", "params": {"milk_price_multiplier": 1.1}},
    )
    assert r_forbidden.status_code == 403
    client.get("/logout")

    # zootech: can create
    _login(client, "zootech", "zootech")
    r_create = client.post(
        "/api/whatif_scenarios_v1",
        json={
            "name": "Scenario 1",
            "description": "test",
            "data_version": "dv_test",
            "params": {"milk_price_multiplier": 1.1, "feed_cost_multiplier": 1.0, "other_cost_multiplier": 1.0},
        },
    )
    assert r_create.status_code == 200
    scenario_id = r_create.json()["scenario_id"]

    # zootech cannot approve
    r_appr_forbidden = client.post(f"/api/whatif_scenarios_v1/{scenario_id}/approve", json={"comment": "ok"})
    assert r_appr_forbidden.status_code == 403
    client.get("/logout")

    # director approves
    _login(client, "director", "director")
    r_get1 = client.get(f"/api/whatif_scenarios_v1/{scenario_id}")
    assert r_get1.status_code == 200
    assert r_get1.json()["status"] == "draft"

    r_approve = client.post(f"/api/whatif_scenarios_v1/{scenario_id}/approve", json={"comment": "approved"})
    assert r_approve.status_code == 200

    r_get2 = client.get(f"/api/whatif_scenarios_v1/{scenario_id}")
    assert r_get2.status_code == 200
    assert r_get2.json()["status"] == "approved"
    assert r_get2.json().get("approved_by_username") == "director"

    # audit contains at least create + approve
    ra = client.get("/api/audit", params={"action": "whatif_scenario.create"})
    assert ra.status_code == 200
    assert any((row.get("object_id") == scenario_id) for row in ra.json().get("rows") or [])

    ra2 = client.get("/api/audit", params={"action": "whatif_scenario.approve"})
    assert ra2.status_code == 200
    assert any((row.get("object_id") == scenario_id) for row in ra2.json().get("rows") or [])


def test_whatif_clone_and_archive(client: TestClient):
    # zootech creates a scenario
    _login(client, "zootech", "zootech")
    r_create = client.post(
        "/api/whatif_scenarios_v1",
        json={
            "name": "S1",
            "data_version": "dv_test",
            "params": {"milk_price_multiplier": 1.1, "feed_cost_multiplier": 1.0, "other_cost_multiplier": 1.0},
        },
    )
    assert r_create.status_code == 200
    sid = r_create.json()["scenario_id"]

    # zootech can clone
    r_clone = client.post(f"/api/whatif_scenarios_v1/{sid}/clone", json={})
    assert r_clone.status_code == 200
    new_id = r_clone.json().get("scenario_id")
    assert new_id and new_id != sid
    r_new = client.get(f"/api/whatif_scenarios_v1/{new_id}")
    assert r_new.status_code == 200
    assert r_new.json().get("status") == "draft"
    assert r_new.json().get("cloned_from_scenario_id") == sid

    # zootech cannot archive
    r_arch_forbidden = client.post(f"/api/whatif_scenarios_v1/{sid}/archive", json={"comment": "done"})
    assert r_arch_forbidden.status_code == 403
    client.get("/logout")

    # director archives
    _login(client, "director", "director")
    r_arch = client.post(f"/api/whatif_scenarios_v1/{sid}/archive", json={"comment": "obsolete"})
    assert r_arch.status_code == 200
    r_get = client.get(f"/api/whatif_scenarios_v1/{sid}")
    assert r_get.status_code == 200
    assert r_get.json().get("status") == "archived"
    assert r_get.json().get("archived_by_username") == "director"

    # archived cannot be approved
    r_bad = client.post(f"/api/whatif_scenarios_v1/{sid}/approve", json={"comment": "no"})
    assert r_bad.status_code == 400
