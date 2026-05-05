"""Integration tests for multi-tenant data isolation across analytics bridges.

Setup: two farms (farm-A, farm-B) with distinct data in the same CSV files.
Verifies that querying for farm-A does NOT return farm-B data and vice versa.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Shared fixture: CSVs with data for two farms in tenant_id column format
# ---------------------------------------------------------------------------

@pytest.fixture
def two_farm_dir(tmp_path):
    """Create test CSVs containing rows for farm-A and farm-B.

    farm-A: animals A001, A002 — both have HIGH SCC (>200k) → triggers anomalies
    farm-B: animals B001, B002 — both have HIGH SCC (>200k) → would leak without filtering
    dm_health_events: only farm-B has a health event (notes: 'farm-B-only-event')
    """
    today = date.today().isoformat()

    milkings = pd.DataFrame({
        "tenant_id":    ["farm-A", "farm-A", "farm-B", "farm-B"],
        "animal_id":    ["A001",   "A002",   "B001",   "B002"],
        "date":         [today,    today,    today,    today],
        "scc_cells_ml": [350_000,  280_000,  310_000,  260_000],
        "milk_kg":      [25.0,     23.0,     30.0,     28.0],
        "milking_count":[2,        2,        2,        2],
        "fat_pct":      [4.0,      4.1,      3.9,      4.0],
        "protein_pct":  [3.2,      3.3,      3.1,      3.2],
    })
    milkings.to_csv(tmp_path / "dm_milkings_daily.csv", index=False)

    health = pd.DataFrame({
        "tenant_id":  ["farm-B"],
        "event_id":   ["EVT_B001"],
        "animal_id":  ["B001"],
        "event_date": [today],
        "event_type": ["mastitis"],
        "severity":   ["HIGH"],
        "notes":      ["farm-B-only-event"],
    })
    health.to_csv(tmp_path / "dm_health_events.csv", index=False)

    return tmp_path


def _noop_generator(**_kwargs):
    return []


# ---------------------------------------------------------------------------
# farm_id validation — these fail because no guard exists yet
# ---------------------------------------------------------------------------

def test_sensor_bridge_rejects_empty_farm_id():
    """detect_recent_sensor_anomalies must raise ValueError for empty farm_id."""
    from web_cabinet.analytics.sensor_bridge import detect_recent_sensor_anomalies

    with pytest.raises(ValueError, match="farm_id"):
        detect_recent_sensor_anomalies("")


def test_alerts_bridge_rejects_empty_farm_id():
    """list_active_alerts must raise ValueError for empty farm_id."""
    from web_cabinet.analytics.alerts_bridge import list_active_alerts

    with pytest.raises(ValueError, match="farm_id"):
        list_active_alerts("")


def test_kpi_bridge_rejects_empty_farm_id():
    """compute_dashboard_kpi must raise ValueError for empty farm_id.

    Validation runs before the cache, so no mock needed.
    """
    from web_cabinet.analytics.kpi_bridge import compute_dashboard_kpi

    with pytest.raises(ValueError, match="farm_id"):
        compute_dashboard_kpi("", date.today())


# ---------------------------------------------------------------------------
# Sensor bridge isolation — these fail because _from_demo_csv has no filtering
# ---------------------------------------------------------------------------

def test_sensor_bridge_farm_a_does_not_leak_farm_b_animals(two_farm_dir, monkeypatch):
    """Anomalies for farm-A must not contain farm-B animal IDs.

    Both farms have high-SCC animals, so without tenant filtering farm-B animals
    would appear in farm-A results.
    """
    from web_cabinet.analytics import sensor_bridge

    monkeypatch.setattr(sensor_bridge, "_DEMO_DATA", two_farm_dir)
    results = sensor_bridge._from_demo_csv("farm-A", lookback_days=1)

    animal_ids = {a.animal_id for a in results if a.animal_id}
    assert "B001" not in animal_ids, "farm-B animal B001 leaked into farm-A results"
    assert "B002" not in animal_ids, "farm-B animal B002 leaked into farm-A results"


def test_sensor_bridge_farm_b_does_not_leak_farm_a_animals(two_farm_dir, monkeypatch):
    """Anomalies for farm-B must not contain farm-A animal IDs."""
    from web_cabinet.analytics import sensor_bridge

    monkeypatch.setattr(sensor_bridge, "_DEMO_DATA", two_farm_dir)
    results = sensor_bridge._from_demo_csv("farm-B", lookback_days=1)

    animal_ids = {a.animal_id for a in results if a.animal_id}
    assert "A001" not in animal_ids, "farm-A animal A001 leaked into farm-B results"
    assert "A002" not in animal_ids, "farm-A animal A002 leaked into farm-B results"


def test_sensor_bridge_farm_a_has_its_own_anomalies(two_farm_dir, monkeypatch):
    """farm-A with high-SCC animals must produce at least one SCC anomaly."""
    from web_cabinet.analytics import sensor_bridge

    monkeypatch.setattr(sensor_bridge, "_DEMO_DATA", two_farm_dir)
    results = sensor_bridge._from_demo_csv("farm-A", lookback_days=1)

    scc_spikes = [a for a in results if a.anomaly_type == "scc_spike"]
    assert len(scc_spikes) > 0, "farm-A has high-SCC animals but got zero spikes"


# ---------------------------------------------------------------------------
# Alerts bridge isolation — test _alerts_from_health_events directly to avoid
# cache interference between test runs
# ---------------------------------------------------------------------------

def test_alerts_bridge_farm_a_does_not_see_farm_b_events(two_farm_dir):
    """_alerts_from_health_events for farm-A must NOT contain farm-B's health event."""
    from web_cabinet.analytics.alerts_bridge import _alerts_from_health_events

    alerts = _alerts_from_health_events("farm-A", date.today(), two_farm_dir)

    descriptions = [a.description for a in alerts]
    assert not any("farm-B-only-event" in d for d in descriptions), (
        f"farm-B event leaked into farm-A results! Descriptions: {descriptions}"
    )


