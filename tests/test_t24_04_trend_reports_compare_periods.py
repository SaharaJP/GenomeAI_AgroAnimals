from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path

import openpyxl
import pandas as pd

from core.trend_reports import (
    build_trend_drilldown,
    build_trend_report_snapshot,
    build_trend_chart_frame,
    export_trend_report,
)
from streamlit_app.trend_reports_compare_periods import build_trend_bucket_table, build_trend_chart_display_table


def _seed_input_dir(tmp_path: Path) -> Path:
    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"tenant_id": "default", "animal_id": "A1", "farm_id": "F1", "site_id": "S1", "current_pen_id": "P1", "current_pen_name": "Fresh", "breed": "Holstein", "status": "active"},
        {"tenant_id": "default", "animal_id": "A2", "farm_id": "F1", "site_id": "S2", "current_pen_id": "P2", "current_pen_name": "Hospital", "breed": "Holstein", "status": "active"},
        {"tenant_id": "default", "animal_id": "A3", "farm_id": "F1", "site_id": "S1", "current_pen_id": "P1", "current_pen_name": "Fresh", "breed": "Jersey", "status": "active"},
    ]).to_csv(input_dir / "dm_animals.csv", index=False)
    pd.DataFrame([
        {"tenant_id": "default", "pen_id": "P1", "site_id": "S1", "pen_name": "Fresh", "pen_type": "fresh", "capacity_head": 50},
        {"tenant_id": "default", "pen_id": "P2", "site_id": "S2", "pen_name": "Hospital", "pen_type": "hospital", "capacity_head": 20},
    ]).to_csv(input_dir / "dm_pens.csv", index=False)
    pd.DataFrame([
        {"tenant_id": "default", "move_id": "M1", "animal_id": "A1", "from_pen_id": "", "to_pen_id": "P1", "move_date": "2026-03-01", "reason": "fresh"},
        {"tenant_id": "default", "move_id": "M2", "animal_id": "A2", "from_pen_id": "", "to_pen_id": "P2", "move_date": "2026-03-01", "reason": "hospital"},
        {"tenant_id": "default", "move_id": "M3", "animal_id": "A3", "from_pen_id": "", "to_pen_id": "P1", "move_date": "2026-03-01", "reason": "fresh"},
    ]).to_csv(input_dir / "dm_pen_moves.csv", index=False)
    pd.DataFrame([
        {"tenant_id": "default", "animal_id": "A1", "date": "2026-03-30", "milk_kg": 38.0, "dim": 25, "scc_cells_ml": 120000},
        {"tenant_id": "default", "animal_id": "A2", "date": "2026-03-30", "milk_kg": 24.0, "dim": 28, "scc_cells_ml": 310000},
        {"tenant_id": "default", "animal_id": "A3", "date": "2026-03-30", "milk_kg": 34.0, "dim": 65, "scc_cells_ml": 160000},
        {"tenant_id": "default", "animal_id": "A1", "date": "2026-03-31", "milk_kg": 37.0, "dim": 26, "scc_cells_ml": 115000},
        {"tenant_id": "default", "animal_id": "A2", "date": "2026-03-31", "milk_kg": 23.0, "dim": 29, "scc_cells_ml": 320000},
        {"tenant_id": "default", "animal_id": "A3", "date": "2026-03-31", "milk_kg": 33.0, "dim": 66, "scc_cells_ml": 150000},
        {"tenant_id": "default", "animal_id": "A1", "date": "2026-03-28", "milk_kg": 39.0, "dim": 23, "scc_cells_ml": 110000},
        {"tenant_id": "default", "animal_id": "A2", "date": "2026-03-28", "milk_kg": 25.0, "dim": 26, "scc_cells_ml": 305000},
        {"tenant_id": "default", "animal_id": "A3", "date": "2026-03-28", "milk_kg": 35.0, "dim": 63, "scc_cells_ml": 140000},
        {"tenant_id": "default", "animal_id": "A1", "date": "2026-03-23", "milk_kg": 36.0, "dim": 18, "scc_cells_ml": 100000},
        {"tenant_id": "default", "animal_id": "A2", "date": "2026-03-23", "milk_kg": 22.0, "dim": 21, "scc_cells_ml": 280000},
        {"tenant_id": "default", "animal_id": "A3", "date": "2026-03-23", "milk_kg": 32.0, "dim": 58, "scc_cells_ml": 130000},
    ]).to_csv(input_dir / "dm_milkings_daily.csv", index=False)
    pd.DataFrame([
        {"tenant_id": "default", "event_id": "HE1", "animal_id": "A2", "event_date": "2026-03-31", "event_type": "mastitis", "severity": "high", "notes": "watch"},
        {"tenant_id": "default", "event_id": "HE2", "animal_id": "A1", "event_date": "2026-03-30", "event_type": "metritis", "severity": "medium", "notes": "followup"},
        {"tenant_id": "default", "event_id": "HE3", "animal_id": "A2", "event_date": "2026-03-24", "event_type": "mastitis", "severity": "high", "notes": "repeat"},
    ]).to_csv(input_dir / "dm_health_events.csv", index=False)
    pd.DataFrame([
        {"tenant_id": "default", "repro_event_id": "RE1", "animal_id": "A1", "event_date": "2026-03-31", "event_type": "insemination", "result": "recorded"},
        {"tenant_id": "default", "repro_event_id": "RE2", "animal_id": "A3", "event_date": "2026-03-26", "event_type": "preg_check", "result": "pregnant"},
    ]).to_csv(input_dir / "dm_repro_events.csv", index=False)
    return input_dir


