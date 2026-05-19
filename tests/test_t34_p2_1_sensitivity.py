"""Unit tests for ``core.economics.sensitivity`` (RFC §4.3, §5.1)."""

from __future__ import annotations

import pytest

from core.economics.sensitivity import (
    METHOD,
    SensitivityInputs,
    SensitivityResult,
    compute_breakeven_sensitivity,
)


def _balanced_inputs() -> SensitivityInputs:
    """Hand-checked inputs whose breakevens are easy to verify by mental math.

    milk_kg = 100, feed_dm_kg = 40, treatments_n = 2.
    Prices: milk 50 / feed 10 / vet event 200 / repro 0 / cull 0 / other 200.
    Revenue: milk 5000, cull 0 → 5000. Cost: feed 400, vet 400, repro 0,
    cull 0, other 200 → 1000. Margin: +4000.

    Breakevens:
      milk_price_floor = (1000 - 0) / 100 = 10.0 ₽/kg
      feed_cost_ceiling = (5000 - 600) / 40 = 110.0 ₽/kg DM
      vet_cost_ceiling = (5000 - 600) / 2 = 2200.0 ₽/event
    """

    return SensitivityInputs(
        revenue_total_rub=5_000.0,
        revenue_cull_rub=0.0,
        total_cost_rub=1_000.0,
        cost_feed_rub=400.0,
        cost_vet_rub=400.0,
        cost_repro_rub=0.0,
        cost_cull_rub=0.0,
        cost_other_rub=200.0,
        milk_kg=100.0,
        feed_dm_kg=40.0,
        treatments_n=2.0,
    )


def test_returns_method_label() -> None:
    res = compute_breakeven_sensitivity(_balanced_inputs())
    assert res.method == METHOD
    assert METHOD == "single_input_holding_others"


def test_breakeven_values_match_hand_check() -> None:
    res = compute_breakeven_sensitivity(_balanced_inputs())
    assert res.milk_price_floor_rub_per_kg == pytest.approx(10.0, abs=1e-9)
    assert res.feed_cost_ceiling_rub_per_kg_dm == pytest.approx(110.0, abs=1e-9)
    assert res.vet_cost_ceiling_rub_per_event == pytest.approx(2_200.0, abs=1e-9)


def test_cull_revenue_credits_milk_price_floor() -> None:
    """revenue_cull subsidises the required milk price."""

    base = _balanced_inputs()
    inputs = SensitivityInputs(
        revenue_total_rub=base.revenue_total_rub + 200.0,
        revenue_cull_rub=200.0,
        total_cost_rub=base.total_cost_rub,
        cost_feed_rub=base.cost_feed_rub,
        cost_vet_rub=base.cost_vet_rub,
        cost_repro_rub=base.cost_repro_rub,
        cost_cull_rub=base.cost_cull_rub,
        cost_other_rub=base.cost_other_rub,
        milk_kg=base.milk_kg,
        feed_dm_kg=base.feed_dm_kg,
        treatments_n=base.treatments_n,
    )
    res = compute_breakeven_sensitivity(inputs)
    # floor drops from 10.0 to (1000 - 200) / 100 = 8.0
    assert res.milk_price_floor_rub_per_kg == pytest.approx(8.0, abs=1e-9)


def test_zero_denominators_return_none() -> None:
    inputs = SensitivityInputs(
        revenue_total_rub=1_000.0,
        revenue_cull_rub=0.0,
        total_cost_rub=800.0,
        cost_feed_rub=300.0,
        cost_vet_rub=200.0,
        cost_repro_rub=0.0,
        cost_cull_rub=0.0,
        cost_other_rub=300.0,
        milk_kg=0.0,
        feed_dm_kg=0.0,
        treatments_n=0.0,
    )
    res = compute_breakeven_sensitivity(inputs)
    assert res.milk_price_floor_rub_per_kg is None
    assert res.feed_cost_ceiling_rub_per_kg_dm is None
    assert res.vet_cost_ceiling_rub_per_event is None


def test_loss_making_period_returns_zero_floor_not_negative() -> None:
    """If non-milk revenue already exceeds total cost, milk price floor
    would mathematically be negative — clamp to 0.0 to communicate
    "already below breakeven, any milk price keeps margin positive"
    rather than emitting a confusing negative number."""

    inputs = SensitivityInputs(
        revenue_total_rub=5_000.0,
        revenue_cull_rub=1_500.0,   # huge cull income
        total_cost_rub=1_000.0,
        cost_feed_rub=400.0,
        cost_vet_rub=400.0,
        cost_repro_rub=0.0,
        cost_cull_rub=0.0,
        cost_other_rub=200.0,
        milk_kg=100.0,
        feed_dm_kg=40.0,
        treatments_n=2.0,
    )
    res = compute_breakeven_sensitivity(inputs)
    # raw: (1000 - 1500)/100 = -5.0 → clamped to 0.0
    assert res.milk_price_floor_rub_per_kg == pytest.approx(0.0, abs=1e-9)


def test_dataclass_is_frozen() -> None:
    res = compute_breakeven_sensitivity(_balanced_inputs())
    assert isinstance(res, SensitivityResult)
    with pytest.raises(Exception):
        res.method = "mutated"   # type: ignore[misc]
