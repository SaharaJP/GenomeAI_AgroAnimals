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


def _login(c: TestClient, username: str = "admin", password: str = "admin"):
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303), r.text


def _latest_action_row(client: TestClient, action: str, object_id: str | None = None):
    params = {"action": action, "limit": 200}
    if object_id is not None:
        params["object_id"] = object_id
    r = client.get("/api/audit", params=params)
    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    assert rows, f"expected audit row for action={action} object_id={object_id}"
    return rows[0]


def test_t13_05_pack_enqueue_audit_uses_job_run_refs(client: TestClient):
    _login(client)

    r = client.post(
        "/pack/run",
        data={
            "data_version": "dv_pack_001",
            "qc_run": "qc_pack_001",
            "model_version": "mv_pack_001",
            "scoring_run": "sr_pack_001",
            "report_version": "rp_pack_001",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), r.text

    row = _latest_action_row(client, "pipeline.enqueue", object_id="pack")
    assert row["data_version"] == "dv_pack_001"
    assert row["run_id"] == "rp_pack_001"
    assert row["after"]["report_version"] == "rp_pack_001"
    assert row["after"]["scoring_run"] == "sr_pack_001"
    assert row["after"]["public_job_id"]


def test_t13_05_weekly_plan_approval_audit_carries_tasks_run_id(client: TestClient):
    _login(client)

    create_resp = client.post(
        "/api/weekly_plans_v1",
        json={
            "name": "Weekly Plan A",
            "week_start": "2026-03-09",
            "data_version": "dv_wp_001",
            "action_items": [
                {"key": "feed-review", "title": "Review feed deviations", "domain": "data"}
            ],
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    plan_id = create_resp.json()["plan_id"]

    approve_resp = client.post(f"/api/weekly_plans_v1/{plan_id}/approve", json={"comment": "ok"})
    assert approve_resp.status_code == 200, approve_resp.text
    tasks_run_id = approve_resp.json()["tasks"]["tasks_run_id"]
    assert tasks_run_id

    row = _latest_action_row(client, "weekly_plan.approve", object_id=plan_id)
    assert row["data_version"] == "dv_wp_001"
    assert row["run_id"] == tasks_run_id
    assert row["after"]["tasks"]["tasks_run_id"] == tasks_run_id


def test_t13_05_report_approval_audit_uses_report_version_as_run_id(client: TestClient):
    _login(client)
    artifacts_root = Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"])
    report_dir = artifacts_root / "dv_rep_001" / "reports" / "rp_approve_001"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "summary.json").write_text("{}", encoding="utf-8")

    resp = client.post(
        "/api/reports_v1/rp_approve_001/approve",
        json={"data_version": "dv_rep_001", "comment": "approved"},
    )
    assert resp.status_code == 200, resp.text

    row = _latest_action_row(client, "report.approve", object_id="dv_rep_001:rp_approve_001")
    assert row["data_version"] == "dv_rep_001"
    assert row["run_id"] == "rp_approve_001"
    assert row["object"]["ref"] == "report:dv_rep_001:rp_approve_001"


def test_t13_05_whatif_approval_audit_uses_last_economics_run(client: TestClient):
    _login(client)

    create_resp = client.post(
        "/api/whatif_scenarios_v1",
        json={
            "name": "Scenario A",
            "data_version": "dv_whatif_001",
            "params": {
                "date_from": "2026-03-01",
                "date_to": "2026-03-31",
                "milk_price_multiplier": 1.05,
            },
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    scenario_id = create_resp.json()["scenario_id"]

    import web_cabinet.app as appmod
    from web_cabinet.db import connect
    from web_cabinet.whatif_scenarios_v1 import attach_last_run

    conn = connect(appmod.settings.db_path)
    try:
        attach_last_run(conn, tenant_id="default", scenario_id=scenario_id, economics_run="econ_run_001")
    finally:
        conn.close()

    approve_resp = client.post(f"/api/whatif_scenarios_v1/{scenario_id}/approve", json={"comment": "ship it"})
    assert approve_resp.status_code == 200, approve_resp.text

    row = _latest_action_row(client, "whatif_scenario.approve", object_id=scenario_id)
    assert row["data_version"] == "dv_whatif_001"
    assert row["run_id"] == "econ_run_001"


def test_t13_05_refdata_price_actions_are_grouped_as_config(client: TestClient):
    _login(client)

    from streamlit_app.common import Context, audit_action

    ctx = Context(
        artifacts_dir=Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"]),
        web_storage_dir=Path(os.environ["GENOMEAI_WEB_STORAGE"]),
    )
    audit_action(
        ctx,
        {"tenant_id": "default", "id": 1, "username": "admin", "role": "Admin"},
        action="refdata.price_book.create",
        object_type="price_book",
        object_id="pb_v1",
        after={"version_id": "pb_v1", "effective_date": "2026-03-01"},
    )

    r = client.get("/api/audit", params={"action_group": "config", "q": "pb_v1", "limit": 100})
    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    assert any(row["action"] == "refdata.price_book.create" for row in rows)
    row = next(row for row in rows if row["action"] == "refdata.price_book.create")
    assert row["action_group"] == "config"
    assert row["object"]["type"] == "price_book"
