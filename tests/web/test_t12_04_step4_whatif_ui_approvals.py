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


def test_whatif_ui_approve_reject_archive_and_rbac(client: TestClient):
    _login(client, "zootech", "zootech")

    r_create = client.post(
        "/api/whatif_scenarios_v1",
        json={"name": "Scenario UI", "data_version": "dv_demo", "params": {"milk_price": 55}},
    )
    assert r_create.status_code == 200
    scenario_id = r_create.json()["scenario_id"]

    # list page works
    r_list = client.get("/whatif_scenarios")
    assert r_list.status_code == 200
    assert "Scenario UI" in r_list.text

    # zootech can't approve/reject
    r_forbidden = client.post(f"/whatif_scenarios/{scenario_id}/approve", data={"comment": "ok"}, follow_redirects=False)
    assert r_forbidden.status_code == 403

    client.get("/logout")
    _login(client, "director", "director")

    # reject via UI keeps status draft but stores metadata
    r_reject = client.post(
        f"/whatif_scenarios/{scenario_id}/reject",
        data={"comment": "Нужно добавить обоснование"},
        follow_redirects=False,
    )
    assert r_reject.status_code in (302, 303)
    s = client.get(f"/api/whatif_scenarios_v1/{scenario_id}").json()
    assert s["status"] == "draft"
    assert s.get("rejected_by_username") == "director"
    assert s.get("rejection_comment") == "Нужно добавить обоснование"

    # approve clears rejection
    r_approve = client.post(
        f"/whatif_scenarios/{scenario_id}/approve",
        data={"comment": "OK"},
        follow_redirects=False,
    )
    assert r_approve.status_code in (302, 303)
    s2 = client.get(f"/api/whatif_scenarios_v1/{scenario_id}").json()
    assert s2["status"] == "approved"
    assert s2.get("rejected_at") is None
    assert s2.get("rejection_comment") is None

    # archive via UI
    r_archive = client.post(
        f"/whatif_scenarios/{scenario_id}/archive",
        data={"comment": "закрыли"},
        follow_redirects=False,
    )
    assert r_archive.status_code in (302, 303)
    s3 = client.get(f"/api/whatif_scenarios_v1/{scenario_id}").json()
    assert s3["status"] == "archived"
    assert s3.get("archived_by_username") == "director"

    # audit has approve/reject/archive
    ra = client.get("/api/audit", params={"action": "whatif_scenario.approve"}).json().get("rows") or []
    assert any(r.get("object_id") == scenario_id for r in ra)
    rr = client.get("/api/audit", params={"action": "whatif_scenario.reject"}).json().get("rows") or []
    assert any(r.get("object_id") == scenario_id for r in rr)
    rarc = client.get("/api/audit", params={"action": "whatif_scenario.archive"}).json().get("rows") or []
    assert any(r.get("object_id") == scenario_id for r in rarc)
