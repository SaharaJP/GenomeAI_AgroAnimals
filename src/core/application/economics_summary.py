"""Economics summary use-case.

Reads pen-day economics_v2 artifacts and produces an
:class:`EconomicsSummaryResponse` for the ``GET /api/economics/summary``
endpoint introduced in P2-1 RFC §3. Slice 2 covers KPI strip, revenue
breakdown, cost breakdown, and per-cow-day (when headcount is provided
via ``cows_total``). Sensitivity, unit-economics ladder and ROI of
actions are returned as defaults (None / empty) until phases §4.3,
§4.5 and roi_attribution wiring land in subsequent slices.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from packages.contracts import (
    EconomicsCost,
    EconomicsKpi,
    EconomicsPerCowDay,
    EconomicsPeriod,
    EconomicsRevenue,
    EconomicsScenariosSummary,
    EconomicsScope,
    EconomicsSummaryResponse,
)

_LEVELS = {"farm", "site", "pen"}

_FORMULA_REFS: dict[str, str] = {
    "revenue_milk_rub": "docs/target/economics_v2.md#L73",
    "cost_feed_rub": "docs/target/economics_v2.md#L74",
    "cost_vet_rub": "docs/target/economics_v2.md#L75",
    "cost_repro_rub": "docs/target/economics_v2.md#L76",
    "cost_cull_rub_or_revenue": "docs/target/economics_v2.md#L77",
    "total_cost_rub": "docs/target/economics_v2.md#L81",
    "margin_rub": "docs/target/economics_v2.md#L82",
    "cost_per_liter_rub": "docs/target/economics_v2.md#L83",
}


def _safe_pct(numerator: float, denominator: float) -> Optional[float]:
    if denominator <= 0:
        return None
    return float(numerator) / float(denominator) * 100.0


def _safe_div(numerator: float, denominator: float) -> Optional[float]:
    if denominator <= 0:
        return None
    return float(numerator) / float(denominator)


def _breakdown_pct(cost: EconomicsCost) -> dict[str, float]:
    total = cost.total_rub
    if total <= 0:
        return {}
    return {
        "feed": round(cost.feed_rub / total * 100.0, 1),
        "vet": round(cost.vet_rub / total * 100.0, 1),
        "repro": round(cost.repro_rub / total * 100.0, 1),
        "cull": round(cost.cull_rub / total * 100.0, 1),
        "other": round(cost.other_rub / total * 100.0, 1),
    }


def _sum_numeric(df: pd.DataFrame, columns: Iterable[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for col in columns:
        if col not in df.columns:
            out[col] = 0.0
            continue
        out[col] = float(pd.to_numeric(df[col], errors="coerce").fillna(0.0).sum())
    return out


def build_economics_summary_v1(
    *,
    artifacts_root: Path,
    tenant_id: str,
    level: str,
    data_version: str,
    economics_run: Optional[str] = None,
    farm_id: Optional[str] = None,
    site_id: Optional[str] = None,
    pen_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    cows_total: Optional[int] = None,
    scenarios_summary: Optional[EconomicsScenariosSummary] = None,
) -> EconomicsSummaryResponse:
    """Build summary from economics_v2 daily artifacts.

    ``cows_total`` lets the caller pass herd headcount for
    ``margin_per_cow_per_day_rub`` and the ``per_cow_day`` block. When
    omitted, those KPIs render as ``None`` and a warning is appended.
    """

    if level not in _LEVELS:
        raise ValueError(f"unsupported_level: expected one of {sorted(_LEVELS)}, got {level!r}")

    from genomeai.economics_v2 import load_economics_v2  # local import — only when endpoint hit

    rid, dfs, _run_dir = load_economics_v2(
        artifacts_root=Path(artifacts_root),
        data_version=str(data_version),
        economics_run=economics_run,
    )
    df = dfs.get("economics_daily")
    if df is None or df.empty:
        df = pd.DataFrame()

    warnings: list[str] = []

    if not df.empty:
        df = df[df["level"].astype(str) == level]
        df = df[df["tenant_id"].astype(str) == str(tenant_id)]
        if farm_id is not None:
            df = df[df["farm_id"].astype(str) == str(farm_id)]
        if site_id is not None and "site_id" in df.columns:
            df = df[df["site_id"].astype(str) == str(site_id)]
        if pen_id is not None and "pen_id" in df.columns:
            df = df[df["pen_id"].astype(str) == str(pen_id)]
        if date_from is not None:
            df = df[df["date"].astype(str) >= str(date_from)]
        if date_to is not None:
            df = df[df["date"].astype(str) <= str(date_to)]

    if df.empty:
        warnings.append(
            f"economics_v2_artifacts_empty_after_filters: level={level}, tenant_id={tenant_id}, "
            f"farm_id={farm_id}, site_id={site_id}, pen_id={pen_id}, "
            f"date_from={date_from}, date_to={date_to}"
        )

    sums = _sum_numeric(
        df,
        [
            "milk_kg",
            "milk_liters",
            "revenue_milk_rub",
            "revenue_cull_rub",
            "revenue_total_rub",
            "cost_feed_rub",
            "cost_vet_rub",
            "cost_repro_rub",
            "cost_cull_rub",
            "cost_other_rub",
            "total_cost_rub",
            "margin_rub",
        ],
    )

    revenue = EconomicsRevenue(
        milk_rub=sums["revenue_milk_rub"],
        cull_rub=sums["revenue_cull_rub"],
        total_rub=sums["revenue_total_rub"],
    )
    cost = EconomicsCost(
        feed_rub=sums["cost_feed_rub"],
        vet_rub=sums["cost_vet_rub"],
        repro_rub=sums["cost_repro_rub"],
        cull_rub=sums["cost_cull_rub"],
        other_rub=sums["cost_other_rub"],
        total_rub=sums["total_cost_rub"],
    )
    cost.breakdown_pct = _breakdown_pct(cost)

    margin_pct = _safe_pct(sums["margin_rub"], sums["revenue_total_rub"])
    cost_per_liter = _safe_div(sums["total_cost_rub"], sums["milk_liters"])

    if cows_total is not None and cows_total > 0:
        unique_dates = 0
        if not df.empty and "date" in df.columns:
            unique_dates = df["date"].astype(str).nunique()
        cow_days = float(cows_total) * float(unique_dates) if unique_dates > 0 else 0.0
        margin_per_cow_per_day = _safe_div(sums["margin_rub"], cow_days) if cow_days > 0 else None
        per_cow_day = EconomicsPerCowDay(
            revenue_rub=_safe_div(sums["revenue_total_rub"], cow_days) if cow_days > 0 else None,
            cost_rub=_safe_div(sums["total_cost_rub"], cow_days) if cow_days > 0 else None,
            margin_rub=margin_per_cow_per_day,
        )
    else:
        margin_per_cow_per_day = None
        per_cow_day = EconomicsPerCowDay()
        warnings.append(
            "per_cow_day_unavailable: cows_total not provided — per-cow KPIs render as null "
            "(see RFC §4 gap 4.5 for animal-allocation rules)"
        )

    kpi = EconomicsKpi(
        margin_per_cow_per_day_rub=margin_per_cow_per_day,
        total_margin_rub=sums["margin_rub"] if not df.empty else None,
        cost_per_liter_rub=cost_per_liter,
        margin_pct=margin_pct,
    )

    if df.empty and date_from is None and date_to is None:
        period_from = ""
        period_to = ""
    else:
        if not df.empty and "date" in df.columns:
            dates = df["date"].astype(str)
            period_from = date_from or str(dates.min())
            period_to = date_to or str(dates.max())
        else:
            period_from = date_from or ""
            period_to = date_to or ""

    scope = EconomicsScope(
        tenant_id=tenant_id,
        level=level,
        period=EconomicsPeriod(date_from=period_from, date_to=period_to),
        farm_id=farm_id,
        site_id=site_id,
        pen_id=pen_id,
        data_version=data_version,
        economics_run=rid,
    )

    return EconomicsSummaryResponse(
        scope=scope,
        kpi=kpi,
        revenue=revenue,
        cost=cost,
        per_cow_day=per_cow_day,
        scenarios_summary=scenarios_summary or EconomicsScenariosSummary(),
        formula_refs=dict(_FORMULA_REFS),
        warnings=warnings,
    )


__all__ = [
    "build_economics_summary_v1",
]
