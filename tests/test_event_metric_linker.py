"""Event-metric AI linker tests (live + fallback)."""
from __future__ import annotations

from unittest.mock import patch
import pytest


def test_static_fallback_for_known_category():
    from web_cabinet.analytics.event_metric_linker import link_event_to_metrics
    event = {"event_type": "ration_change", "title": "Сменили рацион", "body": "Новый TMR"}
    with patch("web_cabinet.analytics.event_metric_linker.get_ai_settings") as gs:
        class S:
            GENOMEAI_AI_DEMO_MODE = True
        gs.return_value = S()
        result = link_event_to_metrics(event)
    assert "feed_efficiency" in result or "dmi" in result


def test_unknown_event_type_returns_empty():
    from web_cabinet.analytics.event_metric_linker import link_event_to_metrics
    event = {"event_type": "completely_unknown_xyz", "title": "X"}
    with patch("web_cabinet.analytics.event_metric_linker.get_ai_settings") as gs:
        class S:
            GENOMEAI_AI_DEMO_MODE = True
        gs.return_value = S()
        result = link_event_to_metrics(event)
    assert result == []


def test_claude_failure_returns_static_fallback():
    from web_cabinet.analytics import event_metric_linker
    event = {"event_type": "ration_change", "title": "X"}
    with patch.object(event_metric_linker, "get_ai_settings") as gs:
        class S:
            GENOMEAI_AI_DEMO_MODE = False
        gs.return_value = S()
        with patch.object(event_metric_linker, "_claude_link", side_effect=Exception("boom")):
            result = event_metric_linker.link_event_to_metrics(event)
    # Falls back to static map for known event_type
    assert "feed_efficiency" in result or "dmi" in result
