from __future__ import annotations

from pathlib import Path

import pytest

from genomeai.economics_whatif import compare_whatif_scenarios


def test_compare_whatif_scenarios(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    fixtures = repo_root / "data" / "fixtures" / "target_v2"
    assert fixtures.exists()

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    res = compare_whatif_scenarios(
        artifacts_root=artifacts,
        data_version="dv_test",
        date_from="2025-01-05",
        date_to="2025-01-05",
        scenarios=[
            {
                "name": "milk_x2",
                "milk_price_multiplier": 2.0,
                "feed_cost_multiplier": 1.0,
                "other_cost_multiplier": 1.0,
            }
        ],
        input_dir=fixtures,
    )

    assert res["ok"] is True
    rows = list(res.get("comparison") or [])
    assert len(rows) == 2
    base = next(r for r in rows if r["scenario"] == "BASE")
    s1 = next(r for r in rows if r["scenario"] == "milk_x2")

    # from existing economics test fixtures:
    # base margin = -630.952
    # milk x2 margin = -614.104
    assert float(base["margin"]) == pytest.approx(-630.952, abs=1e-6)
    assert float(s1["margin"]) == pytest.approx(-614.104, abs=1e-6)
    assert float(s1["margin_delta"]) == pytest.approx(16.848, abs=1e-6)
