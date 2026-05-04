import pytest
from datetime import date
from unittest.mock import MagicMock

from web_cabinet.analytics.timeseries_bridge import (
    build_production_timeseries,
    build_health_timeseries,
    build_reproduction_timeseries,
)


def _make_conn(rows):
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    conn = MagicMock()
    conn.execute.return_value = cursor
    return conn


def test_production_timeseries_empty_db():
    conn = _make_conn([])
    result = build_production_timeseries(conn, farm_id="FARM_001", tenant_id="default", weeks=4)
    assert result["tab"] == "production"
    assert result["labels"] == []
    assert result["charts"]["milk_ecm"]["series"][0]["data"] == []


def test_production_timeseries_aggregates_weekly():
    r1 = MagicMock()
    r1.__getitem__ = lambda self, k: {"date": date(2025, 1, 6), "avg_milk": 30.0, "avg_fat": 4.0,
                                       "avg_protein": 3.3, "avg_scc": 150000.0}[k]
    r2 = MagicMock()
    r2.__getitem__ = lambda self, k: {"date": date(2025, 1, 7), "avg_milk": 28.0, "avg_fat": 3.9,
                                       "avg_protein": 3.2, "avg_scc": 160000.0}[k]
    conn = _make_conn([r1, r2])
    result = build_production_timeseries(conn, farm_id="FARM_001", tenant_id="default", weeks=4)
    assert len(result["labels"]) == 1
    assert len(result["charts"]["milk_ecm"]["series"]) == 2
    milk_val = result["charts"]["milk_ecm"]["series"][0]["data"][0]
    assert milk_val == pytest.approx(29.0, abs=0.5)


def test_production_timeseries_db_exception_returns_empty():
    conn = MagicMock()
    conn.execute.side_effect = Exception("connection refused")
    result = build_production_timeseries(conn, farm_id="FARM_001", tenant_id="default", weeks=4)
    assert result["tab"] == "production"
    assert result["labels"] == []


def test_production_timeseries_null_fat_protein():
    r1 = MagicMock()
    r1.__getitem__ = lambda self, k: {"date": date(2025, 1, 6), "avg_milk": 25.0,
                                       "avg_fat": None, "avg_protein": None, "avg_scc": None}[k]
    conn = _make_conn([r1])
    result = build_production_timeseries(conn, farm_id="FARM_001", tenant_id="default", weeks=4)
    assert len(result["labels"]) == 1
    milk_val = result["charts"]["milk_ecm"]["series"][0]["data"][0]
    assert milk_val == pytest.approx(25.0, abs=0.1)
    fat_val = result["charts"]["fat_protein"]["series"][0]["data"][0]
    assert fat_val == 0.0  # fallback when fat is None


def test_health_timeseries_empty_db():
    conn = _make_conn([])
    result = build_health_timeseries(conn, farm_id="FARM_001", tenant_id="default", weeks=4)
    assert result["tab"] == "health"
    assert result["labels"] == []
    assert "mastitis" in result["charts"]


def test_reproduction_timeseries_empty_db():
    conn = _make_conn([])
    result = build_reproduction_timeseries(conn, farm_id="FARM_001", tenant_id="default", weeks=26)
    assert result["tab"] == "reproduction"
    assert result["labels"] == []
    assert "inseminations" in result["charts"]
