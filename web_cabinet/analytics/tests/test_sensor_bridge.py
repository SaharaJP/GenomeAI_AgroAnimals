"""Tests for web_cabinet.analytics.sensor_bridge."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from web_cabinet.analytics.sensor_bridge import (
    SensorAnomaly,
    detect_recent_sensor_anomalies,
)


def test_sensor_bridge_returns_list():
    """detect_recent_sensor_anomalies must return a list and not crash."""
    result = detect_recent_sensor_anomalies("demo-farm-v1", lookback_days=365)
    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, SensorAnomaly)
        assert item.anomaly_type in ("scc_spike", "yield_drop", "health_event")


def test_sensor_bridge_empty_on_bad_farm():
    """An unknown farm_id should yield an empty list, not raise."""
    result = detect_recent_sensor_anomalies("NONEXISTENT_FARM_XYZ", lookback_days=30)
    assert result == []


def test_sensor_bridge_empty_on_missing_csv():
    """When no CSV data is found, result must be []."""
    with patch(
        "web_cabinet.analytics.sensor_bridge._from_demo_csv",
        side_effect=FileNotFoundError("no csv"),
    ):
        result = detect_recent_sensor_anomalies("any-farm", lookback_days=30)
    assert result == []
