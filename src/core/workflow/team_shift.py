from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

import pandas as pd

from core.audit import write_audit
from core.infra.web_db import utcnow_iso, get_user_by_id
from core.workflow.catalogs import workflow_team_keys
from core.workflow.policies import load_workflow_yaml, workflow_project_root
from core.workflow.worklists import get_worklist
from core.workflow.tasks import update_task_fields


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _as_int(value: Any) -> int | None:
    if value in (None, ''):
        return None
    try:
        return int(value)
    except Exception:
        return None


def _cfg() -> dict[str, Any]:
    root = workflow_project_root()
    return load_workflow_yaml(root / 'configs' / 'ops' / 'team_shift_v1.yaml')


def workflow_shift_catalog() -> dict[str, Any]:
    cfg = (_cfg().get('team_shift_management_v1') or {}) if isinstance(_cfg(), Mapping) else {}
    raw = list(cfg.get('shifts') or [])
    items: list[dict[str, Any]] = []
    keys: list[str] = []
    for row in raw:
        if not isinstance(row, Mapping):
            continue
        key = _clean(row.get('key')).lower()
        if not key:
            continue
        title = _clean(row.get('title')) or key
        items.append({'key': key, 'title': title})
        if key not in keys:
            keys.append(key)
    if not items:
        items = [
            {'key': 'day', 'title': 'Day shift'},
            {'key': 'evening', 'title': 'Evening shift'},
            {'key': 'night', 'title': 'Night shift'},
            {'key': 'unassigned', 'title': 'Unassigned shift'},
        ]
        keys = [x['key'] for x in items]
    return {'shifts': items, 'shift_keys': tuple(keys)}


def workflow_shift_keys(*, include_blank: bool = False) -> tuple[str, ...]:
    keys = list(workflow_shift_catalog().get('shift_keys') or ())
    if include_blank:
        return tuple([''] + keys)
    return tuple(keys)


def workflow_handover_reason_codes() -> tuple[str, ...]:
    cfg = (_cfg().get('team_shift_management_v1') or {}) if isinstance(_cfg(), Mapping) else {}
    out: list[str] = []
    for raw in list(cfg.get('handover_reason_codes') or []):
        key = _clean(raw)
        if key and key not in out:
            out.append(key)
    if not out:
        out = ['shift_end', 'backlog_rebalance', 'team_reassignment', 'site_support', 'expert_review']
    return tuple(out)


def role_team_scope(role: str) -> tuple[str, ...]:
    cfg = (_cfg().get('team_shift_management_v1') or {}) if isinstance(_cfg(), Mapping) else {}
    mapping = dict(cfg.get('role_team_scope') or {}) if isinstance(cfg, Mapping) else {}
    raw = list(mapping.get(str(role or '').strip()) or [])
    out = [_clean(x) for x in raw if _clean(x)]
    if out:
        return tuple(out)
    fallback = {
        'Operator': ('team-data', 'team-qc'),
        'Zootech': ('team-repro', 'team-econ'),
        'Vet': ('team-health',),
        'Director': tuple(workflow_team_keys()),
        'Admin': tuple(workflow_team_keys()),
    }
    return tuple(fallback.get(str(role or '').strip()) or ())


def _shift_title(key: str) -> str:
    for item in list(workflow_shift_catalog().get('shifts') or []):
        if _clean(item.get('key')).lower() == _clean(key).lower():
            return _clean(item.get('title')) or _clean(key)
    return _clean(key)


def _ownership_meta(row: Mapping[str, Any]) -> dict[str, Any]:
    why = dict(row.get('why') or {}) if isinstance(row.get('why'), Mapping) else {}
    ownership = dict(why.get('ownership') or {}) if isinstance(why.get('ownership'), Mapping) else {}
    attachments = list(row.get('attachments') or [])
    handovers = [dict(x) for x in attachments if isinstance(x, Mapping) and _clean(x.get('kind')).lower() == 'handover']
    last_handover = dict(handovers[-1]) if handovers else {}

    current_team = _clean(ownership.get('team_key') or row.get('assignee_team')) or 'unassigned'
    current_shift = _clean(ownership.get('shift_key') or last_handover.get('to_shift') or 'unassigned').lower() or 'unassigned'
    current_owner_user_id = _as_int(ownership.get('owner_user_id'))
    if current_owner_user_id is None:
        current_owner_user_id = _as_int(row.get('owner_user_id'))
    current_owner_username = _clean(ownership.get('owner_username') or last_handover.get('to_owner_username'))

    return {
        'current_team': current_team,
        'shift_key': current_shift,
        'shift_label': _shift_title(current_shift),
        'current_owner_user_id': current_owner_user_id,
        'current_owner_username': current_owner_username or None,
        'handover_count': int(len(handovers)),
        'last_handover_at': _clean(last_handover.get('created_at')) or None,
        'last_handover_reason': _clean(last_handover.get('reason_code')) or None,
        'last_handover_from_team': _clean(last_handover.get('from_team')) or None,
        'last_handover_to_team': _clean(last_handover.get('to_team')) or None,
        'last_handover_from_shift': _clean(last_handover.get('from_shift')) or None,
        'last_handover_to_shift': _clean(last_handover.get('to_shift')) or None,
        'ownership_mode': 'user' if current_owner_user_id is not None else ('team_shift' if current_team != 'unassigned' else 'unassigned'),
        'traceable_handover': bool(handovers),
    }


