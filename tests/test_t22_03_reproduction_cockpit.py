from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from core.reproduction import build_reproduction_cockpit_snapshot, build_reproduction_worklists_snapshot, sync_reproduction_worklists_use_case
from streamlit_app.reproduction_cockpit import build_breakdown_table, build_repro_animals_table, load_reproduction_cockpit_snapshot
from web_cabinet.db import init_db


@pytest.fixture()
def conn() -> sqlite3.Connection:
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture()
def repro_input_dir(tmp_path: Path) -> Path:
    base = tmp_path
    pd.DataFrame(
        [
            {'tenant_id': 'default', 'farm_id': 'F1', 'site_id': 'S1', 'animal_id': 'A1', 'status': 'active', 'current_pen_id': 'P1'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'site_id': 'S1', 'animal_id': 'A2', 'status': 'active', 'current_pen_id': 'P1'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'site_id': 'S1', 'animal_id': 'A3', 'status': 'active', 'current_pen_id': 'P1'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'site_id': 'S1', 'animal_id': 'A4', 'status': 'active', 'current_pen_id': 'P2'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'site_id': 'S1', 'animal_id': 'A5', 'status': 'active', 'current_pen_id': 'P2'},
        ]
    ).to_csv(base / 'dm_animals.csv', index=False)
    pd.DataFrame(
        [
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A1', 'lactation_id': 'L1', 'calving_date': '2025-12-01'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A2', 'lactation_id': 'L2', 'calving_date': '2025-12-01'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A3', 'lactation_id': 'L3', 'calving_date': '2025-12-01'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A4', 'lactation_id': 'L4', 'calving_date': '2025-12-01'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A5', 'lactation_id': 'L5', 'calving_date': '2025-12-01'},
        ]
    ).to_csv(base / 'dm_lactations.csv', index=False)
    pd.DataFrame(
        [
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A2', 'event_type': 'heat', 'event_date': '2026-05-04', 'result': '', 'technician': 'tech1', 'bull_id': '', 'method': ''},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A3', 'event_type': 'insemination', 'event_date': '2026-04-20', 'result': '', 'technician': 'tech1', 'bull_id': 'B1', 'method': 'synch'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A3', 'event_type': 'preg_check', 'event_date': '2026-05-01', 'result': 'positive', 'technician': 'tech1', 'bull_id': 'B1', 'method': 'synch'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A4', 'event_type': 'insemination', 'event_date': '2026-02-01', 'result': '', 'technician': 'tech2', 'bull_id': 'B2', 'method': 'natural'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A4', 'event_type': 'preg_check', 'event_date': '2026-02-25', 'result': 'negative', 'technician': 'tech2', 'bull_id': 'B2', 'method': 'natural'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A4', 'event_type': 'insemination', 'event_date': '2026-03-01', 'result': '', 'technician': 'tech2', 'bull_id': 'B2', 'method': 'natural'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A4', 'event_type': 'preg_check', 'event_date': '2026-03-28', 'result': 'negative', 'technician': 'tech2', 'bull_id': 'B2', 'method': 'natural'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A5', 'event_type': 'insemination', 'event_date': '2026-04-10', 'result': '', 'technician': 'tech1', 'bull_id': 'B1', 'method': 'synch'},
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


def test_t22_03_build_reproduction_cockpit_snapshot_returns_kpis_and_breakdowns(repro_input_dir: Path) -> None:
    snapshot = build_reproduction_cockpit_snapshot(input_dir=repro_input_dir, asof_date=date(2026, 5, 5), period_days=90)
    kpis = dict(snapshot['kpis'])
    assert round(float(kpis['conception_rate']), 4) == round(1 / 3, 4)
    assert int(kpis['repeat_breeders_n']) == 1
    assert int(kpis['services_n']) == 3

    by_tech = list(snapshot['breakdowns']['by_technician'])
    assert by_tech[0]['dimension'] == 'technician'
    vals = {str(r['value']): int(r['services_n']) for r in by_tech}
    assert vals['tech1'] == 2
    assert vals['tech2'] == 1

    by_bull = {str(r['value']): int(r['services_n']) for r in snapshot['breakdowns']['by_bull']}
    assert by_bull['B1'] == 2
    assert by_bull['B2'] == 1

    by_protocol = {str(r['value']): int(r['services_n']) for r in snapshot['breakdowns']['by_protocol']}
    assert by_protocol['synch'] == 2
    assert by_protocol['natural'] == 1

    animal_rows = list(snapshot['animals'])
    a4 = next(row for row in animal_rows if str(row['animal_id']) == 'A4')
    assert a4['repeat_breeder_flag'] is True
    assert a4['due_action'] in {'Recheck / повторно проверить', 'Смотреть на охоту', 'Проверять на стельность', 'Осеменять', 'Dry-off'}


def test_t22_03_cockpit_links_to_materialized_repro_worklists(conn: sqlite3.Connection, repro_input_dir: Path) -> None:
    wl_snapshot = build_reproduction_worklists_snapshot(
        input_dir=repro_input_dir,
        asof_date=date(2026, 5, 5),
        conn=conn,
        tenant_id='default',
        animal_id='A2',
    )
    rows = list(wl_snapshot['items'])
    assert rows
    sync_reproduction_worklists_use_case(
        conn=conn,
        tenant_id='default',
        rows=rows,
        user_id=11,
        username='zootech',
        role='Zootech',
        data_version='dv_repro',
        request_id='REQ-REPRO-COCKPIT',
    )
    snapshot = build_reproduction_cockpit_snapshot(
        input_dir=repro_input_dir,
        asof_date=date(2026, 5, 5),
        conn=conn,
        tenant_id='default',
        animal_id='A2',
        period_days=90,
    )
    animals = list(snapshot['animals'])
    assert len(animals) == 1
    assert str(animals[0]['materialized_worklist_id']).strip()
    assert animals[0]['due_action'] == 'Осеменять'


def test_t22_03_helper_tables_are_user_facing(repro_input_dir: Path) -> None:
    snapshot = load_reproduction_cockpit_snapshot(input_dir=repro_input_dir, asof_date=date(2026, 5, 5), period_days=90)
    df_break = build_breakdown_table(snapshot['breakdowns']['by_technician'])
    df_animals = build_repro_animals_table(snapshot['animals'])
    assert {'value', 'services_n', 'conception_rate'}.issubset(set(df_break.columns))
    assert {'animal_id', 'group', 'repro_state', 'due_action'}.issubset(set(df_animals.columns))


def test_t22_03_docs_pages_and_configs_reference_reproduction_cockpit() -> None:
    doc = Path('docs/reproduction_cockpit.md').read_text(encoding='utf-8')
    page = Path('streamlit_app/pages/46_Reproduction_Cockpit.py').read_text(encoding='utf-8')
    helper = Path('streamlit_app/reproduction_cockpit.py').read_text(encoding='utf-8')
    ia = Path('configs/ui/ia_v3.yaml').read_text(encoding='utf-8')
    home = Path('configs/ui/home_pages_v1.yaml').read_text(encoding='utf-8')
    assumptions = Path('docs/assumptions.md').read_text(encoding='utf-8')

    assert 'Reproduction analytics cockpit' in page
    assert 'build_reproduction_cockpit_snapshot' in helper
    assert 'Open repro worklists' in page
    assert 'Open decisions' in page
    assert 'reproduction_cockpit' in ia
    assert 'reproduction_cockpit' in home
    assert 'T22-03 — reproduction cockpit' in assumptions
    assert 'pregnancy_rate' in doc