def test_t24_04_milk_trend_period_compare_and_export(tmp_path: Path) -> None:
    input_dir = _seed_input_dir(tmp_path)
    snapshot = build_trend_report_snapshot(
        input_dir=input_dir,
        asof_date=date(2026, 3, 31),
        role="Director",
        report_type="milk_output_trend",
        filters={"farm_id": "F1"},
        period_days=7,
        grain="day",
        compare_mode="period",
    )
    chart_table = build_trend_chart_display_table(snapshot)
    frame = build_trend_chart_frame(snapshot)
    assert snapshot["compare_mode"] == "period"
    assert snapshot["compare_period"]["start"] == "2026-03-18"
    assert not chart_table.empty and not frame.empty
    assert "current" in frame.columns and "previous_period" in frame.columns
    assert any(str(row.get("metric")) == "delta_total" for row in snapshot["summary_rows"])

    xlsx = export_trend_report(snapshot, fmt="xlsx")
    wb = openpyxl.load_workbook(BytesIO(xlsx))
    assert set(wb.sheetnames) >= {"trend", "summary", "formulas"}


def test_t24_04_dim_curve_supports_group_compare_and_drilldown(tmp_path: Path) -> None:
    input_dir = _seed_input_dir(tmp_path)
    snapshot = build_trend_report_snapshot(
        input_dir=input_dir,
        asof_date=date(2026, 3, 31),
        role="Zootech",
        report_type="dim_milk_curve",
        filters={"farm_id": "F1", "pen_id": "P1"},
        period_days=14,
        compare_mode="group",
        compare_pen_id="P2",
        dim_bucket_size=20,
    )
    bucket_table = build_trend_bucket_table(snapshot)
    assert snapshot["compare_mode"] == "group"
    assert not bucket_table.empty
    assert str(snapshot["primary_label"]).startswith("group:")
    assert str(snapshot["compare_label"]).startswith("group:")

    bucket_id = str(bucket_table.iloc[0]["bucket_id"])
    drilldown = build_trend_drilldown(
        input_dir=input_dir,
        asof_date=date(2026, 3, 31),
        snapshot=snapshot,
        bucket_id=bucket_id,
        limit=50,
    )
    drill_df = pd.DataFrame(drilldown["rows"])
    assert drilldown["object_type"] == "animals"
    assert not drill_df.empty
    assert "series_label" in drill_df.columns and "animal_id" in drill_df.columns


def test_t24_04_health_trend_bucket_drills_to_events(tmp_path: Path) -> None:
    input_dir = _seed_input_dir(tmp_path)
    snapshot = build_trend_report_snapshot(
        input_dir=input_dir,
        asof_date=date(2026, 3, 31),
        role="Vet",
        report_type="health_events_trend",
        filters={"farm_id": "F1", "event_type": "mastitis"},
        period_days=14,
        compare_mode="none",
    )
    bucket_table = build_trend_bucket_table(snapshot)
    bucket_id = str(bucket_table.iloc[-1]["bucket_id"])
    drilldown = build_trend_drilldown(
        input_dir=input_dir,
        asof_date=date(2026, 3, 31),
        snapshot=snapshot,
        bucket_id=bucket_id,
        limit=50,
    )
    drill_df = pd.DataFrame(drilldown["rows"])
    assert drilldown["object_type"] == "events"
    assert not drill_df.empty
    assert set(["event_date", "event_type", "animal_id"]).issubset(drill_df.columns)


def test_t24_04_contracts_docs_and_page_present() -> None:
    core = Path("src/core/trend_reports.py").read_text(encoding="utf-8")
    helper = Path("streamlit_app/trend_reports_compare_periods.py").read_text(encoding="utf-8")
    page = Path("streamlit_app/pages/57_Trend_Reports_Compare_Periods.py").read_text(encoding="utf-8")
    config = Path("configs/ui/ia_v3.yaml").read_text(encoding="utf-8")
    docs = Path("docs/trend_reports_compare_periods.md").read_text(encoding="utf-8")
    assumptions = Path("docs/assumptions.md").read_text(encoding="utf-8")

    assert "TREND_REPORT_TYPES" in core and "build_trend_report_snapshot" in core
    assert "load_trend_report_snapshot" in helper and "TREND_COMPARE_MODES" in helper
    assert "Trend reports / compare periods" in page
    assert "Open universal list builder" in page and "Open operational report builder" in page
    assert "pages/57_Trend_Reports_Compare_Periods.py" in config
    assert "DIM" in docs and "drilldown" in docs.lower() and "reproducible" in docs.lower()
    assert "## T24-04 — trend reports / compare periods" in assumptions
