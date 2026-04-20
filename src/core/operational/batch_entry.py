from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Sequence

from core.audit import write_audit
from core.common.time import ensure_utc, utc_isoformat
from core.domain import AnimalEventActorType, AnimalEventCreate, AnimalEventReasonCode, AnimalEventSource, AnimalEventType
from core.infra import AnimalEventsRepo
from core.operational.animal_events import append_animal_event, list_animal_events_for_animal
from core.security import policy as security_policy


_BATCH_ACTIONS: dict[str, dict[str, Any]] = {
    'assign_check': {
        'label': 'Назначить проверку',
        'required_permission': security_policy.PERM_ANIMAL_EVENTS_WRITE,
        'event_type': AnimalEventType.CUSTOM_OPERATIONAL_EVENT.value,
        'reason_code': AnimalEventReasonCode.CHECK_ASSIGNED.value,
    },
    'mark_insemination': {
        'label': 'Отметить осеменение',
        'required_permission': security_policy.PERM_ANIMAL_EVENTS_WRITE,
        'event_type': AnimalEventType.INSEMINATION.value,
        'reason_code': AnimalEventReasonCode.INSEMINATION_PERFORMED.value,
    },
    'move_to_group': {
        'label': 'Перевести в группу',
        'required_permission': security_policy.PERM_ANIMAL_EVENTS_WRITE,
        'event_type': AnimalEventType.PEN_MOVE.value,
        'reason_code': AnimalEventReasonCode.PEN_PROTOCOL.value,
    },
    'close_status': {
        'label': 'Закрыть статус',
        'required_permission': security_policy.PERM_ANIMAL_EVENTS_CLOSE,
        'event_type': AnimalEventType.CUSTOM_OPERATIONAL_EVENT.value,
        'reason_code': AnimalEventReasonCode.STATUS_CLOSED.value,
    },
    'schedule_follow_up': {
        'label': 'Назначить follow-up',
        'required_permission': security_policy.PERM_ANIMAL_EVENTS_WRITE,
        'event_type': AnimalEventType.CUSTOM_OPERATIONAL_EVENT.value,
        'reason_code': AnimalEventReasonCode.FOLLOW_UP_ASSIGNED.value,
    },
}


@dataclass(slots=True)
class AnimalEventBatchEntryError(ValueError):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> dict[str, Any]:
        return {'code': self.code, 'message': self.message, 'details': dict(self.details or {})}



def _raise(code: str, message: str, **details: Any) -> None:
    raise AnimalEventBatchEntryError(code=code, message=message, details={k: v for k, v in details.items() if v is not None})



def animal_event_batch_entry_catalog() -> dict[str, Any]:
    return {
        'actions': [
            {
                'action': key,
                'label': value['label'],
                'event_type': value['event_type'],
                'reason_code': value['reason_code'],
                'required_permission': value['required_permission'],
            }
            for key, value in _BATCH_ACTIONS.items()
        ],
        'check_kinds': ['general_check', 'vet_check', 'repro_check', 'zootech_check'],
        'assignee_roles': [security_policy.ROLE_ZOOTECH, security_policy.ROLE_VET, security_policy.ROLE_OPERATOR],
        'insemination_methods': ['AI', 'natural', 'unknown'],
    }



def _normalize_event_ts(value: Any) -> str:
    raw = str(value or '').strip()
    if not raw:
        _raise('event_ts_required', 'Нужно указать дату и время batch-действия.')
    try:
        return utc_isoformat(ensure_utc(datetime.fromisoformat(raw.replace('Z', '+00:00'))))
    except Exception:
        _raise('event_ts_invalid', 'Дата и время batch-действия заполнены некорректно.', value=raw)



def _normalize_date(value: Any, *, field_name: str, label: str) -> str:
    raw = str(value or '').strip()
    if not raw:
        _raise(f'{field_name}_required', f'Нужно заполнить поле: {label}.')
    try:
        return date.fromisoformat(raw).isoformat()
    except Exception:
        _raise(f'{field_name}_invalid', f'Поле {label} заполнено некорректно.', value=raw)



