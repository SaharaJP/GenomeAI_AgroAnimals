"""TDD: TTLCache on compute_dashboard_kpi — verifies second call hits cache, not run_kpi."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from web_cabinet.analytics.kpi_bridge import (
    DashboardKPI,
    compute_dashboard_kpi,
    invalidate_kpi_cache,
)

_FARM = "farm_001"
_AS_OF = date(2025, 1, 5)
_FIXTURES = Path(__file__).resolve().parents[4] / "data" / "fixtures" / "target_v2"


def _make_fake_kpi(farm_id: str = _FARM) -> DashboardKPI:
    return DashboardKPI(
        farm_id=farm_id,
        as_of=_AS_OF,
        avg_milk_yield_kg=25.0,
        ecm_kg=None,
        fat_pct=3.8,
        protein_pct=3.2,
        scc_bulk_k=120.0,
        pregnancy_rate_21d_pct=None,
        days_open_avg=None,
        cows_in_treatment=2,
        mastitis_incidence_pct_per_year=12.0,
        confidence="high",
        sample_size_cows=42,
    )


class TestKpiBridgeCacheHit:
    """Second call with same key must invoke _compute_dashboard_kpi_uncached only once."""

    def test_second_call_hits_cache_not_run_kpi(self) -> None:
        invalidate_kpi_cache(_FARM, _AS_OF, str(_FIXTURES))

        call_count = {"n": 0}

        def counting_compute(*args, **kwargs):
            call_count["n"] += 1
            return _make_fake_kpi()

        with patch(
            "web_cabinet.analytics.kpi_bridge._compute_dashboard_kpi_uncached",
            side_effect=counting_compute,
        ):
            first = compute_dashboard_kpi(_FARM, _AS_OF, input_dir=_FIXTURES)
            second = compute_dashboard_kpi(_FARM, _AS_OF, input_dir=_FIXTURES)

        assert call_count["n"] == 1, (
            f"Expected _compute_dashboard_kpi_uncached to be called exactly once "
            f"(cache hit on second call), but it was called {call_count['n']} times"
        )
        assert first.farm_id == second.farm_id
        assert first.avg_milk_yield_kg == second.avg_milk_yield_kg

    def test_different_farm_ids_call_uncached_separately(self) -> None:
        invalidate_kpi_cache("farm_A", _AS_OF, str(_FIXTURES))
        invalidate_kpi_cache("farm_B", _AS_OF, str(_FIXTURES))

        call_count = {"n": 0}

        def counting_compute(farm_id, as_of, **kwargs):
            call_count["n"] += 1
            return _make_fake_kpi(farm_id)

        with patch(
            "web_cabinet.analytics.kpi_bridge._compute_dashboard_kpi_uncached",
            side_effect=counting_compute,
        ):
            compute_dashboard_kpi("farm_A", _AS_OF, input_dir=_FIXTURES)
            compute_dashboard_kpi("farm_B", _AS_OF, input_dir=_FIXTURES)

        assert call_count["n"] == 2, (
            f"Two different farm_ids must each call the uncached function once, "
            f"got {call_count['n']} calls"
        )

    def test_invalidate_clears_cache_entry(self) -> None:
        invalidate_kpi_cache(_FARM, _AS_OF, str(_FIXTURES))

        call_count = {"n": 0}

        def counting_compute(*args, **kwargs):
            call_count["n"] += 1
            return _make_fake_kpi()

        with patch(
            "web_cabinet.analytics.kpi_bridge._compute_dashboard_kpi_uncached",
            side_effect=counting_compute,
        ):
            compute_dashboard_kpi(_FARM, _AS_OF, input_dir=_FIXTURES)
            invalidate_kpi_cache(_FARM, _AS_OF, str(_FIXTURES))
            compute_dashboard_kpi(_FARM, _AS_OF, input_dir=_FIXTURES)

        assert call_count["n"] == 2, (
            f"After explicit invalidation the second call must recompute; "
            f"expected 2 calls, got {call_count['n']}"
        )
