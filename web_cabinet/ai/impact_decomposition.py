"""§3.2.2 additive decomposition K(t) = T(t) + S(t) + E(t) + ε(t).

Used to remove linear trend and calendar-day seasonality from a KPI
time series before running Welch t-test on pre/post event windows.
The residual E(t) carries the event-attributable signal (formula 3.8
in the diploma): ΔK_adj = mean(post_residual) − mean(pre_residual).

Trend is estimated by OLS on data **outside** the event window.
Seasonality is estimated as the per-calendar-day mean deviation from
the global mean across **prior** years; if history span < 365 days,
the seasonal component is empty (treated as 0 per brief §P3-1).
"""
from __future__ import annotations

import datetime
from typing import Iterable, Optional

import numpy as np


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------

def estimate_trend(
    values: Iterable[float],
    dates: Iterable[datetime.date],
    *,
    exclude_window: Optional[tuple[datetime.date, datetime.date]] = None,
) -> tuple[float, float]:
    """OLS linear trend `T̂(t) = a + b·t` on (date, value) pairs outside the
    event window. Returns (a, b). If <3 points remain, falls back to
    (mean_of_full_series, 0.0)."""
    values_arr = np.asarray(list(values), dtype=float)
    dates_list = list(dates)
    if values_arr.size == 0:
        return (0.0, 0.0)

    if exclude_window is not None:
        start, end = exclude_window
        mask = np.array([(d < start) or (d > end) for d in dates_list], dtype=bool)
    else:
        mask = np.ones_like(values_arr, dtype=bool)

    valid = mask & ~np.isnan(values_arr)
    if valid.sum() < 3:
        global_mean = float(np.nanmean(values_arr)) if np.any(~np.isnan(values_arr)) else 0.0
        return (global_mean, 0.0)

    epoch = dates_list[0].toordinal()
    t = np.array([d.toordinal() - epoch for d in dates_list], dtype=float)
    b, a = np.polyfit(t[valid], values_arr[valid], 1)  # polyfit returns highest-deg first
    return (float(a), float(b))


def _trend_predict(
    a: float, b: float,
    dates: list[datetime.date],
    *,
    epoch: Optional[int] = None,
) -> np.ndarray:
    """Predict trend at given dates. The epoch must match the one used
    by estimate_trend (first date of the original series). When None,
    the first date in `dates` is used — caller must guarantee alignment."""
    if not dates:
        return np.array([], dtype=float)
    if epoch is None:
        epoch = dates[0].toordinal()
    t = np.array([d.toordinal() - epoch for d in dates], dtype=float)
    return a + b * t


# ---------------------------------------------------------------------------
# Seasonality
# ---------------------------------------------------------------------------

def estimate_seasonality(
    values: Iterable[float],
    dates: Iterable[datetime.date],
    *,
    today: Optional[datetime.date] = None,
) -> dict[tuple[int, int], float]:
    """Per-calendar-day mean deviation from global mean across prior years.

    Key: (month, day) tuple — independent of year. Returns empty dict if
    the history span is less than 365 days (no prior-year reference).
    """
    values_arr = np.asarray(list(values), dtype=float)
    dates_list = list(dates)
    if values_arr.size == 0 or not dates_list:
        return {}

    span_days = (max(dates_list) - min(dates_list)).days
    if span_days < 365:
        return {}

    global_mean = float(np.nanmean(values_arr))
    if np.isnan(global_mean):
        return {}

    today = today or max(dates_list)
    out: dict[tuple[int, int], list[float]] = {}
    for d, v in zip(dates_list, values_arr):
        if np.isnan(v):
            continue
        if d >= today.replace(year=today.year):
            # Only include strictly prior dates (any year up to and including today)
            pass
        key = (d.month, d.day)
        out.setdefault(key, []).append(float(v) - global_mean)

    return {k: float(np.mean(vs)) for k, vs in out.items() if vs}


def _seasonal_predict(
    seasonality: dict[tuple[int, int], float],
    dates: list[datetime.date],
) -> np.ndarray:
    if not seasonality:
        return np.zeros(len(dates), dtype=float)
    return np.array(
        [seasonality.get((d.month, d.day), 0.0) for d in dates],
        dtype=float,
    )


# ---------------------------------------------------------------------------
# Adjusted delta + Welch-ready arrays
# ---------------------------------------------------------------------------

