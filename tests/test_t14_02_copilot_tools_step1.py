from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from genomeai.ai_assistant_rag import answer_question_rag, build_fact_pack_for_assistant
from genomeai.copilot_tools import execute_copilot_tool, route_copilot_tool
from web_cabinet.db import init_db
from web_cabinet.tasks_v1 import TaskCreate, create_task


def _write_demo_artifacts(root: Path) -> None:
    kpi_dir = root / "dv_demo" / "runs" / "kpi_run_001" / "kpi"
    kpi_dir.mkdir(parents=True, exist_ok=True)
    (kpi_dir / "kpi_summary.json").write_text(
        json.dumps({"run_id": "kpi_run_001", "kpi_count": 3, "alert_count": 1}, ensure_ascii=False),
        encoding="utf-8",
    )
    (kpi_dir / "kpi_wide.csv").write_text("farm_id,milk_kg\nfarm_1,123.4\n", encoding="utf-8")
    (kpi_dir / "kpi_alerts.csv").write_text("alert_id,severity\na1,high\n", encoding="utf-8")

    econ_dir = root / "dv_demo" / "economics" / "econ_run_001"
    econ_dir.mkdir(parents=True, exist_ok=True)
    (econ_dir / "summary_farm.csv").write_text(
        "farm_id,revenue_milk,margin_total\nfarm_1,100000,42000\n",
        encoding="utf-8",
    )
    (econ_dir / "whatif_params.json").write_text(
        json.dumps({"economics_run": "econ_run_001", "scenario_name": "base"}, ensure_ascii=False),
        encoding="utf-8",
    )


def _build_web_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    create_task(
        conn,
        tenant_id="default",
        t=TaskCreate(
            task_type="health.check",
            title="Проверить животное 1001",
            priority=1,
            related_alert="alert-001",
            object_type="animal",
            object_id="1001",
            data_version="dv_demo",
        ),
    )
    conn.commit()
    conn.close()


def test_build_fact_pack_includes_tasks_v1_from_web_db(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_demo_artifacts(artifacts)
    db_path = tmp_path / "web.db"
    _build_web_db(db_path)

    fp = build_fact_pack_for_assistant(
        artifacts_root=artifacts,
        data_version="dv_demo",
        asof_date="2026-03-09",
        period="daily",
        web_db_path=db_path,
    )

    tasks_block = ((fp.get("assistant_knowledge") or {}).get("tasks_v1") or {})
    assert tasks_block.get("count") == 1
    assert tasks_block.get("open_count") == 1
    copilot = fp.get("copilot_fact_pack") or {}
    assert any(str(f.get("section") or "").startswith("assistant_knowledge.tasks_v1") for f in (copilot.get("facts") or []))
    assert any(str(t.get("section") or "").startswith("assistant_knowledge.tasks_v1") for t in (copilot.get("tables") or []))


def test_route_copilot_tool_by_keywords() -> None:
    assert route_copilot_tool("сколько стоит молоко по ферме").tool_name == "query_economics"
    assert route_copilot_tool("какие аномалии и алерты по маститу").tool_name == "query_anomalies"
    assert route_copilot_tool("какие открытые задачи у персонала").tool_name == "query_tasks"


def test_execute_copilot_tool_enforces_permissions(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_demo_artifacts(artifacts)
    fp = build_fact_pack_for_assistant(
        artifacts_root=artifacts,
        data_version="dv_demo",
        asof_date="2026-03-09",
        period="daily",
        web_db_path=None,
    )

    denied = execute_copilot_tool(
        question="сколько стоит молоко",
        fact_pack=fp,
        user_permissions=["kpi.view"],
    )
    assert denied.allowed is False
    assert denied.required_permission == "economics.view"
    assert "economics.view" in str(denied.denial_message or "")

    allowed = execute_copilot_tool(
        question="сколько стоит молоко",
        fact_pack=fp,
        user_permissions=["economics.view"],
    )
    assert allowed.allowed is True
    filtered = allowed.filtered_fact_pack.get("copilot_fact_pack") or {}
    assert all(str(f.get("section") or "").startswith("modules.economics") for f in (filtered.get("facts") or []))


def test_answer_question_rag_routes_to_tool_and_respects_rbac(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_demo_artifacts(artifacts)

    denied = answer_question_rag(
        artifacts_root=artifacts,
        data_version="dv_demo",
        asof_date="2026-03-09",
        period="daily",
        question="сколько стоит молоко по ферме",
        use_llm=False,
        user_permissions=["kpi.view"],
    )
    assert "Недостаточно прав" in denied.answer
    assert denied.citations == []

    ok = answer_question_rag(
        artifacts_root=artifacts,
        data_version="dv_demo",
        asof_date="2026-03-09",
        period="daily",
        question="сколько стоит молоко по ферме",
        use_llm=False,
        user_permissions=["economics.view"],
    )
    assert "Ответ сформирован только по подтверждённым данным copilot_fact_pack." in ok.answer
    assert "modules.economics" in ok.answer
    assert "economics_run" in ok.answer or "metric=economics_run" in ok.answer
