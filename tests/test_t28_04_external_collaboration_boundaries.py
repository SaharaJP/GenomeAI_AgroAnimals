from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.infra.web_db import connect, create_user_v2, get_user_v2_any_by_username, get_user_v2_any_by_id, get_settings, init_db
from core.security import (
    ROLE_CONSULTANT,
    ROLE_PARTNER,
    ROLE_DIRECTOR,
    ROLE_ADMIN,
    ROLE_VIEWER,
    PERM_COLLAB_COMMENTS_WRITE,
    PERM_COLLAB_RECOMMENDATIONS_WRITE,
    PERM_COLLAB_APPROVAL_REQUEST,
    PERM_COLLAB_APPROVAL_REVIEW,
    build_collaboration_boundary,
    filter_rows_for_boundary,
)
from core.collaboration import create_collaboration_note_use_case, list_collaboration_notes, review_collaboration_note_use_case
from streamlit_app.admin_console import admin_set_user_collaboration_boundary, list_users_security_view
from streamlit_app.ia_v3 import build_nav_for_user, load_ia_config
from web_cabinet.auth import hash_password


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
def ctx(tmp_path: Path):
    root = tmp_path / 'project'
    web = root / 'web'
    art = root / 'artifacts'
    web.mkdir(parents=True, exist_ok=True)
    art.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(web_storage_dir=web, artifacts_dir=art)


def _seed_user(conn: sqlite3.Connection, *, username: str, role: str) -> dict:
    create_user_v2(conn, tenant_id='default', username=username, password_hash=hash_password(username), role=role)
    user = get_user_v2_any_by_username(conn, tenant_id='default', username=username)
    assert user is not None
    return dict(user)


def _seed_ctx_users(ctx) -> dict[str, dict]:
    settings = get_settings()
    db_path = Path(ctx.web_storage_dir) / 'web.db'
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    try:
        users = {}
        for username, role in [('admin', ROLE_ADMIN), ('director', ROLE_DIRECTOR), ('consultant', ROLE_CONSULTANT), ('partner', ROLE_PARTNER)]:
            if not get_user_v2_any_by_username(conn, tenant_id='default', username=username):
                create_user_v2(conn, tenant_id='default', username=username, password_hash=hash_password(username), role=role)
            users[username] = dict(get_user_v2_any_by_username(conn, tenant_id='default', username=username) or {})
        return users
    finally:
        conn.close()


def test_t28_04_external_roles_and_permissions_are_registered() -> None:
    from core import security as rbac

    consultant = set(rbac.DEFAULT_ROLE_PERMISSIONS[ROLE_CONSULTANT])
    partner = set(rbac.DEFAULT_ROLE_PERMISSIONS[ROLE_PARTNER])
    director = set(rbac.DEFAULT_ROLE_PERMISSIONS[ROLE_DIRECTOR])

    for perms in (consultant, partner):
        assert PERM_COLLAB_COMMENTS_WRITE in perms
        assert PERM_COLLAB_RECOMMENDATIONS_WRITE in perms
        assert PERM_COLLAB_APPROVAL_REQUEST in perms
        assert PERM_COLLAB_APPROVAL_REVIEW not in perms

    assert PERM_COLLAB_APPROVAL_REVIEW in director

    cfg = load_ia_config(Path('configs/ui/ia_v3.yaml'))
    for role in [ROLE_CONSULTANT, ROLE_PARTNER]:
        perms = set(rbac.ROLE_PERMISSIONS.get(role, []))
        groups = build_nav_for_user(cfg=cfg, role=role, permissions=perms)
        flat = {it.key: it for g in groups for it in g.items}
        assert 'home' in flat
        assert flat['home'].page.endswith('0_Home_Viewer.py')
        assert 'daily_worklists_by_role' in flat
        assert 'enterprise_benchmark_views' in flat


def test_t28_04_admin_can_update_collaboration_boundaries_and_view_summary(ctx) -> None:
    users = _seed_ctx_users(ctx)
    admin = {'id': users['admin']['id'], 'username': 'admin', 'role': ROLE_ADMIN, 'tenant_id': 'default', 'permissions': ['users.manage']}
    consultant_id = int(users['consultant']['id'])

    res = admin_set_user_collaboration_boundary(
        ctx,
        user=admin,
        user_id=consultant_id,
        collaboration_mode='external_consultant',
        external_org='Agro Advisory LLC',
        allowed_farm_ids=['F1'],
        allowed_site_ids=['S1'],
        allow_comments=True,
        allow_recommendations=True,
        allow_approval_requests=True,
        allow_approval_review=False,
    )
    assert res.ok, res.error

    view = list_users_security_view(ctx, tenant_id='default')
    target = next(row for row in view['users'] if int(row['id']) == consultant_id)
    summary = dict(target.get('collaboration_summary') or {})
    assert summary['is_external'] is True
    assert summary['external_org'] == 'Agro Advisory LLC'
    assert summary['allowed_farm_ids'] == ['F1']
    assert summary['allowed_site_ids'] == ['S1']
    assert summary['allow_comments'] is True


