"""Profile health-tab demo helpers — verifies that we never return an empty
Health card just because the animal id wasn't hand-picked into the original
4-entry demo dictionary.
"""
from __future__ import annotations

import pytest

from web_cabinet.api_boundary_v1 import (
    _DEMO_HEALTH_METRICS,
    _demo_health_events_for,
    _demo_health_metrics_for,
)


def test_demo_metrics_returns_known_id_unchanged() -> None:
    metrics = _demo_health_metrics_for("3142")
    assert metrics == _DEMO_HEALTH_METRICS["3142"]


def test_demo_metrics_returns_complete_metrics_for_unknown_id() -> None:
    metrics = _demo_health_metrics_for("9999")
    for key in ("activity_score", "scc", "scc_trend", "daily_milk_yield_kg", "body_condition_score"):
        assert key in metrics, f"missing {key}"
    assert 35.0 <= metrics["activity_score"] <= 85.0
    assert 70 <= metrics["scc"] <= 510
    assert metrics["scc_trend"] in {"↑", "→", "↓"}
    assert 8.0 <= metrics["daily_milk_yield_kg"] <= 32.0
    assert 2.4 <= metrics["body_condition_score"] <= 3.7


def test_demo_metrics_deterministic() -> None:
    a = _demo_health_metrics_for("12345")
    b = _demo_health_metrics_for("12345")
    assert a == b, "demo metrics must be deterministic per id"


def test_demo_metrics_distinct_ids_diverge() -> None:
    a = _demo_health_metrics_for("aaaa")
    b = _demo_health_metrics_for("bbbb")
    assert a != b, "different ids should not collide"


def test_demo_health_events_returns_at_least_one() -> None:
    events = _demo_health_events_for("9999", limit=5)
    assert len(events) >= 1
    for ev in events:
        assert ev.event_id and ev.event_id.startswith("demo_he_")
        assert ev.event_date and len(ev.event_date) == 10
        assert ev.event_type
        assert ev.severity in {"info", "warn", "high"}


def test_demo_health_events_sorted_desc() -> None:
    events = _demo_health_events_for("xxx", limit=5)
    if len(events) > 1:
        dates = [ev.event_date for ev in events]
        assert dates == sorted(dates, reverse=True), "events must be newest first"


@pytest.mark.parametrize("animal_id", ["1", "100", "abc", "5555"])
def test_demo_health_events_deterministic(animal_id: str) -> None:
    a = _demo_health_events_for(animal_id, limit=5)
    b = _demo_health_events_for(animal_id, limit=5)
    assert [e.event_id for e in a] == [e.event_id for e in b]
