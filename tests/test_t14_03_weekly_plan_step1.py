from __future__ import annotations

from pathlib import Path

import genomeai.ai_assistant_rag as ragmod
from genomeai.copilot_weekly_plan import (
    build_weekly_plan_from_fact_pack,
    is_weekly_plan_request,
    render_weekly_plan_answer,
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
                "src.kpi": {"ref": "/tmp/kpi_summary.json", "section": "modules.kpi", "table": "kpi_summary", "run_id": "kpi_run_001", "report_version": None},
            },
            "facts": [
                {
                    "fact_id": "fact.modules_kpi.alert_count",
                    "section": "modules.kpi",
                    "metric_name": "alert_count",
                    "value": 4,
                    "run_id": "kpi_run_001",
                    "report_version": None,
                    "data_version": "dv_demo",
                    "source_ids": ["src.kpi"],
                },
                {
                    "fact_id": "fact.tasks.overdue_count",
                    "section": "assistant_knowledge.tasks_v1",
                    "metric_name": "overdue_count",
                    "value": 2,
                    "run_id": None,
                    "report_version": None,
                    "data_version": "dv_demo",
                    "source_ids": ["src.tasks"],
                },
            ],
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


def test_weekly_plan_builder_creates_cited_items() -> None:
    assert is_weekly_plan_request("Сформируй план на неделю") is True
    plan = build_weekly_plan_from_fact_pack(
        fact_pack=_sample_fact_pack(),
        question="Сформируй план на неделю",
        week_start="2026-03-09",
        farm_id="farm_1",
    )
    items = list(plan.get("action_items") or [])
    assert 5 <= len(items) <= 15
    assert all(item.get("citations") for item in items)
    assert all(item.get("expected_effect") for item in items)
    text = render_weekly_plan_answer(plan)
    assert "Сформирован weekly plan" in text
    assert "[Источник:" in text


def test_answer_question_rag_returns_weekly_plan_for_matching_question(monkeypatch, tmp_path: Path) -> None:
    sample = _sample_fact_pack()

    def _fake_build_fact_pack_for_assistant(**_: object) -> dict:
        return sample

    monkeypatch.setattr(ragmod, "build_fact_pack_for_assistant", _fake_build_fact_pack_for_assistant)
    resp = ragmod.answer_question_rag(
        artifacts_root=tmp_path,
        data_version="dv_demo",
        asof_date="2026-03-09",
        period="weekly",
        question="Сформируй план на неделю",
        use_llm=False,
    )
    assert "weekly plan" in resp.answer.lower()
    assert "Источники/версии:" in resp.answer
    assert len(resp.citations) >= 3
