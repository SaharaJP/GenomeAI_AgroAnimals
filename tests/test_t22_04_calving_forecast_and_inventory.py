from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from core.reproduction import build_calving_forecast_snapshot
from streamlit_app.calving_forecast import (
    build_animals_table,
    build_breakdown_table,
    build_bucket_table,
    build_event_table,
    build_weekly_table,
    load_calving_forecast_snapshot,
)


@pytest.fixture()
def forecast_input_dir(tmp_path: Path) -> Path:
    base = tmp_path
    pd.DataFrame(
        [
            {'tenant_id': 'default', 'farm_id': 'F1', 'site_id': 'S1', 'animal_id': 'A1', 'status': 'active', 'current_pen_id': 'P1'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'site_id': 'S1', 'animal_id': 'A2', 'status': 'active', 'current_pen_id': 'P1'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'site_id': 'S1', 'animal_id': 'A3', 'status': 'active', 'current_pen_id': 'P1'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'site_id': 'S2', 'animal_id': 'A4', 'status': 'active', 'current_pen_id': 'P2'},
        ]
    ).to_csv(base / 'dm_animals.csv', index=False)
    pd.DataFrame(
        [
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A1', 'lactation_id': 'L1', 'calving_date': '2025-07-01'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A2', 'lactation_id': 'L2', 'calving_date': '2025-07-01'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A3', 'lactation_id': 'L3', 'calving_date': '2025-07-01'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A4', 'lactation_id': 'L4', 'calving_date': '2025-07-01'},
        ]
    ).to_csv(base / 'dm_lactations.csv', index=False)
    pd.DataFrame(
        [
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A1', 'event_type': 'insemination', 'event_date': '2025-10-08', 'result': '', 'technician': 'tech1', 'bull_id': 'B1', 'method': 'synch'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A1', 'event_type': 'preg_check', 'event_date': '2025-11-15', 'result': 'positive', 'technician': 'tech1', 'bull_id': 'B1', 'method': 'synch'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A2', 'event_type': 'insemination', 'event_date': '2025-08-01', 'result': '', 'technician': 'tech1', 'bull_id': 'B2', 'method': 'natural'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A2', 'event_type': 'preg_check', 'event_date': '2025-09-10', 'result': 'positive', 'technician': 'tech1', 'bull_id': 'B2', 'method': 'natural'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A3', 'event_type': 'insemination', 'event_date': '2025-10-20', 'result': '', 'technician': 'tech2', 'bull_id': 'B3', 'method': 'synch'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A4', 'event_type': 'insemination', 'event_date': '2025-10-23', 'result': '', 'technician': 'tech3', 'bull_id': 'B4', 'method': 'protocol-x'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A4', 'event_type': 'preg_check', 'event_date': '2025-11-30', 'result': 'positive', 'technician': 'tech3', 'bull_id': 'B4', 'method': 'protocol-x'},
        ]
    ).to_csv(base / 'dm_repro_events.csv', index=False)
    pd.DataFrame(
        [
            {'tenant_id': 'default', 'pen_id': 'P1', 'pen_name': 'Group 1'},
            {'tenant_id': 'default', 'pen_id': 'P2', 'pen_name': 'Group 2'},
        ]
    ).to_csv(base / 'dm_pens.csv', index=False)
    pd.DataFrame(columns=['tenant_id', 'animal_id', 'to_pen_id', 'move_date']).to_csv(base / 'dm_pen_moves.csv', index=False)
    return base


@pytest.fixture()
def artifacts_root(tmp_path: Path) -> Path:
    root = tmp_path / 'artifacts'
    run_dir = root / 'dv_forecast' / 'economics_v2' / 'econ_run_1'
    run_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {'date': '2026-05-01', 'milk_price_rub_per_kg': 52.0},
    ]).to_csv(run_dir / 'economics_daily.csv', index=False)
    pd.DataFrame(columns=['date']).to_csv(run_dir / 'economics_monthly.csv', index=False)
    meta = root / 'dv_forecast' / 'metadata'
    meta.mkdir(parents=True, exist_ok=True)
    (meta / 'economics_v2_manifest.json').write_text('{"latest": "econ_run_1"}', encoding='utf-8')
    return root


