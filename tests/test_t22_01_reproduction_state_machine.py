from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from core.reproduction import build_reproduction_states_table, compute_reproduction_state, load_reproduction_state_snapshot
from streamlit_app.animal_profile_daily_use import build_animal_daily_use_context
from streamlit_app.group_profile_operational_hub import build_group_operational_context


class _Ctx:
    def __init__(self) -> None:
        self.artifacts_dir = Path('artifacts')


def _animal_row(status: str = 'active') -> dict:
    return {'animal_id': 'A-1', 'status': status, 'sex': 'F'}


def _lact_rows(calving_date: str = '2026-01-01', dryoff_date: str | None = None) -> pd.DataFrame:
    row = {'animal_id': 'A-1', 'lactation_id': 'L1', 'calving_date': calving_date}
    if dryoff_date:
        row['dryoff_date'] = dryoff_date
    return pd.DataFrame([row])


def _repro_rows(rows: list[dict]) -> pd.DataFrame:
    base = []
    for r in rows:
        item = {'animal_id': 'A-1', 'event_type': r['event_type'], 'event_date': r['event_date'], 'result': r.get('result', ''), 'bull_id': r.get('bull_id', '')}
        base.append(item)
    return pd.DataFrame(base)


def test_t22_01_state_machine_core_transitions_are_deterministic() -> None:
    fresh = compute_reproduction_state(
        animal_row=_animal_row(),
        lactation_rows=_lact_rows('2026-03-15'),
        repro_event_rows=pd.DataFrame(),
        operational_event_rows=None,
        asof_date=date(2026, 4, 1),
    )
    assert fresh['state'] == 'fresh'
    assert fresh['reason_code'] == 'REPRO_FRESH_AFTER_CALVING'

    eligible = compute_reproduction_state(
        animal_row=_animal_row(),
        lactation_rows=_lact_rows('2025-12-01'),
        repro_event_rows=pd.DataFrame(),
        operational_event_rows=None,
        asof_date=date(2026, 4, 1),
    )
    assert eligible['state'] == 'eligible'

    bred = compute_reproduction_state(
        animal_row=_animal_row(),
        lactation_rows=_lact_rows('2025-12-01'),
        repro_event_rows=_repro_rows([{'event_type': 'insemination', 'event_date': '2026-03-25'}]),
        operational_event_rows=None,
        asof_date=date(2026, 4, 1),
    )
    assert bred['state'] == 'bred'

    preg_due = compute_reproduction_state(
        animal_row=_animal_row(),
        lactation_rows=_lact_rows('2025-12-01'),
        repro_event_rows=_repro_rows([{'event_type': 'insemination', 'event_date': '2026-02-20'}]),
        operational_event_rows=None,
        asof_date=date(2026, 4, 1),
    )
    assert preg_due['state'] == 'preg_check_due'
    assert preg_due['dates']['next_preg_check_due_date'] == '2026-03-27'

    pregnant = compute_reproduction_state(
        animal_row=_animal_row(),
        lactation_rows=_lact_rows('2025-12-01'),
        repro_event_rows=_repro_rows([
            {'event_type': 'insemination', 'event_date': '2026-02-20'},
            {'event_type': 'preg_check', 'event_date': '2026-03-25', 'result': 'pregnant'},
        ]),
        operational_event_rows=None,
        asof_date=date(2026, 4, 1),
    )
    assert pregnant['state'] == 'pregnant'

    repeat = compute_reproduction_state(
        animal_row=_animal_row(),
        lactation_rows=_lact_rows('2025-12-01'),
        repro_event_rows=_repro_rows([
            {'event_type': 'insemination', 'event_date': '2026-01-20'},
            {'event_type': 'preg_check', 'event_date': '2026-02-25', 'result': 'open'},
            {'event_type': 'insemination', 'event_date': '2026-03-01'},
            {'event_type': 'preg_check', 'event_date': '2026-03-28', 'result': 'open'},
        ]),
        operational_event_rows=None,
        asof_date=date(2026, 4, 1),
    )
    assert repeat['state'] == 'repeat'
    assert repeat['reason_code'] == 'REPRO_REPEAT_AFTER_MULTIPLE_SERVICES'

    dry = compute_reproduction_state(
        animal_row=_animal_row(),
        lactation_rows=_lact_rows('2025-08-01', dryoff_date='2026-03-20'),
        repro_event_rows=pd.DataFrame(),
        operational_event_rows=None,
        asof_date=date(2026, 4, 1),
    )
    assert dry['state'] == 'dry'

    culled = compute_reproduction_state(
        animal_row=_animal_row('culled'),
        lactation_rows=_lact_rows('2025-12-01'),
        repro_event_rows=pd.DataFrame(),
        operational_event_rows=None,
        asof_date=date(2026, 4, 1),
    )
    assert culled['state'] == 'cull_candidate'


