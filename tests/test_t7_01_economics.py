from __future__ import annotations

from pathlib import Path

import pytest

from genomeai.economics_whatif import run_economics_whatif


def test_economics_baseline_and_whatif(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    fixtures = repo_root / "data" / "fixtures" / "target_v2"
    assert fixtures.exists()

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    res = run_economics_whatif(
        artifacts_root=artifacts,
        data_version="dv_test",
        date_from="2025-01-05",
        date_to="2025-01-05",
        milk_price_multiplier=1.0,
        feed_cost_multiplier=1.0,
        other_cost_multiplier=1.0,
        input_dir=fixtures,
    )
    assert res["ok"] is True
    run_id = res["economics_run"]
    run_dir = artifacts / "dv_test" / "economics" / run_id
    assert (run_dir / "farm_day_baseline.csv").exists()
    assert (run_dir / "economics_whatif.xlsx").exists()

    import pandas as pd

    farm_b = pd.read_csv(run_dir / "farm_day_baseline.csv")
    assert len(farm_b) == 1
    row = farm_b.iloc[0]
    # из fixtures:
    # milk_kg=32.4, price=0.52 -> revenue=16.848
    # feed_kg_as_fed=3500, dm_pct=52% -> dm_kg=1820, cost=1820*0.29=527.8
    # other=120 -> margin=16.848-647.8=-630.952
    assert float(row["revenue"]) == pytest.approx(16.848, abs=1e-6)
    assert float(row["feed_cost"]) == pytest.approx(527.8, abs=1e-6)
    assert float(row["other_cost"]) == pytest.approx(120.0, abs=1e-6)
    assert float(row["margin"]) == pytest.approx(-630.952, abs=1e-6)

    # what-if: milk price x2
    res2 = run_economics_whatif(
        artifacts_root=artifacts,
        data_version="dv_test",
        date_from="2025-01-05",
        date_to="2025-01-05",
        milk_price_multiplier=2.0,
        feed_cost_multiplier=1.0,
        other_cost_multiplier=1.0,
        input_dir=fixtures,
        economics_run="econ_fixed",
    )
    assert res2["ok"] is True
    run_dir2 = artifacts / "dv_test" / "economics" / "econ_fixed"
    farm_s = pd.read_csv(run_dir2 / "farm_day_scenario.csv")
    assert float(farm_s.iloc[0]["margin"]) == pytest.approx(-614.104, abs=1e-6)
