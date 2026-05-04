"""Tests for web_cabinet.analytics.alerts_bridge."""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from web_cabinet.analytics.alerts_bridge import (
    ActiveAlert,
    _normalize_severity,
    list_active_alerts,
)


def _make_alert(severity: str = "warning", detected_at: date = date(2026, 1, 1)) -> ActiveAlert:
    return ActiveAlert(
        alert_id="aabbccddeeff",
        farm_id="demo-farm-v1",
        animal_id="42",
        alert_type="HEALTH.MASTITIS",
        severity=severity,  # type: ignore[arg-type]
        title="Test alert",
        description="Test description",
        detected_at=detected_at,
        evidence={},
    )


def test_list_active_alerts_returns_list():
    with patch(
        "web_cabinet.analytics.alerts_bridge._load_generators",
        return_value=(_no_op_generator, _no_op_generator, _no_op_generator),
    ):
        result = list_active_alerts("demo-farm-v1")
    assert isinstance(result, list)
    assert len(result) > 0, "Expected non-empty list of alerts from health events fallback"
    for item in result:
        assert isinstance(item, ActiveAlert)


def test_severity_normalization():
    assert _normalize_severity("HIGH") == "critical"
    assert _normalize_severity("MEDIUM") == "warning"
    assert _normalize_severity("LOW") == "info"
    assert _normalize_severity("high") == "critical"
    assert _normalize_severity("medium") == "warning"
    assert _normalize_severity("UNKNOWN") == "warning"


def _no_op_generator(**_kwargs):
    return []


def test_filter_by_severity():
    mock_alerts = [
        _make_alert("critical"),
        _make_alert("warning"),
        _make_alert("warning"),
        _make_alert("info"),
    ]
    with patch(
        "web_cabinet.analytics.alerts_bridge._load_generators",
        return_value=(_no_op_generator, _no_op_generator, _no_op_generator),
    ), patch(
        "web_cabinet.analytics.alerts_bridge._alerts_from_health_events",
        return_value=mock_alerts,
    ):
        result = list_active_alerts("demo-farm-v1", severity_filter=["critical"])
    assert all(a.severity == "critical" for a in result)
    assert len(result) == 1


def test_limit_param():
    mock_alerts = [_make_alert() for _ in range(20)]
    with patch(
        "web_cabinet.analytics.alerts_bridge._load_generators",
        return_value=(_no_op_generator, _no_op_generator, _no_op_generator),
    ), patch(
        "web_cabinet.analytics.alerts_bridge._alerts_from_health_events",
        return_value=mock_alerts,
    ):
        result = list_active_alerts("demo-farm-v1", limit=5)
    assert len(result) == 5
