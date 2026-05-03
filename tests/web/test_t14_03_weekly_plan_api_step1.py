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


def test_api_generate_weekly_plan_creates_draft_with_citations_and_approval(client: TestClient) -> None:
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
    payload = r_generate.json()
    plan_id = payload["plan_id"]
    generated = payload["generated_plan"]
    assert 5 <= len(generated.get("action_items") or []) <= 15
    assert generated["action_items"][0].get("citations")

    r_plan = client.get(f"/api/weekly_plans_v1/{plan_id}")
    assert r_plan.status_code == 200, r_plan.text
    plan = r_plan.json()
    assert plan["status"] == "draft"
    assert any(item.get("citations") for item in (plan.get("action_items") or []))

    client.get("/logout")
    _login(client, "director", "director")

    r_audit = client.get("/api/audit", params={"action": "weekly_plan.generate", "object_id": plan_id})
    assert r_audit.status_code == 200, r_audit.text
    rows = r_audit.json().get("rows") or []
    assert rows and rows[0]["object_id"] == plan_id

    r_approve = client.post(f"/api/weekly_plans_v1/{plan_id}/approve", json={"comment": "OK"})
    assert r_approve.status_code == 200, r_approve.text
    tasks = r_approve.json().get("tasks") or {}
    assert len(tasks.get("tasks_created") or []) >= 1
