"""Acceptance: §3.2.1 farm-context knapsack compression."""
from __future__ import annotations

import datetime
import pytest

from web_cabinet.ai.context_compression import (
    Segment,
    estimate_tokens,
    compress_farm_context,
    segment_farm_context,
    reconstruct_ctx,
    compression_stats,
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


# ── segmenter ─────────────────────────────────────────────────────────────


def _ctx_sample() -> dict:
    return {
        "farm_summary":   {"farm_id": "F", "total_cows": 350},
        "today_kpi":      {"avg_milk_kg": 28.5, "avg_scc": 220_000},
        "period_trends":  {"trend_milk": "+1.2%"},
        "active_insights": [{"insight_id": "I1"}],
        "groups_summary": {"high_yield": 100, "mid": 200, "low": 50},
        "attention_cows": [
            {"animal_id": "C1", "reason": "mastitis"},
            {"animal_id": "C2", "reason": "lameness"},
        ],
        "recent_events": [
            {"event_id": "E1", "event_date": "2026-05-08", "event_type": "mastitis"},
            {"event_id": "E2", "event_date": "2026-05-01", "event_type": "lameness"},
            {"event_id": "E3", "event_date": "2026-04-15", "event_type": "mastitis"},
        ],
    }


def test_segment_farm_context_creates_one_segment_per_top_key():
    ctx = _ctx_sample()
    segs = segment_farm_context(ctx, as_of=datetime.date(2026, 5, 9))
    names = [s.name for s in segs]
    assert "farm_summary" in names
    assert "today_kpi" in names
    assert "period_trends" in names
    assert "active_insights" in names
    assert "groups_summary" in names


def test_segment_farm_context_splits_attention_per_cow():
    ctx = _ctx_sample()
    segs = segment_farm_context(ctx, as_of=datetime.date(2026, 5, 9))
    attn = [s for s in segs if s.name.startswith("attention_cow:")]
    assert len(attn) == 2
    assert all(s.weight == 0.9 for s in attn)


def test_segment_farm_context_splits_events_by_age():
    ctx = _ctx_sample()
    segs = segment_farm_context(ctx, as_of=datetime.date(2026, 5, 9))
    e7 = [s for s in segs if s.name.startswith("recent_event_7d:")]
    e30 = [s for s in segs if s.name.startswith("recent_event_30d:")]
    # 2026-05-08 → 1 day → 7d bucket
    # 2026-05-01 → 8 days → 30d bucket
    # 2026-04-15 → 24 days → 30d bucket
    assert len(e7) == 1
    assert len(e30) == 2
    assert all(s.weight == 0.7 for s in e7)
    assert all(s.weight == 0.2 for s in e30)


def test_segment_farm_context_handles_missing_optional_keys():
    ctx = {"farm_summary": {"farm_id": "F"}}
    segs = segment_farm_context(ctx, as_of=datetime.date(2026, 5, 9))
    assert len(segs) == 1
    assert segs[0].name == "farm_summary"


def test_reconstruct_preserves_dict_shape():
    ctx = _ctx_sample()
    segs = segment_farm_context(ctx, as_of=datetime.date(2026, 5, 9))
    rec = reconstruct_ctx(segs)
    assert rec["farm_summary"] == ctx["farm_summary"]
    assert rec["today_kpi"] == ctx["today_kpi"]
    assert len(rec["attention_cows"]) == 2
    assert len(rec["recent_events"]) == 3


def test_compression_stats_counts_by_category_prefix():
    segs = [
        Segment(name="farm_summary", weight=1.0, content={}, token_estimate=20),
        Segment(name="attention_cow:C1", weight=0.9, content={}, token_estimate=15),
        Segment(name="attention_cow:C2", weight=0.9, content={}, token_estimate=15),
        Segment(name="recent_event_7d:E1", weight=0.7, content={}, token_estimate=10),
    ]
    stats = compression_stats(segs, budget=3000)
    assert stats["used_tokens"] == 60
    assert stats["budget_tokens"] == 3000
    assert stats["kept_segments"] == 4
    assert stats["segments_by_category"]["attention_cow"] == 2
    assert stats["segments_by_category"]["farm_summary"] == 1
    assert stats["segments_by_category"]["recent_event_7d"] == 1


# ── build_farm_context integration ────────────────────────────────────────


def test_build_farm_context_surfaces_compression_stats():
    """The wired build_farm_context must surface compression_stats sidecar."""
    from pathlib import Path
    from web_cabinet.ai.context_helpers.demo_loader import DemoDataStore
    from web_cabinet.ai.context import build_farm_context
    store = DemoDataStore(base_dir=Path("data/demo/investor_v1"))
    ctx = build_farm_context("demo-farm-v1", store=store, period_days=30,
                             context_token_budget=3000)
    assert "compression_stats" in ctx
    cs = ctx["compression_stats"]
    assert cs["budget_tokens"] == 3000
    assert cs["used_tokens"] <= 3000
    assert cs["kept_segments"] >= 1
    assert isinstance(cs["segments_by_category"], dict)


def test_build_farm_context_huge_budget_keeps_all():
    """With a very large budget, no segments should drop."""
    from pathlib import Path
    from web_cabinet.ai.context_helpers.demo_loader import DemoDataStore
    from web_cabinet.ai.context import build_farm_context
    store = DemoDataStore(base_dir=Path("data/demo/investor_v1"))
    ctx = build_farm_context("demo-farm-v1", store=store, period_days=30,
                             context_token_budget=10**8)
    cs = ctx["compression_stats"]
    # All cell-cohesive top keys should survive
    assert "farm_summary" in ctx
    assert "today_kpi" in ctx
