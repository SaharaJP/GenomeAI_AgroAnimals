from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from streamlit_app.personalization import can_open_favorite, required_permission_for_favorite
from streamlit_app.saved_views_state import apply_saved_view_state, extract_saved_view_state
from web_cabinet import rbac
from web_cabinet.db import init_db
from web_cabinet.favorites import add_favorite, list_favorites
from web_cabinet.saved_views import create_saved_view, list_saved_views


@pytest.fixture()
def conn() -> sqlite3.Connection:
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


def test_t21_05_saved_view_state_supports_daily_worklists_and_planner() -> None:
    sess = {
        'daily_worklists_by_role.day': date(2026, 4, 1),
        'daily_worklists_by_role.include_upcoming': True,
        'daily_worklists_by_role.q': 'mastitis',
        'daily_worklists_by_role.limit': 80,
        'daily_worklists_by_role.selected_worklist_id': 'WL-001',
        'operational_planner.day': date(2026, 4, 1),
        'operational_planner.data_version': 'dv_t21_05',
        'operational_planner.view_mode': 'manager',
        'operational_planner.role': 'Vet',
        'operational_planner.owner': 'vet_user',
        'operational_planner.team': 'team-health',
        'operational_planner.sources': ['alerts', 'worklists', 7],
        'operational_planner.q': 'follow-up',
        'operational_planner.limit_per_bucket': 50,
        'operational_planner.selected_item_id': 'PLAN-001',
    }

    wl = extract_saved_view_state(page_key='daily_worklists_by_role', session_state=sess)
    assert wl['daily_worklists_by_role.day'] == '2026-04-01'
    assert wl['daily_worklists_by_role.selected_worklist_id'] == 'WL-001'

    planner = extract_saved_view_state(page_key='operational_planner', session_state=sess)
    assert planner['operational_planner.day'] == '2026-04-01'
    assert planner['operational_planner.sources'] == ['alerts', 'worklists', '7']

    restored: dict[str, object] = {}
    apply_saved_view_state(page_key='daily_worklists_by_role', state=wl, session_state=restored)
    apply_saved_view_state(page_key='operational_planner', state=planner, session_state=restored)
    assert restored['daily_worklists_by_role.day'] == date(2026, 4, 1)
    assert restored['operational_planner.day'] == date(2026, 4, 1)
    assert restored['operational_planner.sources'] == ['alerts', 'worklists', '7']


def test_t21_05_can_store_worklist_saved_views_and_favorites(conn: sqlite3.Connection) -> None:
    state = {
        'daily_worklists_by_role.day': '2026-04-01',
        'daily_worklists_by_role.include_upcoming': False,
        'daily_worklists_by_role.q': 'repro',
        'daily_worklists_by_role.limit': 60,
        'daily_worklists_by_role.selected_worklist_id': 'WL-777',
    }
    create_saved_view(
        conn,
        view_id='sv-wl-001',
        tenant_id='default',
        created_by=11,
        created_by_username='zootech',
        scope='shared',
        name='Today repro shift',
        page_key='daily_worklists_by_role',
        state=state,
        data_version='dv_t21_05',
        run_id='WL-777',
    )
    rows = list_saved_views(conn, tenant_id='default', user_id=11, page_key='daily_worklists_by_role', include_shared=True)
    assert len(rows) == 1
    assert rows[0]['page_key'] == 'daily_worklists_by_role'
    assert rows[0]['state']['daily_worklists_by_role.selected_worklist_id'] == 'WL-777'

    add_favorite(
        conn,
        tenant_id='default',
        user_id=11,
        object_type='worklist',
        object_id='WL-777',
        label='Follow-up WL-777',
        metadata={'page_key': 'daily_worklists_by_role', 'state': state, 'data_version': 'dv_t21_05'},
    )
    favorites = list_favorites(conn, tenant_id='default', user_id=11, object_type='worklist', limit=20)
    assert len(favorites) == 1
    assert favorites[0]['object_type'] == 'worklist'
    assert favorites[0]['metadata']['state']['daily_worklists_by_role.q'] == 'repro'


def test_t21_05_favorite_permission_mapping_supports_worklist() -> None:
    assert required_permission_for_favorite('worklist') == rbac.PERM_TASKS_VIEW
    assert required_permission_for_favorite('task') == rbac.PERM_TASKS_VIEW
    assert required_permission_for_favorite('planner_item') == rbac.PERM_TASKS_VIEW
    assert can_open_favorite(object_type='worklist', permissions={rbac.PERM_TASKS_VIEW}) is True
    assert can_open_favorite(object_type='worklist', permissions={rbac.PERM_ALERTS_VIEW}) is False


def test_t21_05_streamlit_contracts_and_docs_present() -> None:
    page = Path('streamlit_app/pages/43_Daily_Worklists_By_Role.py').read_text(encoding='utf-8')
    planner = Path('streamlit_app/pages/44_Operational_Planner.py').read_text(encoding='utf-8')
    saved_state = Path('streamlit_app/saved_views_state.py').read_text(encoding='utf-8')
    saved_views_page = Path('streamlit_app/pages/17_Saved_Views_And_Favorites.py').read_text(encoding='utf-8')
    personalization = Path('streamlit_app/personalization.py').read_text(encoding='utf-8')
    docs = Path('docs/worklist_saved_views.md').read_text(encoding='utf-8')
    assumptions = Path('docs/assumptions.md').read_text(encoding='utf-8')

    assert 'Pinned filters / Saved views' in page
    assert 'Применить saved view' in page
    assert 'Сохранить view' in page
    assert 'В избранное' in page or '★ Убрать из избранного' in page
    assert 'Saved views' in planner
    assert 'daily_worklists_by_role' in saved_state
    assert 'operational_planner' in saved_state
    assert 'daily_worklists_by_role' in saved_views_page
    assert 'operational_planner' in saved_views_page
    assert 'object_type=\'worklist\'' in page or 'object_type="worklist"' in page
    assert 'worklist' in personalization
    assert '## Что сделано в T21-05' in docs
    assert '## T21-05 — worklist saved views' in assumptions
