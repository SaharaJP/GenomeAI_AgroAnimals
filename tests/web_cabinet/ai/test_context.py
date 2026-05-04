"""Tests for build_farm_context (MVP-N12)."""
from __future__ import annotations

import pytest

from web_cabinet.ai.context import build_farm_context


class TestFarmContextStructure:
    """All required top-level keys must be present."""

    def test_required_keys_present(self, csv_store):
        ctx = build_farm_context("demo-farm-v1", store=csv_store)
        required = {
            "farm_summary",
            "today_kpi",
            "period_trends",
            "active_insights",
            "recent_events",
            "attention_cows",
            "groups_summary",
            "token_count",
        }
        missing = required - set(ctx.keys())
        assert not missing, f"Missing keys: {missing}"

    def test_farm_summary_fields(self, csv_store):
        ctx = build_farm_context("demo-farm-v1", store=csv_store)
        summary = ctx["farm_summary"]
        for field in ("farm_id", "name", "total_cows", "active_cows_count", "date_as_of"):
            assert field in summary, f"Missing farm_summary.{field}"

    def test_today_kpi_fields(self, csv_store):
        ctx = build_farm_context("demo-farm-v1", store=csv_store)
        kpi = ctx["today_kpi"]
        for field in (
            "milk_yield_avg_kg_per_cow",
            "scc_bulk_k",
            "fresh_cows_count",
            "cows_in_withdrawal_count",
            "conception_rate_21d_pct",
            "health_index_score",
        ):
            assert field in kpi, f"Missing today_kpi.{field}"

    def test_period_trends_is_list_of_dicts(self, csv_store):
        ctx = build_farm_context("demo-farm-v1", store=csv_store)
        trends = ctx["period_trends"]
        assert isinstance(trends, list)
        if trends:
            entry = trends[0]
            for field in ("kpi", "value", "prev_value", "delta", "direction"):
                assert field in entry, f"Trend entry missing '{field}'"

    def test_recent_events_have_evidence_id(self, csv_store):
        ctx = build_farm_context("demo-farm-v1", store=csv_store)
        events = ctx["recent_events"]
        assert isinstance(events, list)
        for ev in events:
            assert "evidence_id" in ev, "Event missing evidence_id"
            assert "date" in ev
            assert "type" in ev

    def test_attention_cows_have_flags(self, csv_store):
        ctx = build_farm_context("demo-farm-v1", store=csv_store)
        for cow in ctx["attention_cows"]:
            assert "cow_id" in cow
            assert "flags" in cow
            assert isinstance(cow["flags"], list)
            assert len(cow["flags"]) > 0

    def test_groups_summary_structure(self, csv_store):
        ctx = build_farm_context("demo-farm-v1", store=csv_store)
        for g in ctx["groups_summary"]:
            assert "group_id" in g
            assert "cow_count" in g

    def test_token_count_is_int(self, csv_store):
        ctx = build_farm_context("demo-farm-v1", store=csv_store)
        assert isinstance(ctx["token_count"], int)
        assert ctx["token_count"] > 0


class TestFarmContextTokenCount:
    """Token count must stay under 10 000 for demo data."""

    def test_token_count_under_10000_csv_data(self, csv_store):
        ctx = build_farm_context("demo-farm-v1", store=csv_store)
        assert ctx["token_count"] < 10_000, (
            f"Context too large: {ctx['token_count']} tokens (limit 10 000)"
        )

    def test_token_count_under_10000_rich_data(self, rich_store):
        ctx = build_farm_context("test-farm", store=rich_store)
        assert ctx["token_count"] < 10_000, (
            f"Context too large: {ctx['token_count']} tokens"
        )


class TestAttentionCowsDetection:
    """Flag the right cows from rich_store fixture."""

    def _cow_flags(self, rich_store):
        ctx = build_farm_context("test-farm", store=rich_store)
        return {c["cow_id"]: c["flags"] for c in ctx["attention_cows"]}

    def test_zvezdochka_flagged_falling_yield(self, rich_store):
        flags = self._cow_flags(rich_store)
        assert "4821" in flags, "Звёздочка (4821) not in attention_cows"
        assert "falling_yield" in flags["4821"], f"Expected falling_yield, got {flags['4821']}"

    def test_malina_flagged_ready_for_culling(self, rich_store):
        flags = self._cow_flags(rich_store)
        assert "7001" in flags, "Малина (7001) not in attention_cows"
        assert "ready_for_culling" in flags["7001"], (
            f"Expected ready_for_culling, got {flags['7001']}"
        )

    def test_nochka_flagged_high_scc(self, rich_store):
        flags = self._cow_flags(rich_store)
        assert "9002" in flags, "Ночка (9002) not in attention_cows"
        assert "high_scc" in flags["9002"], f"Expected high_scc, got {flags['9002']}"


class TestPeriodTrends:
    """Delta must be computed correctly."""

    def test_delta_is_numeric(self, rich_store):
        ctx = build_farm_context("test-farm", store=rich_store, period_days=5)
        for trend in ctx["period_trends"]:
            assert isinstance(trend["delta"], (int, float)), (
                f"Non-numeric delta for {trend['kpi']}: {trend['delta']}"
            )

    def test_direction_values_valid(self, rich_store):
        ctx = build_farm_context("test-farm", store=rich_store)
        valid = {"↑", "↓", "→"}
        for trend in ctx["period_trends"]:
            assert trend["direction"] in valid, (
                f"Invalid direction '{trend['direction']}' for {trend['kpi']}"
            )


class TestBuildFarmContextBridgeDispatch:
    """Settings-based dispatch: demo mode vs real (bridge) mode."""

    def test_build_farm_context_demo_mode(self):
        """Demo mode: returns seeded FarmContext, does NOT call kpi_bridge or alerts_bridge."""
        from types import SimpleNamespace
        from unittest.mock import patch
        from web_cabinet.ai.context import FarmContext

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
        from types import SimpleNamespace
        from unittest.mock import patch, MagicMock

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
        import datetime
        from types import SimpleNamespace
        from unittest.mock import patch, MagicMock
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
