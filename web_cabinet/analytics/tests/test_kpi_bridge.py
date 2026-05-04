"""Tests for web_cabinet.analytics.kpi_bridge."""
from __future__ import annotations

import math
import tempfile
from dataclasses import fields
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from web_cabinet.analytics.kpi_bridge import (
    DashboardKPI,
    _compute_confidence,
    _get_kpi,
    compute_dashboard_kpi,
)

_FIXTURES = Path(__file__).parents[3] / "data" / "fixtures" / "target_v2"
_ASOF = date(2024, 6, 1)  # fixtures contain data around this date


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------

def test_get_kpi_helper_returns_value():
    df = pd.DataFrame([
        {"farm_id": "F1", "kpi_id": "milk_avg_kg_per_cow_1d", "value": 28.5},
        {"farm_id": "F1", "kpi_id": "fat_pct_avg_7d", "value": 3.8},
    ])
    assert _get_kpi(df, "milk_avg_kg_per_cow_1d", "F1") == pytest.approx(28.5)
    assert _get_kpi(df, "fat_pct_avg_7d", "F1") == pytest.approx(3.8)


def test_get_kpi_helper_missing_farm():
    df = pd.DataFrame([{"farm_id": "F1", "kpi_id": "milk_avg_kg_per_cow_1d", "value": 28.5}])
    assert _get_kpi(df, "milk_avg_kg_per_cow_1d", "OTHER") is None


def test_get_kpi_helper_missing_kpi_id():
    df = pd.DataFrame([{"farm_id": "F1", "kpi_id": "milk_avg_kg_per_cow_1d", "value": 28.5}])
    assert _get_kpi(df, "nonexistent_kpi", "F1") is None


def test_get_kpi_helper_empty_df():
    assert _get_kpi(pd.DataFrame(), "any_kpi", "F1") is None


def test_get_kpi_helper_nan_value():
    df = pd.DataFrame([{"farm_id": "F1", "kpi_id": "k", "value": float("nan")}])
    assert _get_kpi(df, "k", "F1") is None


# ---------------------------------------------------------------------------
# Confidence level tests
# ---------------------------------------------------------------------------

def test_confidence_levels_high():
    assert _compute_confidence(28.5, 3.8, 3.2, 50) == "high"


def test_confidence_levels_medium_few_kpis():
    assert _compute_confidence(28.5, None, None, 30) == "medium"


def test_confidence_levels_low_small_herd():
    assert _compute_confidence(28.5, 3.8, 3.2, 3) == "low"


def test_confidence_levels_low_no_data():
    assert _compute_confidence(None, None, None, 0) == "low"


def test_confidence_levels_medium_adequate_size_few_kpis():
    # 20 cows, 2 KPIs → medium (not high because sample < 30)
    assert _compute_confidence(28.5, 3.8, None, 20) == "medium"


# ---------------------------------------------------------------------------
# DashboardKPI dataclass fields
# ---------------------------------------------------------------------------

def test_dashboard_kpi_dataclass_fields_present():
    expected = {
        "farm_id", "as_of",
        "avg_milk_yield_kg", "ecm_kg", "fat_pct", "protein_pct", "scc_bulk_k",
        "pregnancy_rate_21d_pct", "days_open_avg",
        "cows_in_treatment", "mastitis_incidence_pct_per_year",
        "confidence", "sample_size_cows", "raw_kpi_long",
    }
    actual = {f.name for f in fields(DashboardKPI)}
    assert expected == actual


def test_dashboard_kpi_can_be_constructed_with_nones():
    kpi = DashboardKPI(
        farm_id="test",
        as_of=date.today(),
        avg_milk_yield_kg=None,
        ecm_kg=None,
        fat_pct=None,
        protein_pct=None,
        scc_bulk_k=None,
        pregnancy_rate_21d_pct=None,
        days_open_avg=None,
        cows_in_treatment=None,
        mastitis_incidence_pct_per_year=None,
        confidence="low",
        sample_size_cows=0,
        raw_kpi_long=None,
    )
    assert kpi.farm_id == "test"
    assert kpi.confidence == "low"


# ---------------------------------------------------------------------------
# compute_dashboard_kpi — happy path (fixtures)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _FIXTURES.exists(), reason="fixtures not present")
def test_compute_dashboard_kpi_synthetic():
    kpi = compute_dashboard_kpi("FARM_001", _ASOF, input_dir=_FIXTURES)
    assert isinstance(kpi, DashboardKPI)
    assert kpi.farm_id == "FARM_001"
    assert kpi.as_of == _ASOF
    assert kpi.confidence in ("high", "medium", "low")
    assert isinstance(kpi.sample_size_cows, int)
    # At least one production KPI should be populated from fixtures
    has_any = any(
        v is not None
        for v in [kpi.avg_milk_yield_kg, kpi.fat_pct, kpi.protein_pct, kpi.scc_bulk_k]
    )
    assert has_any, "Expected at least one production KPI from fixtures"


@pytest.mark.skipif(not _FIXTURES.exists(), reason="fixtures not present")
def test_compute_dashboard_kpi_raw_kpi_long_attached():
    kpi = compute_dashboard_kpi("FARM_001", _ASOF, input_dir=_FIXTURES)
    # raw_kpi_long is populated when data exists
    assert kpi.raw_kpi_long is not None
    assert isinstance(kpi.raw_kpi_long, pd.DataFrame)
    assert not kpi.raw_kpi_long.empty


# ---------------------------------------------------------------------------
# compute_dashboard_kpi — empty input
# ---------------------------------------------------------------------------

def test_compute_dashboard_kpi_empty_input():
    with tempfile.TemporaryDirectory() as tmp_dir:
        empty_dir = Path(tmp_dir)
        kpi = compute_dashboard_kpi("no-such-farm", date.today(), input_dir=empty_dir)
    assert isinstance(kpi, DashboardKPI)
    assert kpi.confidence == "low"
    assert kpi.avg_milk_yield_kg is None
    assert kpi.fat_pct is None
    assert kpi.protein_pct is None
    assert kpi.scc_bulk_k is None
    assert kpi.raw_kpi_long is None


def test_compute_dashboard_kpi_wrong_farm_id_returns_low_confidence():
    """A valid data dir but non-existent farm_id should yield low confidence."""
    if not _FIXTURES.exists():
        pytest.skip("fixtures not present")
    kpi = compute_dashboard_kpi("demo-farm-v1", date.today(), input_dir=_FIXTURES)
    assert isinstance(kpi, DashboardKPI)
    assert kpi.confidence == "low"
    assert kpi.avg_milk_yield_kg is None
