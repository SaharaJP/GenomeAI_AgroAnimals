"""Strategic (director / investor) KPI block for /economics RFC §4.1, §4.2.

Pure formula module. Inputs come pre-aggregated from
``core.application.build_economics_summary_v1``; this module does not
read artifacts. Formulas mirror ``docs/target/economics_v2.md`` —
the «Стратегические показатели» section added alongside.

CAVEAT: every value is a TARGET, not validated on real pilots. See
``docs/investor_faq_ru.md`` q.22 disclaimer for context. The endpoint
exposes the underlying assumptions (acquisition_cost_rub_per_cow,
saas_cac_rub, lifetime_years, retention_months) so the UI can render
the «target / unvalidated» badge with provenance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


DAYS_PER_MONTH = 30.4375  # average; matches docs/target/economics_v2.md


@dataclass(frozen=True)
class StrategicKpiInputs:
    """Pre-aggregated period totals.

    ``total_margin_rub`` is the sum over the active scope and date
    range (matches the ``kpi.total_margin_rub`` value the endpoint
    already computes from economics_v2 artifacts). ``cows_total``
    and ``period_days`` may be ``None`` — in that case ROI / payback
    return ``None`` rather than raising.
    """

    total_margin_rub: Optional[float]
    cows_total: Optional[int]
    period_days: Optional[int]
    acquisition_cost_rub_per_cow: float
    saas_cac_rub: float
    lifetime_years: float
    retention_months: float


@dataclass(frozen=True)
class StrategicKpiResult:
    roi_per_cow_per_year_pct: Optional[float]
    roi_per_cow_lifetime_pct: Optional[float]
    payback_months: Optional[float]
    ltv_cac_ratio: Optional[float]
    margin_rub_per_cow_per_year: Optional[float]
    monthly_margin_rub_per_farm: Optional[float]


def _annualised_margin_per_cow(
    total_margin_rub: Optional[float],
    cows_total: Optional[int],
    period_days: Optional[int],
) -> Optional[float]:
    if total_margin_rub is None or cows_total is None or period_days is None:
        return None
    if cows_total <= 0 or period_days <= 0:
        return None
    return float(total_margin_rub) / float(cows_total) / float(period_days) * 365.0


def _monthly_margin(total_margin_rub: Optional[float], period_days: Optional[int]) -> Optional[float]:
    if total_margin_rub is None or period_days is None or period_days <= 0:
        return None
    period_months = float(period_days) / DAYS_PER_MONTH
    if period_months <= 0:
        return None
    return float(total_margin_rub) / period_months


def compute_strategic_kpi(inputs: StrategicKpiInputs) -> StrategicKpiResult:
    annual_margin_per_cow = _annualised_margin_per_cow(
        inputs.total_margin_rub, inputs.cows_total, inputs.period_days
    )
    monthly_margin = _monthly_margin(inputs.total_margin_rub, inputs.period_days)

    roi_year_pct: Optional[float] = None
    roi_lifetime_pct: Optional[float] = None
    if annual_margin_per_cow is not None and inputs.acquisition_cost_rub_per_cow > 0:
        roi_year_pct = annual_margin_per_cow / inputs.acquisition_cost_rub_per_cow * 100.0
        if inputs.lifetime_years > 0:
            roi_lifetime_pct = (
                annual_margin_per_cow * inputs.lifetime_years
                / inputs.acquisition_cost_rub_per_cow
                * 100.0
            )

    payback: Optional[float] = None
    if (
        monthly_margin is not None
        and monthly_margin > 0
        and inputs.saas_cac_rub > 0
    ):
        payback = inputs.saas_cac_rub / monthly_margin

    ltv_cac: Optional[float] = None
    if (
        monthly_margin is not None
        and inputs.retention_months > 0
        and inputs.saas_cac_rub > 0
    ):
        ltv_rub = monthly_margin * inputs.retention_months
        if ltv_rub != 0:
            ltv_cac = ltv_rub / inputs.saas_cac_rub

    return StrategicKpiResult(
        roi_per_cow_per_year_pct=roi_year_pct,
        roi_per_cow_lifetime_pct=roi_lifetime_pct,
        payback_months=payback,
        ltv_cac_ratio=ltv_cac,
        margin_rub_per_cow_per_year=annual_margin_per_cow,
        monthly_margin_rub_per_farm=monthly_margin,
    )


__all__ = [
    "DAYS_PER_MONTH",
    "StrategicKpiInputs",
    "StrategicKpiResult",
    "compute_strategic_kpi",
]
