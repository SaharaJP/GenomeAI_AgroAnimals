from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.infra.web_db import init_db
from core.workflow import append_worklist_comment_use_case, create_worklist_use_case, get_worklist
from streamlit_app.mobile_worklists import build_mobile_worklist_cards, classify_mobile_round, filter_mobile_worklists, mobile_round_counts, worklist_comment_rows


@pytest.fixture()
def conn() -> sqlite3.Connection:
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    try:
        yield conn
    finally:
        conn.close()



def _seed(conn: sqlite3.Connection, *, worklist_type: str, object_type: str, object_id: str, title: str, facts: list[str]) -> dict[str, str]:
    created = create_worklist_use_case(
        conn=conn,
        tenant_id='default',
        worklist_type=worklist_type,
        title=title,
        priority=2,
        due_at='2026-04-02T08:00:00+00:00',
        assignee_team='team-health' if worklist_type in {'vet', 'health_follow_up', 'milk_quality'} else 'team-repro',
        confidence=0.8,
        object_type=object_type,
        object_id=object_id,
        linked_source_facts=[{'text': fact} for fact in facts],
        why={'expected_effect': 'Keep execution compact and safe.'},
        data_version='dv_t25_02',
        user_id=7,
        username='seed',
        role='Vet',
        request_id=f'seed-{worklist_type}-{object_id}',
    )
    row = get_worklist(conn, tenant_id='default', worklist_id=str(created['worklist_id'])) or {}
    return dict(row)



def test_t25_02_mobile_round_classifier_and_cards_keep_due_facts_and_context(conn: sqlite3.Connection) -> None:
    vet = _seed(conn, worklist_type='vet', object_type='animal', object_id='AN-1', title='Check mastitis risk', facts=['SCC high', 'Milk drop'])
    repro = _seed(conn, worklist_type='reproduction', object_type='animal', object_id='AN-2', title='Preg check due', facts=['preg check due'])
    group = _seed(conn, worklist_type='movement', object_type='group', object_id='PEN-1', title='Group round PEN-1', facts=['pen occupancy high'])

    rows = [vet, repro, group]
    assert classify_mobile_round(vet) == 'vet'
    assert classify_mobile_round(repro) == 'repro'
    assert classify_mobile_round(group) == 'group'

    counts = mobile_round_counts(rows)
    assert counts['focus'] == 3
    assert counts['vet'] == 1
    assert counts['repro'] == 1
    assert counts['group'] == 1

    filtered = filter_mobile_worklists(rows, round_key='vet', bucket='focus')
    cards = build_mobile_worklist_cards(filtered, today_iso='2026-04-02')
    assert len(cards) == 1
    assert cards[0]['subtitle'].startswith('P2')
    assert 'due=' in cards[0]['due_context']
    assert cards[0]['object_label'] == 'animal:AN-1'
    assert cards[0]['facts'] == ['SCC high', 'Milk drop']



def test_t25_02_append_mobile_comment_preserves_worklist_and_audit(conn: sqlite3.Connection) -> None:
    row = _seed(conn, worklist_type='health_follow_up', object_type='animal', object_id='AN-3', title='Follow-up', facts=['temperature elevated'])
    wid = str(row['worklist_id'])
    res = append_worklist_comment_use_case(
        conn=conn,
        tenant_id='default',
        worklist_id=wid,
        user_id=22,
        username='vet_mobile',
        role='Vet',
        comment='seen during morning round',
        source='mobile_worklists',
        request_id='rq-mobile-comment',
    )
    assert res['comment']['comment'] == 'seen during morning round'
    stored = get_worklist(conn, tenant_id='default', worklist_id=wid) or {}
    comments = worklist_comment_rows(stored)
    assert comments[0]['comment'] == 'seen during morning round'
    actions = [row['action'] for row in conn.execute("SELECT action FROM audit_log WHERE action LIKE 'worklist.%' ORDER BY id").fetchall()]
    assert 'worklist.comment' in actions



def test_t25_02_page_docs_and_navigation_reference_mobile_worklists() -> None:
    root = Path(__file__).resolve().parents[1]
    page = (root / 'streamlit_app' / 'pages' / '58_Mobile_Worklists.py').read_text(encoding='utf-8')
    helper = (root / 'streamlit_app' / 'mobile_worklists.py').read_text(encoding='utf-8')
    docs = (root / 'docs' / 'mobile_worklists.md').read_text(encoding='utf-8')
    assumptions = (root / 'docs' / 'assumptions.md').read_text(encoding='utf-8')
    ia_cfg = (root / 'configs' / 'ui' / 'ia_v3.yaml').read_text(encoding='utf-8')
    mobile_shell = (root / 'streamlit_app' / 'mobile_shell_pwa.py').read_text(encoding='utf-8')

    assert 'Mobile worklists' in page
    assert 'Done' in page
    assert '+1 day' in page
    assert 'Comment' in page
    assert 'Open' in page
    assert 'build_mobile_worklist_cards' in page
    assert 'classify_mobile_round' in helper
    assert 'attachments' in docs.lower()
    assert 'bounded cowside actions' in assumptions.lower()
    assert 'pages/58_Mobile_Worklists.py' in ia_cfg
    assert 'mobile_worklists' in mobile_shell
