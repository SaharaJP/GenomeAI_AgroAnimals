"""Statistical layer for impact analysis.

Provides Welch t-test, Cohen's d, and bootstrap confidence intervals
for diff-in-diff impact computations.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import numpy as np
from scipy import stats

# ---------------------------------------------------------------------------
# Demo data path (used for synthetic data fallback)
# ---------------------------------------------------------------------------
_DEMO_DATA = Path(__file__).parents[3] / "data" / "demo" / "investor_v1"


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class StatisticalImpactResult:
    # Diff-in-diff inputs
    treated_before: float
    treated_after: float
    control_before: float
    control_after: float
    diff_in_diff_effect: float

    # Statistics
    welch_t_pvalue: float
    cohen_d_effect_size: float
    effect_magnitude: Literal["negligible", "small", "medium", "large"]
    bootstrap_ci_95: tuple[float, float]

    # Verdict
    significance: Literal["significant", "not_significant", "inconclusive"]
    sample_sizes: dict  # {"treated": n, "control": n}

    # Analysis path — "diff_in_diff" when control present, "only_treated" otherwise
    analysis_type: Literal["diff_in_diff", "only_treated"] = "diff_in_diff"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    """d = (mean_a - mean_b) / pooled_std. Return 0.0 if both std=0."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    n_a, n_b = len(a), len(b)
    std_a = np.std(a, ddof=1) if n_a > 1 else 0.0
    std_b = np.std(b, ddof=1) if n_b > 1 else 0.0
    if std_a == 0.0 and std_b == 0.0:
        return 0.0
    pooled = np.sqrt(((n_a - 1) * std_a ** 2 + (n_b - 1) * std_b ** 2) / (n_a + n_b - 2))
    if pooled == 0.0:
        return 0.0
    return float((np.mean(a) - np.mean(b)) / pooled)


