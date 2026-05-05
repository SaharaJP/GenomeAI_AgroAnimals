"""KPI Bridge — facade between kpi_v2 computation engine and web_cabinet UI.

Isolates the UI from internal kpi_v2 details. Does NOT duplicate KPI computation.
"""
from __future__ import annotations

from web_cabinet.analytics.cache import cached

import math
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal, Optional

# ---------------------------------------------------------------------------
# In-process TTL cache — collapses repeated tab/brief calls into one run_kpi()
# ---------------------------------------------------------------------------
_CACHE_TTL = 300  # seconds (5 min)
_kpi_cache: dict[tuple, tuple] = {}  # key -> (DashboardKPI, expiry_monotonic)
_kpi_lock = threading.Lock()


def _cache_key(farm_id: str, as_of: date, input_dir_str: str) -> tuple:
    return (farm_id, as_of.isoformat(), input_dir_str)


def invalidate_kpi_cache(farm_id: str, as_of: date, input_dir_str: str) -> None:
    """Remove a single entry from the KPI cache (call after write events)."""
    with _kpi_lock:
        _kpi_cache.pop(_cache_key(farm_id, as_of, input_dir_str), None)


VALID_TABS: frozenset[str] = frozenset(
    {"production", "reproduction", "health", "feed", "finance", "herd", "behavior"}
)

import pandas as pd

# Default fixture path (relative to repo root, resolved at call time)
_FIXTURES_DIR = Path(__file__).parents[3] / "data" / "fixtures" / "target_v2"


@dataclass
class DashboardKPI:
    farm_id: str
    as_of: date
    # Production
    avg_milk_yield_kg: Optional[float]
    ecm_kg: Optional[float]
    fat_pct: Optional[float]
    protein_pct: Optional[float]
    scc_bulk_k: Optional[float]
    # Reproduction
    pregnancy_rate_21d_pct: Optional[float]
    days_open_avg: Optional[float]
    # Health
    cows_in_treatment: Optional[int]
    mastitis_incidence_pct_per_year: Optional[float]
    # Meta
    confidence: Literal["high", "medium", "low"]
    sample_size_cows: int
    raw_kpi_long: Optional[pd.DataFrame] = field(default=None, repr=False)


def _get_kpi(df: pd.DataFrame, kpi_id: str, farm_id: str) -> Optional[float]:
    """Extract a single KPI value for the given farm from a kpi_long DataFrame."""
    if df.empty:
        return None
    sub = df[(df["kpi_id"] == kpi_id) & (df["farm_id"] == farm_id)]
    if sub.empty:
        return None
    val = pd.to_numeric(sub["value"].iloc[0], errors="coerce")
    return None if (val is None or (isinstance(val, float) and math.isnan(val))) else float(val)


def _compute_confidence(
    avg_milk: Optional[float],
    fat_pct: Optional[float],
    protein_pct: Optional[float],
    sample_size: int,
) -> Literal["high", "medium", "low"]:
    if sample_size < 5:
        return "low"
    present = sum(v is not None for v in [avg_milk, fat_pct, protein_pct])
    if sample_size >= 30 and present >= 2:
        return "high"
    if present >= 1:
        return "medium"
    return "low"


def _compute_dashboard_kpi_uncached(
    farm_id: str,
    as_of: date,
    *,
    period_days: int = 7,
    input_dir: Optional[Path] = None,
) -> DashboardKPI:
    from genomeai.kpi_v2 import run_kpi  # lazy import — kpi_v2 is heavy

    resolved_input = input_dir or _FIXTURES_DIR

    with tempfile.TemporaryDirectory(prefix="kpi_bridge_") as tmp:
        artifacts_root = Path(tmp) / "artifacts"
        result = run_kpi(
            data_version="bridge",
            asof_date=as_of.isoformat(),
            artifacts_root=artifacts_root,
            input_dir=resolved_input,
        )
        kpi_long_path = Path(result["kpi_dir"]) / "kpi_long.csv"
        if kpi_long_path.exists():
            kpi_long = pd.read_csv(kpi_long_path)
        else:
            kpi_long = pd.DataFrame()

    sample_size = 0
    if not kpi_long.empty:
        farm_rows = kpi_long[kpi_long["farm_id"] == farm_id]
        sample_size = int(farm_rows.shape[0])

    avg_milk = _get_kpi(kpi_long, "milk_avg_kg_per_cow_1d", farm_id)
    fat_pct = _get_kpi(kpi_long, "fat_pct_avg_7d", farm_id)
    protein_pct = _get_kpi(kpi_long, "protein_pct_avg_7d", farm_id)

    scc_raw = _get_kpi(kpi_long, "scc_avg_7d", farm_id)
    scc_bulk_k = (scc_raw / 1000.0) if scc_raw is not None else None

    mast_30d = _get_kpi(kpi_long, "mastitis_events_30d", farm_id)
    mastitis_pct_year: Optional[float] = None
    if mast_30d is not None and sample_size > 0:
        mastitis_pct_year = round(mast_30d / sample_size * 12 * 100, 1)

    severe = _get_kpi(kpi_long, "severe_health_events_30d", farm_id)
    cows_in_treatment = int(round(severe)) if severe is not None else None

    confidence = _compute_confidence(avg_milk, fat_pct, protein_pct, sample_size)

    farm_rows_df: Optional[pd.DataFrame] = None
    if not kpi_long.empty:
        farm_subset = kpi_long[kpi_long["farm_id"] == farm_id]
        if not farm_subset.empty:
            farm_rows_df = farm_subset.reset_index(drop=True)

    return DashboardKPI(
        farm_id=farm_id,
        as_of=as_of,
        avg_milk_yield_kg=avg_milk,
        ecm_kg=None,  # ECM not computed in kpi_v2; placeholder for Week 4
        fat_pct=fat_pct,
        protein_pct=protein_pct,
        scc_bulk_k=scc_bulk_k,
        pregnancy_rate_21d_pct=None,  # requires insem/preg ratio; not in kpi_v2 yet
        days_open_avg=None,           # requires calving/conception dates; not in kpi_v2 yet
        cows_in_treatment=cows_in_treatment,
        mastitis_incidence_pct_per_year=mastitis_pct_year,
        confidence=confidence,
        sample_size_cows=sample_size,
        raw_kpi_long=farm_rows_df,
    )


