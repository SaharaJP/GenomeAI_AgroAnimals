from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import pandas as pd


def test_t10_02_snapshot_png_perf_smoke(tmp_path: Path):
    """Basic regression guard: PNG rendering should be reasonably fast."""
    from genomeai.dashboard_director import _render_director_png

    # Small synthetic data
    plan_fact = pd.DataFrame(
        {
            "farm_id": ["f1"] * 50,
            "kpi_id": [f"K{i}" for i in range(50)],
            "actual": [100.0] * 50,
            "target": [110.0] * 50,
            "status": ["WARN"] * 50,
            "delta_pct": [-9.09] * 50,
        }
    )
    top_devs = plan_fact[["farm_id", "kpi_id", "status", "delta_pct"]].copy()
    milk_ts = pd.DataFrame({"date": pd.date_range("2025-01-01", periods=30), "milk_kg": [30.0] * 30})

    out_path = tmp_path / "snap.png"
    t0 = time.perf_counter()
    ok = _render_director_png(
        out_path=out_path,
        dv="dv_perf",
        asof=date(2025, 1, 30),
        kpi_run_id="kpi_perf",
        plan_fact=plan_fact,
        top_devs=top_devs,
        milk_ts=milk_ts,
        cfg={"png": {"width_px": 1200, "height_px": 700, "dpi": 120, "top_deviations_rows": 10}},
    )
    dt = time.perf_counter() - t0

    assert ok is True
    assert out_path.exists()
    # Very мягкий порог, чтобы не флапало в CI
    assert dt < 5.0, f"PNG render too slow: {dt:.3f}s"
