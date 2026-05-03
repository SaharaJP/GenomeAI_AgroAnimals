from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from streamlit_app.animal_profile_daily_use import build_animal_daily_use_context, build_animal_timeline_preview_rows


def test_t20_04_daily_use_context_builds_required_blocks_from_fixture() -> None:
    ctx = build_animal_daily_use_context(
        input_dir=Path("data/fixtures/target_v2"),
        animal_id="A1001",
        asof_date=date(2025, 3, 31),
        pen_id="PEN_01",
        pen_name="Fresh",
        quick_history=[
            {
                "event_id": "aevt_1",
                "event_ts": "2025-03-31T08:15:00+00:00",
                "event_type": "heat",
                "display_type": "heat",
                "reason_code": "HEAT_OBSERVED",
                "source": "manual_ui",
            }
        ],
        tasks=[{"task_id": "t1", "status": "open", "title": "Inspect animal", "due_date": "2025-03-30"}],
        decisions=[{"decision_id": "d1", "action": "recommendation.confirm"}],
        alerts=[{"alert_id": "a1", "alert_type": "ML.MASTITIS_RISK", "cause": "SCC high"}],
        prod_card={"available": True, "prediction": 9800},
        mastitis_card={"available": True, "risk_proba": 0.81, "top_factors_text": "SCC rising"},
    )

    assert set(ctx.keys()) == {
        "current_status",
        "reproduction_state",
        "health_state",
        "milk_quality_snapshot",
        "linked_summary",
    }
    assert ctx["current_status"]["pen"] == "PEN_01 · Fresh"
    assert ctx["reproduction_state"]["latest_event_type"] == "insemination"
    assert ctx["health_state"]["status"]["label"] == "Высокий mastitis risk"
    assert ctx["milk_quality_snapshot"]["latest_milk_kg"] == "30.0"
    assert ctx["milk_quality_snapshot"]["prediction_305d"] == "9800"
    assert ctx["linked_summary"]["tasks_open"] == 1
    assert ctx["linked_summary"]["tasks_overdue"] == 1


def test_t20_04_timeline_preview_merges_operational_and_source_rows() -> None:
    quick_history = [
        {"event_ts": "2025-03-31T08:15:00+00:00", "display_type": "heat", "reason_code": "HEAT_OBSERVED", "source": "manual_ui"},
        {"event_ts": "2025-03-30T09:00:00+00:00", "display_type": "comment", "comment": "checked", "source": "manual_ui"},
    ]
    source = pd.DataFrame(
        [
            {"date": "2025-03-29", "category": "health", "event_type": "mastitis", "details": "severity=medium", "source_table": "dm_health_events"},
            {"date": "2025-03-28", "category": "milk", "event_type": "milking_daily", "details": "milk_kg=30", "source_table": "dm_milkings_daily"},
        ]
    )
    out = build_animal_timeline_preview_rows(quick_history=quick_history, source_timeline_df=source, max_rows=10)
    assert out.columns.tolist() == ["ts", "lane", "kind", "summary", "source"]
    assert out.iloc[0]["kind"] == "heat"
    assert set(out["lane"].astype(str)) >= {"operational", "health", "milk"}


def test_t20_04_docs_and_page_reference_daily_use_blocks() -> None:
    page = Path("streamlit_app/pages/15_Animal_Profile.py").read_text(encoding="utf-8")
    helper = Path("streamlit_app/animal_profile_daily_use.py").read_text(encoding="utf-8")
    doc = Path("docs/animal_profile_daily_use.md").read_text(encoding="utf-8")
    assumptions = Path("docs/assumptions.md").read_text(encoding="utf-8")

    assert "Current status / Текущий статус" in page
    assert "Reproduction state" in page
    assert "Health state" in page
    assert "Milk / quality snapshot" in page
    assert "Timeline preview / Последние события" in page
    assert "Quick actions / Быстрые действия" in page
    assert "build_animal_daily_use_context" in page
    assert "build_animal_timeline_preview_rows" in page
    assert "worklists" in doc.lower()
    assert "full source timeline" in assumptions.lower()
    assert "tasks_overdue" in helper
