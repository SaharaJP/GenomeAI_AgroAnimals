from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from core.reproduction import (
    append_breeding_decision_use_case,
    build_repro_mating_integration_snapshot,
    create_breeding_review_worklist_use_case,
    sync_reproduction_worklists_use_case,
)
from core.workflow import get_worklist
from streamlit_app.repro_mating_integration import (
    build_breeding_decision_queue_table,
    build_recommendations_table,
    load_repro_mating_integration_snapshot,
)
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
    base = tmp_path / 'input'
    base.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {'tenant_id': 'default', 'farm_id': 'F1', 'site_id': 'S1', 'animal_id': 'A1', 'status': 'active', 'current_pen_id': 'P1'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'site_id': 'S1', 'animal_id': 'A2', 'status': 'active', 'current_pen_id': 'P1'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'site_id': 'S1', 'animal_id': 'A3', 'status': 'active', 'current_pen_id': 'P2'},
        ]
    ).to_csv(base / 'dm_animals.csv', index=False)
    pd.DataFrame(
        [
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A1', 'lactation_id': 'L1', 'calving_date': '2026-01-01'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A2', 'lactation_id': 'L2', 'calving_date': '2026-01-01'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A3', 'lactation_id': 'L3', 'calving_date': '2026-01-01'},
        ]
    ).to_csv(base / 'dm_lactations.csv', index=False)
    pd.DataFrame(
        [
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A1', 'event_type': 'heat', 'event_date': '2026-05-04', 'result': '', 'technician': 'tech1', 'bull_id': '', 'method': ''},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A2', 'event_type': 'insemination', 'event_date': '2026-01-20', 'result': '', 'technician': 'tech2', 'bull_id': 'B9', 'method': 'natural'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A2', 'event_type': 'preg_check', 'event_date': '2026-02-15', 'result': 'negative', 'technician': 'tech2', 'bull_id': 'B9', 'method': 'natural'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A2', 'event_type': 'insemination', 'event_date': '2026-03-01', 'result': '', 'technician': 'tech2', 'bull_id': 'B9', 'method': 'natural'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A2', 'event_type': 'preg_check', 'event_date': '2026-04-01', 'result': 'negative', 'technician': 'tech2', 'bull_id': 'B9', 'method': 'natural'},
        ]
    ).to_csv(base / 'dm_repro_events.csv', index=False)
    pd.DataFrame(
        [
            {'tenant_id': 'default', 'pen_id': 'P1', 'pen_name': 'Group 1'},
            {'tenant_id': 'default', 'pen_id': 'P2', 'pen_name': 'Group 2'},
        ]
    ).to_csv(base / 'dm_pens.csv', index=False)
    pd.DataFrame(columns=['tenant_id', 'animal_id', 'to_pen_id', 'move_date']).to_csv(base / 'dm_pen_moves.csv', index=False)
    pd.DataFrame(
        [
            {'bull_id': 'B1', 'available': True, 'breed': 'HOL', 'origin': 'RU', 'dose_price_rub': 1200},
            {'bull_id': 'B2', 'available': False, 'breed': 'HOL', 'origin': 'RU', 'dose_price_rub': 900},
            {'bull_id': 'B3', 'available': False, 'breed': 'HOL', 'origin': 'BY', 'dose_price_rub': 800},
        ]
    ).to_csv(base / 'dm_bulls.csv', index=False)
    return base


