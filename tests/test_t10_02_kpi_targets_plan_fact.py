from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from genomeai.kpi_targets import load_kpi_targets, compute_plan_fact


def test_plan_fact_statuses_from_targets_config():
    cfg = load_kpi_targets(cfg_path=Path("configs/kpi/kpi_targets_v1.yaml"), override_dir=None)
    kpi_long = pd.DataFrame(
        [
            {"tenant_id": "default", "farm_id": "FARM_001", "kpi_id": "milk_total_kg_7d", "value": 110000, "unit": "kg"},
            {"tenant_id": "default", "farm_id": "FARM_001", "kpi_id": "scc_avg_7d", "value": 220000, "unit": "cells/ml"},
            {"tenant_id": "default", "farm_id": "FARM_001", "kpi_id": "unknown_kpi", "value": 1, "unit": "x"},
        ]
    )
    pf = compute_plan_fact(kpi_long, targets_cfg=cfg, data_version="dv_x", kpi_run_id="kpi_x")
    s = {r["kpi_id"]: r["status"] for _, r in pf.iterrows()}
    # FARM_001 overrides: target=120000, alert_pct=0.08 -> 110k is -8.33% => ALERT
    assert s["milk_total_kg_7d"] == "ALERT"
    # lower_better: 220k vs 200k => +10% => WARN
    assert s["scc_avg_7d"] == "WARN"
    assert s["unknown_kpi"] == "NO_TARGET"


def test_plan_fact_perf_smoke():
    cfg = load_kpi_targets(cfg_path=Path("configs/kpi/kpi_targets_v1.yaml"), override_dir=None)
    # 10k rows is enough for a basic perf regression guard.
    n = 10000
    df = pd.DataFrame(
        {
            "tenant_id": ["default"] * n,
            "farm_id": ["FARM_001"] * n,
            "kpi_id": ["milk_total_kg_7d"] * n,
            "value": [115000.0] * n,
            "unit": ["kg"] * n,
        }
    )
    t0 = time.perf_counter()
    out = compute_plan_fact(df, targets_cfg=cfg, data_version="dv_x", kpi_run_id="kpi_x")
    dt = time.perf_counter() - t0
    assert not out.empty
    # Keep very loose to avoid flaky failures on CI.
    assert dt < 2.0
