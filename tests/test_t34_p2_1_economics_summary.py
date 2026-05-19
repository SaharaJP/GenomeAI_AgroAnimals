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


def test_unit_ladder_unavailable_yields_warning(economics_run: dict) -> None:
    """Without a prior run_unit_economics call, ladder degrades to defaults."""

    resp = build_economics_summary_v1(
        artifacts_root=economics_run["artifacts_root"],
        tenant_id="default",
        level="farm",
        data_version=economics_run["data_version"],
        economics_run=economics_run["economics_run"],
        date_from="2025-01-05",
        date_to="2025-01-05",
    )
    assert resp.unit_economics_ladder.top_quartile_margin_rub is None
    assert resp.unit_economics_ladder.median_margin_rub is None
    assert resp.unit_economics_ladder.bottom_decile_margin_rub is None
    assert any("unit_economics_ladder_unavailable" in w for w in resp.warnings)


def test_unit_ladder_populated_when_unit_economics_ran(tmp_path_factory: pytest.TempPathFactory) -> None:
    """When unit_economics artifacts exist, ladder reports quartile/median/decile."""

    from genomeai.unit_economics import run_unit_economics

    repo_root = Path(__file__).resolve().parents[1]
    artifacts = tmp_path_factory.mktemp("ladder_artifacts")
    input_dir = repo_root / "data" / "fixtures" / "target_v2"
    dv = "dv_test_p2_1_ladder"

    econ = run_economics_v2(
        artifacts_root=artifacts,
        data_version=dv,
        date_from="2025-01-10",
        date_to="2025-01-10",
        cfg_path=repo_root / "configs" / "economics" / "economics_v2.yaml",
        input_dir=input_dir,
        tenant_id="default",
    )
    assert econ.get("ok") is True
    econ_run = str(econ["economics_run"])

    ue = run_unit_economics(
        artifacts_root=artifacts,
        data_version=dv,
        input_dir=input_dir,
        economics_run=econ_run,
        tenant_id="default",
        date_from="2025-01-10",
        date_to="2025-01-10",
    )
    assert ue.get("ok") is True

    resp = build_economics_summary_v1(
        artifacts_root=artifacts,
        tenant_id="default",
        level="farm",
        data_version=dv,
        economics_run=econ_run,
        date_from="2025-01-10",
        date_to="2025-01-10",
    )
    ladder = resp.unit_economics_ladder
    assert ladder.top_quartile_margin_rub is not None
    assert ladder.median_margin_rub is not None
    assert ladder.bottom_decile_margin_rub is not None
    assert ladder.top_quartile_margin_rub >= ladder.median_margin_rub
    assert ladder.median_margin_rub >= ladder.bottom_decile_margin_rub
    assert ladder.bottom_decile_cohort_n is not None and ladder.bottom_decile_cohort_n >= 1
    assert ladder.bottom_decile_cohort_ref is not None
    assert dv in ladder.bottom_decile_cohort_ref
    assert all("unit_economics_ladder_unavailable" not in w for w in resp.warnings)


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


def test_roi_actions_unavailable_yields_warning(economics_run: dict) -> None:
    """Without a prior run_roi_attribution call, roi_actions degrades to []."""

    resp = build_economics_summary_v1(
        artifacts_root=economics_run["artifacts_root"],
        tenant_id="default",
        level="farm",
        data_version=economics_run["data_version"],
        economics_run=economics_run["economics_run"],
        date_from="2025-01-05",
        date_to="2025-01-05",
    )
    assert resp.roi_actions == []
    assert any("roi_actions_unavailable" in w for w in resp.warnings)


