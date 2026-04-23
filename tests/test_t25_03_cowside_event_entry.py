from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from core.infra.web_db import init_db
from core.operational import (
    CowsideEventEntryError,
    create_cowside_event_entry_use_case,
    get_cowside_event_template,
    list_cowside_event_templates,
    search_cowside_animals,
)
from core.workflow import get_worklist


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
def canonical_dir(tmp_path: Path) -> Path:
    root = tmp_path / 'artifacts' / 'dv_t25_03' / 'canonical'
    root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {'animal_id': 'A-100', 'status': 'active', 'breed': 'Holstein', 'sex': 'F', 'farm_id': 'farm-1', 'site_id': 'site-1', 'current_pen_id': 'P-1', 'current_pen_name': 'Fresh cows'},
        {'animal_id': 'A-200', 'status': 'pregnant', 'breed': 'Holstein', 'sex': 'F', 'farm_id': 'farm-1', 'site_id': 'site-1', 'current_pen_id': 'P-2', 'current_pen_name': 'Preg group'},
    ]).to_csv(root / 'dm_animals.csv', index=False)
    pd.DataFrame([
        {'animal_id': 'A-100', 'lactation_id': 'L1', 'parity': 2, 'calving_date': '2026-03-10', 'scc_cells_ml': 120000},
        {'animal_id': 'A-200', 'lactation_id': 'L2', 'parity': 3, 'calving_date': '2026-02-14', 'scc_cells_ml': 250000},
    ]).to_csv(root / 'dm_lactations.csv', index=False)
    return root


def test_t25_03_templates_are_bounded_and_role_filtered() -> None:
    vet = list_cowside_event_templates(role='Vet')
    zoo = list_cowside_event_templates(role='Zootech')
    assert any(row['key'] == 'treatment_started' for row in vet)
    assert all(row['event_type'] for row in vet)
    assert all(row['reason_code'] for row in vet)
    assert not any(row['key'] == 'treatment_started' for row in zoo)

    tpl = get_cowside_event_template(template_key='manual_note', role='Vet')
    assert tpl['event_type'] == 'manual_note'
    assert tpl['reason_code'] == 'MANUAL_NOTE_ADDED'



def test_t25_03_search_animals_reuses_safe_list_builder_snapshot(canonical_dir: Path) -> None:
    rows = search_cowside_animals(
        input_dir=canonical_dir,
        asof_date=pd.Timestamp('2026-04-02').date(),
        role='Vet',
        q='A-100',
        limit=10,
    )
    assert len(rows) == 1
    assert rows[0]['animal_id'] == 'A-100'
    assert 'Fresh cows' in rows[0]['label']



def test_t25_03_create_cowside_event_and_follow_up_keeps_audit_and_versions(conn: sqlite3.Connection) -> None:
    res = create_cowside_event_entry_use_case(
        conn=conn,
        tenant_id='default',
        animal_id='A-100',
        template_key='treatment_started',
        event_ts='2026-04-02T08:15:00+00:00',
        user_id=11,
        username='vet_mobile',
        role='Vet',
        comment='mastitis protocol step 1',
        create_follow_up=True,
        follow_up_due_at='2026-04-03',
        data_version='dv_t25_03',
        qc_run='qc_1',
        model_version='model_1',
        scoring_run='score_1',
        report_version='report_1',
        request_id='rq-cowside-1',
        farm_id='farm-1',
        site_id='site-1',
    )
    assert res['ok'] is True
    assert res['event_id']
    assert res['worklist_id']
    assert res['event']['payload']['entry_mode'] == 'cowside_entry'
    assert res['event']['payload']['template_key'] == 'treatment_started'
    assert res['event']['payload']['source_versions']['data_version'] == 'dv_t25_03'

    worklist = get_worklist(conn, tenant_id='default', worklist_id=str(res['worklist_id'])) or {}
    assert worklist['object_type'] == 'animal'
    assert worklist['object_id'] == 'A-100'
    assert worklist['data_version'] == 'dv_t25_03'
    assert worklist['qc_run'] == 'qc_1'
    assert worklist['model_version'] == 'model_1'
    assert worklist['scoring_run'] == 'score_1'
    assert worklist['report_version'] == 'report_1'
    assert any(item.get('event_id') == res['event_id'] for item in list(worklist.get('attachments') or []))

    actions = [row['action'] for row in conn.execute("SELECT action FROM audit_log ORDER BY id").fetchall()]
    assert 'animal_event.quick_entry.create' in actions
    assert 'worklist.create' in actions
    assert 'animal_event.cowside_entry.submit' in actions



def test_t25_03_create_without_follow_up_keeps_flow_bounded(conn: sqlite3.Connection) -> None:
    res = create_cowside_event_entry_use_case(
        conn=conn,
        tenant_id='default',
        animal_id='A-200',
        template_key='preg_check_positive',
        event_ts='2026-04-02T09:00:00+00:00',
        user_id=7,
        username='zootech_mobile',
        role='Zootech',
        comment='confirmed in pen 2',
        create_follow_up=False,
        data_version='dv_t25_03',
        request_id='rq-cowside-2',
    )
    assert res['worklist_id'] is None
    assert res['event']['reason_code'] == 'PREGNANCY_CONFIRMED'



def test_t25_03_invalid_template_and_page_docs_are_wired(conn: sqlite3.Connection) -> None:
    with pytest.raises(CowsideEventEntryError) as exc:
        create_cowside_event_entry_use_case(
            conn=conn,
            tenant_id='default',
            animal_id='A-100',
            template_key='does_not_exist',
            event_ts='2026-04-02T09:00:00+00:00',
            user_id=1,
            username='operator',
            role='Operator',
        )
    assert exc.value.code == 'template_not_found'

    root = Path(__file__).resolve().parents[1]
    page = (root / 'streamlit_app' / 'pages' / '59_Cowside_Event_Entry.py').read_text(encoding='utf-8')
    docs = (root / 'docs' / 'cowside_event_entry.md').read_text(encoding='utf-8')
    assumptions = (root / 'docs' / 'assumptions.md').read_text(encoding='utf-8')
    ia_cfg = (root / 'configs' / 'ui' / 'ia_v3.yaml').read_text(encoding='utf-8')
    mobile_shell = (root / 'streamlit_app' / 'mobile_shell_pwa.py').read_text(encoding='utf-8')

    assert 'Cowside event entry' in page
    assert 'create_cowside_event_entry_use_case' in page
    assert 'quick templates' in docs.lower()
    assert 'cowside event entry' in assumptions.lower()
    assert 'pages/59_Cowside_Event_Entry.py' in ia_cfg
    assert 'cowside_event_entry' in mobile_shell
