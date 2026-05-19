"""Slice 2 of P2-1: economics summary use-case.

Covers ``core.application.build_economics_summary_v1`` over a real
``run_economics_v2`` artifact. Verifies revenue/cost/margin math by
direct comparison to the underlying CSV (positive burden of proof
per CLAUDE.md §1: aggregation must match the artifact, not a mock).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from core.application import build_economics_summary_v1
from genomeai.economics_v2 import run_economics_v2


@pytest.fixture(scope="module")
def economics_run(tmp_path_factory: pytest.TempPathFactory) -> dict:
    repo_root = Path(__file__).resolve().parents[1]
    artifacts = tmp_path_factory.mktemp("artifacts")
    res = run_economics_v2(
        artifacts_root=artifacts,
        data_version="dv_test_p2_1",
        date_from="2025-01-05",
        date_to="2025-01-05",
        cfg_path=repo_root / "configs" / "economics" / "economics_v2.yaml",
        input_dir=repo_root / "data" / "fixtures" / "target_v2",
        tenant_id="default",
    )
    assert res.get("ok") is True
    return {
        "artifacts_root": artifacts,
        "data_version": "dv_test_p2_1",
        "economics_run": str(res["economics_run"]),
        "run_dir": Path(res["run_dir"]),
    }


def _farm_row(run_dir: Path) -> pd.Series:
    df = pd.read_csv(run_dir / "economics_daily.csv")
    farm = df[(df["level"] == "farm") & (df["date"] == "2025-01-05")]
    assert len(farm) == 1, "fixture must yield exactly one farm-level row for 2025-01-05"
    return farm.iloc[0]


def test_schema_and_scope(economics_run: dict) -> None:
    resp = build_economics_summary_v1(
        artifacts_root=economics_run["artifacts_root"],
        tenant_id="default",
        level="farm",
        data_version=economics_run["data_version"],
        economics_run=economics_run["economics_run"],
        date_from="2025-01-05",
        date_to="2025-01-05",
    )
    dump = resp.model_dump(by_alias=True)
    assert dump["schema"] == "genomeai.api.economics.summary.v1"
    assert dump["scope"]["tenant_id"] == "default"
    assert dump["scope"]["level"] == "farm"
    assert dump["scope"]["period"]["date_from"] == "2025-01-05"
    assert dump["scope"]["period"]["date_to"] == "2025-01-05"
    assert dump["scope"]["data_version"] == "dv_test_p2_1"
    assert dump["scope"]["economics_run"] == economics_run["economics_run"]


def test_kpi_revenue_cost_match_csv(economics_run: dict) -> None:
    row = _farm_row(economics_run["run_dir"])
    resp = build_economics_summary_v1(
        artifacts_root=economics_run["artifacts_root"],
        tenant_id="default",
        level="farm",
        data_version=economics_run["data_version"],
        economics_run=economics_run["economics_run"],
        date_from="2025-01-05",
        date_to="2025-01-05",
    )

    assert resp.revenue.milk_rub == pytest.approx(float(row["revenue_milk_rub"]), abs=1e-3)
    assert resp.revenue.cull_rub == pytest.approx(float(row["revenue_cull_rub"]), abs=1e-3)
    assert resp.revenue.total_rub == pytest.approx(float(row["revenue_total_rub"]), abs=1e-3)
    assert resp.cost.feed_rub == pytest.approx(float(row["cost_feed_rub"]), abs=1e-3)
    assert resp.cost.vet_rub == pytest.approx(float(row["cost_vet_rub"]), abs=1e-3)
    assert resp.cost.repro_rub == pytest.approx(float(row["cost_repro_rub"]), abs=1e-3)
    assert resp.cost.cull_rub == pytest.approx(float(row["cost_cull_rub"]), abs=1e-3)
    assert resp.cost.other_rub == pytest.approx(float(row["cost_other_rub"]), abs=1e-3)
    assert resp.cost.total_rub == pytest.approx(float(row["total_cost_rub"]), abs=1e-3)
    assert resp.kpi.total_margin_rub == pytest.approx(float(row["margin_rub"]), abs=1e-3)

    if resp.revenue.total_rub > 0:
        expected_margin_pct = float(row["margin_rub"]) / float(row["revenue_total_rub"]) * 100.0
        assert resp.kpi.margin_pct == pytest.approx(expected_margin_pct, abs=1e-6)
    else:
        assert resp.kpi.margin_pct is None


def test_breakdown_pct_sums_to_one_hundred(economics_run: dict) -> None:
    resp = build_economics_summary_v1(
        artifacts_root=economics_run["artifacts_root"],
        tenant_id="default",
        level="farm",
        data_version=economics_run["data_version"],
        economics_run=economics_run["economics_run"],
        date_from="2025-01-05",
        date_to="2025-01-05",
    )
    if resp.cost.total_rub <= 0:
        assert resp.cost.breakdown_pct == {}
        return
    total_pct = sum(resp.cost.breakdown_pct.values())
    assert total_pct == pytest.approx(100.0, abs=0.3)  # rounding tolerance (1 decimal × 5 categories)


def test_per_cow_day_when_headcount_provided(economics_run: dict) -> None:
    resp_with = build_economics_summary_v1(
        artifacts_root=economics_run["artifacts_root"],
        tenant_id="default",
        level="farm",
        data_version=economics_run["data_version"],
        economics_run=economics_run["economics_run"],
        date_from="2025-01-05",
        date_to="2025-01-05",
        cows_total=10,
    )
    assert resp_with.per_cow_day.margin_rub is not None
    expected = resp_with.kpi.total_margin_rub / (10 * 1)  # 10 cows × 1 day
    assert resp_with.per_cow_day.margin_rub == pytest.approx(expected, abs=1e-6)
    assert resp_with.kpi.margin_per_cow_per_day_rub == pytest.approx(expected, abs=1e-6)
    assert all("per_cow_day_unavailable" not in w for w in resp_with.warnings)


def test_per_cow_day_warning_without_headcount(economics_run: dict) -> None:
    resp = build_economics_summary_v1(
        artifacts_root=economics_run["artifacts_root"],
        tenant_id="default",
        level="farm",
        data_version=economics_run["data_version"],
        economics_run=economics_run["economics_run"],
        date_from="2025-01-05",
        date_to="2025-01-05",
    )
    assert resp.kpi.margin_per_cow_per_day_rub is None
    assert resp.per_cow_day.margin_rub is None
    assert any("per_cow_day_unavailable" in w for w in resp.warnings)


def test_empty_filter_returns_warning(economics_run: dict) -> None:
    resp = build_economics_summary_v1(
        artifacts_root=economics_run["artifacts_root"],
        tenant_id="default",
        level="farm",
        data_version=economics_run["data_version"],
        economics_run=economics_run["economics_run"],
        farm_id="nonexistent_farm_id_xyz",
        date_from="2025-01-05",
        date_to="2025-01-05",
    )
    assert resp.revenue.total_rub == 0.0
    assert resp.cost.total_rub == 0.0
    assert resp.kpi.total_margin_rub is None or resp.kpi.total_margin_rub == 0.0
    assert any("economics_v2_artifacts_empty_after_filters" in w for w in resp.warnings)


def test_sensitivity_reflects_csv_aggregates(economics_run: dict) -> None:
    """Sensitivity block must satisfy ``margin = 0`` at the returned breakeven values."""

    row = _farm_row(economics_run["run_dir"])
    resp = build_economics_summary_v1(
        artifacts_root=economics_run["artifacts_root"],
        tenant_id="default",
        level="farm",
        data_version=economics_run["data_version"],
        economics_run=economics_run["economics_run"],
        date_from="2025-01-05",
        date_to="2025-01-05",
    )
    sens = resp.sensitivity
    assert sens.method == "single_input_holding_others"

    milk_kg = float(row["milk_kg"])
    feed_dm_kg = float(row["feed_dm_kg"])
    treatments_n = float(row["treatments_n"])
    revenue_total = float(row["revenue_total_rub"])
    revenue_cull = float(row["revenue_cull_rub"])
    total_cost = float(row["total_cost_rub"])
    cost_feed = float(row["cost_feed_rub"])
    cost_vet = float(row["cost_vet_rub"])
    cost_repro = float(row["cost_repro_rub"])
    cost_cull = float(row["cost_cull_rub"])
    cost_other = float(row["cost_other_rub"])

    if milk_kg > 0:
        expected_milk_floor = max(0.0, (total_cost - revenue_cull) / milk_kg)
        assert sens.milk_price_floor_rub_per_kg == pytest.approx(expected_milk_floor, rel=1e-6)
    else:
        assert sens.milk_price_floor_rub_per_kg is None

    if feed_dm_kg > 0:
        non_feed = cost_vet + cost_repro + cost_cull + cost_other
        expected_feed_ceiling = max(0.0, (revenue_total - non_feed) / feed_dm_kg)
        assert sens.feed_cost_ceiling_rub_per_kg_dm == pytest.approx(expected_feed_ceiling, rel=1e-6)
    else:
        assert sens.feed_cost_ceiling_rub_per_kg_dm is None

    if treatments_n > 0:
        non_vet = cost_feed + cost_repro + cost_cull + cost_other
        expected_vet_ceiling = max(0.0, (revenue_total - non_vet) / treatments_n)
        assert sens.vet_cost_ceiling_rub_per_event == pytest.approx(expected_vet_ceiling, rel=1e-6)
    else:
        assert sens.vet_cost_ceiling_rub_per_event is None


def test_formula_refs_include_sensitivity(economics_run: dict) -> None:
    resp = build_economics_summary_v1(
        artifacts_root=economics_run["artifacts_root"],
        tenant_id="default",
        level="farm",
        data_version=economics_run["data_version"],
        economics_run=economics_run["economics_run"],
        date_from="2025-01-05",
        date_to="2025-01-05",
    )
    assert "sensitivity_method" in resp.formula_refs
    assert "T34-economics-rfc.md" in resp.formula_refs["sensitivity_method"]


def test_unsupported_level_raises(economics_run: dict) -> None:
    with pytest.raises(ValueError, match="unsupported_level"):
        build_economics_summary_v1(
            artifacts_root=economics_run["artifacts_root"],
            tenant_id="default",
            level="cow",  # not in {farm, site, pen}
            data_version=economics_run["data_version"],
            economics_run=economics_run["economics_run"],
        )