def test_t22_01_bulk_states_table_and_animal_daily_use_use_core_state_machine() -> None:
    table = build_reproduction_states_table(
        animals_df=pd.DataFrame([{'animal_id': 'A1001', 'status': 'active'}]),
        lactations_df=pd.DataFrame([{'animal_id': 'A1001', 'lactation_id': 'L1', 'calving_date': '2024-08-01'}]),
        repro_events_df=pd.DataFrame([{'animal_id': 'A1001', 'event_type': 'insemination', 'event_date': '2025-01-10', 'result': 'unknown'}]),
        operational_events_df=None,
        animal_ids=['A1001'],
        asof_date=date(2025, 3, 31),
    )
    assert table.iloc[0]['repro_state'] == 'preg_check_due'
    assert bool(table.iloc[0]['repro_attention']) is True

    ctx = build_animal_daily_use_context(
        input_dir=Path('data/fixtures/target_v2'),
        animal_id='A1001',
        asof_date=date(2025, 3, 31),
        pen_id='PEN_01',
        pen_name='Fresh',
        quick_history=[{'event_id': 'a1', 'event_ts': '2025-03-31T08:15:00+00:00', 'event_type': 'heat', 'display_type': 'heat', 'reason_code': 'HEAT_OBSERVED', 'source': 'manual_ui'}],
        tasks=[{'task_id': 't1', 'status': 'open', 'title': 'Inspect animal', 'due_date': '2025-03-30'}],
        decisions=[],
        alerts=[],
        prod_card={'available': True, 'prediction': 9800},
        mastitis_card={'available': False},
    )
    repro = dict(ctx['reproduction_state'])
    assert repro['state'] in {'heat', 'preg_check_due'}
    assert repro['reason_code'].startswith('REPRO_')


def test_t22_01_group_context_exposes_repro_state_labels_in_roster() -> None:
    roster = pd.DataFrame([
        {'animal_id': 'A1001', 'pen_id': 'PEN_01', 'pen_name': 'Fresh', 'farm_id': 'FARM_001', 'site_id': 'SITE_001'},
        {'animal_id': 'A1002', 'pen_id': 'PEN_01', 'pen_name': 'Fresh', 'farm_id': 'FARM_001', 'site_id': 'SITE_001'},
    ])
    by_animal = pd.DataFrame([
        {'animal_id': 'A1001', 'value': 100.0},
        {'animal_id': 'A1002', 'value': 90.0},
    ])
    out = build_group_operational_context(
        input_dir=Path('data/fixtures/target_v2'),
        pen_id='PEN_01',
        asof_date=date(2025, 3, 31),
        roster=roster,
        by_animal=by_animal,
        alerts=[],
        tasks=[],
        decisions=[],
    )
    cols = set((out['roster_status_rows']).columns)
    assert {'repro_state', 'repro_state_label', 'repro_reason_label'}.issubset(cols)


def test_t22_01_load_snapshot_from_fixture_is_reproducible() -> None:
    snapshot = load_reproduction_state_snapshot(
        input_dir=Path('data/fixtures/target_v2'),
        animal_id='A1001',
        asof_date=date(2025, 3, 31),
    )
    assert snapshot['animal_id'] == 'A1001'
    assert snapshot['state'] == 'preg_check_due'


def test_t22_01_docs_and_pages_reference_reproduction_state_machine() -> None:
    page_animal = Path('streamlit_app/pages/15_Animal_Profile.py').read_text(encoding='utf-8')
    page_group = Path('streamlit_app/pages/14_Group_Profile.py').read_text(encoding='utf-8')
    page_worklists = Path('streamlit_app/pages/43_Daily_Worklists_By_Role.py').read_text(encoding='utf-8')
    helper_worklists = Path('streamlit_app/daily_worklists_by_role.py').read_text(encoding='utf-8')
    helper_animal = Path('streamlit_app/animal_profile_daily_use.py').read_text(encoding='utf-8')
    helper_group = Path('streamlit_app/group_profile_operational_hub.py').read_text(encoding='utf-8')
    doc = Path('docs/reproduction_state_machine.md').read_text(encoding='utf-8')

    assert 'Reproduction state' in page_animal
    assert 'repro_state_label' in page_group
    assert 'Reproduction state / Состояние воспроизводства' in page_worklists
    assert 'load_reproduction_state_snapshot' in helper_worklists
    assert 'load_reproduction_state_snapshot' in helper_animal
    assert 'build_reproduction_states_table' in helper_group
    assert 'state machine' in doc.lower()
    assert 'preg_check_due' in doc
