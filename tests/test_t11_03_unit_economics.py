from __future__ import annotations

from pathlib import Path

import pandas as pd

from genomeai.economics_v2 import run_economics_v2
from genomeai.unit_economics import run_unit_economics, load_unit_economics


def test_t11_03_unit_economics_integration(tmp_path: Path) -> None:
    """Integration: economics_v2 -> unit_economics (fixtures target_v2)."""

    artifacts = tmp_path / "artifacts"
    dv = "dv_t11_03_unit_econ"
    input_dir = Path("data/fixtures/target_v2")

    # 1) economics_v2 for a day that includes vet/repro/cull events
    econ = run_economics_v2(
        artifacts_root=artifacts,
        data_version=dv,
        input_dir=input_dir,
        date_from="2025-01-10",
        date_to="2025-01-10",
        tenant_id="default",
    )
    assert econ.get("ok"), econ
    econ_run = str(econ.get("economics_run"))

    # 2) unit_economics
    ue = run_unit_economics(
        artifacts_root=artifacts,
        data_version=dv,
        input_dir=input_dir,
        economics_run=econ_run,
        tenant_id="default",
        date_from="2025-01-10",
        date_to="2025-01-10",
    )
    assert ue.get("ok"), ue

    rid, dfs, _ = load_unit_economics(artifacts_root=artifacts, data_version=dv, unit_econ_run=str(ue.get("unit_econ_run")))
    assert rid

    adf = dfs["animal_daily"]
    gdf = dfs["group_daily"]
    assert not adf.empty
    assert not gdf.empty

    # both animals should appear: A1001 (milk/treat/repro), A1002 (cull)
    assert set(adf["animal_id"].astype(str).unique()) >= {"A1001", "A1002"}

    # per-animal checks
    adf["date"] = pd.to_datetime(adf["date"]).dt.date

    a1 = adf[(adf["animal_id"].astype(str) == "A1001") & (adf["date"].astype(str) == "2025-01-10")].iloc[0]
    assert float(a1.get("milk_kg")) == 30.0
    assert float(a1.get("cost_vet_rub")) == 1500.0
    assert float(a1.get("cost_repro_rub")) == 800.0
    # milk price from fixtures: 0.52 EUR/kg with fx EUR=100 => 52 RUB/kg
    assert float(a1.get("revenue_milk_rub")) == 1560.0

    a2 = adf[(adf["animal_id"].astype(str) == "A1002") & (adf["date"].astype(str) == "2025-01-10")].iloc[0]
    assert float(a2.get("revenue_cull_rub")) == 45000.0
    assert float(a2.get("cost_cull_rub")) == 5000.0

    # group pen totals should match sum of animal totals
    gdf["date"] = pd.to_datetime(gdf["date"]).dt.date
    pen = gdf[(gdf["level"].astype(str) == "pen") & (gdf["pen_id"].astype(str) == "PEN_01") & (gdf["date"].astype(str) == "2025-01-10")].iloc[0]

    sums = adf[(adf["date"].astype(str) == "2025-01-10")].groupby("pen_id").agg(
        {
            "revenue_total_rub": "sum",
            "total_cost_rub": "sum",
            "margin_rub": "sum",
        }
    )
    s = sums.loc["PEN_01"]

    assert abs(float(pen.get("revenue_total_rub")) - float(s["revenue_total_rub"])) < 1e-6
    assert abs(float(pen.get("total_cost_rub")) - float(s["total_cost_rub"])) < 1e-6
    assert abs(float(pen.get("margin_rub")) - float(s["margin_rub"])) < 1e-6
