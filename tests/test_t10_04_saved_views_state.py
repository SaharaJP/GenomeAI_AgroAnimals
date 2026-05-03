from __future__ import annotations

from datetime import date

from streamlit_app.saved_views_state import apply_saved_view_state, extract_saved_view_state


def test_extract_normalizes_dates_and_lists() -> None:
    sess = {
        "kpi_drilldown.data_version": "dv_demo",
        "kpi_drilldown.kpi_id": "milk_total_kg_7d",
        "kpi_drilldown.asof_date": date(2025, 1, 31),
        "kpi_drilldown.pen_id": "PEN_001",
        "director_summary.tile_ids": ["milk_total_kg_7d", 123],
        "director_summary.asof_date": date(2025, 2, 1),
    }

    k = extract_saved_view_state(page_key="kpi_drilldown", session_state=sess)
    assert k["kpi_drilldown.asof_date"] == "2025-01-31"
    assert k["kpi_drilldown.pen_id"] == "PEN_001"

    d = extract_saved_view_state(page_key="director_summary", session_state=sess)
    assert d["director_summary.asof_date"] == "2025-02-01"
    assert d["director_summary.tile_ids"] == ["milk_total_kg_7d", "123"]


def test_apply_converts_date_strings() -> None:
    sess: dict[str, object] = {}
    state = {
        "kpi_drilldown.asof_date": "2025-01-31",
        "kpi_drilldown.kpi_id": "milk_total_kg_7d",
        "kpi_drilldown.pen_id": "PEN_002",
        "director_summary.asof_date": "2025-02-01",
        "director_summary.tile_ids": ["SCC_mean_7d", 7],
    }

    applied = apply_saved_view_state(page_key="kpi_drilldown", state=state, session_state=sess)
    assert "kpi_drilldown.asof_date" in applied
    assert sess["kpi_drilldown.asof_date"] == date(2025, 1, 31)

    applied2 = apply_saved_view_state(page_key="director_summary", state=state, session_state=sess)
    assert sess["director_summary.asof_date"] == date(2025, 2, 1)
    assert sess["director_summary.tile_ids"] == ["SCC_mean_7d", "7"]
    assert "director_summary.tile_ids" in applied2


def test_unknown_page_key_is_noop() -> None:
    sess: dict[str, object] = {"x": 1}
    assert extract_saved_view_state(page_key="unknown", session_state=sess) == {}
    assert apply_saved_view_state(page_key="unknown", state={"x": 2}, session_state=sess) == []
    assert sess["x"] == 1
