"""Tests for statistical robustness edge cases (T34).

Edge cases covered:
1. n < 7 in both groups → significance = "inconclusive", no fake p-value
2. NaN in treated_after / control_after → filtered before t-test
3. All values identical (variance = 0) → cohen_d = 0
4. control group empty → only_treated_analysis (no diff-in-diff)
5. Window bigger than available history → truncate to available
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) in sys.path:
    sys.path.remove(str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT))

for _k in list(sys.modules):
    if _k == "web_cabinet" or _k.startswith("web_cabinet."):
        del sys.modules[_k]

import numpy as np
import pytest

from web_cabinet.analytics.statistical_extension import compute_impact_from_arrays


# ---------------------------------------------------------------------------
# Edge case 1: small n → inconclusive
# ---------------------------------------------------------------------------

class TestSmallN:
    def test_both_groups_under_7_returns_inconclusive(self):
        """n=3 in both groups → significance='inconclusive', p-value=NaN."""
        tb = [24.0, 25.0, 23.5]
        ta = [25.0, 26.0, 24.5]
        cb = [24.0, 25.0, 23.5]
        ca = [24.0, 25.0, 23.5]
        result = compute_impact_from_arrays(tb, ta, cb, ca)
        assert result.significance == "inconclusive"
        assert math.isnan(result.welch_t_pvalue)

    def test_treated_under_7_even_with_large_control_is_inconclusive(self):
        """treated n=4, control n=20 → inconclusive (min group < 7)."""
        tb = [24.0, 25.0, 24.0, 23.0]
        ta = [25.0, 26.0, 24.5, 23.0]
        rng = np.random.default_rng(42)
        cb = list(rng.normal(25, 3, 20))
        ca = list(rng.normal(25, 3, 20))
        result = compute_impact_from_arrays(tb, ta, cb, ca)
        assert result.significance == "inconclusive"

    def test_exactly_7_uses_pvalue_not_n_threshold(self):
        """n==7 in both groups → significance determined by p-value."""
        rng = np.random.default_rng(0)
        tb = list(rng.normal(25, 2, 7))
        ta = list(rng.normal(30, 2, 7))  # large effect
        cb = list(rng.normal(25, 2, 7))
        ca = list(rng.normal(25, 2, 7))
        result = compute_impact_from_arrays(tb, ta, cb, ca)
        assert result.significance in ("significant", "not_significant")


# ---------------------------------------------------------------------------
# Edge case 2: NaN filtering
# ---------------------------------------------------------------------------

class TestNaNFiltering:
    def test_nan_in_treated_after_filtered(self):
        """NaN entries in treated_after removed; sample_sizes reflects cleaned count."""
        tb = [24.0] * 8
        ta = [25.0, float("nan"), 26.0, float("nan"), 27.0, 25.5, 26.5, 25.0]  # 6 valid
        cb = [24.0] * 10
        ca = list(np.random.default_rng(1).normal(25, 2, 10))
        result = compute_impact_from_arrays(tb, ta, cb, ca)
        assert result.sample_sizes["treated"] == 6
        assert not math.isnan(result.treated_after)

    def test_nan_in_control_after_filtered(self):
        """NaN entries in control_after removed; sample_sizes reflects cleaned count."""
        rng = np.random.default_rng(2)
        tb = list(rng.normal(25, 2, 10))
        ta = list(rng.normal(26, 2, 10))
        cb = [24.0] * 10
        ca = [25.0, float("nan"), 24.5, float("nan"), 25.5, 24.0, 25.0, 24.5, 25.0, 24.0]  # 8 valid
        result = compute_impact_from_arrays(tb, ta, cb, ca)
        assert result.sample_sizes["control"] == 8
        assert not math.isnan(result.control_after)

    def test_all_nan_treated_after_is_inconclusive(self):
        """All-NaN treated_after → inconclusive after filtering yields n=0."""
        tb = [25.0] * 5
        ta = [float("nan")] * 5
        cb = [24.0] * 10
        ca = list(np.random.default_rng(3).normal(25, 2, 10))
        result = compute_impact_from_arrays(tb, ta, cb, ca)
        assert result.significance == "inconclusive"

    def test_nan_before_filtered_for_means(self):
        """NaN entries in treated_before / control_before filtered for mean computation."""
        tb = [24.0, float("nan"), 25.0, float("nan"), 24.5, 23.5, 25.5, 24.0]  # 6 valid
        ta = [25.0, 26.0, 25.5, 24.5, 26.5, 25.0, 26.0, 25.5]
        cb = [24.0] * 8
        ca = [25.0] * 8
        result = compute_impact_from_arrays(tb, ta, cb, ca)
        # treated_before mean should use only 6 non-NaN values
        expected_mean = np.mean([24.0, 25.0, 24.5, 23.5, 25.5, 24.0])
        assert result.treated_before == pytest.approx(expected_mean, abs=1e-9)


# ---------------------------------------------------------------------------
# Edge case 3: zero variance
# ---------------------------------------------------------------------------

class TestZeroVariance:
    def test_identical_treated_values_cohen_d_zero(self):
        """All treated_after identical → cohen_d=0, magnitude='negligible'."""
        tb = [25.0] * 10
        ta = [25.0] * 10  # zero variance
        cb = [24.0] * 10
        ca = [24.0] * 10
        result = compute_impact_from_arrays(tb, ta, cb, ca)
        assert result.cohen_d_effect_size == 0.0
        assert result.effect_magnitude == "negligible"

    def test_identical_both_groups_same_value_cohen_d_zero(self):
        """Both groups all-same value → cohen_d=0."""
        tb = [25.0] * 10
        ta = [25.0] * 10
        cb = [25.0] * 10
        ca = [25.0] * 10
        result = compute_impact_from_arrays(tb, ta, cb, ca)
        assert result.cohen_d_effect_size == 0.0

    def test_zero_variance_does_not_crash(self):
        """Zero variance case completes without exception."""
        tb = [30.0] * 8
        ta = [30.0] * 8
        cb = [30.0] * 8
        ca = [30.0] * 8
        result = compute_impact_from_arrays(tb, ta, cb, ca)
        assert result is not None


# ---------------------------------------------------------------------------
# Edge case 4: empty control group
# ---------------------------------------------------------------------------

class TestEmptyControl:
    def test_empty_control_returns_only_treated_type(self):
        """Empty control → analysis_type='only_treated', diff_in_diff=NaN."""
        rng = np.random.default_rng(5)
        tb = list(rng.normal(25, 2, 10))
        ta = list(rng.normal(26, 2, 10))
        result = compute_impact_from_arrays(tb, ta, [], [])
        assert result.analysis_type == "only_treated"
        assert math.isnan(result.diff_in_diff_effect)

    def test_all_nan_control_falls_back_to_only_treated(self):
        """All-NaN control after filtering → only_treated."""
        rng = np.random.default_rng(6)
        tb = list(rng.normal(25, 2, 10))
        ta = list(rng.normal(26, 2, 10))
        cb = [float("nan")] * 8
        ca = [float("nan")] * 8
        result = compute_impact_from_arrays(tb, ta, cb, ca)
        assert result.analysis_type == "only_treated"
        assert math.isnan(result.diff_in_diff_effect)

    def test_only_treated_has_valid_before_after_means(self):
        """only_treated analysis still computes treated before/after means."""
        tb = [24.0, 24.5, 23.5, 25.0, 24.0, 23.0, 25.5, 24.5, 24.0, 23.5]
        ta = [26.0, 26.5, 25.5, 27.0, 26.0, 25.0, 27.5, 26.5, 26.0, 25.5]
        result = compute_impact_from_arrays(tb, ta, [], [])
        assert result.treated_before == pytest.approx(np.mean(tb))
        assert result.treated_after == pytest.approx(np.mean(ta))
        # control values should be NaN
        assert math.isnan(result.control_before)
        assert math.isnan(result.control_after)

    def test_only_treated_sample_sizes(self):
        """only_treated: sample_sizes has control=0."""
        rng = np.random.default_rng(7)
        ta = list(rng.normal(26, 2, 10))
        tb = list(rng.normal(25, 2, 10))
        result = compute_impact_from_arrays(tb, ta, [], [])
        assert result.sample_sizes["control"] == 0
        assert result.sample_sizes["treated"] == 10

    def test_normal_diff_in_diff_has_analysis_type_diff_in_diff(self):
        """Normal case (enough data, both groups) → analysis_type='diff_in_diff'."""
        rng = np.random.default_rng(8)
        tb = list(rng.normal(25, 2, 15))
        ta = list(rng.normal(26, 2, 15))
        cb = list(rng.normal(25, 2, 15))
        ca = list(rng.normal(25, 2, 15))
        result = compute_impact_from_arrays(tb, ta, cb, ca)
        assert result.analysis_type == "diff_in_diff"


# ---------------------------------------------------------------------------
# Edge case 5: window truncation
# ---------------------------------------------------------------------------

class TestWindowTruncation:
    def test_window_larger_than_available_does_not_crash(self):
        """window_days=14, available_days=5 → truncates gracefully, no error."""
        rng = np.random.default_rng(9)
        tb = list(rng.normal(25, 2, 10))
        ta = list(rng.normal(26, 2, 10))
        cb = list(rng.normal(25, 2, 10))
        ca = list(rng.normal(25, 2, 10))
        result = compute_impact_from_arrays(tb, ta, cb, ca, available_days=5, window_days=14)
        assert result is not None

    def test_available_days_zero_is_inconclusive(self):
        """available_days=0 → no usable data → inconclusive."""
        result = compute_impact_from_arrays([], [], [], [], available_days=0, window_days=7)
        assert result.significance == "inconclusive"

    def test_arrays_truncated_to_available_days(self):
        """When available_days < len(arrays), only available_days items used."""
        tb = [24.0] * 10
        ta = [26.0] * 10
        cb = [24.0] * 10
        ca = [25.0] * 10
        # Only first 3 items should be used → n=3 → inconclusive (< 7)
        result = compute_impact_from_arrays(tb, ta, cb, ca, available_days=3, window_days=14)
        assert result.significance == "inconclusive"

    def test_available_days_equal_to_window_uses_all_data(self):
        """available_days == window_days → no truncation, uses all arrays."""
        rng = np.random.default_rng(10)
        tb = list(rng.normal(25, 2, 10))
        ta = list(rng.normal(26, 2, 10))
        cb = list(rng.normal(25, 2, 10))
        ca = list(rng.normal(25, 2, 10))
        result = compute_impact_from_arrays(tb, ta, cb, ca, available_days=10, window_days=10)
        assert result.sample_sizes["treated"] == 10
        assert result.sample_sizes["control"] == 10