def _normalize_action(action: Any) -> str:
    value = str(action or '').strip()
    if not value:
        _raise('batch_action_required', 'Нужно выбрать пакетное действие.')
    if value not in _BATCH_ACTIONS:
        _raise('batch_action_invalid', f"Пакетное действие '{value}' не поддерживается.", action=value)
    return value



def _require_permission(action: str, permissions: Sequence[str] | None, *, role: str | None = None, operation: str = 'batch entry') -> None:
    required = str(_BATCH_ACTIONS[action]['required_permission'])
    perms = set(str(p) for p in (permissions or []))
    if required not in perms:
        raise security_policy.PermissionDenied((required,), role=role, operation=operation)



def _normalize_animal_rows(animal_rows: Iterable[Mapping[str, Any] | str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for idx, raw in enumerate(animal_rows or []):
        if isinstance(raw, Mapping):
            animal_id = str(raw.get('animal_id') or '').strip()
            row = {k: raw.get(k) for k in raw.keys()}
        else:
            animal_id = str(raw or '').strip()
            row = {'animal_id': animal_id}
        if not animal_id:
            rows.append({'row_index': idx + 1, 'animal_id': '', 'status': 'invalid', 'message': 'animal_id пустой.'})
            continue
        if animal_id in seen:
            rows.append({'row_index': idx + 1, 'animal_id': animal_id, 'status': 'invalid', 'message': 'Животное продублировано в batch-списке.'})
            continue
        seen.add(animal_id)
        row['animal_id'] = animal_id
        row['row_index'] = idx + 1
        rows.append(row)
    return rows



def _build_action_key(*, tenant_id: str, action: str, animal_id: str, event_ts: str, params: Mapping[str, Any]) -> str:
    base = {
        'tenant_id': str(tenant_id),
        'action': str(action),
        'animal_id': str(animal_id),
        'event_ts': str(event_ts),
        'params': json.loads(json.dumps(dict(params or {}), ensure_ascii=False, sort_keys=True, default=str)),
    }
    raw = json.dumps(base, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]



def _prepare_row_spec(*, tenant_id: str, action: str, row: Mapping[str, Any], event_ts: str, params: Mapping[str, Any], data_version: str | None) -> dict[str, Any]:
    animal_id = str(row.get('animal_id') or '').strip()
    if not animal_id:
        return {'status': 'invalid', 'message': 'animal_id обязателен.'}

    shared_payload: dict[str, Any] = {
        'entry_mode': 'batch_entry',
        'workflow_action': str(action),
        'batch_action_label': str(_BATCH_ACTIONS[action]['label']),
    }
    event_type = str(_BATCH_ACTIONS[action]['event_type'])
    reason_code = str(_BATCH_ACTIONS[action]['reason_code'])
    comment = str(params.get('comment') or '').strip() or None

    if action == 'assign_check':
        due_date = _normalize_date(params.get('due_date'), field_name='due_date', label='Срок проверки')
        check_kind = str(params.get('check_kind') or 'general_check').strip()
        assignee_role = str(params.get('assignee_role') or '').strip() or None
        shared_payload.update({'check_kind': check_kind, 'due_date': due_date, 'assignee_role': assignee_role})
    elif action == 'mark_insemination':
        method = str(params.get('method') or 'AI').strip() or 'AI'
        bull_id = str(params.get('bull_id') or '').strip() or None
        shared_payload.update({'method': method, 'bull_id': bull_id})
    elif action == 'move_to_group':
        target_pen_id = str(params.get('target_pen_id') or '').strip()
        if not target_pen_id:
            return {'status': 'invalid', 'message': 'Для перевода в группу нужно указать target_pen_id.'}
        current_pen_id = str(row.get('pen_id') or row.get('current_pen_id') or '').strip() or None
        if current_pen_id and current_pen_id == target_pen_id:
            return {'status': 'invalid', 'message': 'Животное уже находится в выбранной группе.', 'current_pen_id': current_pen_id, 'target_pen_id': target_pen_id}
        shared_payload.update({
            'from_pen_id': current_pen_id,
            'from_pen_name': (str(row.get('pen_name') or row.get('current_pen_name') or '').strip() or None),
            'to_pen_id': target_pen_id,
            'to_pen_name': (str(params.get('target_pen_name') or '').strip() or None),
        })
    elif action == 'close_status':
        status_code = str(params.get('status_code') or '').strip()
        if not status_code:
            return {'status': 'invalid', 'message': 'Для закрытия статуса нужно заполнить status_code.'}
        shared_payload.update({'status_code': status_code, 'episode_status': 'closed'})
    elif action == 'schedule_follow_up':
        due_date = _normalize_date(params.get('due_date'), field_name='due_date', label='Срок follow-up')
        follow_up_kind = str(params.get('follow_up_kind') or 'follow_up').strip() or 'follow_up'
        assignee_role = str(params.get('assignee_role') or '').strip() or None
        shared_payload.update({'follow_up_kind': follow_up_kind, 'due_date': due_date, 'assignee_role': assignee_role})
    else:
        return {'status': 'invalid', 'message': f'Неизвестное действие: {action}'}

    action_key = _build_action_key(
        tenant_id=str(tenant_id),
        action=str(action),
        animal_id=str(animal_id),
        event_ts=str(event_ts),
        params={**shared_payload, 'comment': comment, 'data_version': data_version},
    )
    shared_payload['batch_action_key'] = action_key

    commit_spec = {
        'animal_id': animal_id,
        'farm_id': (str(row.get('farm_id') or '').strip() or None),
        'site_id': (str(row.get('site_id') or '').strip() or None),
        'lactation_id': (str(row.get('lactation_id') or '').strip() or None),
        'event_type': event_type,
        'event_ts': str(event_ts),
        'reason_code': reason_code,
        'comment': comment,
        'data_version': (str(row.get('data_version') or '').strip() or data_version or None),
        'payload': shared_payload,
        'linked_task_id': (str(params.get('linked_task_id') or '').strip() or None),
        'linked_decision_id': (str(params.get('linked_decision_id') or '').strip() or None),
        'source_ref': f'batch_entry:{action}',
        'action_key': action_key,
    }
    message = str(_BATCH_ACTIONS[action]['label'])
    if action == 'move_to_group':
        message = f"Перевод в группу {shared_payload.get('to_pen_id')}"
    elif action == 'close_status':
        message = f"Закрытие статуса {shared_payload.get('status_code')}"
    elif action == 'assign_check':
        message = f"Проверка до {shared_payload.get('due_date')}"
    elif action == 'schedule_follow_up':
        message = f"Follow-up до {shared_payload.get('due_date')}"
    elif action == 'mark_insemination':
        method = shared_payload.get('method') or 'AI'
        message = f"Осеменение ({method})"
    return {
        'status': 'valid',
        'message': message,
        'event_type': event_type,
        'reason_code': reason_code,
        'action_key': action_key,
        'commit_spec': commit_spec,
    }



def _build_preview_digest(action: str, event_ts: str, rows: Sequence[Mapping[str, Any]]) -> str:
    material = {
        'action': str(action),
        'event_ts': str(event_ts),
        'rows': [dict(r.get('commit_spec') or {}) for r in rows if r.get('status') == 'valid'],
    }
    raw = json.dumps(material, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()



def _event_already_exists(conn, *, tenant_id: str, animal_id: str, action_key: str) -> dict[str, Any] | None:
    existing = list_animal_events_for_animal(conn, tenant_id=str(tenant_id), animal_id=str(animal_id), limit=200, offset=0).get('events') or []
    for row in existing:
        payload = dict(row.get('payload') or {})
        if str(payload.get('batch_action_key') or '') == str(action_key):
            return dict(row)
    return None



def preview_animal_event_batch_use_case(
    *,
    conn,
    tenant_id: str,
    animal_rows: Iterable[Mapping[str, Any] | str],
    action: str,
    event_ts: str,
    user_id: int,
    username: str,
    role: str,
    permissions: Sequence[str] | None,
    request_id: str | None = None,
    data_version: str | None = None,
    params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_action = _normalize_action(action)
    _require_permission(normalized_action, permissions, role=role, operation='batch preview')
    normalized_ts = _normalize_event_ts(event_ts)
    base_rows = _normalize_animal_rows(animal_rows)
    prepared_rows: list[dict[str, Any]] = []
    for row in base_rows:
        prepared = {k: row.get(k) for k in row.keys() if k not in {'status', 'message'}}
        if row.get('status') == 'invalid':
            prepared_rows.append({**prepared, 'status': 'invalid', 'message': str(row.get('message') or 'Некорректная строка.')})
            continue
        try:
            result = _prepare_row_spec(
                tenant_id=str(tenant_id),
                action=normalized_action,
                row=row,
                event_ts=normalized_ts,
                params=dict(params or {}),
                data_version=data_version,
            )
            prepared_rows.append({**prepared, **result})
        except AnimalEventBatchEntryError as exc:
            prepared_rows.append({**prepared, 'status': 'invalid', 'message': exc.message, 'error': exc.to_dict()})

    digest = _build_preview_digest(normalized_action, normalized_ts, prepared_rows)
    preview_id = f"batch_{digest[:12]}"
    summary = {
        'rows_total': len(prepared_rows),
        'rows_valid': sum(1 for row in prepared_rows if row.get('status') == 'valid'),
        'rows_invalid': sum(1 for row in prepared_rows if row.get('status') == 'invalid'),
        'rows_conflict': 0,
    }
    result = {
        'ok': True,
        'preview_id': preview_id,
        'preview_kind': 'animal_event_batch_preview_v1',
        'action': normalized_action,
        'action_label': str(_BATCH_ACTIONS[normalized_action]['label']),
        'event_ts': normalized_ts,
        'data_version': data_version,
        'request_id': request_id or preview_id,
        'digest': digest,
        'summary': summary,
        'rows': prepared_rows,
    }
    write_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id or 0),
        username=str(username or ''),
        role=str(role or ''),
        action='animal_event.batch_entry.preview',
        object_type='batch_entry',
        object_id=preview_id,
        data_version=(str(data_version) if data_version not in (None, '') else None),
        run_id=None,
        before=None,
        after={'action': normalized_action, 'summary': summary, 'rows': prepared_rows},
        status='OK',
        request_id=(str(request_id or preview_id) if (request_id or preview_id) else None),
    )
    return result



def _validate_preview_object(preview: Mapping[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    if not isinstance(preview, Mapping):
        _raise('preview_required', 'Нужно сначала выполнить dry-run preview.')
    if str(preview.get('preview_kind') or '') != 'animal_event_batch_preview_v1':
        _raise('preview_invalid', 'Передан некорректный preview объект.')
    action = _normalize_action(preview.get('action'))
    event_ts = _normalize_event_ts(preview.get('event_ts'))
    rows = [dict(row) for row in (preview.get('rows') or [])]
    if not rows:
        _raise('preview_empty', 'Preview пустой: нет строк для применения batch-действия.')
    digest = _build_preview_digest(action, event_ts, rows)
    if str(preview.get('digest') or '') != digest:
        _raise('preview_digest_mismatch', 'Preview устарел или был изменён. Пересоберите dry-run preview.')
    return action, event_ts, rows



def commit_animal_event_batch_use_case(
    *,
    conn,
    tenant_id: str,
    preview: Mapping[str, Any],
    user_id: int,
    username: str,
    role: str,
    permissions: Sequence[str] | None,
    request_id: str | None = None,
) -> dict[str, Any]:
    action, _, rows = _validate_preview_object(preview)
    _require_permission(action, permissions, role=role, operation='batch commit')
    preview_id = str(preview.get('preview_id') or '') or 'batch_commit'
    effective_request_id = str(request_id or preview.get('request_id') or preview_id)
    results: list[dict[str, Any]] = []
    applied = 0
    conflicts = 0
    invalid = 0

    for row in rows:
        base = {
            'row_index': row.get('row_index'),
            'animal_id': row.get('animal_id'),
            'message': row.get('message'),
        }
        if row.get('status') != 'valid':
            invalid += 1
            results.append({**base, 'status': 'skipped_invalid'})
            continue
        commit_spec = dict(row.get('commit_spec') or {})
        existing = _event_already_exists(conn, tenant_id=str(tenant_id), animal_id=str(commit_spec.get('animal_id') or ''), action_key=str(commit_spec.get('action_key') or ''))
        if existing:
            conflicts += 1
            results.append({
                **base,
                'status': 'conflict',
                'message': 'Во время commit найден конфликт: такое batch-действие уже записано.',
                'existing_event_id': str(existing.get('event_id') or ''),
            })
            continue
        payload = dict(commit_spec.get('payload') or {})
        payload['batch_preview_id'] = preview_id
        payload['batch_request_id'] = effective_request_id
        payload['batch_row_index'] = row.get('row_index')
        event = AnimalEventCreate(
            animal_id=str(commit_spec.get('animal_id') or ''),
            farm_id=commit_spec.get('farm_id'),
            site_id=commit_spec.get('site_id'),
            lactation_id=commit_spec.get('lactation_id'),
            event_type=str(commit_spec.get('event_type') or ''),
            event_ts=str(commit_spec.get('event_ts') or ''),
            actor_type=AnimalEventActorType.USER.value,
            actor_user_id=int(user_id or 0),
            actor_username=str(username or ''),
            source=AnimalEventSource.MANUAL_UI.value,
            source_ref=str(commit_spec.get('source_ref') or f'batch_entry:{action}'),
            reason_code=(str(commit_spec.get('reason_code') or '') or None),
            linked_task_id=commit_spec.get('linked_task_id'),
            linked_decision_id=commit_spec.get('linked_decision_id'),
            request_id=effective_request_id,
            data_version=commit_spec.get('data_version'),
            payload=payload,
        )
        try:
            event_id = append_animal_event(
                conn,
                tenant_id=str(tenant_id),
                event=event,
                audit_user_id=int(user_id or 0),
                audit_username=str(username or ''),
                audit_role=str(role or ''),
            )
            applied += 1
            results.append({**base, 'status': 'applied', 'event_id': str(event_id), 'message': 'Batch-действие применено.'})
        except Exception as exc:  # pragma: no cover - protective branch
            conflicts += 1
            results.append({**base, 'status': 'error', 'message': f'{type(exc).__name__}: {exc}'})

    summary = {
        'rows_total': len(rows),
        'rows_applied': applied,
        'rows_conflict': conflicts,
        'rows_invalid': invalid,
    }
    write_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id or 0),
        username=str(username or ''),
        role=str(role or ''),
        action='animal_event.batch_entry.commit',
        object_type='batch_entry',
        object_id=preview_id,
        data_version=(str(preview.get('data_version')) if preview.get('data_version') not in (None, '') else None),
        run_id=None,
        before={'preview_id': preview_id, 'action': action},
        after={'summary': summary, 'results': results},
        status='OK',
        request_id=effective_request_id,
    )
    return {
        'ok': True,
        'preview_id': preview_id,
        'action': action,
        'summary': summary,
        'results': results,
        'notice': f"Batch commit завершён: применено {applied}, конфликтов {conflicts}, пропущено {invalid}.",
    }


__all__ = [
    'AnimalEventBatchEntryError',
    'animal_event_batch_entry_catalog',
    'preview_animal_event_batch_use_case',
    'commit_animal_event_batch_use_case',
]
