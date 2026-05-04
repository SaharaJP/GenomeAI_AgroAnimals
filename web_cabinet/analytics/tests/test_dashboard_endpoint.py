"""Tests for /api/dashboard/today endpoint — demo vs real mode branching.

Tests follow the same unit-test style as test_kpi_bridge.py:
patch helpers at module level rather than spinning up a full TestClient.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from web_cabinet.analytics.kpi_bridge import DashboardKPI


# ---------------------------------------------------------------------------
# Helpers shared by tests
# ---------------------------------------------------------------------------

def _mock_settings(demo_mode: bool) -> MagicMock:
    m = MagicMock()
    m.GENOMEAI_AI_DEMO_MODE = demo_mode
    m.GENOMEAI_DEMO_FARM_ID = "demo-farm-v1"
    return m


def _make_kpi(**overrides) -> DashboardKPI:
    defaults = dict(
        farm_id="demo-farm-v1",
        as_of=date(2026, 5, 4),
        avg_milk_yield_kg=28.3,
        ecm_kg=None,
        fat_pct=3.7,
        protein_pct=3.1,
        scc_bulk_k=185.0,
        pregnancy_rate_21d_pct=None,
        days_open_avg=None,
        cows_in_treatment=3,
        mastitis_incidence_pct_per_year=18.5,
        confidence="high",
        sample_size_cows=120,
        raw_kpi_long=None,
    )
    defaults.update(overrides)
    return DashboardKPI(**defaults)


# ---------------------------------------------------------------------------
# test_endpoint_demo_mode_returns_seeded
# ---------------------------------------------------------------------------

def test_endpoint_demo_mode_returns_seeded(monkeypatch):
    """With DEMO_MODE=True, _compute_dashboard_today returns seeded data with demo=True."""
    from web_cabinet import analytics_v1

    monkeypatch.setattr(analytics_v1, "_get_ai_settings", lambda: _mock_settings(demo_mode=True))

    result = analytics_v1._compute_dashboard_today("demo-farm-v1", date(2026, 5, 4))

    assert isinstance(result, dict)
    assert result.get("demo") is True
    assert "confidence" in result
    assert "farm_id" in result
    assert "as_of" in result


def test_endpoint_demo_mode_seeded_has_required_keys():
    """Seeded JSON has all keys a real DashboardKPI would produce."""
    from web_cabinet.analytics_v1 import _load_seeded_dashboard

    result = _load_seeded_dashboard("demo-farm-v1")

    required = {"farm_id", "as_of", "confidence", "sample_size_cows", "demo"}
    assert required.issubset(result.keys()), f"Missing keys: {required - result.keys()}"
    assert result["demo"] is True


def test_endpoint_demo_mode_unknown_farm_fallback(monkeypatch):
    """Unknown farm in demo mode falls back gracefully (returns some dict)."""
    from web_cabinet import analytics_v1

    monkeypatch.setattr(analytics_v1, "_get_ai_settings", lambda: _mock_settings(demo_mode=True))

    result = analytics_v1._compute_dashboard_today("nonexistent-farm", date(2026, 5, 4))
    assert isinstance(result, dict)
    assert result.get("demo") is True


# ---------------------------------------------------------------------------
# test_endpoint_real_mode_returns_computed
# ---------------------------------------------------------------------------

def test_endpoint_real_mode_returns_computed(monkeypatch):
    """With DEMO_MODE=False, _compute_dashboard_today calls compute_dashboard_kpi."""
    from web_cabinet import analytics_v1

    expected_kpi = _make_kpi()
    monkeypatch.setattr(analytics_v1, "_get_ai_settings", lambda: _mock_settings(demo_mode=False))

    with patch("web_cabinet.analytics_v1.compute_dashboard_kpi", return_value=expected_kpi):
        result = analytics_v1._compute_dashboard_today("demo-farm-v1", date(2026, 5, 4))

    assert isinstance(result, dict)
    assert result.get("demo") is False
    assert result["avg_milk_yield_kg"] == pytest.approx(28.3)
    assert result["confidence"] == "high"
    assert result["sample_size_cows"] == 120


def test_endpoint_real_mode_kpi_to_dict_serializes_all_fields():
    """_kpi_to_dict converts a DashboardKPI to a dict without DataFrame."""
    from web_cabinet.analytics_v1 import _kpi_to_dict

    kpi = _make_kpi()
    result = _kpi_to_dict(kpi)

    assert result["farm_id"] == "demo-farm-v1"
    assert result["as_of"] == "2026-05-04"
    assert result["fat_pct"] == pytest.approx(3.7)
    assert result["protein_pct"] == pytest.approx(3.1)
    assert result["scc_bulk_k"] == pytest.approx(185.0)
    assert result["cows_in_treatment"] == 3
    assert result["mastitis_incidence_pct_per_year"] == pytest.approx(18.5)
    assert "raw_kpi_long" not in result, "raw DataFrame must not be serialised into HTTP response"
    assert result["demo"] is False


def test_endpoint_real_mode_compute_called_with_correct_args(monkeypatch):
    """_compute_dashboard_today passes farm_id and date to compute_dashboard_kpi."""
    from web_cabinet import analytics_v1

    expected_kpi = _make_kpi(farm_id="special-farm", as_of=date(2026, 5, 4))
    monkeypatch.setattr(analytics_v1, "_get_ai_settings", lambda: _mock_settings(demo_mode=False))

    with patch("web_cabinet.analytics_v1.compute_dashboard_kpi", return_value=expected_kpi) as mock_fn:
        analytics_v1._compute_dashboard_today("special-farm", date(2026, 5, 4))

    mock_fn.assert_called_once_with("special-farm", date(2026, 5, 4))
