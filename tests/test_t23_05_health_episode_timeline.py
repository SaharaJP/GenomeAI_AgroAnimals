from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from core.health import build_health_episode_snapshot
from core.health.treatment_journal import start_treatment_course_use_case
from core.infra.web_db import init_db
from core.workflow.outcomes import record_completion_outcome_use_case
from core.workflow.worklists import create_worklist_use_case


def _seed_input_dir(tmp_path: Path) -> Path:
    input_dir = tmp_path / 'input'
    input_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {'tenant_id': 'default', 'animal_id': 'A1001', 'farm_id': 'F1', 'site_id': 'S1', 'current_pen_id': 'P1', 'current_pen_name': 'Hospital'},
    ]).to_csv(input_dir / 'dm_animals.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'animal_id': 'A1001', 'farm_id': 'F1', 'lactation_id': 'L1', 'calving_date': '2026-02-01', 'parity': 2, 'lactation_status': 'active'},
    ]).to_csv(input_dir / 'dm_lactations.csv', index=False)
    return input_dir


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_t23_05_health_episode_groups_health_treatment_alert_worklist_and_outcome(tmp_path: Path) -> None:
    input_dir = _seed_input_dir(tmp_path)
    pd.DataFrame([
        {'tenant_id': 'default', 'event_id': 'HE1', 'animal_id': 'A1001', 'event_date': '2026-03-10', 'event_type': 'mastitis', 'severity': 'high', 'notes': 'SCC rise'},
    ]).to_csv(input_dir / 'dm_health_events.csv', index=False)

    conn = _conn()
    conn.execute(
        """
        INSERT INTO alerts_v2(
          alert_id, tenant_id, created_at, updated_at, alert_type, title, source, cause, confidence,
          object_type, object_id, status, attachments_json, why_json, what_to_do_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            'AL1', 'default', '2026-03-10T08:00:00+00:00', '2026-03-10T08:00:00+00:00',
            'mastitis_risk', 'Mastitis check', 'health', 'mastitis follow-up', 0.92,
            'animal', 'A1001', 'acknowledged', '[]', '{}', '[]'
        ),
    )
    conn.commit()

    course = start_treatment_course_use_case(
        conn,
        tenant_id='default',
        user_id=1,
        username='vet',
        role='Vet',
        animal_id='A1001',
        treatment_type='mastitis',
        diagnosis_label='mastitis',
        start_date='2026-03-10',
        drug_name='DrugA',
        linked_alert_id='AL1',
        linked_health_event_id='HE1',
        farm_id='F1',
        site_id='S1',
        pen_id='P1',
        data_version='dv1',
        request_id='req-start',
    )
    work = create_worklist_use_case(
        conn=conn,
        tenant_id='default',
        worklist_type='health_follow_up',
        user_id=1,
        username='vet',
        role='Vet',
        title='Mastitis follow-up',
        priority=1,
        due_at='2026-03-12',
        object_type='animal',
        object_id='A1001',
        related_alert='AL1',
        linked_source_facts=[{'label': 'family', 'text': 'mastitis event'}],
        why={'summary': 'Need review', 'expected_effect': 'Resolve mastitis episode'},
        what_to_do=[{'action': 'Check udder'}],
        data_version='dv1',
        request_id='req-work',
    )
    record_completion_outcome_use_case(
        conn=conn,
        tenant_id='default',
        worklist_id=str(work['worklist_id']),
        user_id=1,
        username='vet',
        role='Vet',
        outcome_status='done',
        reason_code='COMPLETED',
        comment='resolved',
        request_id='req-outcome',
    )

    snap = build_health_episode_snapshot(
        input_dir=input_dir,
        conn=conn,
        tenant_id='default',
        asof_date=date(2026, 3, 20),
        animal_id='A1001',
        limit=50,
    )
    assert snap['summary']['episodes_n'] == 1
    episode = snap['episodes'][0]
    assert episode['family'] == 'mastitis'
    assert 'HE1' in episode['linked_health_event_ids']
    assert str(course['course_id']) in episode['linked_treatment_course_ids']
    assert 'AL1' in episode['linked_alert_ids']
    assert str(work['worklist_id']) in episode['linked_worklist_ids']
    assert episode['linked_outcome_ids']
    assert episode['state'] in {'resolved', 'monitoring', 'active', 'blocked'}
    assert any('treatments связаны' in x for x in (episode['linking_explanation'] or []))
    assert any(item['kind'] == 'worklist' for item in episode['timeline'])
    assert any(item['kind'] == 'outcome' for item in episode['timeline'])


def test_t23_05_health_episode_gap_rule_splits_episodes(tmp_path: Path) -> None:
    input_dir = _seed_input_dir(tmp_path)
    pd.DataFrame([
        {'tenant_id': 'default', 'event_id': 'HE1', 'animal_id': 'A1001', 'event_date': '2026-01-01', 'event_type': 'mastitis', 'severity': 'medium', 'notes': ''},
        {'tenant_id': 'default', 'event_id': 'HE2', 'animal_id': 'A1001', 'event_date': '2026-02-15', 'event_type': 'mastitis', 'severity': 'medium', 'notes': ''},
    ]).to_csv(input_dir / 'dm_health_events.csv', index=False)
    conn = _conn()
    snap = build_health_episode_snapshot(
        input_dir=input_dir,
        conn=conn,
        tenant_id='default',
        asof_date=date(2026, 2, 20),
        animal_id='A1001',
        family='mastitis',
        limit=50,
    )
    assert snap['summary']['episodes_n'] == 2
    ids = [e['episode_id'] for e in snap['episodes']]
    assert ids[0] != ids[1]


def test_t23_05_page_and_docs_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    page = (root / 'streamlit_app' / 'pages' / '53_Health_Episode_Timeline.py').read_text(encoding='utf-8')
    helper = (root / 'streamlit_app' / 'health_episode_timeline.py').read_text(encoding='utf-8')
    doc = (root / 'docs' / 'health_episode_timeline.md').read_text(encoding='utf-8')
    assert 'Health episode timeline' in page
    assert 'Open animal' in page and 'Open group' in page and 'Open worklists' in page and 'Open reports' in page
    assert 'build_health_episode_snapshot' in helper
    assert 'health events' in doc.lower() and 'treatments' in doc.lower() and 'outcomes' in doc.lower()