def compute_dashboard_kpi(
    farm_id: str,
    as_of: date,
    *,
    period_days: int = 7,
    input_dir: Optional[Path] = None,
) -> DashboardKPI:
    """KPI snapshot for UI Dashboard. Second call with same args returns cached result.

    Validation runs before the cache so an empty farm_id always raises.
    """
    if not farm_id:
        raise ValueError("farm_id must not be empty")
    return _compute_dashboard_kpi_cached(
        farm_id, as_of, period_days=period_days, input_dir=input_dir
    )


def _compute_dashboard_kpi_cached(
    farm_id: str,
    as_of: date,
    *,
    period_days: int = 7,
    input_dir: Optional[Path] = None,
) -> DashboardKPI:
    key = _cache_key(farm_id, as_of, str(input_dir or _FIXTURES_DIR))
    now = time.monotonic()
    with _kpi_lock:
        entry = _kpi_cache.get(key)
        if entry is not None:
            cached_result, expiry = entry
            if now < expiry:
                return cached_result
    result = _compute_dashboard_kpi_uncached(
        farm_id, as_of, period_days=period_days, input_dir=input_dir
    )
    with _kpi_lock:
        _kpi_cache[key] = (result, now + _CACHE_TTL)
    return result


# ---------------------------------------------------------------------------
# Tab KPI — per-tab facade for the analytics dashboard
# ---------------------------------------------------------------------------

@dataclass
class TabKPIData:
    tab_name: str
    farm_id: str
    as_of: date
    metrics: dict[str, Any]
    confidence: Literal["high", "medium", "low"]
    sample_size_cows: int


def _kpi_to_tab_metrics(kpi: DashboardKPI, tab_name: str) -> dict[str, Any]:
    if tab_name == "production":
        return {
            "avg_milk_yield_kg": kpi.avg_milk_yield_kg,
            "ecm_kg": kpi.ecm_kg,
            "fat_pct": kpi.fat_pct,
            "protein_pct": kpi.protein_pct,
            "scc_bulk_k": kpi.scc_bulk_k,
        }
    if tab_name == "reproduction":
        return {
            "pregnancy_rate_21d_pct": kpi.pregnancy_rate_21d_pct,
            "days_open_avg": kpi.days_open_avg,
        }
    if tab_name == "health":
        return {
            "cows_in_treatment": kpi.cows_in_treatment,
            "mastitis_incidence_pct_per_year": kpi.mastitis_incidence_pct_per_year,
        }
    # feed, finance, herd, behavior — not yet in kpi_v2; return empty metrics
    return {}


def compute_tab_kpi(
    farm_id: str,
    as_of: date,
    tab_name: str,
    *,
    input_dir: Optional[Path] = None,
) -> TabKPIData:
    """Computes KPI snapshot for a specific analytics dashboard tab.

    Delegates to compute_dashboard_kpi() and projects to tab-specific fields.
    Tabs feed/finance/herd/behavior return empty metrics until kpi_v2 supports them.
    """
    if tab_name not in VALID_TABS:
        raise ValueError(f"Unknown tab: {tab_name!r}. Valid: {sorted(VALID_TABS)}")
    kpi = compute_dashboard_kpi(farm_id, as_of, input_dir=input_dir)
    return TabKPIData(
        tab_name=tab_name,
        farm_id=farm_id,
        as_of=as_of,
        metrics=_kpi_to_tab_metrics(kpi, tab_name),
        confidence=kpi.confidence,
        sample_size_cows=kpi.sample_size_cows,
    )
