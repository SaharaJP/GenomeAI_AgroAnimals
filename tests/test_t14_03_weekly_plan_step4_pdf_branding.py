from __future__ import annotations

import json
from pathlib import Path

from pypdf import PdfReader

from genomeai.copilot_weekly_plan import build_weekly_plan_from_fact_pack
from genomeai.weekly_plan_pdf import generate_weekly_plan_pdf


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
                "src.repro": {"ref": "/tmp/repro_alerts.csv", "section": "modules.repro", "table": "heat_alerts", "run_id": "repro_run_010", "report_version": None},
            },
            "facts": [
                {
                    "fact_id": "fact.modules_kpi.alert_count",
                    "section": "modules.kpi",
                    "metric_name": "alert_count",
                    "value": 6,
                    "run_id": "kpi_run_001",
                    "report_version": None,
                    "data_version": "dv_demo",
                    "source_ids": ["src.mastitis"],
                }
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
                    "table_id": "table.repro.alerts",
                    "section": "modules.repro",
                    "table": "heat_alerts",
                    "rows": [
                        {"farm_id": "farm_1", "animal_id": "2001", "severity": "medium", "days_in_milk": 95},
                        {"farm_id": "farm_1", "animal_id": "2002", "severity": "medium", "days_in_milk": 102},
                    ],
                    "row_count": 2,
                    "run_id": "repro_run_010",
                    "report_version": None,
                    "data_version": "dv_demo",
                    "source_ids": ["src.repro"],
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


def test_weekly_plan_pdf_is_branded_and_contains_charts(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    plan = build_weekly_plan_from_fact_pack(
        fact_pack=_sample_fact_pack(),
        question="Сформируй план на неделю",
        week_start="2026-03-09",
        farm_id="farm_1",
    )
    plan["plan_id"] = "plan_demo_004"
    plan["status"] = "approved"
    plan["created_by_username"] = "zootech"
    plan["approval_requested_by_username"] = "zootech"
    plan["approved_by_username"] = "director"

    rep = generate_weekly_plan_pdf(artifacts_root=artifacts_root, plan=plan)
    pdf_path = Path(rep["pdf_path"])
    meta = json.loads(Path(rep["meta_path"]).read_text(encoding="utf-8"))

    assert pdf_path.exists()
    assert meta["branding_theme"] == "genomeai_weekly_plan_v1"
    assert meta["brand_name"] == "GenomeAI AgroAnimals"
    assert meta["chart_count"] >= 2
    assert meta["page_count"] >= 2
    assert any("приоритет" in title.lower() for title in meta["chart_titles"])
    assert any("домен" in title.lower() for title in meta["chart_titles"])

    reader = PdfReader(str(pdf_path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "GenomeAI AgroAnimals" in text
    assert "Графики недели" in text
    assert "План действий по пунктам" in text
