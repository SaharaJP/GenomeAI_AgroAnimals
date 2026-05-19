"""Single-input breakeven sensitivity for pen-day economics (RFC §4.3).

Computes the input level at which ``margin_rub`` collapses to zero
when every other input is held constant. Formulas are derived from the
pen-day identities in ``docs/target/economics_v2.md`` §69-§83:

    margin_rub = revenue_total_rub - total_cost_rub
    revenue_total_rub = revenue_milk_rub + revenue_cull_rub
    revenue_milk_rub = milk_kg * milk_price_rub_per_kg
    total_cost_rub = cost_feed_rub + cost_vet_rub + cost_repro_rub
                   + cost_cull_rub + cost_other_rub
    cost_feed_rub = feed_dm_kg * feed_cost_rub_per_kg_dm
    cost_vet_rub  = treatments_n * vet_cost_per_treatment_event_rub

Solving ``margin_rub = 0`` for each individual price/rate while
holding the rest yields the three breakeven values returned by
:func:`compute_breakeven_sensitivity`.

This is the «single_input_holding_others» method declared in the
RFC §5.1; a future multi-variate Monte-Carlo variant ships in a
separate RFC per RFC §9.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


METHOD = "single_input_holding_others"


@dataclass(frozen=True)
class SensitivityInputs:
    """Aggregated pen-day totals for the period and scope of interest.

    All values are expected to be non-negative sums over the active
    rows of ``economics_daily.csv`` (post-filter).
    """

    revenue_total_rub: float
    revenue_cull_rub: float
    total_cost_rub: float
    cost_feed_rub: float
    cost_vet_rub: float
    cost_repro_rub: float
    cost_cull_rub: float
    cost_other_rub: float
    milk_kg: float
    feed_dm_kg: float
    treatments_n: float


@dataclass(frozen=True)
class SensitivityResult:
    milk_price_floor_rub_per_kg: Optional[float]
    feed_cost_ceiling_rub_per_kg_dm: Optional[float]
    vet_cost_ceiling_rub_per_event: Optional[float]
    method: str = METHOD


def _safe_floor(numerator: float, denominator: float) -> Optional[float]:
    """Return ``numerator / denominator`` if denominator > 0, else ``None``."""
    if denominator <= 0:
        return None
    value = float(numerator) / float(denominator)
    # Negative breakeven means the period is already loss-making at zero
    # price/rate — surface that explicitly as ``0.0`` so the UI can flag
    # "already below breakeven", instead of returning a meaningless
    # negative price.
    return max(0.0, value)


def compute_breakeven_sensitivity(inputs: SensitivityInputs) -> SensitivityResult:
    """Compute single-input breakeven thresholds.

    Returns ``None`` for any threshold whose denominator (milk_kg,
    feed_dm_kg, treatments_n) is zero — for those inputs no
    breakeven exists because the cost/revenue term is structurally
    zero regardless of the per-unit price/rate.
    """

    # milk_kg * P_milk + revenue_cull_rub = total_cost_rub  =>  P_milk = (total_cost - cull) / milk_kg
    milk_price_floor = _safe_floor(
        inputs.total_cost_rub - inputs.revenue_cull_rub,
        inputs.milk_kg,
    )

    non_feed_cost = (
        inputs.cost_vet_rub
        + inputs.cost_repro_rub
        + inputs.cost_cull_rub
        + inputs.cost_other_rub
    )
    # feed_dm_kg * C_feed = revenue_total - other_costs  =>  C_feed = (revenue_total - other_costs) / feed_dm_kg
    feed_cost_ceiling = _safe_floor(
        inputs.revenue_total_rub - non_feed_cost,
        inputs.feed_dm_kg,
    )

    non_vet_cost = (
        inputs.cost_feed_rub
        + inputs.cost_repro_rub
        + inputs.cost_cull_rub
        + inputs.cost_other_rub
    )
    # treatments_n * V_event = revenue_total - other_costs  =>  V_event = (revenue_total - other_costs) / treatments_n
    vet_cost_ceiling = _safe_floor(
        inputs.revenue_total_rub - non_vet_cost,
        inputs.treatments_n,
    )

    return SensitivityResult(
        milk_price_floor_rub_per_kg=milk_price_floor,
        feed_cost_ceiling_rub_per_kg_dm=feed_cost_ceiling,
        vet_cost_ceiling_rub_per_event=vet_cost_ceiling,
        method=METHOD,
    )


__all__ = [
    "METHOD",
    "SensitivityInputs",
    "SensitivityResult",
    "compute_breakeven_sensitivity",
]
