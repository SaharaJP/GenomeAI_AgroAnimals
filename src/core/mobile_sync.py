from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from core.audit.events import write_audit
from core.infra.web_db import utcnow_iso
from core.workflow import get_worklist


MOBILE_SYNC_STATUSES: tuple[str, ...] = ('saved', 'pending_retry', 'conflict')


@dataclass(slots=True)
class MobileSyncConflictError(ValueError):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> dict[str, Any]:
        return {'code': self.code, 'message': self.message, 'details': dict(self.details or {})}



def _clean(value: Any) -> str:
    return str(value or '').strip()



def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))



def canonical_payload_hash(payload: Mapping[str, Any]) -> str:
    body = _json(dict(payload or {})).encode('utf-8')
    return hashlib.sha1(body).hexdigest()



def build_mobile_action_key(*, page_key: str, action_kind: str, object_type: str | None, object_id: str | None, nonce: str) -> str:
    raw = _json({
        'page_key': _clean(page_key),
        'action_kind': _clean(action_kind),
        'object_type': _clean(object_type),
        'object_id': _clean(object_id),
        'nonce': _clean(nonce),
    }).encode('utf-8')
    return f"msa-{hashlib.sha1(raw).hexdigest()[:24]}"



def _loads_json(value: Any) -> dict[str, Any]:
    if value in (None, ''):
        return {}
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {'value': parsed}



def _row_to_dict(row: Any) -> dict[str, Any]:
    if not row:
        return {}
    data = dict(row)
    for key in ('payload_json', 'result_json', 'conflict_json'):
        parsed_key = key.replace('_json', '')
        data[parsed_key] = _loads_json(data.get(key))
    return data



def _extract_links(result: Mapping[str, Any] | None) -> dict[str, str | None]:
    row = dict(result or {})
    after = dict(row.get('after') or {})
    worklist = dict(row.get('worklist') or {})
    decision = dict(row.get('decision') or {})
    return {
        'linked_event_id': _clean(row.get('event_id') or after.get('event_id')) or None,
        'linked_worklist_id': _clean(row.get('worklist_id') or worklist.get('worklist_id') or after.get('worklist_id') or after.get('task_id')) or None,
        'linked_decision_id': _clean(row.get('decision_id') or decision.get('decision_id') or after.get('linked_decision_id')) or None,
    }



