from __future__ import annotations

from pathlib import Path

import pytest

from genomeai.economics_v2 import run_economics_v2


def test_economics_v2_rub(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    fixtures = repo_root / "data" / "fixtures" / "target_v2"
    assert fixtures.exists()

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    res = run_economics_v2(
        artifacts_root=artifacts,
        data_version="dv_test",
        date_from="2025-01-05",
        date_to="2025-01-05",
        cfg_path=repo_root / "configs" / "economics" / "economics_v2.yaml",
        input_dir=fixtures,
        tenant_id="default",
    )
    assert res.get("ok") is True
    run_id = str(res.get("economics_run"))
    run_dir = artifacts / "dv_test" / "economics_v2" / run_id
    assert (run_dir / "economics_daily.csv").exists()
    assert (run_dir / "economics_monthly.csv").exists()
    assert (run_dir / "formulas_catalog.json").exists()
    assert (run_dir / "manifest.json").exists()

    import pandas as pd

    df = pd.read_csv(run_dir / "economics_daily.csv")
    # We assert farm-level row from fixtures:
    # dm_economics_daily: milk_price_per_kg=0.52 (milk_price_ccy=EUR), feed_cost_per_kg_dm=0.29 (feed_cost_ccy=EUR), other_cost_eur=120 EUR
    # cfg: fx EUR=100 => RUB (output currency всегда RUB)
    # dm_milkings_daily: milk_kg=32.4
    # dm_feed_deliveries: 3500 kg as fed, dm_pct=52% => 1820 kg DM
    # revenue=32.4*52=1684.8
    # feed_cost=1820*29=52780
    # other_cost=120*100=12000
    # margin=1684.8-64780=-63095.2
    farm = df[(df["level"] == "farm") & (df["date"] == "2025-01-05")]
    assert len(farm) == 1
    row = farm.iloc[0]
    assert float(row["milk_kg"]) == pytest.approx(32.4, abs=1e-6)
    assert float(row["revenue_total_rub"]) == pytest.approx(1684.8, abs=1e-6)
    assert float(row["revenue_milk_rub"]) == pytest.approx(1684.8, abs=1e-6)
    assert float(row["cost_feed_rub"]) == pytest.approx(52780.0, abs=1e-6)
    assert float(row["cost_other_rub"]) == pytest.approx(12000.0, abs=1e-6)
    assert float(row["total_cost_rub"]) == pytest.approx(64780.0, abs=1e-6)
    assert float(row["margin_rub"]) == pytest.approx(-63095.2, abs=1e-6)

def test_economics_v2_with_vet_repro_cull(tmp_path: Path) -> None:
    """Control example: vet+repro+cull appear and affect totals (all in RUB)."""
    repo_root = Path(__file__).resolve().parents[1]
    fixtures = repo_root / "data" / "fixtures" / "target_v2"
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    res = run_economics_v2(
        artifacts_root=artifacts,
        data_version="dv_test",
        date_from="2025-01-10",
        date_to="2025-01-10",
        cfg_path=repo_root / "configs" / "economics" / "economics_v2.yaml",
        input_dir=fixtures,
        tenant_id="default",
    )
    assert res.get("ok") is True
    run_id = str(res.get("economics_run"))
    run_dir = artifacts / "dv_test" / "economics_v2" / run_id

    import pandas as pd

    df = pd.read_csv(run_dir / "economics_daily.csv")
    farm = df[(df["level"] == "farm") & (df["date"] == "2025-01-10")]
    assert len(farm) == 1
    row = farm.iloc[0]

    # Milk: 30kg, price 0.52 EUR, fx=100 => 52 RUB/kg => 1560 RUB
    assert float(row["milk_kg"]) == pytest.approx(30.0, abs=1e-6)
    assert float(row["revenue_milk_rub"]) == pytest.approx(1560.0, abs=1e-6)

    # Cull: event provides revenue_rub=45000 and cost_rub=5000
    assert float(row["revenue_cull_rub"]) == pytest.approx(45000.0, abs=1e-6)
    assert float(row["cost_cull_rub"]) == pytest.approx(5000.0, abs=1e-6)

    # Feed: 3200 as-fed, dm_pct 52% => 1664 DM, cost 0.29 EUR, fx=100 => 29 RUB/kgDM => 48256
    assert float(row["cost_feed_rub"]) == pytest.approx(48256.0, abs=1e-6)

    # Vet/Repro from config: 1 treatment * 1500; 1 insemination * 800
    assert float(row["cost_vet_rub"]) == pytest.approx(1500.0, abs=1e-6)
    assert float(row["cost_repro_rub"]) == pytest.approx(800.0, abs=1e-6)

    # Other: 120 EUR * 100 = 12000
    assert float(row["cost_other_rub"]) == pytest.approx(12000.0, abs=1e-6)

    # Totals
    assert float(row["revenue_total_rub"]) == pytest.approx(46560.0, abs=1e-6)
    assert float(row["total_cost_rub"]) == pytest.approx(67556.0, abs=1e-6)
    assert float(row["margin_rub"]) == pytest.approx(-20996.0, abs=1e-6)