@pytest.fixture()
def artifacts_root(tmp_path: Path) -> Path:
    root = tmp_path / 'artifacts'
    (root / 'dv1' / 'mating_plan' / 'mating_run_001').mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {'tenant_id': 'default', 'data_version': 'dv1', 'mating_plan_run': 'mating_run_001', 'pedigree_run': 'ped_run_001', 'farm_id': 'F1', 'cow_id': 'A1', 'bull_id': 'B1', 'rank': 1, 'score': 1.2, 'confidence': 'HIGH', 'reasons': 'Milk goal + low SCC', 'constraints_reason_code': 'OK', 'constraints_confidence': 'HIGH'},
            {'tenant_id': 'default', 'data_version': 'dv1', 'mating_plan_run': 'mating_run_001', 'pedigree_run': 'ped_run_001', 'farm_id': 'F1', 'cow_id': 'A1', 'bull_id': 'B2', 'rank': 2, 'score': 0.8, 'confidence': 'MEDIUM', 'reasons': 'Budget option', 'constraints_reason_code': 'OK', 'constraints_confidence': 'HIGH'},
        ]
    ).to_csv(root / 'dv1' / 'mating_plan' / 'mating_run_001' / 'mating_plan.csv', index=False)
    (root / 'dv1' / 'pedigree' / 'ped_run_001').mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {'cow_id': 'A1', 'bull_id': 'B1', 'allowed': True, 'reason_code': 'OK'},
            {'cow_id': 'A1', 'bull_id': 'B2', 'allowed': True, 'reason_code': 'OK'},
            {'cow_id': 'A2', 'bull_id': 'B2', 'allowed': False, 'reason_code': 'COMMON_ANCESTOR_WITHIN_N'},
            {'cow_id': 'A2', 'bull_id': 'B3', 'allowed': False, 'reason_code': 'COMMON_ANCESTOR_WITHIN_N'},
            {'cow_id': 'A3', 'bull_id': 'B2', 'allowed': True, 'reason_code': 'OK'},
            {'cow_id': 'A3', 'bull_id': 'B3', 'allowed': True, 'reason_code': 'OK'},
        ]
    ).to_csv(root / 'dv1' / 'pedigree' / 'ped_run_001' / 'inbreeding_constraints.csv', index=False)
    return root


def test_t22_05_build_snapshot_returns_pending_breeding_queue(conn: sqlite3.Connection, repro_input_dir: Path, artifacts_root: Path) -> None:
    snapshot = build_repro_mating_integration_snapshot(
        input_dir=repro_input_dir,
        artifacts_root=artifacts_root,
        data_version='dv1',
        asof_date=date(2026, 5, 5),
        conn=conn,
        tenant_id='default',
    )
    rows = list(snapshot['queue'])
    mapping = {str(r['animal_id']): str(r['decision_status']) for r in rows}
    assert mapping == {
        'A1': 'ready_for_decision',
        'A2': 'blocked_inbreeding',
        'A3': 'awaiting_timing_window',
    }
    a1 = next(r for r in rows if r['animal_id'] == 'A1')
    assert a1['pending_decision'] is True
    assert a1['mating_plan_run'] == 'mating_run_001'
    assert a1['pedigree_run'] == 'ped_run_001'
    assert len(a1['top_recommendations']) == 2
    assert a1['top_recommendations'][0]['bull_id'] == 'B1'

    a2 = next(r for r in rows if r['animal_id'] == 'A2')
    assert a2['constraints_summary']['status'] == 'blocked_inbreeding'
    assert a2['requires_approval'] is True

    a3 = next(r for r in rows if r['animal_id'] == 'A3')
    assert a3['decision_status_label']
    assert a3['requires_approval'] is True

    assert snapshot['summary']['ready_for_decision_n'] == 1
    assert snapshot['summary']['blocked_n'] == 1


def test_t22_05_append_breeding_decision_links_existing_worklist(conn: sqlite3.Connection, repro_input_dir: Path, artifacts_root: Path) -> None:
    snap = build_repro_mating_integration_snapshot(
        input_dir=repro_input_dir,
        artifacts_root=artifacts_root,
        data_version='dv1',
        asof_date=date(2026, 5, 5),
        conn=conn,
        tenant_id='default',
    )
    a1 = next(r for r in snap['queue'] if r['animal_id'] == 'A1')
    sync = sync_reproduction_worklists_use_case(
        conn=conn,
        tenant_id='default',
        rows=[a1],
        user_id=7,
        username='zootech',
        role='Zootech',
        data_version='dv1',
        request_id='REQ-SYNC-1',
    )
    worklist_id = str(sync['created'][0]['worklist_id'])

    res = append_breeding_decision_use_case(
        conn=conn,
        tenant_id='default',
        animal_id='A1',
        chosen_bull_id='B1',
        user_id=7,
        username='zootech',
        role='Zootech',
        reason='Выбираем топ-рекомендацию для текущего окна осеменения.',
        farm_id='F1',
        group_id='P1',
        data_version='dv1',
        mating_plan_run='mating_run_001',
        pedigree_run='ped_run_001',
        worklist_id=worklist_id,
        recommendation_id='mating_plan:mating_run_001:A1',
        recommendation_rank=1,
        override=False,
        approval_required=False,
        constraints={'status': 'ok'},
        source_versions={'data_version': 'dv1', 'mating_plan_run': 'mating_run_001', 'pedigree_run': 'ped_run_001'},
        source_facts=[{'label': 'Due action', 'text': 'Осеменять'}],
        request_id='REQ-BREED-DEC-1',
    )
    assert str(res['decision_id']).strip()
    wl = get_worklist(conn, tenant_id='default', worklist_id=worklist_id)
    assert wl is not None
    assert str(wl['linked_decision_id']) == str(res['decision_id'])

    snapshot2 = build_repro_mating_integration_snapshot(
        input_dir=repro_input_dir,
        artifacts_root=artifacts_root,
        data_version='dv1',
        asof_date=date(2026, 5, 5),
        conn=conn,
        tenant_id='default',
    )
    a1_after = next(r for r in snapshot2['queue'] if r['animal_id'] == 'A1')
    assert a1_after['decision_status'] == 'decision_recorded'