def test_t28_04_scope_filter_and_collaboration_notes_are_bounded(conn: sqlite3.Connection) -> None:
    consultant = _seed_user(conn, username='consultant', role=ROLE_CONSULTANT)
    director = _seed_user(conn, username='director', role=ROLE_DIRECTOR)

    conn.execute(
        "UPDATE users_v2 SET external_org=?, collaboration_mode=?, allowed_farm_ids_json=?, allowed_site_ids_json=?, collaboration_flags_json=? WHERE tenant_id='default' AND id=?",
        ('Agro Advisory LLC', 'external_consultant', '["F1"]', '["S1"]', '{"allow_comments": true, "allow_recommendations": true, "allow_approval_requests": true}', int(consultant['id'])),
    )
    conn.commit()
    consultant = dict(get_user_v2_any_by_id(conn, tenant_id='default', user_id=int(consultant['id'])) or {})
    director = dict(get_user_v2_any_by_id(conn, tenant_id='default', user_id=int(director['id'])) or {})
    director['permissions'] = [PERM_COLLAB_APPROVAL_REVIEW]

    boundary = build_collaboration_boundary({**consultant, 'permissions': [PERM_COLLAB_COMMENTS_WRITE, PERM_COLLAB_RECOMMENDATIONS_WRITE, PERM_COLLAB_APPROVAL_REQUEST]})
    rows = [
        {'worklist_id': 'W1', 'farm_id': 'F1', 'site_id': 'S1', 'title': 'Allowed'},
        {'worklist_id': 'W2', 'farm_id': 'F2', 'site_id': 'S2', 'title': 'Leak'},
    ]
    visible = filter_rows_for_boundary(rows, boundary)
    assert [r['worklist_id'] for r in visible] == ['W1']

    note = create_collaboration_note_use_case(
        conn=conn,
        tenant_id='default',
        user={**consultant, 'permissions': [PERM_COLLAB_COMMENTS_WRITE, PERM_COLLAB_RECOMMENDATIONS_WRITE, PERM_COLLAB_APPROVAL_REQUEST]},
        kind='recommendation',
        object_type='animal',
        object_id='AN-001',
        farm_id='F1',
        site_id='S1',
        body='Проверить protocol adherence на площадке S1.',
        metadata={'source': 'external_review'},
        request_id='REQ-COLLAB-1',
    )
    assert note['kind'] == 'recommendation'

    with pytest.raises(PermissionError):
        create_collaboration_note_use_case(
            conn=conn,
            tenant_id='default',
            user={**consultant, 'permissions': [PERM_COLLAB_COMMENTS_WRITE, PERM_COLLAB_RECOMMENDATIONS_WRITE, PERM_COLLAB_APPROVAL_REQUEST]},
            kind='comment',
            object_type='animal',
            object_id='AN-002',
            farm_id='F2',
            site_id='S2',
            body='Это уже outside scope.',
            metadata={},
            request_id='REQ-COLLAB-LEAK',
        )

    notes = list_collaboration_notes(conn, tenant_id='default', object_type='animal', object_id='AN-001', farm_id='F1', site_id='S1', limit=20)
    assert len(notes) == 1
    reviewed = review_collaboration_note_use_case(
        conn=conn,
        tenant_id='default',
        user={**director, 'permissions': [PERM_COLLAB_APPROVAL_REVIEW]},
        note_id=str(note['note_id']),
        new_status='accepted',
        review_comment='Принято к исполнению внутри хозяйства.',
        request_id='REQ-COLLAB-REVIEW',
    )
    assert reviewed['status'] == 'accepted'
    assert reviewed['review_comment'] == 'Принято к исполнению внутри хозяйства.'

    audit_actions = [
        row['action']
        for row in conn.execute("SELECT action FROM audit_log WHERE action LIKE 'collaboration.note.%' ORDER BY id").fetchall()
    ]
    assert audit_actions == ['collaboration.note.create', 'collaboration.note.review']


def test_t28_04_docs_and_pages_are_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    page_admin = (root / 'streamlit_app' / 'pages' / '35_Admin_Users_Security.py').read_text(encoding='utf-8')
    page_dw = (root / 'streamlit_app' / 'pages' / '43_Daily_Worklists_By_Role.py').read_text(encoding='utf-8')
    docs = (root / 'docs' / 'external_collaboration_boundaries.md').read_text(encoding='utf-8')
    assumptions = (root / 'docs' / 'assumptions.md').read_text(encoding='utf-8')
    helper = (root / 'src' / 'core' / 'security' / 'external_collaboration.py').read_text(encoding='utf-8')

    assert 'External collaboration' in page_admin
    assert 'Collaboration / comments / recommendations' in page_dw
    assert 'deny-by-default' in docs or 'deny-by-default' in helper
    assert '## T28-04 — external consultant / partner collaboration boundaries' in assumptions
