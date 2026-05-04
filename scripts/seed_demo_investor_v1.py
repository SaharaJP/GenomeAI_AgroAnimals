"""Seed dm_* tables from data/demo/investor_v1/ fixtures.

Handles column mapping between investor_v1 CSV/JSON and the dm_* table schemas.
Safe to re-run — truncates all dm_* tables before loading.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = REPO_ROOT / "data" / "demo" / "investor_v1"


def get_engine():
    dsn = os.environ.get("GENOMEAI_DB_DSN")
    if not dsn:
        dsn_file = os.environ.get("GENOMEAI_DB_DSN_FILE")
        if dsn_file:
            dsn = Path(dsn_file).read_text().strip()
    if not dsn:
        sys.exit("ERROR: GENOMEAI_DB_DSN or GENOMEAI_DB_DSN_FILE must be set")
    return create_engine(dsn)


def truncate_all(engine):
    # Truncate in CASCADE mode — clears all dm_* tables safely
    with engine.begin() as conn:
        conn.execute(text("""
            TRUNCATE
                dm_treatments, dm_milkings_daily, dm_testday, dm_sensors_daily,
                dm_repro_events, dm_pen_moves, dm_decisions, dm_health_events,
                dm_lactations, dm_animals, dm_animal_id_map, dm_master_animals,
                dm_identity_events, animal_events_v1, dm_pens, dm_feed_deliveries,
                dm_feed_rations, dm_sites, dm_alerts, dm_decisions,
                dm_economics_daily, dm_reports, dm_user_roles, dm_users, dm_roles,
                dm_prices, dm_bulls, scanner_insights, dm_farms
            CASCADE
        """))
    print("  truncated all dm_* tables")


def load_farms(engine):
    df = pd.read_csv(DEMO_DIR / "dm_farms.csv")
    # CSV: farm_id, farm_name, region, country, lat, lon, created_at, is_active
    # Table: tenant_id, farm_id, farm_name, country_code, timezone, currency, created_at, updated_at
    out = pd.DataFrame({
        "tenant_id": "default",
        "farm_id": df["farm_id"],
        "farm_name": df["farm_name"],
        "country_code": df["country"],
        "timezone": None,
        "currency": "EUR",
        "created_at": pd.to_datetime(df["created_at"], errors="coerce"),
        "updated_at": None,
    })
    out.to_sql("dm_farms", engine, if_exists="append", index=False)
    print(f"  dm_farms: {len(out)} rows")


def load_animals(engine):
    df = pd.read_csv(DEMO_DIR / "dm_animals.csv")
    # CSV: animal_id, farm_id, ear_tag, breed, sex, birth_date, is_alive, status
    # Table: tenant_id, animal_id, farm_id, site_id, current_pen_id, master_animal_id, external_id, sex, birth_date, breed, status
    out = pd.DataFrame({
        "tenant_id": "default",
        "animal_id": df["animal_id"].astype(str),
        "farm_id": df["farm_id"],
        "site_id": None,
        "current_pen_id": None,
        "master_animal_id": None,
        "external_id": df["ear_tag"].astype(str),
        "sex": df["sex"],
        "birth_date": pd.to_datetime(df["birth_date"], errors="coerce").dt.date,
        "breed": df["breed"],
        "status": df["status"],
        "created_at": None,
        "updated_at": None,
    })
    out.to_sql("dm_animals", engine, if_exists="append", index=False)
    print(f"  dm_animals: {len(out)} rows")


def load_lactations(engine):
    df = pd.read_csv(DEMO_DIR / "dm_lactations.csv")
    # CSV: animal_id, lactation_no, calving_date, dryoff_date, days_in_milk, milk_305d_kg, fat_pct, protein_pct
    # Table: tenant_id, lactation_id, animal_id, lactation_no, calving_date, dryoff_date, milk_305d_kg, calving_outcome
    out = pd.DataFrame({
        "tenant_id": "default",
        "lactation_id": "LAC_" + df["animal_id"].astype(str) + "_" + df["lactation_no"].astype(str),
        "animal_id": df["animal_id"].astype(str),
        "lactation_no": df["lactation_no"],
        "calving_date": pd.to_datetime(df["calving_date"], errors="coerce").dt.date,
        "dryoff_date": pd.to_datetime(df["dryoff_date"], errors="coerce").dt.date,
        "milk_305d_kg": df["milk_305d_kg"],
        "calving_outcome": None,
        "created_at": None,
        "updated_at": None,
    })
    out.to_sql("dm_lactations", engine, if_exists="append", index=False)
    print(f"  dm_lactations: {len(out)} rows")


def load_health_events(engine):
    # CSV already matches table schema: tenant_id, event_id, animal_id, event_date, event_type, severity, notes
    df = pd.read_csv(DEMO_DIR / "dm_health_events.csv")
    df["created_at"] = None
    df["updated_at"] = None
    df.to_sql("dm_health_events", engine, if_exists="append", index=False)
    print(f"  dm_health_events: {len(df)} rows")


def load_treatments(engine):
    # CSV already matches table schema: tenant_id, treatment_id, animal_id, start_date, end_date, treatment_type, reason_event_id, withdrawal_end_date
    df = pd.read_csv(DEMO_DIR / "dm_treatments.csv")
    df["created_at"] = None
    df["updated_at"] = None
    df.to_sql("dm_treatments", engine, if_exists="append", index=False)
    print(f"  dm_treatments: {len(df)} rows")


def load_milkings(engine):
    # Source: milk_yields.json — list of {record_id, animal_id, date, milk_kg, fat_pct, protein_pct, scc_cells_ml}
    data = json.loads((DEMO_DIR / "milk_yields.json").read_text())
    df = pd.DataFrame(data)
    # Table: tenant_id, record_id, animal_id, lactation_id, date, milk_kg, milking_count, fat_pct, protein_pct, scc_cells_ml
    out = pd.DataFrame({
        "tenant_id": "default",
        "record_id": df["record_id"],
        "animal_id": df["animal_id"].astype(str),
        "lactation_id": None,
        "date": pd.to_datetime(df["date"]).dt.date,
        "milk_kg": df["milk_kg"],
        "milking_count": None,
        "fat_pct": df["fat_pct"],
        "protein_pct": df["protein_pct"],
        "scc_cells_ml": df["scc_cells_ml"],
        "created_at": None,
        "updated_at": None,
    })
    # Load in chunks to avoid memory issues
    chunk_size = 5000
    total = 0
    for i in range(0, len(out), chunk_size):
        chunk = out.iloc[i : i + chunk_size]
        chunk.to_sql("dm_milkings_daily", engine, if_exists="append", index=False)
        total += len(chunk)
    print(f"  dm_milkings_daily: {total} rows")


def main():
    engine = get_engine()
    print("Seeding dm_* tables from investor_v1...")
    truncate_all(engine)
    load_farms(engine)
    load_animals(engine)
    load_lactations(engine)
    load_health_events(engine)
    load_treatments(engine)
    load_milkings(engine)
    print("Done.")

    # Quick verification
    with engine.connect() as conn:
        for table in ["dm_farms", "dm_animals", "dm_lactations", "dm_health_events", "dm_treatments", "dm_milkings_daily"]:
            n = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
            print(f"  {table}: {n}")


if __name__ == "__main__":
    main()