def test_t22_05_create_manager_review_worklist_and_helpers(conn: sqlite3.Connection, repro_input_dir: Path, artifacts_root: Path) -> None:
    snapshot = load_repro_mating_integration_snapshot(
        input_dir=repro_input_dir,
        artifacts_root=artifacts_root,
        data_version='dv1',
        asof_date=date(2026, 5, 5),
        conn=conn,
        tenant_id='default',
    )
    queue_df = build_breeding_decision_queue_table(snapshot['queue'])
    assert {'animal_id', 'decision_status', 'top_bull'}.issubset(set(queue_df.columns))
    a1 = next(r for r in snapshot['queue'] if r['animal_id'] == 'A1')
    recs_df = build_recommendations_table(a1['top_recommendations'])
    assert {'bull_id', 'rank', 'reasons'}.issubset(set(recs_df.columns))

    a2 = next(r for r in snapshot['queue'] if r['animal_id'] == 'A2')
    res = create_breeding_review_worklist_use_case(
        conn=conn,
        tenant_id='default',
        animal_id='A2',
        user_id=9,
        username='director',
        role='Director',
        title='Breeding review · A2',
        why={'decision_status': a2['decision_status'], 'constraints_summary': a2['constraints_summary']},
        linked_source_facts=a2['linked_source_facts'],
        due_at=str(a2['due_at'] or ''),
        farm_id='F1',
        group_id='P1',
        data_version='dv1',
        dedupe_key='breeding_review:A2:mating_run_001:blocked_inbreeding',
        request_id='REQ-BREED-REVIEW-1',
    )
    wl = get_worklist(conn, tenant_id='default', worklist_id=str(res['worklist_id']))
    assert wl is not None
    assert wl['worklist_type'] == 'manager_review'
    assert wl['object_type'] == 'animal'


def test_t22_05_docs_pages_and_configs_reference_repro_mating_integration() -> None:
    doc = Path('docs/repro_mating_integration.md').read_text(encoding='utf-8')
    page = Path('streamlit_app/pages/48_Repro_Mating_Integration.py').read_text(encoding='utf-8')
    helper = Path('streamlit_app/repro_mating_integration.py').read_text(encoding='utf-8')
    repro_page = Path('streamlit_app/pages/45_Reproduction_Worklists.py').read_text(encoding='utf-8')
    cockpit_page = Path('streamlit_app/pages/46_Reproduction_Cockpit.py').read_text(encoding='utf-8')
    ia = Path('configs/ui/ia_v3.yaml').read_text(encoding='utf-8')
    home = Path('configs/ui/home_pages_v1.yaml').read_text(encoding='utf-8')
    assumptions = Path('docs/assumptions.md').read_text(encoding='utf-8')

    assert 'Reproduction → Mating integration' in page
    assert 'pending breeding decision queue' in doc
    assert 'build_repro_mating_integration_snapshot' in helper
    assert 'Open repro→mating' in repro_page
    assert 'Open repro→mating' in cockpit_page
    assert 'repro_mating_integration' in ia
    assert 'repro_mating_integration' in home
    assert 'T22-05' in assumptions
