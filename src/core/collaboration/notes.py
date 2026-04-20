from __future__ import annotations

import json
import sqlite3
from typing import Any, Mapping
from uuid import uuid4

from core.audit import write_audit
from core.infra.web_db import utcnow_iso
from core.security import build_collaboration_boundary, boundary_allows_scope

_ALLOWED_KINDS = {'comment', 'recommendation', 'approval_request'}
_ALLOWED_STATUSES = {'open', 'accepted', 'rejected', 'resolved'}


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _loads_json(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    text = _clean(value)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _note_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    d = dict(row)
    d['metadata'] = _loads_json(d.get('metadata_json'))
    return d


def list_collaboration_notes(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    object_type: str | None = None,
    object_id: str | None = None,
    farm_id: str | None = None,
    site_id: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    where = ['tenant_id=?']
    args: list[Any] = [tenant_id]
    if _clean(object_type):
        where.append('object_type=?')
        args.append(_clean(object_type))
    if _clean(object_id):
        where.append('object_id=?')
        args.append(_clean(object_id))
    if _clean(farm_id):
        where.append('farm_id=?')
        args.append(_clean(farm_id))
    if _clean(site_id):
        where.append('site_id=?')
        args.append(_clean(site_id))
    rows = conn.execute(
        f"SELECT * FROM collaboration_notes_v1 WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ?",
        tuple(args + [max(1, int(limit))]),
    ).fetchall()
    return [_note_from_row(dict(r)) for r in rows]


def create_collaboration_note_use_case(
    *,
    conn: sqlite3.Connection,
    tenant_id: str,
    user: Mapping[str, Any],
    kind: str,
    object_type: str,
    object_id: str,
    farm_id: str | None,
    site_id: str | None,
    body: str,
    metadata: Mapping[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    kind_v = _clean(kind).lower()
    if kind_v not in _ALLOWED_KINDS:
        raise ValueError(f'invalid_kind: expected one of {sorted(_ALLOWED_KINDS)}, got {kind}')
    body_v = _clean(body)
    if not body_v:
        raise ValueError('empty_body')

    boundary = build_collaboration_boundary(user)
    if kind_v == 'comment' and not boundary.allow_comments:
        raise PermissionError('permission_denied: comments are not allowed')
    if kind_v == 'recommendation' and not boundary.allow_recommendations:
        raise PermissionError('permission_denied: recommendations are not allowed')
    if kind_v == 'approval_request' and not boundary.allow_approval_requests:
        raise PermissionError('permission_denied: approval requests are not allowed')
    if not boundary_allows_scope(boundary, farm_id=farm_id, site_id=site_id):
        raise PermissionError('scope_denied: object is outside allowed farm/site boundary')

    note_id = f'cn-{uuid4().hex[:12]}'
    now = utcnow_iso()
    payload = {
        'note_id': note_id,
        'tenant_id': tenant_id,
        'created_at': now,
        'updated_at': now,
        'created_by_user_id': int(user.get('id') or 0),
        'created_by_username': _clean(user.get('username')),
        'created_by_role': _clean(user.get('role')),
        'collaboration_mode': boundary.collaboration_mode,
        'external_org': boundary.external_org,
        'kind': kind_v,
        'object_type': _clean(object_type),
        'object_id': _clean(object_id),
        'farm_id': _clean(farm_id) or None,
        'site_id': _clean(site_id) or None,
        'body': body_v,
        'status': 'open',
        'reviewed_at': None,
        'reviewed_by_user_id': None,
        'reviewed_by_username': None,
        'review_comment': None,
        'metadata_json': json.dumps(dict(metadata or {}), ensure_ascii=False),
        'linked_note_id': None,
    }
    conn.execute(
        '''
        INSERT INTO collaboration_notes_v1(
          note_id, tenant_id, created_at, updated_at, created_by_user_id, created_by_username, created_by_role,
          collaboration_mode, external_org, kind, object_type, object_id, farm_id, site_id, body, status,
          reviewed_at, reviewed_by_user_id, reviewed_by_username, review_comment, metadata_json, linked_note_id
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''',
        tuple(payload[k] for k in [
            'note_id', 'tenant_id', 'created_at', 'updated_at', 'created_by_user_id', 'created_by_username', 'created_by_role',
            'collaboration_mode', 'external_org', 'kind', 'object_type', 'object_id', 'farm_id', 'site_id', 'body', 'status',
            'reviewed_at', 'reviewed_by_user_id', 'reviewed_by_username', 'review_comment', 'metadata_json', 'linked_note_id',
        ]),
    )
    conn.commit()
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get('id') or 0),
        username=_clean(user.get('username')),
        role=_clean(user.get('role')),
        action='collaboration.note.create',
        object_type='collaboration_note',
        object_id=note_id,
        before=None,
        after={
            'kind': kind_v,
            'target': {'object_type': _clean(object_type), 'object_id': _clean(object_id), 'farm_id': _clean(farm_id) or None, 'site_id': _clean(site_id) or None},
            'collaboration_mode': boundary.collaboration_mode,
            'external_org': boundary.external_org,
        },
        request_id=request_id,
    )
    return _note_from_row(payload)


def review_collaboration_note_use_case(
    *,
    conn: sqlite3.Connection,
    tenant_id: str,
    user: Mapping[str, Any],
    note_id: str,
    new_status: str,
    review_comment: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    boundary = build_collaboration_boundary(user)
    if not boundary.allow_approval_review:
        raise PermissionError('permission_denied: approval review is not allowed')
    status_v = _clean(new_status).lower()
    if status_v not in {'accepted', 'rejected', 'resolved'}:
        raise ValueError(f'invalid_status: expected accepted/rejected/resolved, got {new_status}')
    row = conn.execute('SELECT * FROM collaboration_notes_v1 WHERE tenant_id=? AND note_id=?', (tenant_id, _clean(note_id))).fetchone()
    if not row:
        raise KeyError('not_found')
    before = _note_from_row(dict(row))
    if before.get('status') == status_v and _clean(before.get('review_comment')) == _clean(review_comment):
        return before
    if not boundary_allows_scope(boundary, farm_id=before.get('farm_id'), site_id=before.get('site_id')):
        raise PermissionError('scope_denied: note is outside allowed farm/site boundary')
    now = utcnow_iso()
    conn.execute(
        'UPDATE collaboration_notes_v1 SET status=?, reviewed_at=?, reviewed_by_user_id=?, reviewed_by_username=?, review_comment=?, updated_at=? WHERE tenant_id=? AND note_id=?',
        (status_v, now, int(user.get('id') or 0), _clean(user.get('username')), _clean(review_comment) or None, now, tenant_id, _clean(note_id)),
    )
    conn.commit()
    after = _note_from_row(dict(conn.execute('SELECT * FROM collaboration_notes_v1 WHERE tenant_id=? AND note_id=?', (tenant_id, _clean(note_id))).fetchone()))
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user.get('id') or 0),
        username=_clean(user.get('username')),
        role=_clean(user.get('role')),
        action='collaboration.note.review',
        object_type='collaboration_note',
        object_id=_clean(note_id),
        before={'status': before.get('status'), 'review_comment': before.get('review_comment')},
        after={'status': after.get('status'), 'review_comment': after.get('review_comment')},
        request_id=request_id,
    )
    return after


__all__ = [
    'create_collaboration_note_use_case',
    'list_collaboration_notes',
    'review_collaboration_note_use_case',
]
