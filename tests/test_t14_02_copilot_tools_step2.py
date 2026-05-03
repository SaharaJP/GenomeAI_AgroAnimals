from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from genomeai.ai_assistant_rag import answer_question_rag, build_fact_pack_for_assistant
from genomeai.copilot_tools import build_tool_query_spec, execute_copilot_tool, route_copilot_tool
from web_cabinet.db import init_db
from web_cabinet.tasks_v1 import TaskCreate, create_task


def _write_demo_artifacts(root: Path) -> None:
    kpi_dir = root / "dv_demo" / "runs" / "kpi_run_001" / "kpi"
    kpi_dir.mkdir(parents=True, exist_ok=True)
    (kpi_dir / "kpi_summary.json").write_text(
        json.dumps({"run_id": "kpi_run_001", "kpi_count": 3, "alert_count": 2}, ensure_ascii=False),
        encoding="utf-8",
    )
    (kpi_dir / "kpi_wide.csv").write_text(
        "farm_id,milk_kg\nfarm_1,123.4\nfarm_2,111.1\n",
        encoding="utf-8",
    )
    (kpi_dir / "kpi_alerts.csv").write_text(
        "alert_id,severity,farm_id\nalert_1,high,farm_1\nalert_2,medium,farm_2\n",
        encoding="utf-8",
    )

    econ_dir = root / "dv_demo" / "economics" / "econ_run_001"
    econ_dir.mkdir(parents=True, exist_ok=True)
    (econ_dir / "summary_farm.csv").write_text(
        "farm_id,revenue_milk,margin_total\nfarm_1,100000,42000\nfarm_2,90000,35000\n",
        encoding="utf-8",
    )
    (econ_dir / "whatif_params.json").write_text(
        json.dumps({"economics_run": "econ_run_001", "scenario_name": "base"}, ensure_ascii=False),
        encoding="utf-8",
    )

    mast_dir = root / "dv_demo" / "mastitis" / "scoring" / "mast_run_001"
    mast_dir.mkdir(parents=True, exist_ok=True)
    (mast_dir / "scoring_summary.json").write_text(
        json.dumps({"scoring_run": "mast_run_001", "asof_date": "2026-03-09", "horizon_days": 7, "risk_threshold": 0.7}, ensure_ascii=False),
        encoding="utf-8",
    )
    (mast_dir / "mastitis_risk_scores.csv").write_text(
        "farm_id,animal_id,risk_score,severity\nfarm_1,1001,0.91,high\nfarm_2,2002,0.45,medium\n",
        encoding="utf-8",
    )


def _build_web_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    t1 = create_task(
        conn,
        tenant_id="default",
        t=TaskCreate(
            task_type="health.check",
            title="Проверить животное 1001",
            priority=1,
            related_alert="alert_1",
            object_type="animal",
            object_id="1001",
            data_version="dv_demo",
        ),
    )
    t2 = create_task(
        conn,
        tenant_id="default",
        t=TaskCreate(
            task_type="health.check",
            title="Проверить животное 2002",
            priority=2,
            related_alert="alert_2",
            object_type="animal",
            object_id="2002",
            data_version="dv_demo",
        ),
    )
    t3 = create_task(
        conn,
        tenant_id="default",
        t=TaskCreate(
            task_type="health.check",
            title="Проверить животное 1001 повторно",
            priority=3,
            related_alert="alert_1",
            object_type="animal",
            object_id="1001",
            data_version="dv_demo",
        ),
    )
    conn.execute("UPDATE tasks_v1 SET status='open', assignee_team='vet' WHERE task_id=?", (t1,))
    conn.execute("UPDATE tasks_v1 SET status='done', assignee_team='vet' WHERE task_id=?", (t2,))
    conn.execute("UPDATE tasks_v1 SET status='in_progress', assignee_team='zootech' WHERE task_id=?", (t3,))
    conn.commit()
    conn.close()


def test_build_tool_query_spec_parses_filters() -> None:
    decision = route_copilot_tool("какие 2 открытые задачи по животному 1001 на ферме farm_1")
    assert decision.tool_name == "query_tasks"
    spec = build_tool_query_spec(
        question="какие 2 открытые задачи по животному 1001 на ферме farm_1",
        decision=decision,
    )
    assert spec.top_n == 2
    assert spec.status == "open"
    assert spec.object_id == "1001"
    assert spec.farm_id == "farm_1"


def test_execute_copilot_tool_filters_task_rows(tmp_path: Path) -> None:
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
    result = execute_copilot_tool(
        question="какие 2 открытые задачи по животному 1001",
        fact_pack=fp,
        user_permissions=["tasks.view"],
    )
    assert result.allowed is True
    assert result.query_spec.top_n == 2
    copilot = result.filtered_fact_pack.get("copilot_fact_pack") or {}
    tasks_tables = [t for t in (copilot.get("tables") or []) if str(t.get("section") or "").startswith("assistant_knowledge.tasks_v1")]
    assert tasks_tables, "ожидалась хотя бы одна tasks-таблица"
    rows = tasks_tables[0].get("rows") or []
    assert len(rows) == 1
    assert rows[0]["object_id"] == "1001"
    assert rows[0]["status"] == "open"


def test_execute_copilot_tool_hides_aux_sections_without_permission(tmp_path: Path) -> None:
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

    limited = execute_copilot_tool(
        question="почему мастит по farm_1",
        fact_pack=fp,
        user_permissions=["alerts.view"],
    )
    assert limited.allowed is True
    assert "assistant_knowledge.playbooks" in limited.hidden_section_prefixes
    limited_sections = {str(t.get("section") or "") for t in ((limited.filtered_fact_pack.get("copilot_fact_pack") or {}).get("tables") or [])}
    assert not any(s.startswith("assistant_knowledge.playbooks") for s in limited_sections)

    full = execute_copilot_tool(
        question="почему мастит по farm_1",
        fact_pack=fp,
        user_permissions=["alerts.view", "playbooks.view"],
    )
    full_sections = {str(t.get("section") or "") for t in ((full.filtered_fact_pack.get("copilot_fact_pack") or {}).get("tables") or [])}
    assert any(s.startswith("assistant_knowledge.playbooks") for s in full_sections)


def test_answer_question_rag_includes_tool_trace_and_filtered_preview(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_demo_artifacts(artifacts)

    res = answer_question_rag(
        artifacts_root=artifacts,
        data_version="dv_demo",
        asof_date="2026-03-09",
        period="daily",
        question="сколько стоит по farm_1",
        use_llm=False,
        user_permissions=["economics.view"],
    )
    assert "Tool route: query_economics" in res.answer
    assert "farm_id=farm_1" in res.answer
    assert '"farm_id": "farm_1"' in res.answer
    assert '"farm_id": "farm_2"' not in res.answer
