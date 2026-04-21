from __future__ import annotations

from pathlib import Path

import pandas as pd

from streamlit_app.profiles_ux import (
    build_animal_snapshot,
    build_compare_frame,
    build_group_activity_rows,
    build_group_snapshot,
    build_source_event_rows,
    build_sticky_header_html,
)


def test_build_sticky_header_html_contains_sticky_shell_and_pills() -> None:
    html = build_sticky_header_html(title="Animal 1001", subtitle="Summary → detail → timeline", pills={"dv": "dv_demo", "group": "P-01"})
    assert "position:sticky" in html
    assert "Animal 1001" in html
    assert "dv: dv_demo" in html
    assert "group: P-01" in html



def test_build_group_snapshot_summarizes_roster_and_kpi() -> None:
    roster = pd.DataFrame(
        [
            {"animal_id": "A1", "farm_id": "F1"},
            {"animal_id": "A2", "farm_id": "F1"},
            {"animal_id": "A3", "farm_id": "F1"},
        ]
    )
    by_animal = pd.DataFrame(
        [
            {"animal_id": "A1", "value": 10.0, "unit": "kg"},
            {"animal_id": "A2", "value": 12.0, "unit": "kg"},
            {"animal_id": "A3", "value": 8.0, "unit": "kg"},
        ]
    )
    snap = build_group_snapshot(pen_id="P-01", roster=roster, by_animal=by_animal, alerts=[{"alert_id": "a1"}], tasks=[{"task_id": "t1"}], decisions=[])
    assert snap.title == "Группа P-01"
    assert snap.metrics["animals_n"] == "3"
    assert snap.metrics["avg_kpi"] == "10.0 kg"
    assert snap.metrics["top_animal"] == "A2"
    assert snap.linked_counts["alerts"] == 1
    assert snap.linked_counts["tasks"] == 1



def test_build_animal_snapshot_uses_latest_event_if_available() -> None:
    tl = pd.DataFrame([{"category": "health", "event_type": "mastitis"}])
    snap = build_animal_snapshot(animal_id="1001", pen_id="P-01", pen_name="Fresh", alerts=[], tasks=[], decisions=[], timeline_df=tl)
    assert snap.title == "Животное 1001"
    assert snap.metrics["group"] == "P-01 · Fresh"
    assert snap.metrics["latest_event"] == "health:mastitis"



def test_build_compare_frame_adds_peer_average() -> None:
    df = pd.DataFrame(
        [
            {"animal_id": "A1", "value": 100.0},
            {"animal_id": "A2", "value": 120.0},
            {"animal_id": "A3", "value": 80.0},
        ]
    )
    cmp_df = build_compare_frame(by_animal=df, focus_animal_id="A1", compare_animal_id="A2")
    assert cmp_df["animal_id"].tolist() == ["A2", "A1", "peer_avg"]
    assert float(cmp_df[cmp_df["animal_id"] == "peer_avg"]["value"].iloc[0]) == 100.0



def test_build_group_activity_rows_orders_latest_first() -> None:
    df = build_group_activity_rows(
        alerts=[{"alert_id": "a1", "status": "new", "created_at": "2026-03-28T10:00:00Z", "cause": "SCC high"}],
        tasks=[{"task_id": "t1", "status": "open", "created_at": "2026-03-29T09:00:00Z", "title": "Inspect pen"}],
        decisions=[{"decision_id": "d1", "action": "recommendation.confirm", "created_at": "2026-03-27T09:00:00Z", "reason": "ok"}],
    )
    assert df["kind"].tolist() == ["task", "alert", "decision"]



def test_build_source_event_rows_keeps_profile_event_columns() -> None:
    tl = pd.DataFrame(
        [{"date": "2026-03-29", "category": "milk", "event_type": "milking_daily", "details": "milk_kg=32", "source_table": "dm_milkings_daily", "extra": 1}]
    )
    rows = build_source_event_rows(tl)
    assert rows.columns.tolist() == ["date", "category", "event_type", "details", "source_table"]
    assert rows.iloc[0]["source_table"] == "dm_milkings_daily"



def test_profile_pages_reference_new_profiles_helper() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    group_page = (repo_root / "streamlit_app" / "pages" / "14_Group_Profile.py").read_text(encoding="utf-8")
    animal_page = (repo_root / "streamlit_app" / "pages" / "15_Animal_Profile.py").read_text(encoding="utf-8")
    for text in (group_page, animal_page):
        assert "build_sticky_header_html" in text
        assert 'Workspace' in text
    assert "build_source_event_rows" in group_page
    assert "render_timeline" in animal_page
