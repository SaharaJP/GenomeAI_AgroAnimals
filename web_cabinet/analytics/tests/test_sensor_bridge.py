"""Tests for web_cabinet.analytics.sensor_bridge."""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from web_cabinet.analytics.sensor_bridge import (
    SensorAnomalyAlert,
    _compute_severity,
    _load_sensor_df,
    detect_recent_sensor_anomalies,
)


# ---------------------------------------------------------------------------
# 1. Synthetic end-to-end test with the real demo CSV
# ---------------------------------------------------------------------------

def test_sensor_bridge_synthetic():
    """Call detect_recent_sensor_anomalies with real demo CSV.

    The demo CSV has only ~3 rows per animal (not enough baseline data), so
    the detector should return 0 anomalies — but must NOT crash.
    """
    result = detect_recent_sensor_anomalies("demo-farm-v1", lookback_days=365)
    assert isinstance(result, list)
    # With a small demo dataset the detector cannot build a baseline, so we
    # expect 0 anomalies. Verify the type of any items that do appear.
    for alert in result:
        assert isinstance(alert, SensorAnomalyAlert)
        assert alert.severity in ("critical", "warning", "info")
        assert alert.anomaly_type in ("data_dropout", "outlier", "baseline_drift")


# ---------------------------------------------------------------------------
# 2. Severity computation for all 3 anomaly types
# ---------------------------------------------------------------------------

def test_severity_computation():
    """_compute_severity must map anomaly types and scores correctly."""
    # data_dropout → critical regardless of score
    row_dropout = pd.Series({"anomaly_type": "data_dropout", "score": 3.0})
    assert _compute_severity(row_dropout) == "critical"

    # outlier with high score → critical
    row_outlier_critical = pd.Series({"anomaly_type": "outlier", "score": 7.0})
    assert _compute_severity(row_outlier_critical) == "critical"

    # outlier with low score → warning
    row_outlier_warning = pd.Series({"anomaly_type": "outlier", "score": 3.0})
    assert _compute_severity(row_outlier_warning) == "warning"

    # baseline_drift → warning
    row_drift = pd.Series({"anomaly_type": "baseline_drift", "score": 0.3})
    assert _compute_severity(row_drift) == "warning"


# ---------------------------------------------------------------------------
# 3. Empty input returns empty list
# ---------------------------------------------------------------------------

def test_empty_input_returns_empty_list():
    """When _load_sensor_df returns an empty DataFrame, result must be []."""
    with patch(
        "web_cabinet.analytics.sensor_bridge._load_sensor_df",
        return_value=pd.DataFrame(),
    ):
        result = detect_recent_sensor_anomalies("any-farm", lookback_days=30)
    assert result == []


# ---------------------------------------------------------------------------
# 4. Invalid farm_id returns empty list
# ---------------------------------------------------------------------------

def test_invalid_farm_id_returns_empty_list():
    """An unknown farm_id should yield an empty list, not raise."""
    result = detect_recent_sensor_anomalies("NONEXISTENT_FARM_XYZ", lookback_days=30)
    assert result == []
    assert isinstance(result, list)