def enrich_team_shift_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for raw in rows or []:
        row = dict(raw)
        meta = _ownership_meta(row)
        current_team = _clean(meta.get('current_team')) or 'unassigned'
        shift_key = _clean(meta.get('shift_key')).lower() or 'unassigned'
        owner_user_id = meta.get('current_owner_user_id')
        owner_username = _clean(meta.get('current_owner_username') or row.get('owner_username')) or None
        if owner_user_id is None:
            owner_user_id = _as_int(row.get('owner_user_id'))
        if not owner_username:
            owner_username = _clean(row.get('owner_username')) or None
        queue_key = f"{current_team}:{shift_key}"
        queue_owner_label = f"{current_team} · {_shift_title(shift_key)}"
        if owner_username:
            queue_owner_label = f"{queue_owner_label} · {owner_username}"
        elif owner_user_id is not None:
            queue_owner_label = f"{queue_owner_label} · user:{owner_user_id}"
        row['current_team'] = current_team
        row['shift_key'] = shift_key
        row['shift_label'] = _shift_title(shift_key)
        row['queue_key'] = queue_key
        row['queue_owner_label'] = queue_owner_label
        row['ownership_mode'] = meta.get('ownership_mode')
        row['handover_count'] = int(meta.get('handover_count') or 0)
        row['last_handover_at'] = meta.get('last_handover_at')
        row['last_handover_reason'] = meta.get('last_handover_reason')
        row['last_handover_from_team'] = meta.get('last_handover_from_team')
        row['last_handover_to_team'] = meta.get('last_handover_to_team')
        row['last_handover_from_shift'] = meta.get('last_handover_from_shift')
        row['last_handover_to_shift'] = meta.get('last_handover_to_shift')
        row['traceable_handover'] = bool(meta.get('traceable_handover'))
        row['team_shift_context'] = {
            'current_team': current_team,
            'shift_key': shift_key,
            'queue_key': queue_key,
            'queue_owner_label': queue_owner_label,
            'ownership_mode': row.get('ownership_mode'),
            'handover_count': row.get('handover_count'),
            'last_handover_at': row.get('last_handover_at'),
            'last_handover_reason': row.get('last_handover_reason'),
        }
        enriched.append(row)
    return enriched


def filter_team_shift_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    assignee_team: str | None = None,
    shift_key: str | None = None,
    owner_user_id: int | None = None,
) -> list[dict[str, Any]]:
    team_filter = _clean(assignee_team)
    shift_filter = _clean(shift_key).lower()
    owner_filter = _as_int(owner_user_id)
    out: list[dict[str, Any]] = []
    for raw in rows or []:
        row = dict(raw)
        team = _clean(row.get('current_team') or row.get('assignee_team'))
        shift = _clean(row.get('shift_key')).lower()
        owner = _as_int(row.get('owner_user_id'))
        if team_filter and team != team_filter:
            continue
        if shift_filter and shift != shift_filter:
            continue
        if owner_filter is not None and owner != owner_filter:
            continue
        out.append(row)
    return out


def _load_units(row: Mapping[str, Any]) -> float:
    if row.get('load_units') not in (None, ''):
        try:
            return float(row.get('load_units') or 0.0)
        except Exception:
            return 1.0
    priority = int(row.get('priority') or 3)
    return {1: 1.8, 2: 1.5, 3: 1.2, 4: 1.0, 5: 0.8}.get(priority, 1.0)


