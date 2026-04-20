from __future__ import annotations

import importlib
import os
import shutil
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

    # Prepare canonical data for economics in the temp artifacts root
    canon = artifacts / "dv_test" / "canonical"
    canon.mkdir(parents=True, exist_ok=True)
    fixtures = repo_root / "data" / "fixtures" / "target_v2"
    for f in fixtures.glob("*.csv"):
        shutil.copy2(f, canon / f.name)

    with TestClient(appmod.app) as c:
        yield c


def _login(c: TestClient, username: str, password: str):
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_whatif_compare_api_happy_path_and_audit(client: TestClient):
    # zootech creates scenarios
    _login(client, "zootech", "zootech")
    r1 = client.post(
        "/api/whatif_scenarios_v1",
        json={
            "name": "MILK_X2",
            "data_version": "dv_test",
            "params": {
                "date_from": "2025-01-05",
                "date_to": "2025-01-05",
                "cfg_path": "configs/economics/economics_v1.yaml",
                "milk_price_multiplier": 2.0,
                "feed_cost_multiplier": 1.0,
                "other_cost_multiplier": 1.0,
            },
        },
    )
    assert r1.status_code == 200
    s1 = r1.json()["scenario_id"]

    r2 = client.post(
        "/api/whatif_scenarios_v1",
        json={
            "name": "FEED_X2",
            "data_version": "dv_test",
            "params": {
                "date_from": "2025-01-05",
                "date_to": "2025-01-05",
                "cfg_path": "configs/economics/economics_v1.yaml",
                "milk_price_multiplier": 1.0,
                "feed_cost_multiplier": 2.0,
                "other_cost_multiplier": 1.0,
            },
        },
    )
    assert r2.status_code == 200
    s2 = r2.json()["scenario_id"]

    # Compare via API
    r_cmp = client.post(
        "/api/whatif_compare_v1",
        json={
            "scenario_ids": [s1, s2],
            "base_context": {
                "data_version": "dv_test",
                "date_from": "2025-01-05",
                "date_to": "2025-01-05",
                "cfg_path": "configs/economics/economics_v1.yaml",
            },
        },
    )
    assert r_cmp.status_code == 200
    payload = r_cmp.json()
    assert payload.get("ok") is True
    rows = payload.get("comparison") or []
    # BASE + 2 scenarios
    assert len(rows) == 3
    assert any((r.get("scenario") == "BASE") for r in rows)
    assert payload.get("base_economics_run")
    assert set(payload.get("scenario_runs") or {}).issuperset({s1, s2})

    # last_economics_run attached
    g1 = client.get(f"/api/whatif_scenarios_v1/{s1}")
    assert g1.status_code == 200
    assert g1.json().get("last_economics_run")

    client.get("/logout")

    # audit is visible to director
    _login(client, "director", "director")
    ra = client.get("/api/audit", params={"action": "whatif_scenario.compare"})
    assert ra.status_code == 200
    obj = ",".join([s1, s2])
    assert any((row.get("object_id") == obj) for row in ra.json().get("rows") or [])


def test_whatif_compare_requires_2_scenarios(client: TestClient):
    _login(client, "zootech", "zootech")
    r = client.post("/api/whatif_compare_v1", json={"scenario_ids": []})
    assert r.status_code == 400
    r2 = client.post("/api/whatif_compare_v1", json={"scenario_ids": ["one"]})
    assert r2.status_code == 400
