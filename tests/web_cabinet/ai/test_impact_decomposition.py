"""Acceptance: §3.2.2 K(t)=T+S+E+ε decomposition before Welch."""
from __future__ import annotations

import datetime
import numpy as np
import pytest

from web_cabinet.ai.impact_decomposition import (
    estimate_trend,
    estimate_seasonality,
    compute_adjusted_delta,
    decompose_for_welch,
    _trend_predict,
    _seasonal_predict,
)


# ── trend ────────────────────────────────────────────────────────────────


def _date_range(start: datetime.date, n: int) -> list[datetime.date]:
    return [start + datetime.timedelta(days=i) for i in range(n)]


def test_estimate_trend_recovers_known_slope():
    """y = 2 + 0.5·t on 60 days → a≈2, b≈0.5."""
    dates = _date_range(datetime.date(2025, 11, 1), 60)
    values = [2.0 + 0.5 * i for i in range(60)]
    a, b = estimate_trend(values, dates)
    assert abs(a - 2.0) < 1e-9
    assert abs(b - 0.5) < 1e-9


def test_estimate_trend_excludes_event_window():
    """Inject sharp drop inside the window; trend on outer data is unaffected."""
    dates = _date_range(datetime.date(2025, 11, 1), 60)
    values = [2.0 + 0.5 * i for i in range(60)]
    # Inject a -10 anomaly inside days 25..34 (window 30±5)
    for i in range(25, 35):
        values[i] -= 10.0
    event_date = datetime.date(2025, 11, 1) + datetime.timedelta(days=30)
    pre_start = event_date - datetime.timedelta(days=5)
    post_end = event_date + datetime.timedelta(days=4)
    a, b = estimate_trend(values, dates, exclude_window=(pre_start, post_end))
    # Outer data is clean → coefficients stay near (2, 0.5)
    assert abs(a - 2.0) < 0.5
    assert abs(b - 0.5) < 0.05


def test_estimate_trend_falls_back_when_too_few_points():
    """≤2 points outside window → (mean, 0.0)."""
    dates = _date_range(datetime.date(2025, 11, 1), 5)
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    # Exclude all but 2
    a, b = estimate_trend(
        values, dates,
        exclude_window=(dates[1], dates[3]),  # excludes 3 of 5 → 2 left
    )
    assert b == 0.0
    assert abs(a - 30.0) < 1e-9  # mean of full series


def test_estimate_trend_handles_empty_input():
    a, b = estimate_trend([], [])
    assert (a, b) == (0.0, 0.0)


# ── seasonality ──────────────────────────────────────────────────────────


def test_estimate_seasonality_empty_for_short_history():
    """6 months of data → returns {}."""
    dates = _date_range(datetime.date(2025, 11, 1), 180)
    values = [25.0] * 180
    s = estimate_seasonality(values, dates)
    assert s == {}


def test_estimate_seasonality_non_empty_for_2_year_history():
    """≥365 days span → seasonal dict non-empty (calendar-day keys)."""
    dates = _date_range(datetime.date(2024, 1, 1), 730)  # 2 years
    # Add weekly oscillation
    values = [25.0 + 2.0 * np.sin(2 * np.pi * i / 7) for i in range(730)]
    s = estimate_seasonality(values, dates)
    assert len(s) > 0
    # All keys are (month, day) tuples
    for k in s:
        assert isinstance(k, tuple) and len(k) == 2
        assert 1 <= k[0] <= 12
        assert 1 <= k[1] <= 31


def test_estimate_seasonality_handles_empty_input():
    assert estimate_seasonality([], []) == {}


# ── adjusted delta ───────────────────────────────────────────────────────


def test_compute_adjusted_delta_subtracts_trend():
    """Linear ramp + temporary post-event drop (recovers after window) → adjusted_delta ≈ drop, raw delta is much smaller because the trend offsets it."""
    dates = _date_range(datetime.date(2025, 11, 1), 60)
    # Days 0..29: trend; 30..44: trend − 5 (event window only); 45..59: back on trend
    values = [25.0 + 0.1 * i for i in range(60)]
    drop = 5.0
    for i in range(30, 45):
        values[i] -= drop

    event_date = datetime.date(2025, 11, 1) + datetime.timedelta(days=30)
    result = compute_adjusted_delta(values, dates, event_date, window_days=14)

    # Adjusted delta recovers the true drop (within 0.1 kg — clean synthetic)
    assert result["delta"] < 0
    assert abs(result["delta"] + drop) < 0.1

    # Raw delta is masked by the +0.1·30 ≈ +3 kg trend ramp
    raw_pre_mean = float(np.mean(values[16:30]))
    raw_post_mean = float(np.mean(values[31:45]))
    raw_delta = raw_post_mean - raw_pre_mean
    # Decomposition recovers an additional ~1.5 kg of magnitude (the trend ramp)
    assert abs(result["delta"]) > abs(raw_delta) + 1.0

    assert result["n_pre"] == 14
    assert result["n_post"] == 14


def test_compute_adjusted_delta_returns_trend_coeffs():
    dates = _date_range(datetime.date(2025, 11, 1), 60)
    values = [25.0 + 0.1 * i for i in range(60)]
    event_date = datetime.date(2025, 11, 1) + datetime.timedelta(days=30)
    result = compute_adjusted_delta(values, dates, event_date, window_days=14)
    a, b = result["trend"]
    assert b > 0.05  # captures the ramp
    assert result["seasonal_keys"] == 0  # short history


# ── Welch-ready arrays ───────────────────────────────────────────────────


def test_decompose_for_welch_returns_residual_arrays():
    dates = _date_range(datetime.date(2025, 11, 1), 60)
    values = [25.0 + 0.1 * i for i in range(60)]
    event_date = datetime.date(2025, 11, 1) + datetime.timedelta(days=30)

    pre_resid, post_resid = decompose_for_welch(values, dates, event_date, window_days=14)
    assert isinstance(pre_resid, np.ndarray)
    assert isinstance(post_resid, np.ndarray)
    assert pre_resid.shape == (14,)
    assert post_resid.shape == (14,)


def test_decompose_for_welch_residuals_centered_after_detrend():
    """A pure linear trend with no event should give residuals close to 0."""
    dates = _date_range(datetime.date(2025, 11, 1), 60)
    values = [25.0 + 0.5 * i for i in range(60)]  # pure trend, no event
    event_date = datetime.date(2025, 11, 1) + datetime.timedelta(days=30)
    pre, post = decompose_for_welch(values, dates, event_date, window_days=14)
    assert abs(float(np.mean(pre))) < 0.5
    assert abs(float(np.mean(post))) < 0.5
