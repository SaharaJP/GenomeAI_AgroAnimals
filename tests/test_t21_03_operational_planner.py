from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from core.operational.animal_events import append_animal_event
from core.workflow import AlertCreate, build_operational_planner_snapshot, create_alert
from core.workflow.worklists import create_worklist_use_case
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


def _seed_worklist(conn: sqlite3.Connection) -> str:
    created = create_worklist_use_case(
        conn=conn,
        tenant_id='default',
        worklist_type='vet',
        title='Проверить treatment outcome',
        priority=1,
        due_at='2026-03-30T08:00:00+00:00',
        owner_user_id=22,
        assignee_team='team-health',
        confidence=0.81,
        object_type='animal',
        object_id='AN-001',
        linked_source_facts=[{'label': 'Signal', 'text': 'mastitis_risk'}, {'effect_text': 'Снижение риска осложнений.'}],
        why={'expected_effect': 'Снижение риска осложнений.'},
        what_to_do=[{'action': 'inspect'}],
        data_version='dv_t21_03',
        user_id=99,
        username='seed',
        role='Vet',
        request_id='REQ-WL',
    )
    return str(created['worklist_id'])


def _seed_alert(conn: sqlite3.Connection) -> str:
    return create_alert(
        conn,
        tenant_id='default',
        a=AlertCreate(
            alert_type='QC.MILK_QUALITY',
            title='SCC выше порога',
            source='rules',
            cause='scc_high',
            confidence=0.66,
            object_type='animal',
            object_id='AN-002',
            deadline='2026-03-31T09:00:00+00:00',
            owner_user_id=22,
            attachments=[],
            why={'expected_effect': 'Снижение потерь по качеству молока.'},
            what_to_do=[{'action': 'check_milk', 'expected_effect': 'Снижение потерь по качеству молока.'}],
            data_version='dv_t21_03',
            qc_run='qc_t21_03',
            model_version='mdl_t21_03',
            scoring_run='score_t21_03',
            report_version='report_t21_03',
            dedupe_key='alert:AN-002:scc',
        ),
    )


def _seed_follow_up(conn: sqlite3.Connection) -> str:
    return append_animal_event(
        conn,
        tenant_id='default',
        event={
            'animal_id': 'AN-003',
            'event_type': 'custom_operational_event',
            'event_ts': '2026-03-31T07:00:00+00:00',
            'actor_type': 'user',
            'actor_user_id': 11,
            'actor_username': 'zootech',
            'source': 'manual_ui',
            'reason_code': 'CUSTOM_OTHER',
            'data_version': 'dv_t21_03',
            'payload': {
                'follow_up_kind': 'preg_check_follow_up',
                'due_date': '2026-04-01',
                'assignee_role': 'Zootech',
                'comment': 'Контроль через 1 день',
            },
        },
        audit_user_id=11,
        audit_username='zootech',
        audit_role='Zootech',
    )


def _make_input_dir(tmp_path: Path) -> Path:
    input_dir = tmp_path / 'target_v2'
    input_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {'animal_id': 'AN-010', 'event_date': '2026-03-31', 'event_type': 'heat', 'result': ''},
        {'animal_id': 'AN-011', 'event_date': '2026-02-24', 'event_type': 'insemination', 'result': ''},
    ]).to_csv(input_dir / 'dm_repro_events.csv', index=False)
    pd.DataFrame([
        {'treatment_id': 'TR-1', 'animal_id': 'AN-020', 'start_date': '2026-03-28', 'end_date': '2026-03-31', 'withdrawal_end_date': '2026-04-01', 'diagnosis': 'mastitis', 'drug_name': 'abx'},
        {'treatment_id': 'TR-2', 'animal_id': 'AN-021', 'start_date': '2026-03-25', 'end_date': '2026-03-30', 'withdrawal_end_date': '2026-03-30', 'diagnosis': 'lameness', 'drug_name': 'nsaid'},
    ]).to_csv(input_dir / 'dm_treatments.csv', index=False)
    return input_dir


