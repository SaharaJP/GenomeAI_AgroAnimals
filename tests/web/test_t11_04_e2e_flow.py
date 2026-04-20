from __future__ import annotations

import importlib
import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path):
    """E2E fixture with isolated web storage + isolated artifacts root and canonical fixtures."""
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


def test_t11_04_e2e_create_approve_compare_report_and_audit(client: TestClient):
    """Acceptance-like flow:

    - Zootech creates 2 scenarios
    - Director approves one scenario
    - Zootech compares scenarios vs BASE
    - Zootech generates PDF report for approved scenario (reusing last run)
    - Director sees audit actions
    """

    # 1) Zootech creates scenarios
    _login(client, "zootech", "zootech")

    r1 = client.post(
        "/api/whatif_scenarios_v1",
        json={
            "name": "S1_MILK_X2",
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
            "name": "S2_FEED_X2",
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

    client.get("/logout")

    # 2) Director approves one scenario
    _login(client, "director", "director")
    r_app = client.post(f"/api/whatif_scenarios_v1/{s1}/approve", json={"comment": "approved"})
    assert r_app.status_code == 200
    client.get("/logout")

    # 3) Zootech compares two scenarios vs BASE
    _login(client, "zootech", "zootech")
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
    assert len(rows) == 3  # BASE + 2 scenarios
    assert any((r.get("scenario") == "BASE") for r in rows)

    # Ensure last_economics_run set for approved scenario
    g1 = client.get(f"/api/whatif_scenarios_v1/{s1}")
    assert g1.status_code == 200
    last_run = g1.json().get("last_economics_run")
    assert last_run

    # 4) Generate PDF report for approved scenario (reuse last run)
    r_rep = client.post(f"/api/whatif_scenarios_v1/{s1}/report_pdf", json={"reuse_last_run": True})
    assert r_rep.status_code == 200
    rep_ver = r_rep.json().get("report_version")
    assert rep_ver

    r_list = client.get("/api/whatif_reports_v1", params={"scenario_id": s1})
    assert r_list.status_code == 200
    assert any((row.get("report_version") == rep_ver) for row in (r_list.json().get("reports") or []))

    client.get("/logout")

    # 5) Director can see audit
    _login(client, "director", "director")
    ra_create = client.get("/api/audit", params={"action": "whatif_scenario.create"})
    assert ra_create.status_code == 200
    assert any((row.get("object_id") in (s1, s2)) for row in (ra_create.json().get("rows") or []))

    ra_approve = client.get("/api/audit", params={"action": "whatif_scenario.approve"})
    assert ra_approve.status_code == 200
    assert any((row.get("object_id") == s1) for row in (ra_approve.json().get("rows") or []))

    ra_compare = client.get("/api/audit", params={"action": "whatif_scenario.compare"})
    assert ra_compare.status_code == 200

    ra_report = client.get("/api/audit", params={"action": "whatif_report.generate"})
    assert ra_report.status_code == 200
    assert any((row.get("object_id") == rep_ver) for row in (ra_report.json().get("rows") or []))
