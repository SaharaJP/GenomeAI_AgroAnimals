from __future__ import annotations

import json
from pathlib import Path

from genomeai.template_reports import run_template_report


def test_template_report_focus_filters_web_inputs(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    dv = "dv_test"

    template = {
        "template_id": "tpl_1",
        "name": "My Template",
        "scope": "user",
        "sections": ["alerts", "tasks", "decisions"],
        "metrics": ["milk_total_kg_7d"],
        "options": {},
    }

    inputs = {
        "alerts": [
            {"alert_id": "a1", "title": "A1", "object_type": "pen", "object_id": "P1"},
            {"alert_id": "a2", "title": "A2", "object_type": "animal", "object_id": "C9"},
        ],
        "tasks": [
            {"task_id": "t1", "title": "T1", "object_type": "group", "object_id": "P1"},
            {"task_id": "t2", "title": "T2", "object_type": "animal", "object_id": "C9"},
        ],
        "decisions": [
            {"decision_id": "d1", "title": "D1", "object_type": "pen", "object_id": "P1"},
            {"decision_id": "d2", "title": "D2", "object_type": "animal", "object_id": "C9"},
        ],
    }

    # Focus on a group/pen P1 (aliases group+pen should match)
    res = run_template_report(
        artifacts_root=artifacts_root,
        data_version=dv,
        asof_date="2025-01-31",
        template=template,
        inputs=inputs,
        mode="fallback",
        options_override={"focus_type": "group", "focus_id": "P1"},
    )
    assert res.get("ok") is True

    fp = Path(res["report_dir"]) / "fact_pack.json"
    fact = json.loads(fp.read_text(encoding="utf-8"))
    assert fact.get("focus", {}).get("focus_type") == "group"
    assert fact.get("focus", {}).get("focus_id") == "P1"
    assert len(fact.get("web", {}).get("alerts_top") or []) == 1
    assert len(fact.get("web", {}).get("tasks_top") or []) == 1
    assert len(fact.get("web", {}).get("decisions_top") or []) == 1


def test_template_report_focus_alert_filters_related_records(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    dv = "dv_test"

    template = {
        "template_id": "tpl_1",
        "name": "My Template",
        "scope": "user",
        "sections": ["alerts", "tasks", "decisions"],
        "metrics": ["milk_total_kg_7d"],
        "options": {},
    }

    inputs = {
        "alerts": [
            {"alert_id": "a1", "title": "A1", "object_type": "pen", "object_id": "P1"},
            {"alert_id": "a2", "title": "A2", "object_type": "pen", "object_id": "P2"},
        ],
        "tasks": [
            {"task_id": "t1", "title": "T1", "related_alert": "a1"},
            {"task_id": "t2", "title": "T2", "related_alert": "a2"},
        ],
        "decisions": [
            {"decision_id": "d1", "title": "D1", "related_alert": "a1"},
            {"decision_id": "d2", "title": "D2", "related_alert": "a2"},
        ],
    }

    res = run_template_report(
        artifacts_root=artifacts_root,
        data_version=dv,
        asof_date="2025-01-31",
        template=template,
        inputs=inputs,
        mode="fallback",
        options_override={"focus_type": "alert", "focus_id": "a1"},
    )
    assert res.get("ok") is True

    fp = Path(res["report_dir"]) / "fact_pack.json"
    fact = json.loads(fp.read_text(encoding="utf-8"))
    assert len(fact.get("web", {}).get("alerts_top") or []) == 1
    assert len(fact.get("web", {}).get("tasks_top") or []) == 1
    assert len(fact.get("web", {}).get("decisions_top") or []) == 1