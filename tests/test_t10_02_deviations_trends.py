from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from genomeai.kpi_targets import load_kpi_targets, compute_plan_fact
from genomeai.dashboard_director import load_kpi_dictionary, compute_milk_trend_windows
from genomeai.dashboard_insights import compute_top_deviations, load_trend_exceptions_rules, compute_milk_trend_exceptions


def test_top_deviations_contains_lineage_and_sources():
    targets_cfg = load_kpi_targets(cfg_path=Path("configs/kpi/kpi_targets_v1.yaml"), override_dir=None)

    kpi_long = pd.DataFrame(
        [
            {"tenant_id": "default", "farm_id": "FARM_001", "kpi_id": "milk_total_kg_7d", "value": 110000, "unit": "kg"},
            {"tenant_id": "default", "farm_id": "FARM_001", "kpi_id": "scc_avg_7d", "value": 220000, "unit": "cells/ml"},
        ]
    )

    plan_fact = compute_plan_fact(kpi_long, targets_cfg=targets_cfg, data_version="dv_x", kpi_run_id="kpi_x")
    kpi_cfg = load_kpi_dictionary(Path("configs/kpi/kpi_v2.yaml"))

    top = compute_top_deviations(plan_fact, kpi_cfg=kpi_cfg, top_n=10)
    assert not top.empty
    assert "kpi_artifact_relpath" in top.columns
    assert set(top["kpi_run_id"].astype(str).unique()) == {"kpi_x"}

    sources = " ".join(top["sources"].fillna("").astype(str).tolist())
    assert "dm_milkings_daily" in sources

    expl = " ".join(top["explanation"].fillna("").astype(str).tolist())
    assert "run_id=kpi_x" in expl


def test_milk_trend_windows_returns_3_rows():
    asof = datetime.strptime("2025-01-05", "%Y-%m-%d").date()
    df = compute_milk_trend_windows(input_dir=Path("data/fixtures/target_v2"), asof=asof, windows=(7, 30, 90))
    assert len(df) == 3
    assert "source_table" in df.columns


def test_milk_trend_exceptions_rules_and_explanation():
    rules = load_trend_exceptions_rules(Path("configs/kpi/kpi_trend_exceptions_v1.yaml"))

    # Synthetic windows: ensure one ALERT and one WARN
    milk_windows = pd.DataFrame(
        [
            {
                "window_days": 7,
                "cur_start": "2025-01-01",
                "cur_end": "2025-01-07",
                "cur_sum_kg": 110.0,
                "prev_start": "2024-12-25",
                "prev_end": "2024-12-31",
                "prev_sum_kg": 100.0,
                "change_kg": 10.0,
                "change_pct": 0.10,
                "source_table": "dm_milkings_daily",
                "source_path": "data/fixtures/target_v2/dm_milkings_daily.csv",
            },
            {
                "window_days": 30,
                "cur_start": "2025-01-01",
                "cur_end": "2025-01-30",
                "cur_sum_kg": 105.0,
                "prev_start": "2024-12-02",
                "prev_end": "2024-12-31",
                "prev_sum_kg": 100.0,
                "change_kg": 5.0,
                "change_pct": 0.05,
                "source_table": "dm_milkings_daily",
                "source_path": "data/fixtures/target_v2/dm_milkings_daily.csv",
            },
        ]
    )

    exc = compute_milk_trend_exceptions(milk_windows, rules=rules, data_version="dv_x", dashboard_run_id="dash_x")
    assert set(["severity", "explanation", "source_path", "windows_artifact_relpath", "exceptions_artifact_relpath"]).issubset(set(exc.columns))
    assert not exc.empty
    assert set(exc["severity"].astype(str).unique()).issubset({"WARN", "ALERT"})

    expl = " ".join(exc["explanation"].fillna("").astype(str).tolist())
    assert "run_id=dash_x" in expl
    assert "milk_trend_windows.csv" in expl
    assert "milk_trend_exceptions.csv" in expl