def test_t21_03_build_operational_planner_snapshot_collects_existing_objects(conn: sqlite3.Connection, tmp_path: Path) -> None:
    _seed_worklist(conn)
    _seed_alert(conn)
    _seed_follow_up(conn)
    input_dir = _make_input_dir(tmp_path)

    snapshot = build_operational_planner_snapshot(
        conn,
        tenant_id='default',
        today_iso='2026-03-31',
        data_version='dv_t21_03',
        input_dir=input_dir,
        role=None,
        owner_user_id=None,
        assignee_team=None,
        view_mode='manager',
        include_sources=['alerts', 'worklists', 'follow_ups', 'reproduction_cycles', 'treatments'],
        q=None,
        limit_per_bucket=50,
    )

    assert snapshot['summary']['items_total'] >= 6
    assert snapshot['summary']['by_source']['worklist'] >= 1
    assert snapshot['summary']['by_source']['alert'] >= 1
    assert snapshot['summary']['by_source']['follow_up'] >= 1
    assert snapshot['summary']['by_source']['reproduction_cycle'] >= 2
    assert snapshot['summary']['by_source']['treatment'] >= 2

    overdue_ids = {str(x['planner_item_id']) for x in snapshot['buckets']['overdue']}
    today_ids = {str(x['planner_item_id']) for x in snapshot['buckets']['today']}
    tomorrow_ids = {str(x['planner_item_id']) for x in snapshot['buckets']['tomorrow']}
    assert any(pid.startswith('worklist:') for pid in overdue_ids)
    assert any(pid.startswith('alert:') for pid in today_ids)
    assert any(pid.startswith('follow_up:') for pid in tomorrow_ids)
    assert any(pid.startswith('treatment:') for pid in tomorrow_ids)

    bucket_titles = {str(x['title']) for x in snapshot['buckets']['today'] + snapshot['buckets']['this_week']}
    assert 'Окно осеменения' in bucket_titles
    assert 'Проверить стельность' in bucket_titles

    assert snapshot['expected_load']['items_total'] == snapshot['summary']['items_total']
    assert snapshot['expected_load']['load_units_total'] > 0


def test_t21_03_planner_filters_executor_queue_and_reports_bottlenecks(conn: sqlite3.Connection, tmp_path: Path) -> None:
    _seed_worklist(conn)
    _seed_alert(conn)
    _seed_follow_up(conn)
    input_dir = _make_input_dir(tmp_path)

    snapshot = build_operational_planner_snapshot(
        conn,
        tenant_id='default',
        today_iso='2026-03-31',
        data_version='dv_t21_03',
        input_dir=input_dir,
        role='Vet',
        owner_user_id=22,
        assignee_team='team-health',
        view_mode='executor',
        include_sources=['alerts', 'worklists', 'follow_ups', 'reproduction_cycles', 'treatments'],
        q='treatment',
        limit_per_bucket=50,
    )

    assert snapshot['summary']['items_total'] >= 1
    assert all(str(x.get('assignee_team') or '') == 'team-health' for x in snapshot['all_items'])
    assert all((x.get('owner_user_id') in (22, None)) for x in snapshot['all_items'])
    assert all('treatment' in ' '.join([
        str(x.get('title') or ''),
        str(x.get('expected_effect') or ''),
        ' '.join(list(x.get('linked_facts_preview') or [])),
    ]).lower() for x in snapshot['all_items'])

    by_team = snapshot['expected_load']['by_team']
    assert by_team and by_team[0]['assignee_team'] == 'team-health'
    assert snapshot['bottlenecks']


def test_t21_03_docs_and_page_wiring_present() -> None:
    doc = Path('docs/operational_planner.md').read_text(encoding='utf-8')
    assumptions = Path('docs/assumptions.md').read_text(encoding='utf-8')
    helper = Path('streamlit_app/operational_planner.py').read_text(encoding='utf-8')
    page = Path('streamlit_app/pages/44_Operational_Planner.py').read_text(encoding='utf-8')
    workflow_init = Path('src/core/workflow/__init__.py').read_text(encoding='utf-8')
    workflow_planner = Path('src/core/workflow/planner.py').read_text(encoding='utf-8')
    ia_cfg = Path('configs/ui/ia_v3.yaml').read_text(encoding='utf-8')
    home_cfg = Path('configs/ui/home_pages_v1.yaml').read_text(encoding='utf-8')

    assert '# Operational planner' in doc
    assert '## T21-03 — operational planner' in assumptions
    assert 'build_operational_planner_snapshot' in helper
    assert 'Планировщик смены / дня / недели' in page
    assert 'time-bucket planner' in page.lower()
    assert 'build_operational_planner_snapshot' in workflow_init
    assert 'def build_operational_planner_snapshot' in workflow_planner
    assert 'key: operational_planner' in ia_cfg
    assert '- operational_planner' in home_cfg
