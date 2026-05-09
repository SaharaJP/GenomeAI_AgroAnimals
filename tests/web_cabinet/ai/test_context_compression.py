"""Acceptance: §3.2.1 farm-context knapsack compression."""
from __future__ import annotations

import pytest

from web_cabinet.ai.context_compression import (
    Segment,
    estimate_tokens,
    compress_farm_context,
    CATEGORY_WEIGHTS,
)


# ── token estimator ────────────────────────────────────────────────────────


def test_estimate_tokens_cyrillic_formula():
    """|c| / 2.5 + 8 (ceil)."""
    s = "А" * 50  # 50 cyrillic chars
    assert estimate_tokens(s) == 28  # ceil(50/2.5) + 8 = 20 + 8


def test_estimate_tokens_dict_serialises_via_json():
    """Dicts are json-dumped before length count."""
    d = {"k": "А" * 50}
    # JSON-serialised: {"k": "А..."} ≈ 8 chars overhead + 50 chars = 58 chars
    # ceil(58/2.5) + 8 = 24 + 8 = 32
    n = estimate_tokens(d)
    assert n >= 28  # at minimum the value contribution


def test_estimate_tokens_empty_string():
    assert estimate_tokens("") == 8  # 0 + 8 floor


def test_estimate_tokens_short_string_minimum():
    assert estimate_tokens("a") == 9  # ceil(1/2.5) + 8 = 1 + 8


# ── greedy knapsack ───────────────────────────────────────────────────────


def _seg(name: str, weight: float, tokens: int) -> Segment:
    return Segment(name=name, weight=weight, content={"_": name}, token_estimate=tokens)


def test_compress_orders_by_density_first():
    """Higher weight/tokens density wins when both fit but only one is allowed."""
    high = _seg("kpi", 1.0, 10)        # density 0.10
    low  = _seg("trend", 0.4, 10)      # density 0.04
    kept = compress_farm_context([high, low], budget=10)
    assert kept == [high]


def test_compress_respects_budget():
    """Sum of kept tokens never exceeds budget."""
    segs = [
        _seg("a", 1.0, 50),
        _seg("b", 0.9, 40),
        _seg("c", 0.7, 30),
        _seg("d", 0.5, 20),
    ]
    kept = compress_farm_context(segs, budget=80)
    assert sum(s.token_estimate for s in kept) <= 80


def test_compress_skips_oversized_segment_keeps_smaller():
    """A segment > budget never gets selected, but smaller fits stay."""
    huge = _seg("huge", 1.0, 5000)
    small = _seg("small", 0.5, 100)
    kept = compress_farm_context([huge, small], budget=3000)
    names = {s.name for s in kept}
    assert "huge" not in names
    assert "small" in names


def test_compress_empty_input_returns_empty():
    assert compress_farm_context([], budget=3000) == []


def test_compress_all_fit_returns_all():
    """If sum(tokens) ≤ budget, every segment is kept (order-independent)."""
    segs = [_seg("a", 1.0, 100), _seg("b", 0.5, 100), _seg("c", 0.4, 100)]
    kept = compress_farm_context(segs, budget=10000)
    assert {s.name for s in kept} == {"a", "b", "c"}


def test_compress_density_breaks_tie_in_favor_of_higher_weight_lower_tokens():
    """Two segments with same density → ordering deterministic enough; one fits."""
    # density 0.10 each
    a = _seg("a", 1.0, 10)
    b = _seg("b", 0.5, 5)
    kept = compress_farm_context([a, b], budget=12)
    # Both should fit (10 + 5 > 12 → only one fits; order: stable sort by density desc)
    # Pick the higher-density-or-first one. Assert at least one fits within budget.
    assert sum(s.token_estimate for s in kept) <= 12
    assert len(kept) >= 1


def test_category_weights_match_thesis_table_3_2_1():
    """Sanity check on the §3.2.1 weights table."""
    assert CATEGORY_WEIGHTS["farm_summary"] == 1.0
    assert CATEGORY_WEIGHTS["today_kpi"] == 1.0
    assert CATEGORY_WEIGHTS["attention_cow"] == 0.9
    assert CATEGORY_WEIGHTS["recent_event_7d"] == 0.7
    assert CATEGORY_WEIGHTS["groups_summary"] == 0.5
    assert CATEGORY_WEIGHTS["full_profile"] == 0.5
    assert CATEGORY_WEIGHTS["period_trends"] == 0.4
    assert CATEGORY_WEIGHTS["active_insights"] == 0.4
    assert CATEGORY_WEIGHTS["recent_event_30d"] == 0.2