def build_team_queue_balance(rows: Sequence[Mapping[str, Any]], *, level: str = 'team_shift') -> pd.DataFrame:
    level_key = _clean(level).lower() or 'team_shift'
    prepared = enrich_team_shift_rows(rows)
    df = pd.DataFrame(prepared)
    if df.empty:
        cols = ['assignee_team', 'shift_key', 'items_total', 'overdue', 'today', 'in_progress', 'open_items', 'high_priority', 'load_units', 'owned_by_user', 'team_unowned', 'queue_owner_labels', 'explainability', 'balance_hint']
        if level_key == 'team':
            cols.remove('shift_key')
        return pd.DataFrame(columns=cols)

    for col in ['current_team', 'shift_key', 'status', 'due_bucket', 'bucket', 'priority', 'queue_owner_label', 'owner_user_id']:
        if col not in df.columns:
            df[col] = pd.NA
    df['team_key'] = df['current_team'].fillna(df.get('assignee_team')).fillna('unassigned').astype(str)
    df['shift_key_v'] = df['shift_key'].fillna('unassigned').astype(str)

    def _row_bucket(r: Mapping[str, Any]) -> str:
        for key in ('due_bucket', 'bucket'):
            value = r.get(key)
            try:
                if pd.isna(value):
                    continue
            except Exception:
                pass
            cleaned = _clean(value).lower()
            if cleaned:
                return cleaned
        return 'undated'

    df['bucket_v'] = df.apply(lambda r: _row_bucket(r), axis=1)
    df['status_v'] = df['status'].fillna('open').astype(str)
    df['priority_num'] = pd.to_numeric(df['priority'], errors='coerce').fillna(3)
    df['load_units_num'] = df.apply(lambda r: _load_units(r.to_dict()), axis=1)
    group_cols = ['team_key'] if level_key == 'team' else ['team_key', 'shift_key_v']

    out: list[dict[str, Any]] = []
    for keys, sub in df.groupby(group_cols, dropna=False, sort=True):
        key_values = keys if isinstance(keys, tuple) else (keys,)
        rec: dict[str, Any] = {'assignee_team': key_values[0]}
        if level_key != 'team':
            rec['shift_key'] = key_values[1]
        rec['items_total'] = int(len(sub))
        rec['overdue'] = int((sub['bucket_v'] == 'overdue').sum())
        rec['today'] = int((sub['bucket_v'] == 'today').sum())
        rec['in_progress'] = int((sub['status_v'] == 'in_progress').sum())
        rec['open_items'] = int((sub['status_v'].isin(['open', 'in_progress'])).sum())
        rec['high_priority'] = int((sub['priority_num'] <= 2).sum())
        rec['load_units'] = round(float(sub['load_units_num'].sum()), 2)
        rec['owned_by_user'] = int(sub['owner_user_id'].notna().sum())
        rec['team_unowned'] = int(sub['owner_user_id'].isna().sum())
        labels = sorted({str(x) for x in sub['queue_owner_label'].astype(str).tolist() if _clean(x) and _clean(x) not in {'nan', 'None'}})
        rec['queue_owner_labels'] = ' | '.join(labels[:3]) or '—'
        explain_shift = f" / shift={rec['shift_key']}" if level_key != 'team' else ''
        rec['explainability'] = f"{rec['items_total']} visible items aggregated by team={rec['assignee_team']}{explain_shift}"
        hint_parts: list[str] = []
        if rec['overdue']:
            hint_parts.append(f"overdue={rec['overdue']}")
        if rec['team_unowned']:
            hint_parts.append(f"unowned={rec['team_unowned']}")
        if rec['high_priority']:
            hint_parts.append(f"high_priority={rec['high_priority']}")
        if rec['load_units'] >= 4.0:
            hint_parts.append(f"load={rec['load_units']}")
        rec['balance_hint'] = ', '.join(hint_parts) or 'balanced'
        out.append(rec)
    sort_cols = ['assignee_team'] if level_key == 'team' else ['assignee_team', 'shift_key']
    return pd.DataFrame(out).sort_values(sort_cols).reset_index(drop=True)