def test_t22_04_build_calving_forecast_snapshot_returns_buckets_and_inventory(forecast_input_dir: Path, artifacts_root: Path) -> None:
    snapshot = build_calving_forecast_snapshot(
        input_dir=forecast_input_dir,
        asof_date=date(2026, 5, 1),
        data_version='dv_forecast',
        artifacts_root=artifacts_root,
    )
    summary = dict(snapshot['summary'])
    assert int(summary['projected_calvings_7d']) == 1
    assert int(summary['projected_calvings_30d']) == 1
    assert int(summary['projected_calvings_60d']) == 1
    assert int(summary['projected_calvings_90d']) == 4
    assert int(summary['projected_dry_offs_30d']) == 3
    assert float(summary['projected_replacements_90d']) > 1.2

    bucket_map = {int(r['bucket_days']): dict(r) for r in snapshot['bucket_rows']}
    assert int(bucket_map[30]['projected_dry_offs_n']) == 3
    assert int(bucket_map[90]['projected_calvings_n']) == 4

    inventory = dict(snapshot['inventory'])
    assert int((inventory['current_by_repro_state'] or {}).get('pregnant', 0)) == 3
    assert int((inventory['current_by_repro_state'] or {}).get('preg_check_due', 0)) == 1

    econ = dict(snapshot['economics'])
    assert econ['available'] is True
    assert float(econ['milk_price_rub_per_kg']) == 52.0
    assert float(econ['projected_replacement_value_90d_rub']) > 100000.0


def test_t22_04_filters_by_site_and_group(forecast_input_dir: Path) -> None:
    snap_site = build_calving_forecast_snapshot(
        input_dir=forecast_input_dir,
        asof_date=date(2026, 5, 1),
        site_id='S2',
    )
    assert int(snap_site['summary']['animals_total']) == 1
    assert int(snap_site['summary']['projected_calvings_90d']) == 1
    animals = list(snap_site['animals'])
    assert len(animals) == 1
    assert animals[0]['animal_id'] == 'A4'

    snap_pen = build_calving_forecast_snapshot(
        input_dir=forecast_input_dir,
        asof_date=date(2026, 5, 1),
        pen_id='P1',
    )
    assert int(snap_pen['summary']['animals_total']) == 3
    assert int(snap_pen['summary']['projected_calvings_90d']) == 3


def test_t22_04_helper_tables_are_user_facing(forecast_input_dir: Path, artifacts_root: Path) -> None:
    snapshot = load_calving_forecast_snapshot(
        input_dir=forecast_input_dir,
        asof_date=date(2026, 5, 1),
        data_version='dv_forecast',
        artifacts_root=artifacts_root,
    )
    df_bucket = build_bucket_table(snapshot['bucket_rows'])
    df_week = build_weekly_table(snapshot['weekly_rows'])
    df_events = build_event_table(snapshot['events'])
    df_animals = build_animals_table(snapshot['animals'])
    df_group = build_breakdown_table(snapshot['breakdowns']['by_group'])

    assert {'bucket_days', 'projected_calvings_n', 'projected_dry_offs_n'}.issubset(set(df_bucket.columns))
    assert {'week_start', 'projected_calvings_n', 'projected_replacements_est'}.issubset(set(df_week.columns))
    assert {'animal_id', 'event', 'due', 'bucket'}.issubset(set(df_events.columns))
    assert {'animal_id', 'projected_calving_date', 'projected_dry_off_date'}.issubset(set(df_animals.columns))
    assert {'value', 'projected_calvings_n', 'projected_replacements_est'}.issubset(set(df_group.columns))


def test_t22_04_docs_pages_and_configs_reference_calving_forecast() -> None:
    doc = Path('docs/calving_forecast_and_inventory.md').read_text(encoding='utf-8')
    page = Path('streamlit_app/pages/47_Calving_Forecast_And_Inventory.py').read_text(encoding='utf-8')
    helper = Path('streamlit_app/calving_forecast.py').read_text(encoding='utf-8')
    ia = Path('configs/ui/ia_v3.yaml').read_text(encoding='utf-8')
    home = Path('configs/ui/home_pages_v1.yaml').read_text(encoding='utf-8')
    assumptions = Path('docs/assumptions.md').read_text(encoding='utf-8')

    assert 'Calving forecast & projected herd inventory' in page
    assert 'build_calving_forecast_snapshot' in helper
    assert 'Open planner' in page
    assert 'Open economics' in page
    assert 'calving_forecast_inventory' in ia
    assert 'calving_forecast_inventory' in home
    assert 'T22-04 — calving forecast' in assumptions
    assert 'projected_replacements_est' in doc