def _date_window(
    dates: list[datetime.date],
    values: np.ndarray,
    start: datetime.date,
    end: datetime.date,
) -> tuple[list[datetime.date], np.ndarray]:
    """Return (dates, values) within [start, end] inclusive."""
    out_dates: list[datetime.date] = []
    out_idx: list[int] = []
    for i, d in enumerate(dates):
        if start <= d <= end:
            out_dates.append(d)
            out_idx.append(i)
    return out_dates, values[np.array(out_idx, dtype=int)] if out_idx else np.array([], dtype=float)


def _full_residuals(
    values_arr: np.ndarray,
    dates_list: list[datetime.date],
    *,
    exclude_window: tuple[datetime.date, datetime.date],
) -> tuple[np.ndarray, tuple[float, float], dict]:
    """Compute residuals on the full series using a single trend epoch.

    Returns (residuals, (a,b), seasonality). Caller indexes pre/post windows
    from the residuals array to keep epoch alignment between fit and predict.
    """
    a, b = estimate_trend(values_arr, dates_list, exclude_window=exclude_window)
    seasonality = estimate_seasonality(values_arr, dates_list)
    epoch = dates_list[0].toordinal() if dates_list else 0
    trend_pred = _trend_predict(a, b, dates_list, epoch=epoch)
    seasonal_pred = _seasonal_predict(seasonality, dates_list)
    residuals = values_arr - trend_pred - seasonal_pred
    return residuals, (a, b), seasonality


def compute_adjusted_delta(
    values: Iterable[float],
    dates: Iterable[datetime.date],
    event_date: datetime.date,
    *,
    window_days: int = 14,
) -> dict:
    """Formula 3.8: ΔK_adj = mean(post_resid) − mean(pre_resid)."""
    values_arr = np.asarray(list(values), dtype=float)
    dates_list = list(dates)
    pre_start = event_date - datetime.timedelta(days=window_days)
    pre_end = event_date - datetime.timedelta(days=1)
    post_start = event_date + datetime.timedelta(days=1)
    post_end = event_date + datetime.timedelta(days=window_days)

    residuals, (a, b), seasonality = _full_residuals(
        values_arr, dates_list, exclude_window=(pre_start, post_end),
    )

    pre_idx = [i for i, d in enumerate(dates_list) if pre_start <= d <= pre_end]
    post_idx = [i for i, d in enumerate(dates_list) if post_start <= d <= post_end]
    pre_residual = residuals[pre_idx] if pre_idx else np.array([], dtype=float)
    post_residual = residuals[post_idx] if post_idx else np.array([], dtype=float)
    pre_residual = pre_residual[~np.isnan(pre_residual)]
    post_residual = post_residual[~np.isnan(post_residual)]

    pre_mean = float(np.mean(pre_residual)) if pre_residual.size else float("nan")
    post_mean = float(np.mean(post_residual)) if post_residual.size else float("nan")
    delta = post_mean - pre_mean if not (np.isnan(pre_mean) or np.isnan(post_mean)) else float("nan")

    return {
        "pre_mean":      pre_mean,
        "post_mean":     post_mean,
        "delta":         delta,
        "trend":         (a, b),
        "seasonal_keys": len(seasonality),
        "n_pre":         int(pre_residual.size),
        "n_post":        int(post_residual.size),
    }


def decompose_for_welch(
    values: Iterable[float],
    dates: Iterable[datetime.date],
    event_date: datetime.date,
    *,
    window_days: int = 14,
) -> tuple[np.ndarray, np.ndarray]:
    """Wire-ready output: trend+seasonal-subtracted (pre, post) arrays
    for direct feed into scipy.stats.ttest_ind(equal_var=False)."""
    values_arr = np.asarray(list(values), dtype=float)
    dates_list = list(dates)
    pre_start = event_date - datetime.timedelta(days=window_days)
    pre_end = event_date - datetime.timedelta(days=1)
    post_start = event_date + datetime.timedelta(days=1)
    post_end = event_date + datetime.timedelta(days=window_days)

    residuals, _, _ = _full_residuals(
        values_arr, dates_list, exclude_window=(pre_start, post_end),
    )
    pre_idx = [i for i, d in enumerate(dates_list) if pre_start <= d <= pre_end]
    post_idx = [i for i, d in enumerate(dates_list) if post_start <= d <= post_end]
    pre_resid = residuals[pre_idx] if pre_idx else np.array([], dtype=float)
    post_resid = residuals[post_idx] if post_idx else np.array([], dtype=float)
    return pre_resid[~np.isnan(pre_resid)], post_resid[~np.isnan(post_resid)]
