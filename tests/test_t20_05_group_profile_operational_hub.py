from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from streamlit_app.group_profile_operational_hub import (
    build_group_operational_context,
    build_group_recent_events_preview_rows,
)


def _fixture_roster() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"animal_id": "A1001", "farm_id": "FARM_001", "site_id": "SITE_001", "pen_id": "PEN_01", "pen_name": "Fresh"},
            {"animal_id": "A1002", "farm_id": "FARM_001", "site_id": "SITE_001", "pen_id": "PEN_01", "pen_name": "Fresh"},
        ]
    )


def _fixture_by_animal() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"animal_id": "A1001", "value": 32.4, "unit": "kg"},
            {"animal_id": "A1002", "value": 27.1, "unit": "kg"},
        ]
    )


def test_t20_05_group_operational_context_builds_required_blocks() -> None:
    ctx = build_group_operational_context(
        input_dir=Path("data/fixtures/target_v2"),
        pen_id="PEN_01",
        asof_date=date(2025, 3, 31),
        roster=_fixture_roster(),
        by_animal=_fixture_by_animal(),
        alerts=[{"alert_id": "a1", "status": "new"}],
        tasks=[{"task_id": "t1", "status": "open"}],
        decisions=[{"decision_id": "d1", "action": "confirm"}],
    )

    assert set(ctx.keys()) == {
        "group_status",
        "group_kpis",
        "roster_status_rows",
        "worklists",
        "recent_events_preview",
        "linked_summary",
    }
    assert ctx["group_status"]["label"] == "Нужен triage"
    assert int(ctx["group_kpis"]["animals_n"]) == 2
    assert int(ctx["group_kpis"]["health_attention_n"]) >= 1
    roster_df = ctx["roster_status_rows"]
    assert set(["animal_id", "current_status_label", "repro_state", "health_state", "next_action"]).issubset(roster_df.columns)
    a1001 = roster_df[roster_df["animal_id"].astype(str) == "A1001"].iloc[0].to_dict()
    assert a1001["current_status_label"] == "Нужно действие"
    assert a1001["health_state"] in {"recent_health_event", "under_treatment", "scc_high"}
    assert ctx["linked_summary"]["tasks_total"] == 1


def test_t20_05_recent_events_preview_rows_have_group_columns() -> None:
    repro = pd.DataFrame([
        {"animal_id": "A1001", "event_date": "2025-03-28", "event_type": "heat", "result": "observed", "notes": "manual"},
    ])
    health = pd.DataFrame([
        {"animal_id": "A1002", "event_date": "2025-03-27", "event_type": "mastitis", "severity": "medium", "notes": "check"},
    ])
    treatments = pd.DataFrame([
        {"animal_id": "A1001", "start_date": "2025-03-29", "treatment_type": "antibiotic", "withdrawal_end_date": "2025-04-05"},
    ])
    moves = pd.DataFrame([
        {"animal_id": "A1002", "move_date": "2025-03-30", "to_pen_id": "PEN_02", "reason": "sort"},
    ])
    out = build_group_recent_events_preview_rows(
        roster_status_rows=pd.DataFrame(),
        repro_df=repro,
        health_df=health,
        treatments_df=treatments,
        pen_moves_df=moves,
        max_rows=10,
    )
    assert out.columns.tolist() == ["ts", "animal_id", "lane", "kind", "summary", "source"]
    assert set(out["lane"].astype(str)) >= {"reproduction", "health", "treatment", "pen_move"}


def test_t20_05_docs_and_page_reference_operational_hub_blocks() -> None:
    page = Path("streamlit_app/pages/14_Group_Profile.py").read_text(encoding="utf-8")
    helper = Path("streamlit_app/group_profile_operational_hub.py").read_text(encoding="utf-8")
    doc = Path("docs/group_profile_operational_hub.md").read_text(encoding="utf-8")
    assumptions = Path("docs/assumptions.md").read_text(encoding="utf-8")

    assert "Group KPIs / KPI группы" in page
    assert "Group worklists / Рабочие списки группы" in page
    assert "Recent events / Последние события" in page
    assert "Batch actions / Пакетные действия" in page
    assert "Roster / Состав группы" in page
    assert "Deep-link navigation" in page
    assert "build_group_operational_context" in page
    assert "build_group_recent_events_preview_rows" in helper
    assert "daily-use" in doc.lower() or "ежеднев" in doc.lower()
    assert "session_state" in assumptions.lower()
    assert "group state-machine" in assumptions.lower()