def _classify_transient(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    msg = str(exc).lower()
    if any(tok in msg for tok in ('locked', 'busy', 'unable to open database file')):
        return True
    return any(tok in msg for tok in ('timeout', 'timed out', 'temporar', 'connection reset', 'connection aborted', 'try again', 'locked'))



def get_mobile_sync_action(conn, *, tenant_id: str, action_key: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM mobile_sync_actions_v1 WHERE tenant_id=? AND action_key=?",
        (str(tenant_id), str(action_key)),
    ).fetchone()
    return _row_to_dict(row)



def list_mobile_sync_actions(
    conn,
    *,
    tenant_id: str,
    user_id: int | None = None,
    page_key: str | None = None,
    statuses: Sequence[str] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM mobile_sync_actions_v1 WHERE tenant_id=?"
    params: list[Any] = [str(tenant_id)]
    if user_id is not None:
        sql += " AND user_id=?"
        params.append(int(user_id))
    if _clean(page_key):
        sql += " AND page_key=?"
        params.append(_clean(page_key))
    wanted = [_clean(x) for x in (statuses or []) if _clean(x)]
    if wanted:
        sql += f" AND status IN ({','.join('?' for _ in wanted)})"
        params.extend(wanted)
    sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
    params.append(max(1, int(limit or 20)))
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [_row_to_dict(row) for row in rows]



def summarize_mobile_sync_actions(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    summary = {'total': 0, 'saved': 0, 'pending_retry': 0, 'conflict': 0}
    for row in rows or []:
        summary['total'] += 1
        status = _clean(row.get('status'))
        if status in summary:
            summary[status] += 1
    return summary



def _upsert_mobile_sync_action(
    conn,
    *,
    tenant_id: str,
    user_id: int,
    username: str,
    role: str,
    page_key: str,
    action_key: str,
    action_kind: str,
    object_type: str | None,
    object_id: str | None,
    status: str,
    payload: Mapping[str, Any],
    request_id: str | None,
    result: Mapping[str, Any] | None = None,
    conflict: Mapping[str, Any] | None = None,
    last_error: str | None = None,
    retry_delta: int = 1,
) -> dict[str, Any]:
    now = utcnow_iso()
    payload_hash = canonical_payload_hash(payload)
    existing = get_mobile_sync_action(conn, tenant_id=tenant_id, action_key=action_key)
    payload_row = dict(payload or {})
    links = _extract_links(result)
    versions = {
        'data_version': _clean(payload_row.get('data_version')) or _clean((result or {}).get('data_version')) or None,
        'qc_run': _clean(payload_row.get('qc_run')) or None,
        'model_version': _clean(payload_row.get('model_version')) or None,
        'scoring_run': _clean(payload_row.get('scoring_run')) or None,
        'report_version': _clean(payload_row.get('report_version')) or None,
    }
    if existing:
        conn.execute(
            """
            UPDATE mobile_sync_actions_v1
            SET updated_at=?, status=?, payload_hash=?, payload_json=?, result_json=?, conflict_json=?,
                last_error=?, retry_count=?, request_id=?, linked_event_id=?, linked_worklist_id=?, linked_decision_id=?,
                data_version=?, qc_run=?, model_version=?, scoring_run=?, report_version=?
            WHERE tenant_id=? AND action_key=?
            """,
            (
                now,
                str(status),
                payload_hash,
                _json(payload_row),
                _json(dict(result or {})) if result is not None else None,
                _json(dict(conflict or {})) if conflict is not None else None,
                str(last_error or '') or None,
                int(existing.get('retry_count') or 0) + int(retry_delta or 0),
                _clean(request_id) or None,
                links.get('linked_event_id'),
                links.get('linked_worklist_id'),
                links.get('linked_decision_id'),
                versions['data_version'],
                versions['qc_run'],
                versions['model_version'],
                versions['scoring_run'],
                versions['report_version'],
                str(tenant_id),
                str(action_key),
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO mobile_sync_actions_v1(
              action_key, tenant_id, created_at, updated_at, user_id, username, role, page_key, action_kind,
              object_type, object_id, status, payload_hash, payload_json, result_json, conflict_json, last_error,
              retry_count, request_id, linked_event_id, linked_worklist_id, linked_decision_id,
              data_version, qc_run, model_version, scoring_run, report_version
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                str(action_key),
                str(tenant_id),
                now,
                now,
                int(user_id or 0),
                str(username or ''),
                str(role or ''),
                str(page_key or ''),
                str(action_kind or ''),
                _clean(object_type) or None,
                _clean(object_id) or None,
                str(status),
                payload_hash,
                _json(payload_row),
                _json(dict(result or {})) if result is not None else None,
                _json(dict(conflict or {})) if conflict is not None else None,
                str(last_error or '') or None,
                max(0, int(retry_delta or 0)),
                _clean(request_id) or None,
                links.get('linked_event_id'),
                links.get('linked_worklist_id'),
                links.get('linked_decision_id'),
                versions['data_version'],
                versions['qc_run'],
                versions['model_version'],
                versions['scoring_run'],
                versions['report_version'],
            ),
        )
    return get_mobile_sync_action(conn, tenant_id=tenant_id, action_key=action_key)



def _write_mobile_sync_audit(
    conn,
    *,
    tenant_id: str,
    user_id: int,
    username: str,
    role: str,
    action: str,
    object_type: str | None,
    object_id: str | None,
    request_id: str | None,
    payload: Mapping[str, Any],
    row: Mapping[str, Any],
    error: str | None = None,
    status: str = 'OK',
) -> None:
    write_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id or 0),
        username=str(username or ''),
        role=str(role or ''),
        action=action,
        object_type=_clean(object_type) or 'mobile_sync_action',
        object_id=_clean(object_id) or _clean(row.get('action_key')) or None,
        data_version=_clean(row.get('data_version')) or _clean(payload.get('data_version')) or None,
        before={
            'page_key': _clean(row.get('page_key')),
            'action_kind': _clean(row.get('action_kind')),
            'action_key': _clean(row.get('action_key')),
        },
        after={
            'status': _clean(row.get('status')),
            'retry_count': int(row.get('retry_count') or 0),
            'linked_event_id': _clean(row.get('linked_event_id')) or None,
            'linked_worklist_id': _clean(row.get('linked_worklist_id')) or None,
            'linked_decision_id': _clean(row.get('linked_decision_id')) or None,
            'conflict': dict(row.get('conflict') or {}),
        },
        status=status,
        error=str(error or '') or None,
        request_id=_clean(request_id) or None,
    )



def detect_worklist_mobile_conflict(
    conn,
    *,
    tenant_id: str,
    worklist_id: str,
    snapshot_status: str | None,
    action_kind: str,
) -> dict[str, Any] | None:
    current = get_worklist(conn, tenant_id=str(tenant_id), worklist_id=str(worklist_id))
    if not current:
        return {
            'code': 'worklist_not_found',
            'message': 'Work item не найден или уже недоступен.',
            'worklist_id': str(worklist_id),
        }
    current_status = _clean(current.get('status'))
    expected = _clean(snapshot_status)
    kind = _clean(action_kind)
    if kind in {'worklist.close', 'worklist.postpone', 'worklist.accept'}:
        if current_status in {'done', 'cancelled'}:
            return {
                'code': 'worklist_already_closed',
                'message': 'Work item уже закрыт на другом устройстве или другим пользователем.',
                'expected_status': expected or None,
                'current_status': current_status,
                'worklist_id': str(worklist_id),
            }
        if expected and expected != current_status:
            return {
                'code': 'worklist_state_changed',
                'message': 'Состояние work item изменилось с момента последнего mobile snapshot.',
                'expected_status': expected,
                'current_status': current_status,
                'worklist_id': str(worklist_id),
            }
    return None



def execute_mobile_sync_action(
    conn,
    *,
    tenant_id: str,
    user_id: int,
    username: str,
    role: str,
    page_key: str,
    action_kind: str,
    action_key: str,
    object_type: str | None,
    object_id: str | None,
    payload: Mapping[str, Any],
    executor: Callable[[Any, Mapping[str, Any]], Mapping[str, Any]],
    request_id: str | None = None,
    conflict_checker: Callable[[Any, Mapping[str, Any]], Mapping[str, Any] | None] | None = None,
) -> dict[str, Any]:
    existing = get_mobile_sync_action(conn, tenant_id=tenant_id, action_key=action_key)
    payload_hash = canonical_payload_hash(payload)
    if existing and _clean(existing.get('payload_hash')) == payload_hash and _clean(existing.get('status')) == 'saved':
        return {
            'state': 'saved',
            'reused': True,
            'notice': 'Уже сохранено ранее; повторная отправка не создала дубль.',
            'sync': existing,
            'result': dict(existing.get('result') or {}),
        }

    if existing and _clean(existing.get('payload_hash')) and _clean(existing.get('payload_hash')) != payload_hash:
        conflict = {
            'code': 'mobile_action_payload_changed',
            'message': 'Повторная отправка использует другой payload для того же mobile action key.',
            'existing_payload_hash': _clean(existing.get('payload_hash')),
            'attempt_payload_hash': payload_hash,
        }
        row = _upsert_mobile_sync_action(
            conn,
            tenant_id=tenant_id,
            user_id=user_id,
            username=username,
            role=role,
            page_key=page_key,
            action_key=action_key,
            action_kind=action_kind,
            object_type=object_type,
            object_id=object_id,
            status='conflict',
            payload=payload,
            request_id=request_id,
            conflict=conflict,
            last_error=conflict['message'],
            retry_delta=1,
        )
        _write_mobile_sync_audit(conn, tenant_id=tenant_id, user_id=user_id, username=username, role=role, action='mobile.sync.conflict', object_type=object_type, object_id=object_id, request_id=request_id, payload=payload, row=row, error=conflict['message'], status='ERROR')
        return {'state': 'conflict', 'notice': conflict['message'], 'sync': row, 'result': {}, 'conflict': conflict}

    if conflict_checker is not None:
        conflict = conflict_checker(conn, payload)
        if conflict:
            row = _upsert_mobile_sync_action(
                conn,
                tenant_id=tenant_id,
                user_id=user_id,
                username=username,
                role=role,
                page_key=page_key,
                action_key=action_key,
                action_kind=action_kind,
                object_type=object_type,
                object_id=object_id,
                status='conflict',
                payload=payload,
                request_id=request_id,
                conflict=conflict,
                last_error=str(conflict.get('message') or 'conflict'),
                retry_delta=1,
            )
            _write_mobile_sync_audit(conn, tenant_id=tenant_id, user_id=user_id, username=username, role=role, action='mobile.sync.conflict', object_type=object_type, object_id=object_id, request_id=request_id, payload=payload, row=row, error=str(conflict.get('message') or 'conflict'), status='ERROR')
            return {'state': 'conflict', 'notice': str(conflict.get('message') or 'conflict'), 'sync': row, 'result': {}, 'conflict': conflict}

    try:
        result = dict(executor(conn, payload) or {})
        row = _upsert_mobile_sync_action(
            conn,
            tenant_id=tenant_id,
            user_id=user_id,
            username=username,
            role=role,
            page_key=page_key,
            action_key=action_key,
            action_kind=action_kind,
            object_type=object_type,
            object_id=object_id,
            status='saved',
            payload=payload,
            request_id=request_id,
            result=result,
            retry_delta=1,
        )
        _write_mobile_sync_audit(conn, tenant_id=tenant_id, user_id=user_id, username=username, role=role, action='mobile.sync.saved', object_type=object_type, object_id=object_id, request_id=request_id, payload=payload, row=row, status='OK')
        return {'state': 'saved', 'notice': 'Действие сохранено.', 'sync': row, 'result': result}
    except Exception as exc:
        if _classify_transient(exc):
            row = _upsert_mobile_sync_action(
                conn,
                tenant_id=tenant_id,
                user_id=user_id,
                username=username,
                role=role,
                page_key=page_key,
                action_key=action_key,
                action_kind=action_kind,
                object_type=object_type,
                object_id=object_id,
                status='pending_retry',
                payload=payload,
                request_id=request_id,
                last_error=str(exc),
                retry_delta=1,
            )
            _write_mobile_sync_audit(conn, tenant_id=tenant_id, user_id=user_id, username=username, role=role, action='mobile.sync.pending_retry', object_type=object_type, object_id=object_id, request_id=request_id, payload=payload, row=row, error=str(exc), status='WARN')
            return {'state': 'pending_retry', 'notice': 'Связь/сохранение нестабильны: действие поставлено в pending retry.', 'sync': row, 'result': {}, 'error': str(exc)}
        conflict = {'code': type(exc).__name__, 'message': str(exc), 'kind': 'action_rejected'}
        row = _upsert_mobile_sync_action(
            conn,
            tenant_id=tenant_id,
            user_id=user_id,
            username=username,
            role=role,
            page_key=page_key,
            action_key=action_key,
            action_kind=action_kind,
            object_type=object_type,
            object_id=object_id,
            status='conflict',
            payload=payload,
            request_id=request_id,
            conflict=conflict,
            last_error=str(exc),
            retry_delta=1,
        )
        _write_mobile_sync_audit(conn, tenant_id=tenant_id, user_id=user_id, username=username, role=role, action='mobile.sync.conflict', object_type=object_type, object_id=object_id, request_id=request_id, payload=payload, row=row, error=str(exc), status='ERROR')
        return {'state': 'conflict', 'notice': str(exc), 'sync': row, 'result': {}, 'conflict': conflict}


__all__ = [
    'MOBILE_SYNC_STATUSES',
    'MobileSyncConflictError',
    'build_mobile_action_key',
    'canonical_payload_hash',
    'detect_worklist_mobile_conflict',
    'execute_mobile_sync_action',
    'get_mobile_sync_action',
    'list_mobile_sync_actions',
    'summarize_mobile_sync_actions',
]
