from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from genomeai.copilot_weekly_plan import build_weekly_plan_from_fact_pack
from web_cabinet.db import init_db
from web_cabinet.weekly_plans_v1 import (
    WeeklyPlanCreate,
    approve_weekly_plan,
    create_weekly_plan,
    export_weekly_plan_pdf,
    get_weekly_plan,
    list_pending_approval_weekly_plans,
    request_approval_weekly_plan,
    summarize_weekly_plan,
)


def _sample_fact_pack() -> dict:
    return {
        "schema": "genomeai.assistant_fact_pack.v1",
        "period": "weekly",
        "asof_date": "2026-03-09",
        "versions": {"data_version": "dv_demo", "model_version": "mv_demo"},
        "copilot_fact_pack": {
            "schema": "genomeai.copilot.fact_pack.v1",
            "period": "weekly",
            "asof_date": "2026-03-09",
            "versions": {"data_version": "dv_demo", "model_version": "mv_demo", "report_version": "NA"},
            "sources": {
                "src.tasks": {"ref": "/tmp/web.db", "section": "assistant_knowledge.tasks_v1", "table": "top", "run_id": None, "report_version": None},
                "src.mastitis": {"ref": "/tmp/mastitis_risk_scores.csv", "section": "modules.health.mastitis_risk", "table": "top_risk", "run_id": "mast_run_001", "report_version": None},
                "src.economics": {"ref": "/tmp/summary_farm.csv", "section": "modules.economics", "table": "summary_farm_top", "run_id": "econ_run_001", "report_version": None},
            },
            "facts": [],
            "tables": [
                {
                    "table_id": "table.tasks.top",
                    "section": "assistant_knowledge.tasks_v1",
                    "table": "top",
                    "rows": [
                        {"task_id": "t1", "title": "Проверить животное 1001", "status": "open", "priority": 1, "domain": "health", "assignee_team": "vet", "object_type": "animal", "object_id": "1001"},
                        {"task_id": "t2", "title": "Сверить осеменения", "status": "open", "priority": 2, "domain": "repro", "assignee_team": "zootech", "object_type": "farm", "object_id": "farm_1"},
                    ],
                    "row_count": 2,
                    "run_id": None,
                    "report_version": None,
                    "data_version": "dv_demo",
                    "source_ids": ["src.tasks"],
                },
                {
                    "table_id": "table.mastitis.top",
                    "section": "modules.health.mastitis_risk",
                    "table": "top_risk",
                    "rows": [
                        {"farm_id": "farm_1", "animal_id": "1001", "risk_score": 0.91, "severity": "high"},
                        {"farm_id": "farm_1", "animal_id": "1002", "risk_score": 0.89, "severity": "high"},
                    ],
                    "row_count": 2,
                    "run_id": "mast_run_001",
                    "report_version": None,
                    "data_version": "dv_demo",
                    "source_ids": ["src.mastitis"],
                },
                {
                    "table_id": "table.econ.summary",
                    "section": "modules.economics",
                    "table": "summary_farm_top",
                    "rows": [
                        {"farm_id": "farm_1", "revenue_milk": 100000, "margin_total": 42000},
                    ],
                    "row_count": 1,
                    "run_id": "econ_run_001",
                    "report_version": None,
                    "data_version": "dv_demo",
                    "source_ids": ["src.economics"],
                },
            ],
            "missing_data_requests": [],
        },
    }


def _build_plan() -> dict:
    return build_weekly_plan_from_fact_pack(
        fact_pack=_sample_fact_pack(),
        question="Сформируй план на неделю",
        week_start="2026-03-09",
        farm_id="farm_1",
    )


def test_pending_approval_queue_returns_only_requested_non_rejected_items(tmp_path: Path) -> None:
    db_path = tmp_path / "web.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    plan = _build_plan()
    plan_id = create_weekly_plan(
        conn,
        tenant_id="default",
        user_id=101,
        username="zootech",
        p=WeeklyPlanCreate(
            name=str(plan.get("name") or "AI-план"),
            week_start="2026-03-09",
            summary=str(plan.get("summary") or ""),
            farm_id="farm_1",
            data_version="dv_demo",
            action_items=list(plan.get("action_items") or []),
        ),
    )
    request_approval_weekly_plan(
        conn,
        tenant_id="default",
        plan_id=plan_id,
        requested_by=101,
        requested_by_username="zootech",
        comment="Нужен директор",
    )

    pending = list_pending_approval_weekly_plans(conn, tenant_id="default")
    assert pending["total"] == 1
    summary = summarize_weekly_plan(pending["weekly_plans"][0])
    assert summary["plan_id"] == plan_id
    assert summary["item_count"] >= 5
    assert summary["citation_count"] >= 5
    assert "mast_run_001" in summary["source_run_ids"]
    assert "econ_run_001" in summary["source_run_ids"]

    approve_weekly_plan(
        conn,
        tenant_id="default",
        plan_id=plan_id,
        approved_by=1,
        approved_by_username="director",
        comment="OK",
    )
    pending_after = list_pending_approval_weekly_plans(conn, tenant_id="default")
    assert pending_after["total"] == 0
    conn.close()


def test_weekly_plan_pdf_meta_contains_approval_and_citation_summary(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    db_path = tmp_path / "web.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    plan = _build_plan()
    plan_id = create_weekly_plan(
        conn,
        tenant_id="default",
        user_id=101,
        username="zootech",
        p=WeeklyPlanCreate(
            name=str(plan.get("name") or "AI-план"),
            week_start="2026-03-09",
            summary=str(plan.get("summary") or ""),
            farm_id="farm_1",
            data_version="dv_demo",
            action_items=list(plan.get("action_items") or []),
        ),
    )
    request_approval_weekly_plan(
        conn,
        tenant_id="default",
        plan_id=plan_id,
        requested_by=101,
        requested_by_username="zootech",
        comment="Нужен директор",
    )
    approve_weekly_plan(
        conn,
        tenant_id="default",
        plan_id=plan_id,
        approved_by=1,
        approved_by_username="director",
        comment="OK",
    )
    rep = export_weekly_plan_pdf(
        conn,
        artifacts_root=artifacts_root,
        tenant_id="default",
        plan_id=plan_id,
        exported_by=1,
        exported_by_username="director",
    )
    assert rep["ok"] is True

    stored = get_weekly_plan(conn, tenant_id="default", plan_id=plan_id)
    assert stored is not None
    meta_path = Path(rep["meta_path"])
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["plan_id"] == plan_id
    assert meta["approval_requested_by_username"] == "zootech"
    assert meta["approved_by_username"] == "director"
    assert meta["citation_count"] >= 5
    assert meta["item_count"] >= 5
    assert "mast_run_001" in meta["source_run_ids"]
    assert "econ_run_001" in meta["source_run_ids"]
    conn.close()
