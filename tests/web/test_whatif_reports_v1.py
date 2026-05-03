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


def test_whatif_report_generate_rbac_and_indexing(client: TestClient):
    # viewer: can view reports list, cannot generate
    _login(client, "viewer", "viewer")
    r_list0 = client.get("/api/whatif_reports_v1")
    assert r_list0.status_code == 200
    r_forbidden = client.post("/api/whatif_scenarios_v1/unknown/report_pdf", json={"reuse_last_run": True})
    assert r_forbidden.status_code in (403, 404)  # 403 (no generate perm) preferred
    client.get("/logout")

    # zootech: create scenario + generate report
    _login(client, "zootech", "zootech")
    r_create = client.post(
        "/api/whatif_scenarios_v1",
        json={
            "name": "S_MILK_X2",
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
    assert r_create.status_code == 200
    scenario_id = r_create.json()["scenario_id"]

    r_gen = client.post(f"/api/whatif_scenarios_v1/{scenario_id}/report_pdf", json={"reuse_last_run": False})
    assert r_gen.status_code == 200
    rep_ver = r_gen.json().get("report_version")
    assert rep_ver

    r_list = client.get("/api/whatif_reports_v1", params={"scenario_id": scenario_id})
    assert r_list.status_code == 200
    rows = r_list.json().get("reports") or []
    assert any((row.get("report_version") == rep_ver) for row in rows)

    client.get("/logout")

    # audit has report.generate (audit.view is typically Director/Admin)
    _login(client, "director", "director")
    ra = client.get("/api/audit", params={"action": "whatif_report.generate"})
    assert ra.status_code == 200
    assert any((row.get("object_id") == rep_ver) for row in ra.json().get("rows") or [])


def test_whatif_report_governance_requires_approval_when_enabled(client: TestClient, tmp_path: Path):
    # custom economics cfg with governance.require_approval_for_report_pdf
    cfg = tmp_path / "econ_cfg.yaml"
    cfg.write_text(
        """
schema: genomeai.economics.v1
defaults:
  currency: EUR
  milk_price_per_kg: 0.5
  feed_cost_per_kg_dm: 0.28
  other_cost_per_farm_day: 120.0
allocation:
  other_cost_allocation: revenue_share
what_if:
  milk_price_multiplier_range: [0.5, 2.0]
  feed_cost_multiplier_range: [0.5, 2.0]
  other_cost_multiplier_range: [0.5, 2.0]
governance:
  require_approval_for_report_pdf: true
""".strip()
        + "\n",
        encoding="utf-8",
    )

    # zootech: create scenario
    _login(client, "zootech", "zootech")
    r_create = client.post(
        "/api/whatif_scenarios_v1",
        json={
            "name": "S_NEEDS_APPROVAL",
            "data_version": "dv_test",
            "params": {
                "date_from": "2025-01-05",
                "date_to": "2025-01-05",
                "cfg_path": str(cfg),
                "milk_price_multiplier": 1.0,
                "feed_cost_multiplier": 1.0,
                "other_cost_multiplier": 1.0,
            },
        },
    )
    assert r_create.status_code == 200
    scenario_id = r_create.json()["scenario_id"]

    # draft -> should be forbidden for report generation
    r_forbidden = client.post(f"/api/whatif_scenarios_v1/{scenario_id}/report_pdf", json={"reuse_last_run": False})
    assert r_forbidden.status_code == 403
    client.get("/logout")

    # director approves
    _login(client, "director", "director")
    r_app = client.post(f"/api/whatif_scenarios_v1/{scenario_id}/approve", json={"comment": "ok"})
    assert r_app.status_code == 200
    client.get("/logout")

    # zootech can generate after approval
    _login(client, "zootech", "zootech")
    r_gen = client.post(f"/api/whatif_scenarios_v1/{scenario_id}/report_pdf", json={"reuse_last_run": False})
    assert r_gen.status_code == 200
