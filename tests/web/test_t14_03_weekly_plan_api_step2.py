from __future__ import annotations

import importlib
import json
import os
import sqlite3
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


def _login(c: TestClient, username: str, password: str) -> None:
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303), r.text


def _seed_artifacts_and_tasks(base_artifacts: Path, db_path: Path) -> None:
    kpi_dir = base_artifacts / "dv_demo" / "runs" / "kpi_run_001" / "kpi"
    kpi_dir.mkdir(parents=True, exist_ok=True)
    (kpi_dir / "kpi_summary.json").write_text(
        json.dumps({"run_id": "kpi_run_001", "kpi_count": 3, "alert_count": 2}, ensure_ascii=False),
        encoding="utf-8",
    )
    (kpi_dir / "kpi_wide.csv").write_text("farm_id,milk_kg\nfarm_1,123.4\n", encoding="utf-8")
    (kpi_dir / "kpi_alerts.csv").write_text("alert_id,severity,farm_id\na1,high,farm_1\na2,medium,farm_1\n", encoding="utf-8")

    mast_dir = base_artifacts / "dv_demo" / "mastitis" / "scoring" / "mast_run_001"
    mast_dir.mkdir(parents=True, exist_ok=True)
    (mast_dir / "scoring_summary.json").write_text(
        json.dumps({"scoring_run": "mast_run_001", "asof_date": "2026-03-09", "horizon_days": 7, "risk_threshold": 0.7}, ensure_ascii=False),
        encoding="utf-8",
    )
    (mast_dir / "mastitis_risk_scores.csv").write_text(
        "farm_id,animal_id,risk_score,severity\nfarm_1,1001,0.91,high\nfarm_1,1002,0.89,high\n",
        encoding="utf-8",
    )

    econ_dir = base_artifacts / "dv_demo" / "economics" / "econ_run_001"
    econ_dir.mkdir(parents=True, exist_ok=True)
    (econ_dir / "summary_farm.csv").write_text(
        "farm_id,revenue_milk,margin_total\nfarm_1,100000,42000\n",
        encoding="utf-8",
    )
    (econ_dir / "whatif_params.json").write_text(
        json.dumps({"economics_run": "econ_run_001", "scenario_name": "base"}, ensure_ascii=False),
        encoding="utf-8",
    )

    from web_cabinet.db import init_db
    from web_cabinet.tasks_v1 import TaskCreate, create_task

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    create_task(
        conn,
        tenant_id="default",
        t=TaskCreate(
            task_type="health.check",
            title="Проверить животное 1001",
            priority=1,
            object_type="animal",
            object_id="1001",
            data_version="dv_demo",
        ),
    )
    create_task(
        conn,
        tenant_id="default",
        t=TaskCreate(
            task_type="repro.check",
            title="Сверить осеменения",
            priority=2,
            object_type="farm",
            object_id="farm_1",
            data_version="dv_demo",
        ),
    )
    conn.execute("UPDATE tasks_v1 SET status='open', assignee_team='vet' WHERE object_id='1001'")
    conn.execute("UPDATE tasks_v1 SET status='open', assignee_team='zootech' WHERE object_id='farm_1'")
    conn.commit()
    conn.close()


def test_api_weekly_plan_request_approval_and_export_pdf(client: TestClient) -> None:
    artifacts_root = Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"])
    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    _seed_artifacts_and_tasks(artifacts_root, db_path)

    _login(client, "zootech", "zootech")
    r_generate = client.post(
        "/api/weekly_plans_v1/generate",
        json={
            "week_start": "2026-03-09",
            "data_version": "dv_demo",
            "farm_id": "farm_1",
            "question": "Сформируй план на неделю",
        },
    )
    assert r_generate.status_code == 200, r_generate.text
    plan_id = r_generate.json()["plan_id"]

    r_request = client.post(f"/api/weekly_plans_v1/{plan_id}/request_approval", json={"comment": "Нужен обзор директора"})
    assert r_request.status_code == 200, r_request.text
    req_payload = r_request.json()
    assert req_payload["plan"]["approval_requested_at"]
    assert req_payload["plan"]["approval_request_comment"] == "Нужен обзор директора"

    client.get("/logout")
    _login(client, "director", "director")

    r_audit_req = client.get("/api/audit", params={"action": "weekly_plan.request_approval", "object_id": plan_id})
    assert r_audit_req.status_code == 200, r_audit_req.text
    rows_req = r_audit_req.json().get("rows") or []
    assert rows_req and rows_req[0]["object_id"] == plan_id

    r_approve = client.post(f"/api/weekly_plans_v1/{plan_id}/approve", json={"comment": "OK"})
    assert r_approve.status_code == 200, r_approve.text
    tasks = r_approve.json().get("tasks") or {}
    assert len(tasks.get("tasks_created") or []) >= 1

    r_export = client.post(f"/api/weekly_plans_v1/{plan_id}/export_pdf")
    assert r_export.status_code == 200, r_export.text
    export_payload = r_export.json()
    pdf_rel_path = str(export_payload["pdf_rel_path"])
    assert pdf_rel_path.endswith("weekly_plan.pdf")
    full_pdf = artifacts_root / Path(pdf_rel_path).relative_to("artifacts")
    assert full_pdf.exists()
    assert full_pdf.read_bytes().startswith(b"%PDF")

    r_download = client.get("/download", params={"path": pdf_rel_path})
    assert r_download.status_code == 200, r_download.text
    assert r_download.content.startswith(b"%PDF")

    r_plan = client.get(f"/api/weekly_plans_v1/{plan_id}")
    assert r_plan.status_code == 200, r_plan.text
    plan = r_plan.json()
    assert plan["pdf_rel_path"].endswith("weekly_plan.pdf")
    assert plan["pdf_exported_at"]

    r_audit_pdf = client.get("/api/audit", params={"action": "weekly_plan.export_pdf", "object_id": plan_id})
    assert r_audit_pdf.status_code == 200, r_audit_pdf.text
    rows_pdf = r_audit_pdf.json().get("rows") or []
    assert rows_pdf and rows_pdf[0]["object_id"] == plan_id
