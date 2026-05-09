"""Acceptance: 7 canonical tools per thesis §3.1.4 work on demo store."""
from __future__ import annotations
import pytest
from web_cabinet.ai.tools import CANONICAL_TOOLS, EXTRA_TOOLS, ALL_TOOLS, execute_tool


def test_canonical_set_is_seven():
    names = {t["name"] for t in CANONICAL_TOOLS}
    expected = {
        "get_animal_profile",
        "analyze_event_impact",
        "forecast_milk_yield",
        "calculate_cull_npv",
        "find_attention_cows",
        "get_kpi_summary",
        "search_events_timeline",
    }
    assert names == expected, f"canonical drift: {names ^ expected}"


def test_all_tools_total_ten():
    assert len(ALL_TOOLS) == 10
    assert len(EXTRA_TOOLS) == 3


def test_analyze_event_impact_returns_kpi_payload(rich_store):
    """Smoke: must return event_id, kpi, window_days, before/after, delta, evidence_chips."""
    # Use any event id from the seeded timeline. Try a known stable ID first;
    # if the demo timeline doesn't have it, fall back to picking the first event.
    candidate_ids = ["TL_001", "evt_2026_03_diet_change", "EVT-001", "1"]
    result = None
    for eid in candidate_ids:
        result = execute_tool("analyze_event_impact", {"event_id": eid, "kpi": "milk_kg", "window_days": 14}, rich_store)
        if "event_id" in result:
            break
    assert result is not None
    assert "event_id" in result
    assert "kpi" in result
    assert "window_days" in result
    assert "before" in result
    assert "after" in result
    assert "delta" in result
    assert "evidence_chips" in result
    assert isinstance(result["evidence_chips"], list)


def test_find_attention_cows_returns_top_n_with_reasons(rich_store):
    """Smoke: must return cows[] sorted by score, each with cow_id+score+reasons."""
    result = execute_tool("find_attention_cows", {"threshold_count": 3}, rich_store)
    assert "cows" in result
    assert isinstance(result["cows"], list)
    assert len(result["cows"]) <= 3
    # Sorted descending by score
    scores = [c["score"] for c in result["cows"]]
    assert scores == sorted(scores, reverse=True)
    # Each cow has the expected shape
    for c in result["cows"]:
        assert "cow_id" in c
        assert "score" in c
        assert "reasons" in c
        assert isinstance(c["reasons"], list)
    assert "evidence_chips" in result


def test_find_attention_cows_picks_high_scc(rich_store):
    """Ночка (cow 9002, SCC 350k) must be in the attention set."""
    result = execute_tool("find_attention_cows", {"threshold_count": 10}, rich_store)
    cow_ids = {c["cow_id"] for c in result["cows"]}
    assert "9002" in cow_ids, f"Ночка (9002, high SCC) missing from {cow_ids}"