def _bootstrap_ci_diff(
    a: np.ndarray,
    b: np.ndarray,
    confidence: float = 0.95,
    n_bootstrap: int = 1000,
) -> tuple[float, float]:
    """CI for difference of means via bootstrap. Uses numpy.random.default_rng(seed=42)."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    rng = np.random.default_rng(seed=42)
    diffs = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        sample_a = rng.choice(a, size=len(a), replace=True)
        sample_b = rng.choice(b, size=len(b), replace=True)
        diffs[i] = np.mean(sample_a) - np.mean(sample_b)
    alpha = 1.0 - confidence
    lo = float(np.percentile(diffs, 100 * alpha / 2))
    hi = float(np.percentile(diffs, 100 * (1 - alpha / 2)))
    return (lo, hi)


def _classify_significance(
    p_value: float, n: int
) -> Literal["significant", "not_significant", "inconclusive"]:
    """n<7 or nan → inconclusive, p<0.05 → significant, otherwise not_significant."""
    if n < 7:
        return "inconclusive"
    if np.isnan(p_value):
        return "inconclusive"
    if p_value < 0.05:
        return "significant"
    return "not_significant"


def _magnitude_from_d(abs_d: float) -> str:
    """<0.2 → negligible, <0.5 → small, <0.8 → medium, >=0.8 → large."""
    if abs_d < 0.2:
        return "negligible"
    if abs_d < 0.5:
        return "small"
    if abs_d < 0.8:
        return "medium"
    return "large"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_WINDOW_DAYS_MAP: dict[str, int] = {"3d": 3, "1w": 7, "2w": 14, "4w": 28}


def compute_full_impact(
    farm_id: str,
    event_date: date,
    event_type: str,
    affected_groups: list[str],
    kpi_metric: str,
    window: Literal["3d", "1w", "2w", "4w"],
) -> StatisticalImpactResult:
    """Compute full statistical impact result for a farm event.

    Steps:
    1. Generate synthetic treated/control time-series arrays (or load demo data).
    2. Compute diff-in-diff.
    3. Apply Welch t-test.
    4. Compute Cohen's d.
    5. Bootstrap CI 95%.
    6. Return verdict.
    """
    n_days = _WINDOW_DAYS_MAP[window]
    seed = hash(f"{farm_id}{event_date}{event_type}{kpi_metric}") & 0xFFFFFFFF
    rng = np.random.default_rng(seed)

    n_treated = max(len(affected_groups), 15)
    n_control = max(n_treated * 3, 30)

    treated_before_arr = rng.normal(25.0, 5.0, (n_treated, n_days))
    treated_after_arr = rng.normal(26.5, 5.0, (n_treated, n_days))
    control_before_arr = rng.normal(25.0, 5.0, (n_control, n_days))
    control_after_arr = rng.normal(25.0, 5.0, (n_control, n_days))

    tb_mean = float(treated_before_arr.mean())
    ta_mean = float(treated_after_arr.mean())
    cb_mean = float(control_before_arr.mean())
    ca_mean = float(control_after_arr.mean())
    did = (ta_mean - tb_mean) - (ca_mean - cb_mean)

    # Per-animal means for Welch t-test
    ta_per_animal = treated_after_arr.mean(axis=1)   # shape: (n_treated,)
    ca_per_animal = control_after_arr.mean(axis=1)   # shape: (n_control,)

    # Welch t-test
    t_result = stats.ttest_ind(ta_per_animal, ca_per_animal, equal_var=False)
    p_value = float(t_result.pvalue)

    # Cohen's d
    d = _cohens_d(ta_per_animal, ca_per_animal)

    # Bootstrap CI
    ci = _bootstrap_ci_diff(ta_per_animal, ca_per_animal)

    # Significance verdict (use min of the two group sizes)
    n_min = min(n_treated, n_control)
    significance = _classify_significance(p_value, n_min)

    magnitude = _magnitude_from_d(abs(d))

    return StatisticalImpactResult(
        treated_before=tb_mean,
        treated_after=ta_mean,
        control_before=cb_mean,
        control_after=ca_mean,
        diff_in_diff_effect=did,
        welch_t_pvalue=p_value,
        cohen_d_effect_size=d,
        effect_magnitude=magnitude,  # type: ignore[arg-type]
        bootstrap_ci_95=ci,
        significance=significance,  # type: ignore[arg-type]
        sample_sizes={"treated": n_treated, "control": n_control},
        analysis_type="diff_in_diff",
    )


# ---------------------------------------------------------------------------
# Robust array-based API (handles NaN, small n, zero variance, no control)
# ---------------------------------------------------------------------------

def compute_impact_from_arrays(
    treated_before: "list[float] | np.ndarray",
    treated_after: "list[float] | np.ndarray",
    control_before: "list[float] | np.ndarray",
    control_after: "list[float] | np.ndarray",
    *,
    available_days: "int | None" = None,
    window_days: "int | None" = None,
) -> StatisticalImpactResult:
    """Compute statistical impact result from pre-aggregated per-animal arrays.

    Handles real-world data problems:
    - NaN values in any array are removed before any computation.
    - available_days < window_days truncates each array to available_days items.
    - n < 7 in the smaller group → significance='inconclusive', p-value=NaN.
    - Zero variance → cohen_d=0 (no divide-by-zero crash).
    - Empty (or all-NaN) control → analysis_type='only_treated', diff_in_diff=NaN.
    """
    _NAN = float("nan")

    def _clean(arr: "list[float] | np.ndarray") -> np.ndarray:
        a = np.asarray(arr, dtype=float)
        if available_days is not None and available_days < len(a):
            a = a[:available_days]
        return a[~np.isnan(a)]

    tb = _clean(treated_before)
    ta = _clean(treated_after)
    cb = _clean(control_before)
    ca = _clean(control_after)

    n_ta = len(ta)
    n_ca = len(ca)

    # No usable treated data → fully inconclusive
    if n_ta == 0:
        return StatisticalImpactResult(
            treated_before=float(np.mean(tb)) if len(tb) else _NAN,
            treated_after=_NAN,
            control_before=_NAN,
            control_after=_NAN,
            diff_in_diff_effect=_NAN,
            welch_t_pvalue=_NAN,
            cohen_d_effect_size=0.0,
            effect_magnitude="negligible",  # type: ignore[arg-type]
            bootstrap_ci_95=(_NAN, _NAN),
            significance="inconclusive",  # type: ignore[arg-type]
            sample_sizes={"treated": 0, "control": n_ca},
            analysis_type="diff_in_diff",
        )

    tb_mean = float(np.mean(tb)) if len(tb) else _NAN
    ta_mean = float(np.mean(ta))

    # No usable control data → only-treated analysis (no diff-in-diff)
    if n_ca == 0:
        n_min = n_ta
        if n_min < 7:
            significance: str = "inconclusive"
            p_value = _NAN
        else:
            t_result = stats.ttest_1samp(ta, popmean=tb_mean if not np.isnan(tb_mean) else ta_mean)
            p_value = float(t_result.pvalue)
            significance = _classify_significance(p_value, n_min)
        d = _cohens_d(ta, tb) if len(tb) else 0.0
        ci = _bootstrap_ci_diff(ta, tb) if len(tb) >= 2 else (_NAN, _NAN)
        return StatisticalImpactResult(
            treated_before=tb_mean,
            treated_after=ta_mean,
            control_before=_NAN,
            control_after=_NAN,
            diff_in_diff_effect=_NAN,
            welch_t_pvalue=p_value,
            cohen_d_effect_size=d,
            effect_magnitude=_magnitude_from_d(abs(d)),  # type: ignore[arg-type]
            bootstrap_ci_95=ci,
            significance=significance,  # type: ignore[arg-type]
            sample_sizes={"treated": n_ta, "control": 0},
            analysis_type="only_treated",
        )

    cb_mean = float(np.mean(cb)) if len(cb) else _NAN
    ca_mean = float(np.mean(ca))
    did = (ta_mean - tb_mean) - (ca_mean - cb_mean) if not (np.isnan(tb_mean) or np.isnan(cb_mean)) else _NAN

    # Small-n check (use min group size after NaN removal)
    n_min = min(n_ta, n_ca)
    if n_min < 7:
        return StatisticalImpactResult(
            treated_before=tb_mean,
            treated_after=ta_mean,
            control_before=cb_mean,
            control_after=ca_mean,
            diff_in_diff_effect=did,
            welch_t_pvalue=_NAN,
            cohen_d_effect_size=_cohens_d(ta, ca),
            effect_magnitude=_magnitude_from_d(abs(_cohens_d(ta, ca))),  # type: ignore[arg-type]
            bootstrap_ci_95=(_NAN, _NAN),
            significance="inconclusive",  # type: ignore[arg-type]
            sample_sizes={"treated": n_ta, "control": n_ca},
            analysis_type="diff_in_diff",
        )

    # Full diff-in-diff path
    ta_std = float(np.std(ta, ddof=1)) if len(ta) > 1 else 0.0
    ca_std = float(np.std(ca, ddof=1)) if len(ca) > 1 else 0.0
    if ta_std == 0.0 or ca_std == 0.0:
        p_value = _NAN
        significance = "inconclusive"
    else:
        t_result = stats.ttest_ind(ta, ca, equal_var=False)
        p_value = float(t_result.pvalue)
        significance = _classify_significance(p_value, n_min)
    d = _cohens_d(ta, ca)
    ci = _bootstrap_ci_diff(ta, ca)

    return StatisticalImpactResult(
        treated_before=tb_mean,
        treated_after=ta_mean,
        control_before=cb_mean,
        control_after=ca_mean,
        diff_in_diff_effect=did,
        welch_t_pvalue=p_value,
        cohen_d_effect_size=d,
        effect_magnitude=_magnitude_from_d(abs(d)),  # type: ignore[arg-type]
        bootstrap_ci_95=ci,
        significance=significance,  # type: ignore[arg-type]
        sample_sizes={"treated": n_ta, "control": n_ca},
        analysis_type="diff_in_diff",
    )
