from __future__ import annotations

from datetime import date
from pathlib import Path

from genomeai.drilldown import (
    build_animal_timeline,
    compute_pen_assignments,
    kpi_breakdown_by_animal,
    kpi_breakdown_by_pen,
)


def test_pen_assignments_smoke() -> None:
    input_dir = Path("data/fixtures/target_v2")
    df = compute_pen_assignments(input_dir=input_dir, asof_date=date(2025, 1, 10))
    assert not df.empty
    for c in ["tenant_id", "animal_id", "pen_id", "pen_name"]:
        assert c in df.columns


def test_kpi_breakdown_pen_smoke() -> None:
    # Use fixtures as canonical input (no artifacts required)
    art = Path("artifacts")
    dv = "dv_demo"
    df = kpi_breakdown_by_pen(
        artifacts_dir=art,
        data_version=dv,
        kpi_id="milk_total_kg_7d",
        asof_date=date(2025, 1, 10),
        input_dir=Path("data/fixtures/target_v2"),
    )
    assert not df.empty
    assert "pen_id" in df.columns
    assert "value" in df.columns


def test_kpi_breakdown_animal_smoke() -> None:
    art = Path("artifacts")
    dv = "dv_demo"
    df = kpi_breakdown_by_animal(
        artifacts_dir=art,
        data_version=dv,
        kpi_id="milk_total_kg_7d",
        asof_date=date(2025, 1, 10),
        input_dir=Path("data/fixtures/target_v2"),
        pen_id="PEN_01",
    )
    assert not df.empty
    assert {"animal_id", "value"}.issubset(set(df.columns))


def test_animal_timeline_smoke() -> None:
    art = Path("artifacts")
    dv = "dv_demo"
    df = build_animal_timeline(
        artifacts_dir=art,
        data_version=dv,
        animal_id="A1001",
        asof_date=date(2025, 1, 10),
        days_back=30,
        input_dir=Path("data/fixtures/target_v2"),
    )
    # timeline can be empty for some animals/dates, but columns must be stable
    assert {"date", "category", "event_type", "source_table"}.issubset(set(df.columns))
