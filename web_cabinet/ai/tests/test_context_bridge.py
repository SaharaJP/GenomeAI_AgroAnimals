"""Tests for build_farm_context settings-based bridge dispatch."""
from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from web_cabinet.ai.context import FarmContext, build_farm_context


class TestBuildFarmContextBridgeDispatch:
    """Settings-based dispatch: demo mode vs real (bridge) mode."""

    def test_build_farm_context_demo_mode(self):
        """Demo mode: returns seeded FarmContext, does NOT call kpi_bridge or alerts_bridge."""
        settings = SimpleNamespace(GENOMEAI_AI_DEMO_MODE=True)
        with (
            patch("web_cabinet.analytics.kpi_bridge.compute_dashboard_kpi") as mock_kpi,
            patch("web_cabinet.analytics.alerts_bridge.list_active_alerts") as mock_alerts,
        ):
            result = build_farm_context("demo-farm-v1", settings=settings)
        mock_kpi.assert_not_called()
        mock_alerts.assert_not_called()
        assert isinstance(result, FarmContext)

    def test_build_farm_context_real_mode_returns_real_kpi(self):
        """Real mode: kpi field is the object returned by compute_dashboard_kpi."""
        settings = SimpleNamespace(GENOMEAI_AI_DEMO_MODE=False)
        mock_kpi_obj = MagicMock()
        with (
            patch("web_cabinet.analytics.kpi_bridge.compute_dashboard_kpi", return_value=mock_kpi_obj),
            patch("web_cabinet.analytics.alerts_bridge.list_active_alerts", return_value=[]),
            patch("web_cabinet.analytics.sensor_bridge.detect_recent_sensor_anomalies", return_value=[]),
        ):
            result = build_farm_context("farm-1", settings=settings)
        assert result.kpi is mock_kpi_obj

    def test_real_mode_includes_sensor_anomalies(self):
        """Real mode: sensor_anomalies list from sensor_bridge is attached to the context."""
        from web_cabinet.analytics.sensor_bridge import SensorAnomaly

        settings = SimpleNamespace(GENOMEAI_AI_DEMO_MODE=False)
        anomaly = SensorAnomaly(
            animal_id="9002",
            farm_id="farm-1",
            anomaly_type="scc_spike",
            detected_at=datetime.date(2026, 4, 20),
            value=350.0,
            threshold=200.0,
            description="SCC spike",
        )
        with (
            patch("web_cabinet.analytics.kpi_bridge.compute_dashboard_kpi", return_value=MagicMock()),
            patch("web_cabinet.analytics.alerts_bridge.list_active_alerts", return_value=[]),
            patch(
                "web_cabinet.analytics.sensor_bridge.detect_recent_sensor_anomalies",
                return_value=[anomaly],
            ),
        ):
            result = build_farm_context("farm-1", settings=settings)
        assert result.sensor_anomalies == [anomaly]
