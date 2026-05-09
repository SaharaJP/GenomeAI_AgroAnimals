"""Tests for tool executors (MVP-N12)."""
from __future__ import annotations

import datetime

import pytest

from web_cabinet.ai.tools import execute_tool, ALL_TOOLS


class TestToolDefinitions:
    """All 7 tools must have proper Anthropic format."""

    def test_all_tools_have_required_keys(self):
        for tool in ALL_TOOLS:
            for key in ("name", "description", "input_schema"):
                assert key in tool, f"Tool missing '{key}': {tool}"

    def test_all_tools_have_input_schema_type(self):
        for tool in ALL_TOOLS:
            schema = tool["input_schema"]
            assert schema.get("type") == "object", f"Tool {tool['name']} schema type != 'object'"

    def test_seven_tools_defined(self):
        assert len(ALL_TOOLS) == 7, f"Expected 7 tools, got {len(ALL_TOOLS)}"

    def test_tool_names(self):
        names = {t["name"] for t in ALL_TOOLS}
        expected = {
            "get_animal_profile",
            "get_kpi_summary",
            "search_events_timeline",
            "get_treatment_records",
            "get_reproduction_status",
            "get_milk_quality_trend",
            "get_economics_snapshot",
        }
        assert names == expected


class TestGetCowHistory4821:
    """Returns all events for Звёздочка including mastitis episode."""

    def test_returns_dict_with_rows(self, rich_store):
        result = execute_tool("get_animal_profile", {"cow_id": "4821", "days_back": 60}, rich_store)
        assert isinstance(result, dict)
        assert "rows" in result

    def test_includes_mastitis_in_health_events(self, rich_store):
        result = execute_tool("get_animal_profile", {"cow_id": "4821", "days_back": 70}, rich_store)
        he = result["rows"]["health_events"]
        types = [e["event_type"] for e in he]
        assert "mastitis" in types, f"No mastitis event found. Got: {types}"

    def test_includes_milkings(self, rich_store):
        result = execute_tool("get_animal_profile", {"cow_id": "4821", "days_back": 30}, rich_store)
        milkings = result["rows"]["milkings"]
        assert len(milkings) > 0, "No milking records for Звёздочка"

    def test_includes_treatments(self, rich_store):
        result = execute_tool("get_animal_profile", {"cow_id": "4821", "days_back": 30}, rich_store)
        treatments = result["rows"]["treatments"]
        assert len(treatments) > 0, "No treatment records for Звёздочка"

    def test_unknown_cow_returns_empty_rows(self, rich_store):
        result = execute_tool("get_animal_profile", {"cow_id": "NONEXISTENT_999"}, rich_store)
        assert isinstance(result, dict)
        # All sub-lists should be empty
        for key, val in result["rows"].items():
            assert val == [], f"Expected empty {key} for unknown cow, got {val}"


class TestSearchEventsByType:
    """Filter by event type works correctly."""

    def test_mastitis_filter(self, rich_store):
        result = execute_tool(
            "search_events_timeline",
            {"event_types": ["mastitis"]},
            rich_store,
        )
        rows = result["rows"]
        for row in rows:
            assert row["type"] == "mastitis", f"Got non-mastitis type: {row['type']}"

    def test_treatment_filter(self, rich_store):
        result = execute_tool(
            "search_events_timeline",
            {"event_types": ["treatment"]},
            rich_store,
        )
        rows = result["rows"]
        assert len(rows) > 0
        for row in rows:
            assert row["type"] == "treatment"

    def test_date_range_filter(self, rich_store):
        date_from = (datetime.date(2026, 4, 22) - datetime.timedelta(days=5)).isoformat()
        date_to = datetime.date(2026, 4, 22).isoformat()
        result = execute_tool(
            "search_events_timeline",
            {"event_types": ["health"], "date_from": date_from, "date_to": date_to},
            rich_store,
        )
        # All results should be in the date window
        for row in result["rows"]:
            assert row["date"] >= date_from, f"Date {row['date']} before {date_from}"
            assert row["date"] <= date_to, f"Date {row['date']} after {date_to}"

    def test_cow_id_filter(self, rich_store):
        result = execute_tool(
            "search_events_timeline",
            {"event_types": ["health", "treatment"], "cow_ids": ["4821"]},
            rich_store,
        )
        for row in result["rows"]:
            assert row["cow_id"] == "4821", f"Got cow_id {row['cow_id']}, expected 4821"

    def test_all_returns_multiple_types(self, rich_store):
        result = execute_tool(
            "search_events_timeline",
            {"event_types": ["all"]},
            rich_store,
        )
        types_found = {r["type"] for r in result["rows"]}
        assert len(types_found) >= 2, f"Expected multiple event types, got {types_found}"

    def test_limit_respected(self, rich_store):
        result = execute_tool(
            "search_events_timeline",
            {"event_types": ["all"], "limit": 2},
            rich_store,
        )
        assert len(result["rows"]) <= 2

    def test_result_has_evidence_id(self, rich_store):
        result = execute_tool("search_events_timeline", {"event_types": ["health"]}, rich_store)
        for row in result["rows"]:
            assert "evidence_id" in row


