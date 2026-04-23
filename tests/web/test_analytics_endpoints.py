from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    storage = tmp_path / "web_storage"
    artifacts = tmp_path / "artifacts"
    os.environ["GENOMEAI_PROJECT_ROOT"] = str(repo_root)
    os.environ["GENOMEAI_WEB_STORAGE"] = str(storage)
    os.environ["GENOMEAI_ARTIFACTS_ROOT"] = str(artifacts)
    os.environ["GENOMEAI_WEB_DISABLE_WORKER"] = "1"
    os.environ["GENOMEAI_WEB_SECRET"] = "test-secret"

    import web_cabinet.app as appmod
    importlib.reload(appmod)

    with TestClient(appmod.app) as c:
        # Seed demo farm data into the test SQLite DB
        from web_cabinet.db import connect, get_settings
        conn = connect(get_settings().db_path)
        try:
            _seed_demo_farm(conn)
        finally:
            conn.close()
        yield c


def _seed_demo_farm(conn) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO dm_farms(tenant_id, farm_id, farm_name) VALUES(?,?,?)",
        ("default", "DEMO_FARM_001", "Demo Farm 1"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO dm_farms(tenant_id, farm_id, farm_name) VALUES(?,?,?)",
        ("default", "DEMO_FARM_002", "Demo Farm 2"),
    )

    animals = [
        ("DEMO_COW_1001", "DEMO_FARM_001"),
        ("DEMO_COW_1002", "DEMO_FARM_001"),
        ("DEMO_COW_1003", "DEMO_FARM_001"),
        ("DEMO_COW_2001", "DEMO_FARM_001"),
        ("DEMO_COW_2002", "DEMO_FARM_001"),
        ("DEMO_COW_2003", "DEMO_FARM_001"),
        ("DEMO_COW_3001", "DEMO_FARM_002"),
        ("DEMO_COW_3002", "DEMO_FARM_002"),
        ("DEMO_COW_3003", "DEMO_FARM_002"),
    ]
    for animal_id, farm_id in animals:
        conn.execute(
            "INSERT OR IGNORE INTO dm_animals(tenant_id, animal_id, farm_id) VALUES(?,?,?)",
            ("default", animal_id, farm_id),
        )

    # Lactations (needed for days_open query)
    lactations = [
        ("LAC_DEMO_COW_1001_2", "DEMO_COW_1001", 2, "2025-01-10"),
        ("LAC_DEMO_COW_1002_2", "DEMO_COW_1002", 2, "2025-01-12"),
        ("LAC_DEMO_COW_1003_2", "DEMO_COW_1003", 2, "2025-01-15"),
        ("LAC_DEMO_COW_2001_2", "DEMO_COW_2001", 2, "2025-01-20"),
        ("LAC_DEMO_COW_2002_2", "DEMO_COW_2002", 2, "2025-01-22"),
        ("LAC_DEMO_COW_2003_2", "DEMO_COW_2003", 2, "2025-01-25"),
        ("LAC_DEMO_COW_3001_2", "DEMO_COW_3001", 2, "2025-01-28"),
        ("LAC_DEMO_COW_3002_2", "DEMO_COW_3002", 2, "2025-02-01"),
        ("LAC_DEMO_COW_3003_2", "DEMO_COW_3003", 2, "2025-02-05"),
    ]
    for lac_id, animal_id, lac_no, calving_date in lactations:
        conn.execute(
            """INSERT OR IGNORE INTO dm_lactations
               (tenant_id, lactation_id, animal_id, lactation_no, calving_date)
               VALUES(?,?,?,?,?)""",
            ("default", lac_id, animal_id, lac_no, calving_date),
        )

    # Milkings — 3 test dates × 9 cows = 27 records
    milkings = [
        ("MD_001_1", "DEMO_COW_1001", "LAC_DEMO_COW_1001_2", "2025-04-05", 32.6, 4.0, 3.2, 162000),
        ("MD_001_2", "DEMO_COW_1001", "LAC_DEMO_COW_1001_2", "2025-03-29", 32.2, 4.0, 3.2, 167000),
        ("MD_001_3", "DEMO_COW_1001", "LAC_DEMO_COW_1001_2", "2025-03-22", 31.8, 4.0, 3.2, 172000),
        ("MD_002_1", "DEMO_COW_1002", "LAC_DEMO_COW_1002_2", "2025-04-05", 33.7, 3.8, 3.25, 174000),
        ("MD_002_2", "DEMO_COW_1002", "LAC_DEMO_COW_1002_2", "2025-03-29", 33.3, 3.8, 3.25, 179000),
        ("MD_002_3", "DEMO_COW_1002", "LAC_DEMO_COW_1002_2", "2025-03-22", 32.9, 3.8, 3.25, 184000),
        ("MD_003_1", "DEMO_COW_1003", "LAC_DEMO_COW_1003_2", "2025-04-05", 31.4, 4.0, 3.15, 186000),
        ("MD_003_2", "DEMO_COW_1003", "LAC_DEMO_COW_1003_2", "2025-03-29", 31.0, 4.0, 3.15, 191000),
        ("MD_003_3", "DEMO_COW_1003", "LAC_DEMO_COW_1003_2", "2025-03-22", 30.6, 4.0, 3.15, 196000),
        ("MD_004_1", "DEMO_COW_2001", "LAC_DEMO_COW_2001_2", "2025-04-05", 32.3, 3.8, 3.2, 198000),
        ("MD_004_2", "DEMO_COW_2001", "LAC_DEMO_COW_2001_2", "2025-03-29", 31.9, 3.8, 3.2, 203000),
        ("MD_004_3", "DEMO_COW_2001", "LAC_DEMO_COW_2001_2", "2025-03-22", 31.5, 3.8, 3.2, 208000),
        ("MD_005_1", "DEMO_COW_2002", "LAC_DEMO_COW_2002_2", "2025-04-05", 33.5, 4.0, 3.25, 210000),
        ("MD_005_2", "DEMO_COW_2002", "LAC_DEMO_COW_2002_2", "2025-03-29", 33.1, 4.0, 3.25, 215000),
        ("MD_005_3", "DEMO_COW_2002", "LAC_DEMO_COW_2002_2", "2025-03-22", 32.7, 4.0, 3.25, 220000),
        ("MD_006_1", "DEMO_COW_2003", "LAC_DEMO_COW_2003_2", "2025-04-05", 31.1, 3.8, 3.15, 222000),
        ("MD_006_2", "DEMO_COW_2003", "LAC_DEMO_COW_2003_2", "2025-03-29", 30.7, 3.8, 3.15, 227000),
        ("MD_006_3", "DEMO_COW_2003", "LAC_DEMO_COW_2003_2", "2025-03-22", 30.3, 3.8, 3.15, 232000),
        ("MD_007_1", "DEMO_COW_3001", "LAC_DEMO_COW_3001_2", "2025-04-05", 32.5, 4.0, 3.2, 234000),
        ("MD_007_2", "DEMO_COW_3001", "LAC_DEMO_COW_3001_2", "2025-03-29", 32.1, 4.0, 3.2, 239000),
        ("MD_007_3", "DEMO_COW_3001", "LAC_DEMO_COW_3001_2", "2025-03-22", 31.7, 4.0, 3.2, 244000),
        ("MD_008_1", "DEMO_COW_3002", "LAC_DEMO_COW_3002_2", "2025-04-05", 33.6, 3.8, 3.25, 246000),
        ("MD_008_2", "DEMO_COW_3002", "LAC_DEMO_COW_3002_2", "2025-03-29", 33.2, 3.8, 3.25, 251000),
        ("MD_008_3", "DEMO_COW_3002", "LAC_DEMO_COW_3002_2", "2025-03-22", 32.8, 3.8, 3.25, 256000),
        ("MD_009_1", "DEMO_COW_3003", "LAC_DEMO_COW_3003_2", "2025-04-05", 30.8, 4.0, 3.15, 258000),
        ("MD_009_2", "DEMO_COW_3003", "LAC_DEMO_COW_3003_2", "2025-03-29", 30.4, 4.0, 3.15, 263000),
        ("MD_009_3", "DEMO_COW_3003", "LAC_DEMO_COW_3003_2", "2025-03-22", 30.0, 4.0, 3.15, 268000),
    ]
    for rec_id, animal_id, lac_id, dt, milk, fat, protein, scc in milkings:
        conn.execute(
            """INSERT OR IGNORE INTO dm_milkings_daily
               (tenant_id, record_id, animal_id, lactation_id, date, milk_kg,
                milking_count, fat_pct, protein_pct, scc_cells_ml)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            ("default", rec_id, animal_id, lac_id, dt, milk, 2, fat, protein, scc),
        )

    repro_events = [
        ("RE_001", "DEMO_COW_2001", "2025-03-18", "heat", None, "candidate"),
        ("RE_002", "DEMO_COW_2001", "2025-03-20", "insemination", None, "done"),
        ("RE_003", "DEMO_COW_2003", "2025-04-01", "preg_check_due", None, "due"),
        ("RE_004", "DEMO_COW_1002", "2025-04-04", "fresh", None, "event"),
        ("RE_005", "DEMO_COW_3003", "2025-03-30", "dry_off_due", None, "due"),
    ]
    for ev_id, animal_id, ev_date, ev_type, bull_id, result in repro_events:
        conn.execute(
            """INSERT OR IGNORE INTO dm_repro_events
               (tenant_id, repro_event_id, animal_id, event_date, event_type, bull_id, result)
               VALUES(?,?,?,?,?,?,?)""",
            ("default", ev_id, animal_id, ev_date, ev_type, bull_id, result),
        )

    health_events = [
        ("HE_001", "DEMO_COW_1002", "2025-04-04", "metritis", "medium"),
        ("HE_002", "DEMO_COW_2002", "2025-04-03", "lameness", "high"),
        ("HE_003", "DEMO_COW_3002", "2025-04-02", "mastitis", "medium"),
        ("HE_004", "DEMO_COW_3003", "2025-04-01", "ketosis_risk", "warn"),
    ]
    for ev_id, animal_id, ev_date, ev_type, severity in health_events:
        conn.execute(
            """INSERT OR IGNORE INTO dm_health_events
               (tenant_id, event_id, animal_id, event_date, event_type, severity)
               VALUES(?,?,?,?,?,?)""",
            ("default", ev_id, animal_id, ev_date, ev_type, severity),
        )

    conn.commit()


def _login(c: TestClient, username: str = "zootech", password: str = "zootech") -> None:
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303), f"login failed: {r.status_code}"


# ── /api/analytics/production ─────────────────────────────────────────────────

def test_production_returns_200(client: TestClient) -> None:
    _login(client)
    r = client.get("/api/analytics/production?start_date=2025-03-01&end_date=2025-04-30")
    assert r.status_code == 200


def test_production_schema_field(client: TestClient) -> None:
    _login(client)
    r = client.get("/api/analytics/production?start_date=2025-03-01&end_date=2025-04-30")
    assert r.json()["schema"] == "genomeai.api.analytics.production.v1"


def test_production_time_series_has_3_dates(client: TestClient) -> None:
    _login(client)
    r = client.get("/api/analytics/production?start_date=2025-03-01&end_date=2025-04-30")
    data = r.json()
    assert len(data["time_series"]) == 3
    dates = [p["date"] for p in data["time_series"]]
    assert "2025-03-22" in dates
    assert "2025-03-29" in dates
    assert "2025-04-05" in dates


def test_production_aggregation_9_animals_per_day(client: TestClient) -> None:
    """Each date has 9 milking records (one per cow)."""
    _login(client)
    r = client.get("/api/analytics/production?start_date=2025-03-01&end_date=2025-04-30")
    data = r.json()
    for point in data["time_series"]:
        assert point["n_records"] == 9


def test_production_avg_milk_within_range(client: TestClient) -> None:
    """Average milk should be between 30 and 35 kg."""
    _login(client)
    r = client.get("/api/analytics/production?start_date=2025-03-01&end_date=2025-04-30")
    data = r.json()
    for point in data["time_series"]:
        assert 30.0 <= point["avg_milk_kg"] <= 35.0


def test_production_ecm_computed(client: TestClient) -> None:
    """ECM must be present and positive when fat/protein are available."""
    _login(client)
    r = client.get("/api/analytics/production?start_date=2025-03-01&end_date=2025-04-30")
    data = r.json()
    for point in data["time_series"]:
        assert point["ecm_kg"] is not None
        assert point["ecm_kg"] > 0


def test_production_summary_total_records(client: TestClient) -> None:
    """27 total records across 3 dates × 9 cows."""
    _login(client)
    r = client.get("/api/analytics/production?start_date=2025-03-01&end_date=2025-04-30")
    data = r.json()
    assert data["summary"]["total_records"] == 27


def test_production_farm_filter(client: TestClient) -> None:
    """Filter by farm_id=DEMO_FARM_001 returns only 6 cows per date."""
    _login(client)
    r = client.get("/api/analytics/production?start_date=2025-03-01&end_date=2025-04-30&farm_id=DEMO_FARM_001")
    data = r.json()
    assert len(data["time_series"]) == 3
    for point in data["time_series"]:
        assert point["n_records"] == 6


def test_production_empty_range(client: TestClient) -> None:
    """Empty date range returns no time series but valid JSON."""
    _login(client)
    r = client.get("/api/analytics/production?start_date=2020-01-01&end_date=2020-01-31")
    data = r.json()
    assert r.status_code == 200
    assert data["time_series"] == []
    assert data["summary"]["total_records"] == 0


def test_production_requires_auth(client: TestClient) -> None:
    r = client.get("/api/analytics/production?start_date=2025-03-01&end_date=2025-04-30")
    assert r.status_code in (401, 403)


# ── /api/analytics/reproduction ───────────────────────────────────────────────

def test_reproduction_returns_200(client: TestClient) -> None:
    _login(client)
    r = client.get("/api/analytics/reproduction?start_date=2025-03-01&end_date=2025-04-30")
    assert r.status_code == 200


def test_reproduction_schema_field(client: TestClient) -> None:
    _login(client)
    r = client.get("/api/analytics/reproduction?start_date=2025-03-01&end_date=2025-04-30")
    assert r.json()["schema"] == "genomeai.api.analytics.reproduction.v1"


def test_reproduction_events_total(client: TestClient) -> None:
    """5 demo repro events fall in the range."""
    _login(client)
    r = client.get("/api/analytics/reproduction?start_date=2025-03-01&end_date=2025-04-30")
    data = r.json()
    assert data["events_total"] == 5


def test_reproduction_inseminations_count(client: TestClient) -> None:
    """1 insemination event in demo data."""
    _login(client)
    r = client.get("/api/analytics/reproduction?start_date=2025-03-01&end_date=2025-04-30")
    data = r.json()
    assert data["inseminations"] == 1


def test_reproduction_days_open_populated(client: TestClient) -> None:
    """days_open_by_lactation is populated when insemination + lactation data available."""
    _login(client)
    r = client.get("/api/analytics/reproduction?start_date=2025-03-01&end_date=2025-04-30")
    data = r.json()
    # DEMO_COW_2001 was inseminated 2025-03-20, calved 2025-01-20 → 59 days open
    assert len(data["days_open_by_lactation"]) >= 1
    entry = data["days_open_by_lactation"][0]
    assert entry["n_animals"] >= 1
    assert entry["avg_days_open"] == pytest.approx(59.0, abs=1.0)


def test_reproduction_vwp_default(client: TestClient) -> None:
    _login(client)
    r = client.get("/api/analytics/reproduction?start_date=2025-03-01&end_date=2025-04-30")
    assert r.json()["vwp_days"] == 50


def test_reproduction_requires_auth(client: TestClient) -> None:
    r = client.get("/api/analytics/reproduction?start_date=2025-03-01&end_date=2025-04-30")
    assert r.status_code in (401, 403)


# ── /api/analytics/health ─────────────────────────────────────────────────────

def test_health_returns_200(client: TestClient) -> None:
    _login(client)
    r = client.get("/api/analytics/health?start_date=2025-03-01&end_date=2025-04-30")
    assert r.status_code == 200


def test_health_schema_field(client: TestClient) -> None:
    _login(client)
    r = client.get("/api/analytics/health?start_date=2025-03-01&end_date=2025-04-30")
    assert r.json()["schema"] == "genomeai.api.analytics.health.v1"


def test_health_events_total(client: TestClient) -> None:
    """4 health events in demo data."""
    _login(client)
    r = client.get("/api/analytics/health?start_date=2025-03-01&end_date=2025-04-30")
    data = r.json()
    assert data["events_total"] == 4


def test_health_mastitis_count(client: TestClient) -> None:
    """1 mastitis event in demo data."""
    _login(client)
    r = client.get("/api/analytics/health?start_date=2025-03-01&end_date=2025-04-30")
    data = r.json()
    assert data["mastitis_count"] == 1


def test_health_breakdown_all_types_present(client: TestClient) -> None:
    """All 4 distinct event types present in breakdown."""
    _login(client)
    r = client.get("/api/analytics/health?start_date=2025-03-01&end_date=2025-04-30")
    data = r.json()
    types = {item["event_type"] for item in data["health_issues_breakdown"]}
    assert types == {"mastitis", "metritis", "lameness", "ketosis_risk"}


def test_health_breakdown_pct_sums_to_100(client: TestClient) -> None:
    _login(client)
    r = client.get("/api/analytics/health?start_date=2025-03-01&end_date=2025-04-30")
    data = r.json()
    total_pct = sum(item["pct"] for item in data["health_issues_breakdown"])
    assert abs(total_pct - 100.0) < 0.1


def test_health_empty_range(client: TestClient) -> None:
    _login(client)
    r = client.get("/api/analytics/health?start_date=2020-01-01&end_date=2020-12-31")
    data = r.json()
    assert r.status_code == 200
    assert data["events_total"] == 0
    assert data["mastitis_count"] == 0
    assert data["health_issues_breakdown"] == []


def test_health_requires_auth(client: TestClient) -> None:
    r = client.get("/api/analytics/health?start_date=2025-03-01&end_date=2025-04-30")
    assert r.status_code in (401, 403)
