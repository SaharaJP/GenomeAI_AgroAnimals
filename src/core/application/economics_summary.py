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

from core.economics.sensitivity import (
    SensitivityInputs,
    compute_breakeven_sensitivity,
)
from core.economics.strategic_kpi import (
    StrategicKpiInputs,
    compute_strategic_kpi,
)
from packages.contracts import (
    EconomicsCost,
    EconomicsKpi,
    EconomicsPerCowDay,
    EconomicsPeriod,
    EconomicsRevenue,
    EconomicsRoiAction,
    EconomicsScenariosSummary,
    EconomicsScope,
    EconomicsSensitivity,
    EconomicsStrategicKpi,
    EconomicsSummaryResponse,
    EconomicsUnitLadder,
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
    "sensitivity_method": "docs/iterations/T34-economics-rfc.md#5.1",
    "unit_economics_allocation": "docs/marts/unit_economics.md#allocation-methodology-rfc-45-gap-closure",
    "roi_actions_method": "docs/marts/roi_attribution.md",
    "strategic_kpi": "docs/target/economics_v2.md#стратегические-показатели-t34-p2-1-rfc-41-42",
}


_DEFAULT_STRATEGIC_CONFIG = {
    "acquisition_cost_rub_per_cow": 200_000.0,
    "saas_cac_rub": 135_000.0,
    "lifetime_years": 5.0,
    "retention_months": 60.0,
}


def _load_strategic_config(artifacts_root: Path) -> dict[str, float]:
    """Load strategic config block from configs/economics/economics_v2.yaml.

    Walks up from artifacts_root looking for a repo root that contains
    the config; falls back to compiled defaults if not found. Defaults
    track docs/target/economics_v2.md «Стратегические показатели».
    """

    import yaml

    candidate = Path(artifacts_root).resolve()
    cfg_path: Optional[Path] = None
    for _ in range(8):
        test = candidate / "configs" / "economics" / "economics_v2.yaml"
        if test.exists():
            cfg_path = test
            break
        if candidate.parent == candidate:
            break
        candidate = candidate.parent

    if cfg_path is None:
        cfg_path = Path(__file__).resolve().parents[3] / "configs" / "economics" / "economics_v2.yaml"

    if not cfg_path.exists():
        return dict(_DEFAULT_STRATEGIC_CONFIG)

    try:
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return dict(_DEFAULT_STRATEGIC_CONFIG)
    strategic = (raw.get("strategic") or {}) if isinstance(raw, dict) else {}
    merged = dict(_DEFAULT_STRATEGIC_CONFIG)
    for key in _DEFAULT_STRATEGIC_CONFIG:
        if key in strategic:
            try:
                merged[key] = float(strategic[key])
            except (TypeError, ValueError):
                pass
    return merged


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


def _build_roi_actions(
    *,
    artifacts_root: Path,
    tenant_id: str,
    data_version: str,
    farm_id: Optional[str],
    site_id: Optional[str],
    pen_id: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    top_n: int,
    warnings: list[str],
) -> list[EconomicsRoiAction]:
    """Read top-N actions from roi_attribution artifacts (RFC §3).

    Sorted by ``delta_margin_window_used`` desc. Returns an empty list
    plus a warning when no roi run exists yet — endpoint stays useful.
    """

    try:
        from genomeai.roi_attribution import load_roi  # local import
    except Exception as exc:  # pragma: no cover — defensive
        warnings.append(f"roi_module_unavailable: {exc!r}")
        return []

    try:
        _run_id, dfs, _run_dir = load_roi(
            artifacts_root=Path(artifacts_root),
            data_version=str(data_version),
        )
    except FileNotFoundError:
        warnings.append(
            "roi_actions_unavailable: no roi_attribution run found for data_version="
            f"{data_version} — run genomeai roi-attribution first"
        )
        return []

    df = dfs.get("actions")
    if df is None or df.empty:
        warnings.append("roi_actions_unavailable: actions table empty")
        return []

    if "tenant_id" in df.columns:
        df = df[df["tenant_id"].astype(str) == str(tenant_id)]
    if farm_id is not None:
        for col in ("farm_id", "object_id"):
            if col == "farm_id" and "farm_id" in df.columns:
                df = df[df["farm_id"].astype(str) == str(farm_id)]
                break
    if site_id is not None and "site_id" in df.columns:
        df = df[df["site_id"].astype(str) == str(site_id)]
    if pen_id is not None and "pen_id" in df.columns:
        df = df[df["pen_id"].astype(str) == str(pen_id)]
    if date_from is not None and "action_date" in df.columns:
        df = df[df["action_date"].astype(str) >= str(date_from)]
    if date_to is not None and "action_date" in df.columns:
        df = df[df["action_date"].astype(str) <= str(date_to)]

    if df.empty:
        warnings.append("roi_actions_unavailable: no actions after filters")
        return []

    delta_col = "delta_margin_window_used"
    if delta_col not in df.columns:
        warnings.append(f"roi_actions_unavailable: column {delta_col} missing")
        return []
    df = df.assign(_delta=pd.to_numeric(df[delta_col], errors="coerce"))
    df = df[df["_delta"].notna()]
    if df.empty:
        warnings.append("roi_actions_unavailable: all delta values invalid")
        return []

    top = df.sort_values("_delta", ascending=False).head(int(top_n))

    items: list[EconomicsRoiAction] = []
    for _, row in top.iterrows():
        per_day_raw = row.get("delta_margin_per_day_used")
        window_total_raw = row.get("delta_margin_window_used")
        try:
            window_days = int(pd.to_numeric(row.get("window_days"), errors="coerce"))
        except Exception:
            window_days = 14
        items.append(
            EconomicsRoiAction(
                action_id=str(row.get("action_id") or ""),
                label=str(row.get("action_type") or row.get("action_label") or row.get("object_id") or ""),
                cohort_n=1,  # roi_actions is per-action; cohort modelled at summary level
                window_days=window_days,
                delta_margin_per_cow_day_rub=float(per_day_raw) if pd.notna(per_day_raw) else None,
                total_margin_delta_rub=float(window_total_raw) if pd.notna(window_total_raw) else None,
                method=str(row.get("method") or "before_after"),
            )
        )
    return items


