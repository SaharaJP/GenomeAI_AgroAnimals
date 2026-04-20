from __future__ import annotations

from pathlib import Path

import pytest

from genomeai.economics_whatif import run_economics_whatif
from genomeai.whatif_report import generate_whatif_report_pdf


def test_whatif_report_pdf_from_single_run(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    fixtures = repo_root / "data" / "fixtures" / "target_v2"
    assert fixtures.exists()

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    # Compute economics once (contains both baseline and scenario columns)
    res = run_economics_whatif(
        artifacts_root=artifacts,
        data_version="dv_test",
        date_from="2025-01-05",
        date_to="2025-01-05",
        milk_price_multiplier=2.0,
        feed_cost_multiplier=1.0,
        other_cost_multiplier=1.0,
        input_dir=fixtures,
        economics_run="econ_for_report",
    )
    assert res["ok"] is True
    econ_run = str(res["economics_run"])

    rep = generate_whatif_report_pdf(
        artifacts_root=artifacts,
        data_version="dv_test",
        scenario_id="sid_test",
        scenario_name="S_MILK_X2",
        scenario_params={"milk_price_multiplier": 2.0, "feed_cost_multiplier": 1.0, "other_cost_multiplier": 1.0},
        date_from="2025-01-05",
        date_to="2025-01-05",
        cfg_path="configs/economics/economics_v1.yaml",
        base_economics_run=econ_run,
        scenario_economics_run=econ_run,
        report_version="rep_fixed",
    )
    assert rep["ok"] is True
    out_dir = artifacts / "dv_test" / "whatif_reports" / "rep_fixed"
    assert (out_dir / "whatif_report.pdf").exists()
    assert (out_dir / "report_meta.json").exists()
    assert (out_dir / "checksums.json").exists()

    import json

    meta = json.loads((out_dir / "report_meta.json").read_text(encoding="utf-8"))
    assert meta["data_version"] == "dv_test"
    assert meta["scenario_name"] == "S_MILK_X2"

    base = meta["totals"]["base"]
    scen = meta["totals"]["scenario"]
    delta = meta["totals"]["delta"]

    # from fixtures (see tests/test_t7_01_economics.py): baseline revenue=16.848
    assert float(base["revenue"]) == pytest.approx(16.848, abs=1e-6)
    assert float(scen["revenue"]) == pytest.approx(33.696, abs=1e-6)
    assert float(delta["revenue"]) == pytest.approx(16.848, abs=1e-6)
