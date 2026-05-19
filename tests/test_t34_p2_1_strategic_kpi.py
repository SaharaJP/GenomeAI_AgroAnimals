"""Unit tests for ``core.economics.strategic_kpi`` (RFC §4.1, §4.2)."""

from __future__ import annotations

import pytest

from core.economics.strategic_kpi import (
    DAYS_PER_MONTH,
    StrategicKpiInputs,
    StrategicKpiResult,
    compute_strategic_kpi,
)


def _balanced_inputs(**overrides) -> StrategicKpiInputs:
    base = dict(
        total_margin_rub=1_200_000.0,         # 30 days × 100 cows × 400 ₽/day per cow
        cows_total=100,
        period_days=30,
        acquisition_cost_rub_per_cow=200_000.0,
        saas_cac_rub=120_000.0,
        lifetime_years=5.0,
        retention_months=60.0,
    )
    base.update(overrides)
    return StrategicKpiInputs(**base)


def test_roi_per_cow_hand_check() -> None:
    """margin/cow/day = 1.2M / 100 / 30 = 400; annualised = 400 × 365 = 146 000;
    ROI/year = 146 000 / 200 000 = 73%; lifetime = 73 × 5 = 365%."""

    res = compute_strategic_kpi(_balanced_inputs())
    assert res.margin_rub_per_cow_per_year == pytest.approx(146_000.0, abs=1e-3)
    assert res.roi_per_cow_per_year_pct == pytest.approx(73.0, abs=1e-3)
    assert res.roi_per_cow_lifetime_pct == pytest.approx(365.0, abs=1e-3)


def test_payback_hand_check() -> None:
    """monthly_margin = 1.2M / (30 / 30.4375) = 1 217 500 (close); payback = 120 000 / 1 217 500 ≈ 0.0985 months."""

    res = compute_strategic_kpi(_balanced_inputs())
    expected_monthly = 1_200_000.0 / (30.0 / DAYS_PER_MONTH)
    assert res.monthly_margin_rub_per_farm == pytest.approx(expected_monthly, abs=1e-3)
    expected_payback = 120_000.0 / expected_monthly
    assert res.payback_months == pytest.approx(expected_payback, abs=1e-6)


def test_ltv_cac_hand_check() -> None:
    """ltv = monthly_margin × 60 months; ltv/cac = ltv / 120k."""

    res = compute_strategic_kpi(_balanced_inputs())
    expected_monthly = 1_200_000.0 / (30.0 / DAYS_PER_MONTH)
    expected_ltv = expected_monthly * 60.0
    expected_ratio = expected_ltv / 120_000.0
    assert res.ltv_cac_ratio == pytest.approx(expected_ratio, abs=1e-6)


def test_zero_cows_total_yields_null_roi() -> None:
    res = compute_strategic_kpi(_balanced_inputs(cows_total=0))
    assert res.roi_per_cow_per_year_pct is None
    assert res.roi_per_cow_lifetime_pct is None
    assert res.margin_rub_per_cow_per_year is None


def test_none_period_days_yields_null_everything() -> None:
    res = compute_strategic_kpi(_balanced_inputs(period_days=None))
    assert res.roi_per_cow_per_year_pct is None
    assert res.payback_months is None
    assert res.ltv_cac_ratio is None


def test_negative_margin_yields_null_payback() -> None:
    """When monthly margin <= 0 the SaaS investment does not break even."""

    res = compute_strategic_kpi(_balanced_inputs(total_margin_rub=-50_000.0))
    assert res.payback_months is None
    # ROI still computes; it'll just be negative
    assert res.roi_per_cow_per_year_pct is not None
    assert res.roi_per_cow_per_year_pct < 0


def test_zero_acquisition_cost_yields_null_roi() -> None:
    res = compute_strategic_kpi(_balanced_inputs(acquisition_cost_rub_per_cow=0.0))
    assert res.roi_per_cow_per_year_pct is None


def test_zero_saas_cac_yields_null_payback_and_ltv_cac() -> None:
    res = compute_strategic_kpi(_balanced_inputs(saas_cac_rub=0.0))
    assert res.payback_months is None
    assert res.ltv_cac_ratio is None


def test_dataclass_frozen() -> None:
    res = compute_strategic_kpi(_balanced_inputs())
    assert isinstance(res, StrategicKpiResult)
    with pytest.raises(Exception):
        res.payback_months = 99.0  # type: ignore[misc]