def _build_unit_economics_ladder(
    *,
    artifacts_root: Path,
    tenant_id: str,
    data_version: str,
    farm_id: Optional[str],
    site_id: Optional[str],
    pen_id: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    warnings: list[str],
) -> EconomicsUnitLadder:
    """Compute per-cow margin distribution from unit_economics artifacts.

    Returns defaults + appends a warning when the unit_economics
    manifest isn't found — the endpoint stays useful even before that
    pipeline has been run. Per-animal aggregation: mean(margin_rub)
    across the filtered date range, then 75 / 50 / 10 percentiles.
    """

    try:
        from genomeai.unit_economics import load_unit_economics  # local import
    except Exception as exc:  # pragma: no cover — defensive
        warnings.append(f"unit_economics_module_unavailable: {exc!r}")
        return EconomicsUnitLadder()

    try:
        _run_id, dfs, _run_dir = load_unit_economics(
            artifacts_root=Path(artifacts_root),
            data_version=str(data_version),
        )
    except FileNotFoundError:
        warnings.append(
            "unit_economics_ladder_unavailable: no unit_economics run found "
            f"for data_version={data_version} — run genomeai unit-economics first"
        )
        return EconomicsUnitLadder()

    df = dfs.get("animal_daily")
    if df is None or df.empty or "margin_rub" not in df.columns or "animal_id" not in df.columns:
        warnings.append("unit_economics_ladder_unavailable: animal_daily empty or missing columns")
        return EconomicsUnitLadder()

    df = df[df["tenant_id"].astype(str) == str(tenant_id)]
    if farm_id is not None and "farm_id" in df.columns:
        df = df[df["farm_id"].astype(str) == str(farm_id)]
    if site_id is not None and "site_id" in df.columns:
        df = df[df["site_id"].astype(str) == str(site_id)]
    if pen_id is not None and "pen_id" in df.columns:
        df = df[df["pen_id"].astype(str) == str(pen_id)]
    if date_from is not None and "date" in df.columns:
        df = df[df["date"].astype(str) >= str(date_from)]
    if date_to is not None and "date" in df.columns:
        df = df[df["date"].astype(str) <= str(date_to)]

    if df.empty:
        warnings.append("unit_economics_ladder_unavailable: no animal-day rows after filters")
        return EconomicsUnitLadder()

    margin_series = pd.to_numeric(df["margin_rub"], errors="coerce")
    per_animal = (
        df.assign(_m=margin_series)
        .groupby(df["animal_id"].astype(str), dropna=False)["_m"]
        .mean()
        .dropna()
    )
    if per_animal.empty:
        warnings.append("unit_economics_ladder_unavailable: zero animals after aggregation")
        return EconomicsUnitLadder()

    quantiles = per_animal.quantile([0.10, 0.50, 0.75])
    bottom_decile = float(quantiles.loc[0.10])
    median = float(quantiles.loc[0.50])
    top_quartile = float(quantiles.loc[0.75])
    bottom_cohort = per_animal[per_animal <= bottom_decile]

    return EconomicsUnitLadder(
        top_quartile_margin_rub=top_quartile,
        median_margin_rub=median,
        bottom_decile_margin_rub=bottom_decile,
        bottom_decile_cohort_n=int(bottom_cohort.size),
        bottom_decile_cohort_ref=f"worklist:culling_review:{data_version}",
    )


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
            "feed_dm_kg",
            "treatments_n",
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

    sensitivity_inputs = SensitivityInputs(
        revenue_total_rub=sums["revenue_total_rub"],
        revenue_cull_rub=sums["revenue_cull_rub"],
        total_cost_rub=sums["total_cost_rub"],
        cost_feed_rub=sums["cost_feed_rub"],
        cost_vet_rub=sums["cost_vet_rub"],
        cost_repro_rub=sums["cost_repro_rub"],
        cost_cull_rub=sums["cost_cull_rub"],
        cost_other_rub=sums["cost_other_rub"],
        milk_kg=sums["milk_kg"],
        feed_dm_kg=sums["feed_dm_kg"],
        treatments_n=sums["treatments_n"],
    )
    sensitivity_result = compute_breakeven_sensitivity(sensitivity_inputs)
    sensitivity = EconomicsSensitivity(
        milk_price_floor_rub_per_kg=sensitivity_result.milk_price_floor_rub_per_kg,
        feed_cost_ceiling_rub_per_kg_dm=sensitivity_result.feed_cost_ceiling_rub_per_kg_dm,
        vet_cost_ceiling_rub_per_event=sensitivity_result.vet_cost_ceiling_rub_per_event,
        method=sensitivity_result.method,
    )

    unit_ladder = _build_unit_economics_ladder(
        artifacts_root=Path(artifacts_root),
        tenant_id=tenant_id,
        data_version=data_version,
        farm_id=farm_id,
        site_id=site_id,
        pen_id=pen_id,
        date_from=date_from,
        date_to=date_to,
        warnings=warnings,
    )

    roi_actions = _build_roi_actions(
        artifacts_root=Path(artifacts_root),
        tenant_id=tenant_id,
        data_version=data_version,
        farm_id=farm_id,
        site_id=site_id,
        pen_id=pen_id,
        date_from=date_from,
        date_to=date_to,
        top_n=5,
        warnings=warnings,
    )

    strategic_cfg = _load_strategic_config(Path(artifacts_root))
    period_days: Optional[int] = None
    if not df.empty and "date" in df.columns:
        try:
            period_days = int(df["date"].astype(str).nunique())
        except Exception:
            period_days = None
    strategic_inputs = StrategicKpiInputs(
        total_margin_rub=kpi.total_margin_rub,
        cows_total=cows_total if cows_total and cows_total > 0 else None,
        period_days=period_days,
        acquisition_cost_rub_per_cow=strategic_cfg["acquisition_cost_rub_per_cow"],
        saas_cac_rub=strategic_cfg["saas_cac_rub"],
        lifetime_years=strategic_cfg["lifetime_years"],
        retention_months=strategic_cfg["retention_months"],
    )
    strategic_result = compute_strategic_kpi(strategic_inputs)
    if strategic_result.roi_per_cow_per_year_pct is None and (cows_total is None or cows_total <= 0):
        warnings.append(
            "strategic_kpi_unavailable: cows_total not provided — ROI per cow renders as null"
        )
    if strategic_result.payback_months is None and kpi.total_margin_rub is not None and kpi.total_margin_rub <= 0:
        warnings.append("payback_negative_margin: monthly margin <= 0, payback is undefined")
    strategic_kpi_block = EconomicsStrategicKpi(
        roi_per_cow_per_year_pct=strategic_result.roi_per_cow_per_year_pct,
        roi_per_cow_lifetime_pct=strategic_result.roi_per_cow_lifetime_pct,
        payback_months=strategic_result.payback_months,
        ltv_cac_ratio=strategic_result.ltv_cac_ratio,
        acquisition_cost_rub_per_cow=strategic_cfg["acquisition_cost_rub_per_cow"],
        saas_cac_rub=strategic_cfg["saas_cac_rub"],
        lifetime_years=strategic_cfg["lifetime_years"],
        retention_months=strategic_cfg["retention_months"],
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
        sensitivity=sensitivity,
        unit_economics_ladder=unit_ladder,
        roi_actions=roi_actions,
        strategic_kpi=strategic_kpi_block,
        scenarios_summary=scenarios_summary or EconomicsScenariosSummary(),
        formula_refs=dict(_FORMULA_REFS),
        warnings=warnings,
    )


__all__ = [
    "build_economics_summary_v1",
]