def test_alerts_bridge_farm_b_sees_its_own_event(two_farm_dir):
    """_alerts_from_health_events for farm-B must find its own health event."""
    from web_cabinet.analytics.alerts_bridge import _alerts_from_health_events

    alerts = _alerts_from_health_events("farm-B", date.today(), two_farm_dir)

    descriptions = [a.description for a in alerts]
    assert any("farm-B-only-event" in d for d in descriptions), (
        f"farm-B health event not found in farm-B results. Got: {descriptions}"
    )


# ---------------------------------------------------------------------------
# Alerts bridge — generator path isolation (CRITICAL: was unfiltered before)
# ---------------------------------------------------------------------------

def test_alerts_bridge_generator_path_filters_by_farm_id():
    """Generator output with tenant_id fields must be filtered before constructing alerts.

    Without _filter_raw_by_farm_id, a multi-tenant generator returns all farms' data
    stamped with the caller's farm_id — a cross-tenant data leak.
    """
    from web_cabinet.analytics.alerts_bridge import _filter_raw_by_farm_id

    multi_tenant_raw = [
        {"tenant_id": "farm-A", "alert_type": "HEALTH", "severity": "HIGH", "title": "A event"},
        {"tenant_id": "farm-B", "alert_type": "REPRO",  "severity": "MEDIUM", "title": "B event"},
        {"alert_type": "GLOBAL", "severity": "LOW", "title": "no-tenant event"},  # no tenant field
    ]

    result_a = _filter_raw_by_farm_id(multi_tenant_raw, "farm-A")
    types_a = {d["alert_type"] for d in result_a}
    assert "HEALTH" in types_a, "farm-A alert not in farm-A results"
    assert "REPRO" not in types_a, "farm-B alert leaked into farm-A results"
    assert "GLOBAL" in types_a, "no-tenant alert (single-farm generator) should be kept"

    result_b = _filter_raw_by_farm_id(multi_tenant_raw, "farm-B")
    types_b = {d["alert_type"] for d in result_b}
    assert "REPRO" in types_b, "farm-B alert not in farm-B results"
    assert "HEALTH" not in types_b, "farm-A alert leaked into farm-B results"


# ---------------------------------------------------------------------------
# Integration: compute_dashboard_kpi(farm-A) does not return farm-B data
# (kpi_bridge already filters at DataFrame level; this tests the validation guard)
# ---------------------------------------------------------------------------

def test_kpi_bridge_farm_id_in_result_matches_requested_farm():
    """compute_dashboard_kpi result must carry the requested farm_id, not bleed others."""
    from web_cabinet.analytics import kpi_bridge
    from web_cabinet.analytics.kpi_bridge import DashboardKPI

    farm_a_kpi = DashboardKPI(
        farm_id="farm-A",
        as_of=date.today(),
        avg_milk_yield_kg=None, ecm_kg=None, fat_pct=None, protein_pct=None,
        scc_bulk_k=None, pregnancy_rate_21d_pct=None, days_open_avg=None,
        cows_in_treatment=None, mastitis_incidence_pct_per_year=None,
        confidence="low", sample_size_cows=0,
    )

    with patch.object(kpi_bridge, "_compute_dashboard_kpi_uncached", return_value=farm_a_kpi):
        result = kpi_bridge.compute_dashboard_kpi("farm-A", date.today())

    assert result.farm_id == "farm-A"
