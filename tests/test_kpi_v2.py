from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from genomeai.kpi_v2 import run_kpi


def test_kpi_v2_runs_and_outputs(tmp_path: Path):
    # Use target_v2 fixtures
    repo_root = Path(__file__).resolve().parents[1]
    fixtures = repo_root / "data" / "fixtures" / "target_v2"
    assert fixtures.exists()

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    dv = "dv_test_kpi"
    res = run_kpi(
        data_version=dv,
        asof_date="2025-01-05",
        artifacts_root=artifacts,
        input_dir=fixtures,
        run_id="kpi_20250105_test",
        config_kpi=repo_root / "configs" / "kpi" / "kpi_v2.yaml",
        config_thresholds=repo_root / "configs" / "kpi" / "kpi_thresholds_v2.yaml",
    )

    run_root = Path(res["run_root"])
    kpi_dir = run_root / "kpi"
    assert (kpi_dir / "kpi_long.csv").exists()
    assert (kpi_dir / "kpi_wide.csv").exists()
    assert (kpi_dir / "kpi_alerts.csv").exists()
    assert (kpi_dir / "kpi_summary.json").exists()
    assert (run_root / "run_manifest.json").exists()
    assert (run_root / "checksums.json").exists()

    kpi_long = pd.read_csv(kpi_dir / "kpi_long.csv")
    # At least 20 KPI ids should be present
    assert kpi_long["kpi_id"].nunique() >= 20

    # Numerical sanity on fixture: milk_total_kg_1d equals sum milk_kg on 2025-01-05
    m = pd.read_csv(fixtures / "dm_milkings_daily.csv")
    m["date"] = pd.to_datetime(m["date"]).dt.date
    total_1d = m.loc[m["date"] == datetime(2025, 1, 5).date(), "milk_kg"].sum()

    got = kpi_long.loc[kpi_long["kpi_id"] == "milk_total_kg_1d", "value"].iloc[0]
    assert abs(got - float(total_1d)) < 1e-6
