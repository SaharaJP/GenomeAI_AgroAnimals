from __future__ import annotations

from pathlib import Path

from genomeai.template_reports import run_template_report


def test_template_report_generation_smoke(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    dv = "dv_test"

    template = {
        "template_id": "tpl_1",
        "name": "My Template",
        "scope": "user",
        "sections": ["kpi_summary", "alerts", "tasks", "decisions", "groups", "animals"],
        "metrics": ["milk_total_kg_7d"],
        "options": {"role": "director"},
    }

    # Inputs are factual lists (web extracts them), here we pass tiny samples.
    inputs = {
        "alerts": [{"alert_id": "a1", "title": "Test alert", "status": "open", "severity": "high"}],
        "tasks": [{"task_id": "t1", "title": "Test task", "status": "open", "priority": "high"}],
        "decisions": [{"decision_id": "d1", "title": "Test decision", "status": "approved"}],
    }

    res = run_template_report(
        artifacts_root=artifacts_root,
        data_version=dv,
        asof_date="2025-01-31",
        template=template,
        inputs=inputs,
        mode="fallback",
    )
    assert res.get("ok") is True

    report_dir = Path(res["report_dir"]) / "exports"
    assert (report_dir / "report_director.md").exists()
    assert (report_dir / "report_director.html").exists()
    # reportlab is part of the environment; pdf should normally exist
    assert (report_dir / "report_director.pdf").exists() or res["outputs"].get("director_pdf") == "NA"
