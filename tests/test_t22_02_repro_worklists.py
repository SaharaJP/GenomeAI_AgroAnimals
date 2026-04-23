from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from core.operational.animal_events import list_animal_events_for_animal
from core.reproduction import (
    batch_complete_reproduction_worklists_use_case,
    build_reproduction_worklists_snapshot,
    bulk_comment_reproduction_animals_use_case,
    sync_reproduction_worklists_use_case,
)
from core.workflow import get_worklist, list_completion_outcomes
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
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A1', 'lactation_id': 'L1', 'calving_date': '2026-01-01'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A2', 'lactation_id': 'L2', 'calving_date': '2026-01-01'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A3', 'lactation_id': 'L3', 'calving_date': '2026-01-01'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A4', 'lactation_id': 'L4', 'calving_date': '2026-01-01'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A5', 'lactation_id': 'L5', 'calving_date': '2025-07-01'},
        ]
    ).to_csv(base / 'dm_lactations.csv', index=False)
    pd.DataFrame(
        [
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A2', 'event_type': 'heat', 'event_date': '2026-05-04', 'result': ''},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A3', 'event_type': 'insemination', 'event_date': '2026-03-25', 'result': ''},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A4', 'event_type': 'insemination', 'event_date': '2026-02-01', 'result': ''},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A4', 'event_type': 'insemination', 'event_date': '2026-03-01', 'result': ''},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A4', 'event_type': 'preg_check', 'event_date': '2026-04-01', 'result': 'negative'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A5', 'event_type': 'insemination', 'event_date': '2025-10-01', 'result': ''},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A5', 'event_type': 'preg_check', 'event_date': '2025-11-01', 'result': 'positive'},
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


def test_t22_02_build_snapshot_returns_operational_repro_due_actions(repro_input_dir: Path) -> None:
    snapshot = build_reproduction_worklists_snapshot(input_dir=repro_input_dir, asof_date=date(2026, 5, 5))
    rows = list(snapshot['items'])
    mapping = {str(row['animal_id']): str(row['action_type']) for row in rows}
    assert mapping == {
        'A1': 'watch_heat',
        'A2': 'inseminate',
        'A3': 'preg_check',
        'A4': 'recheck',
        'A5': 'dry_off',
    }
    a3 = next(row for row in rows if row['animal_id'] == 'A3')
    assert a3['due_at'] == '2026-04-29'
    assert a3['worklist_type'] == 'reproduction'
    assert a3['assignee_team'] == 'team-repro'
    assert a3['source_facts_preview']
    assert snapshot['summary']['by_action']['preg_check'] == 1


def test_t22_02_sync_materializes_general_worklists_with_dedupe(conn: sqlite3.Connection, repro_input_dir: Path) -> None:
    snapshot = build_reproduction_worklists_snapshot(
        input_dir=repro_input_dir,
        asof_date=date(2026, 5, 5),
        conn=conn,
        tenant_id='default',
        pen_id='P1',
    )
    rows = list(snapshot['items'])
    assert len(rows) == 3

    res1 = sync_reproduction_worklists_use_case(
        conn=conn,
        tenant_id='default',
        rows=rows[:2],
        user_id=11,
        username='zootech',
        role='Zootech',
        data_version='dv_repro',
        request_id='REQ-REPRO-SYNC-1',
    )
    assert res1['summary']['created_n'] == 2
    first_id = str(res1['created'][0]['worklist_id'])
    wl = get_worklist(conn, tenant_id='default', worklist_id=first_id)
    assert wl is not None
    assert wl['worklist_type'] == 'reproduction'
    assert wl['assignee_team'] == 'team-repro'
    assert wl['object_type'] == 'animal'

    res2 = sync_reproduction_worklists_use_case(
        conn=conn,
        tenant_id='default',
        rows=rows[:2],
        user_id=11,
        username='zootech',
        role='Zootech',
        data_version='dv_repro',
        request_id='REQ-REPRO-SYNC-2',
    )
    assert res2['summary']['created_n'] == 0
    assert res2['summary']['existing_n'] == 2


def test_t22_02_batch_completion_and_bulk_comments_use_common_loops(conn: sqlite3.Connection, repro_input_dir: Path) -> None:
    snapshot = build_reproduction_worklists_snapshot(input_dir=repro_input_dir, asof_date=date(2026, 5, 5))
    selected = list(snapshot['items'])[:2]
    sync_res = sync_reproduction_worklists_use_case(
        conn=conn,
        tenant_id='default',
        rows=selected,
        user_id=22,
        username='repro',
        role='Zootech',
        data_version='dv_repro',
        request_id='REQ-REPRO-SYNC-3',
    )
    worklist_ids = [str(row['worklist_id']) for row in sync_res['created']]

    batch_res = batch_complete_reproduction_worklists_use_case(
        conn=conn,
        tenant_id='default',
        worklist_ids=worklist_ids,
        user_id=22,
        username='repro',
        role='Zootech',
        outcome_status='done',
        reason='COMPLETED_AS_PLANNED',
        comment='completed in batch',
        request_id='REQ-REPRO-BATCH-DONE',
    )
    assert batch_res['summary']['completed_n'] == 2
    outcomes = list_completion_outcomes(conn, tenant_id='default', worklist_type='reproduction', limit=20)
    assert outcomes['total'] == 2

    wl = get_worklist(conn, tenant_id='default', worklist_id=worklist_ids[0])
    assert wl is not None
    assert wl['latest_outcome_status'] == 'done'

    comment_res = bulk_comment_reproduction_animals_use_case(
        conn=conn,
        tenant_id='default',
        animal_ids=['A1', 'A2'],
        comment='bulk repro note',
        user_id=22,
        username='repro',
        role='Zootech',
        event_ts='2026-05-05T10:00:00Z',
        data_version='dv_repro',
        request_id='REQ-REPRO-BULK-COMMENT',
    )
    assert comment_res['summary']['added_n'] == 2
    events = list_animal_events_for_animal(conn, tenant_id='default', animal_id='A1', limit=20)
    assert any(str(row.get('event_type') or '') == 'comment' for row in events['events'])


def test_t22_02_docs_and_pages_reference_repro_worklists() -> None:
    doc = Path('docs/repro_worklists.md').read_text(encoding='utf-8')
    page = Path('streamlit_app/pages/45_Reproduction_Worklists.py').read_text(encoding='utf-8')
    helper = Path('streamlit_app/repro_worklists.py').read_text(encoding='utf-8')
    group_page = Path('streamlit_app/pages/14_Group_Profile.py').read_text(encoding='utf-8')
    animal_page = Path('streamlit_app/pages/15_Animal_Profile.py').read_text(encoding='utf-8')
    assumptions = Path('docs/assumptions.md').read_text(encoding='utf-8')

    assert 'Reproduction worklists' in page
    assert 'build_reproduction_worklists_snapshot' in helper
    assert 'Materialize selected as worklists' in page
    assert 'Batch complete materialized' in page
    assert 'Bulk comment selected animals' in page
    assert 'group.quick.goto.repro' in group_page
    assert 'animal.quick.goto.repro' in animal_page
    assert 'T22-02 — repro worklists' in assumptions
    assert 'core.reproduction.worklists' in doc