def _seed_synthetic_roi_run(artifacts_root: Path, data_version: str) -> str:
    """Write a minimal roi_attribution run layout that load_roi() can resolve.

    Avoids the heavyweight run_roi_attribution + sqlite setup — we are
    testing the reader, not the engine. Reader contract per agent
    mapping: artifacts/<dv>/roi/<run>/roi_actions.csv +
    metadata/roi_manifest.json with 'latest'.
    """

    import json

    run_id = "roi_test_synthetic"
    run_dir = artifacts_root / data_version / "roi" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    rows = pd.DataFrame(
        [
            {
                "tenant_id": "default",
                "action_id": "decision_log:A1001:insemination",
                "object_type": "animal",
                "object_id": "A1001",
                "action_type": "insemination",
                "action_date": "2025-01-08",
                "window_days": 14,
                "method": "before_after",
                "delta_margin_per_day_used": 30.0,
                "delta_margin_window_used": 420.0,
                "cost_rub": 800.0,
                "roi_ratio_used": 0.525,
                "quality_flag": "OK",
            },
            {
                "tenant_id": "default",
                "action_id": "tasks_v1:T1:feed_adjustment",
                "object_type": "pen",
                "object_id": "PEN_A",
                "action_type": "feed_adjustment",
                "action_date": "2025-01-09",
                "window_days": 14,
                "method": "diff_in_diff",
                "delta_margin_per_day_used": 12.0,
                "delta_margin_window_used": 168.0,
                "cost_rub": 200.0,
                "roi_ratio_used": -0.16,
                "quality_flag": "LOW_COVERAGE",
            },
            {
                "tenant_id": "default",
                "action_id": "decision_log:A2002:mastitis",
                "object_type": "animal",
                "object_id": "A2002",
                "action_type": "mastitis_treatment",
                "action_date": "2025-01-10",
                "window_days": 14,
                "method": "before_after",
                "delta_margin_per_day_used": 55.0,
                "delta_margin_window_used": 770.0,
                "cost_rub": 1500.0,
                "roi_ratio_used": -0.486,
                "quality_flag": "OK",
            },
        ]
    )
    rows.to_csv(run_dir / "roi_actions.csv", index=False)

    meta_dir = artifacts_root / data_version / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "genomeai.roi_runs_manifest.v1",
        "data_version": data_version,
        "runs": {run_id: {"created_at_utc": "2025-01-11T00:00:00Z"}},
        "latest": run_id,
    }
    (meta_dir / "roi_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return run_id


def test_roi_actions_populated_when_run_present(tmp_path_factory: pytest.TempPathFactory) -> None:
    """When roi_actions.csv exists, top-N sorted by delta_margin_window_used desc."""

    repo_root = Path(__file__).resolve().parents[1]
    artifacts = tmp_path_factory.mktemp("roi_artifacts")
    dv = "dv_test_p2_1_roi"
    econ = run_economics_v2(
        artifacts_root=artifacts,
        data_version=dv,
        date_from="2025-01-05",
        date_to="2025-01-12",
        cfg_path=repo_root / "configs" / "economics" / "economics_v2.yaml",
        input_dir=repo_root / "data" / "fixtures" / "target_v2",
        tenant_id="default",
    )
    assert econ.get("ok") is True
    _seed_synthetic_roi_run(artifacts, dv)

    resp = build_economics_summary_v1(
        artifacts_root=artifacts,
        tenant_id="default",
        level="farm",
        data_version=dv,
        economics_run=str(econ["economics_run"]),
        date_from="2025-01-05",
        date_to="2025-01-12",
    )
    actions = resp.roi_actions
    assert len(actions) == 3
    # sorted desc by total_margin_delta_rub
    deltas = [a.total_margin_delta_rub for a in actions]
    assert deltas == sorted(deltas, reverse=True)
    # leader is the mastitis_treatment (770.0)
    assert actions[0].total_margin_delta_rub == pytest.approx(770.0, abs=1e-6)
    assert actions[0].label == "mastitis_treatment"
    assert actions[0].method in {"before_after", "diff_in_diff"}
    assert actions[0].window_days == 14
    assert all("roi_actions_unavailable" not in w for w in resp.warnings)


def test_strategic_kpi_returns_config_provenance(economics_run: dict) -> None:
    resp = build_economics_summary_v1(
        artifacts_root=economics_run["artifacts_root"],
        tenant_id="default",
        level="farm",
        data_version=economics_run["data_version"],
        economics_run=economics_run["economics_run"],
        date_from="2025-01-05",
        date_to="2025-01-05",
    )
    sk = resp.strategic_kpi
    # config provenance always populated even when ROI/payback can't be computed
    assert sk.acquisition_cost_rub_per_cow is not None
    assert sk.saas_cac_rub is not None
    assert sk.lifetime_years is not None
    assert sk.retention_months is not None
    # without cows_total → ROI per cow is null
    assert sk.roi_per_cow_per_year_pct is None
    assert sk.roi_per_cow_lifetime_pct is None
    assert any("strategic_kpi_unavailable" in w for w in resp.warnings)


def test_strategic_kpi_populated_with_cows_total(economics_run: dict) -> None:
    resp = build_economics_summary_v1(
        artifacts_root=economics_run["artifacts_root"],
        tenant_id="default",
        level="farm",
        data_version=economics_run["data_version"],
        economics_run=economics_run["economics_run"],
        date_from="2025-01-05",
        date_to="2025-01-05",
        cows_total=10,
    )
    sk = resp.strategic_kpi
    # If total_margin_rub is negative for these fixtures, roi_per_cow stays computed (could be negative)
    # but ltv_cac and payback require positive margin
    if resp.kpi.total_margin_rub is not None and resp.kpi.total_margin_rub > 0:
        assert sk.payback_months is not None
        assert sk.ltv_cac_ratio is not None
    else:
        assert sk.payback_months is None
    # ROI per cow always computes when cows_total and period_days are valid
    if resp.kpi.total_margin_rub is not None:
        assert sk.roi_per_cow_per_year_pct is not None
        assert sk.roi_per_cow_lifetime_pct is not None


def test_unsupported_level_raises(economics_run: dict) -> None:
    with pytest.raises(ValueError, match="unsupported_level"):
        build_economics_summary_v1(
            artifacts_root=economics_run["artifacts_root"],
            tenant_id="default",
            level="cow",  # not in {farm, site, pen}
            data_version=economics_run["data_version"],
            economics_run=economics_run["economics_run"],
        )