def build_handover_monitor(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    prepared = enrich_team_shift_rows(rows)
    candidates: list[dict[str, Any]] = []
    for row in prepared:
        bucket = _clean(row.get('due_bucket') or row.get('bucket')).lower()
        status = _clean(row.get('status')).lower()
        if status in {'done', 'cancelled'}:
            continue
        if bucket in {'overdue', 'today'} or row.get('owner_user_id') in (None, ''):
            candidates.append(dict(row))
    by_shift = build_team_queue_balance(candidates, level='team_shift')
    return {
        'candidates_total': len(candidates),
        'unowned_total': sum(1 for r in candidates if r.get('owner_user_id') in (None, '')),
        'overdue_total': sum(1 for r in candidates if _clean(r.get('due_bucket') or r.get('bucket')).lower() == 'overdue'),
        'by_team_shift': by_shift.to_dict(orient='records'),
    }


def _user_username(conn, *, tenant_id: str, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    try:
        user = get_user_by_id(conn, user_id=int(user_id), tenant_id=str(tenant_id))
    except Exception:
        user = None
    return _clean((user or {}).get('username')) or None


def _assert_role_can_manage(*, role: str, current_team: str, target_team: str) -> None:
    role_key = _clean(role)
    if role_key in {'Admin', 'Director'}:
        return
    allowed = set(role_team_scope(role_key))
    if allowed and current_team not in allowed and target_team not in allowed:
        raise PermissionError('permission_denied: role cannot handover this team queue')


def handover_worklist_use_case(
    *,
    conn,
    tenant_id: str,
    worklist_id: str,
    user_id: int,
    username: str,
    role: str,
    to_shift_key: str,
    to_team: str | None = None,
    to_owner_user_id: int | None = None,
    reason_code: str,
    note: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    before = get_worklist(conn, tenant_id=tenant_id, worklist_id=worklist_id)
    if not before:
        raise KeyError('not_found')

    target_shift = _clean(to_shift_key).lower() or 'unassigned'
    if target_shift not in set(workflow_shift_keys()):
        raise ValueError(f'invalid_shift_key: expected one of {list(workflow_shift_keys())}, got {to_shift_key}')
    if _clean(reason_code) not in set(workflow_handover_reason_codes()):
        raise ValueError(f'invalid_handover_reason: expected one of {list(workflow_handover_reason_codes())}, got {reason_code}')

    current = enrich_team_shift_rows([before])[0]
    current_team = _clean(current.get('current_team') or current.get('assignee_team')) or 'unassigned'
    target_team = _clean(to_team or current_team) or 'unassigned'
    valid_teams = set(workflow_team_keys())
    if valid_teams and target_team != 'unassigned' and target_team not in valid_teams:
        raise ValueError(f'invalid_assignee_team: expected one of {list(valid_teams)}, got {target_team}')
    _assert_role_can_manage(role=role, current_team=current_team, target_team=target_team)

    now = utcnow_iso()
    from_owner_user_id = _as_int(current.get('owner_user_id'))
    to_owner_id = _as_int(to_owner_user_id)
    to_owner_username = _user_username(conn, tenant_id=tenant_id, user_id=to_owner_id) if to_owner_id is not None else None

    attachments = list(current.get('attachments') or [])
    handover_entry = {
        'kind': 'handover',
        'handover_id': f"wh-{uuid4().hex[:8]}",
        'from_team': current_team,
        'from_shift': _clean(current.get('shift_key') or 'unassigned'),
        'from_owner_user_id': from_owner_user_id,
        'from_owner_username': _clean(current.get('owner_username')) or None,
        'to_team': target_team,
        'to_shift': target_shift,
        'to_owner_user_id': to_owner_id,
        'to_owner_username': to_owner_username,
        'reason_code': _clean(reason_code),
        'note': _clean(note) or None,
        'created_at': now,
        'created_by': int(user_id or 0),
        'created_by_username': _clean(username) or None,
        'created_by_role': _clean(role) or None,
    }
    attachments.append(handover_entry)

    why = dict(current.get('why') or {}) if isinstance(current.get('why'), Mapping) else {}
    ownership = dict(why.get('ownership') or {}) if isinstance(why.get('ownership'), Mapping) else {}
    ownership.update({
        'team_key': target_team,
        'shift_key': target_shift,
        'owner_user_id': to_owner_id,
        'owner_username': to_owner_username,
        'last_handover_at': now,
        'last_handover_by': int(user_id or 0),
        'last_handover_by_username': _clean(username) or None,
        'last_handover_reason': _clean(reason_code),
        'handover_count': int(current.get('handover_count') or 0) + 1,
    })
    why['ownership'] = ownership

    patch: dict[str, Any] = {
        'assignee_team': (None if target_team == 'unassigned' else target_team),
        'owner_user_id': to_owner_id,
        'attachments': attachments,
        'why': why,
        'status': 'open',
        'stage': 'review',
    }
    update_task_fields(conn, tenant_id=tenant_id, task_id=worklist_id, patch=patch)
    after = get_worklist(conn, tenant_id=tenant_id, worklist_id=worklist_id)

    write_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id or 0),
        username=str(username or ''),
        role=str(role or ''),
        action='worklist.handover',
        object_type='worklist',
        object_id=str(worklist_id),
        data_version=(str((after or before or {}).get('data_version') or '') or None),
        before={
            'assignee_team': before.get('assignee_team'),
            'owner_user_id': before.get('owner_user_id'),
            'shift_key': current.get('shift_key'),
            'status': before.get('status'),
            'stage': before.get('stage'),
        },
        after={
            'assignee_team': (after or {}).get('assignee_team'),
            'owner_user_id': (after or {}).get('owner_user_id'),
            'shift_key': target_shift,
            'status': (after or {}).get('status'),
            'stage': (after or {}).get('stage'),
            'reason_code': _clean(reason_code),
        },
        status='OK',
        request_id=(str(request_id) if request_id not in (None, '') else None),
    )
    return {'before': before or {}, 'after': after or {}, 'handover': handover_entry}


__all__ = [
    'build_handover_monitor',
    'build_team_queue_balance',
    'enrich_team_shift_rows',
    'filter_team_shift_rows',
    'handover_worklist_use_case',
    'role_team_scope',
    'workflow_handover_reason_codes',
    'workflow_shift_catalog',
    'workflow_shift_keys',
]
