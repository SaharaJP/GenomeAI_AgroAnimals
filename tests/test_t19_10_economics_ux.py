from __future__ import annotations

import pandas as pd

from streamlit_app.economics_ux import (
    build_director_metrics,
    build_driver_rows,
    build_loss_rows,
    build_scenario_table_for_display,
    build_transparency_items,
    latest_scope_rows,
)


def test_latest_scope_rows_filters_and_latest_date() -> None:
    df = pd.DataFrame(
        [
            {"date": "2026-01-01", "farm_id": "F1", "level": "farm", "margin_rub": 100.0},
            {"date": "2026-01-02", "farm_id": "F1", "level": "farm", "margin_rub": 150.0},
            {"date": "2026-01-02", "farm_id": "F2", "level": "farm", "margin_rub": 999.0},
        ]
    )
    latest, dt = latest_scope_rows(df, filters={"farm_id": "F1", "level": "farm"})
    assert dt is not None
    assert str(dt.date()) == "2026-01-02"
    assert latest.shape[0] == 1
    assert float(latest.iloc[0]["margin_rub"]) == 150.0



def test_build_driver_and_loss_rows_are_director_readable() -> None:
    df = pd.DataFrame(
        [
            {
                "revenue_milk_rub": 10000.0,
                "cost_feed_rub": 4000.0,
                "cost_other_rub": 500.0,
                "cost_vet_rub": 700.0,
                "cost_repro_rub": 300.0,
                "cost_cull_rub": 100.0,
            }
        ]
    )
    drivers = build_driver_rows(df, limit=3)
    assert drivers
    assert drivers[0]["label"] == "Выручка молока"

    losses = build_loss_rows(df)
    assert [row["component"] for row in losses] == ["cost_vet_rub", "cost_other_rub", "cost_repro_rub", "cost_cull_rub"]



def test_build_director_metrics_combines_economics_and_roi() -> None:
    econ = pd.DataFrame(
        [
            {
                "date": "2026-02-01",
                "margin_rub": 5000.0,
                "cost_other_rub": 250.0,
                "cost_vet_rub": 400.0,
                "cost_repro_rub": 100.0,
                "cost_cull_rub": 50.0,
            }
        ]
    )
    roi = pd.DataFrame(
        [
            {
                "roi_weighted_used": 0.35,
                "cost_sum": 1000.0,
                "delta_margin_window_used_sum": 2500.0,
            }
        ]
    )
    metrics = build_director_metrics(economics_frame=econ, roi_summary=roi)
    by_label = {m.label: m for m in metrics}
    assert by_label["Маржа"].value == 5000.0
    assert by_label["Потери"].value == 800.0
    assert by_label["ROI"].value == 0.35
    assert round(float(by_label["Payback"].value or 0.0), 2) == 0.40



def test_scenario_table_display_computes_payback() -> None:
    df = build_scenario_table_for_display(
        [
            {"scenario": "BASE", "economics_run": "econ_base", "margin": 1000.0, "margin_delta": 0.0, "total_cost_delta": 0.0},
            {"scenario": "Higher milk price", "economics_run": "econ_s1", "margin": 1300.0, "margin_delta": 300.0, "total_cost_delta": 150.0, "margin_pct_delta": 0.12},
        ]
    )
    assert not df.empty
    row = df[df["scenario"] == "Higher milk price"].iloc[0]
    assert float(row["payback_ratio"]) == 0.5
    assert row["margin_delta_label"].endswith("₽")



def test_transparency_items_keep_versions_visible() -> None:
    rows = build_transparency_items(
        manifest={
            "data_version": "dv_demo",
            "economics_run": "econ_001",
            "versions": {"price_book_version": "pv_1", "assumptions_version": "av_1"},
        },
        extra={"cfg_path": "configs/economics/economics_v2.yaml"},
    )
    values = {(row.label, row.value) for row in rows}
    assert ("data_version", "dv_demo") in values
    assert ("price_book_version", "pv_1") in values
    assert ("assumptions_version", "av_1") in values
    assert ("cfg_path", "configs/economics/economics_v2.yaml") in values