class TestGetTreatmentRecordsActive:
    """5 active treatments must be found in the rich_store fixture."""

    def test_active_count_is_5(self, rich_store):
        result = execute_tool("get_treatment_records", {"status": "active"}, rich_store)
        rows = result["rows"]
        assert len(rows) == 5, f"Expected 5 active treatments, got {len(rows)}"

    def test_active_have_withdrawal_end_date(self, rich_store):
        result = execute_tool("get_treatment_records", {"status": "active"}, rich_store)
        for row in result["rows"]:
            assert row.get("withdrawal_end_date") is not None, (
                f"Treatment {row['treatment_id']} has no withdrawal_end_date"
            )
            assert row["in_withdrawal"] is True

    def test_completed_not_in_active(self, rich_store):
        result = execute_tool("get_treatment_records", {"status": "active"}, rich_store)
        ids = {r["treatment_id"] for r in result["rows"]}
        assert "TR_OLD_001" not in ids, "Completed treatment in active list"

    def test_all_returns_completed_too(self, rich_store):
        result = execute_tool("get_treatment_records", {"status": "all"}, rich_store)
        ids = {r["treatment_id"] for r in result["rows"]}
        assert "TR_OLD_001" in ids

    def test_cow_id_filter(self, rich_store):
        result = execute_tool(
            "get_treatment_records",
            {"status": "active", "cow_ids": ["4821"]},
            rich_store,
        )
        for row in result["rows"]:
            assert row["cow_id"] == "4821"


class TestGetReproductionStatusGroup:
    """Group-level aggregation returns rows for all group members."""

    def test_group_returns_cows_in_pen(self, rich_store):
        result = execute_tool(
            "get_reproduction_status",
            {"group_id": "PEN_LACT"},
            rich_store,
        )
        assert result["cow_count"] == 4, f"Expected 4 cows in PEN_LACT, got {result['cow_count']}"

    def test_rows_have_required_fields(self, rich_store):
        result = execute_tool("get_reproduction_status", {"group_id": "PEN_LACT"}, rich_store)
        for row in result["rows"]:
            assert "cow_id" in row
            assert "last_heat_date" in row
            assert "last_breeding_date" in row
            assert "preg_check_status" in row

    def test_specific_cow_ids(self, rich_store):
        result = execute_tool(
            "get_reproduction_status",
            {"cow_ids": ["4821", "9002"]},
            rich_store,
        )
        cow_ids = {r["cow_id"] for r in result["rows"]}
        assert cow_ids == {"4821", "9002"}


class TestGetMilkQualityTrend:
    """Milk quality trend returns correct structure."""

    def test_cow_level_returns_rows(self, rich_store):
        result = execute_tool(
            "get_milk_quality_trend",
            {"cow_id": "4821", "period": "14d"},
            rich_store,
        )
        assert len(result["rows"]) > 0
        assert result["cow_id"] == "4821"

    def test_rows_have_scc_k(self, rich_store):
        result = execute_tool(
            "get_milk_quality_trend",
            {"cow_id": "9002", "period": "7d"},
            rich_store,
        )
        for row in result["rows"]:
            assert "scc_k" in row


class TestGetEconomicsSnapshot:
    """Economics snapshot returns non-null cash flow."""

    def test_farm_level_snapshot(self, rich_store):
        result = execute_tool("get_economics_snapshot", {}, rich_store)
        assert "farm_daily_revenue_eur" in result or "daily_cash_flow_eur" in result

    def test_cow_level_snapshot(self, rich_store):
        result = execute_tool("get_economics_snapshot", {"cow_id": "4821"}, rich_store)
        assert result.get("cow_id") == "4821"
        assert "daily_cash_flow_eur" in result


class TestExecuteToolUnknown:
    def test_unknown_tool_returns_error(self, rich_store):
        result = execute_tool("nonexistent_tool", {}, rich_store)
        assert "error" in result
