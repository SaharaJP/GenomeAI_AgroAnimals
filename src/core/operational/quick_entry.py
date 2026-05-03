from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional

from core.audit import write_audit
from core.common.time import ensure_utc, utc_isoformat
from core.domain import AnimalEventActorType, AnimalEventCreate, AnimalEventReasonCode, AnimalEventSource, AnimalEventType
from core.domain.enums import ANIMAL_EVENT_REASON_CODES, ANIMAL_EVENT_TYPES
from core.infra import AnimalEventsRepo
from core.operational.animal_events import append_animal_event, get_animal_event, list_animal_events_for_animal


_CREATE_DEFAULT_REASON_CODES: dict[str, str] = {
    AnimalEventType.HEAT.value: AnimalEventReasonCode.HEAT_OBSERVED.value,
    AnimalEventType.INSEMINATION.value: AnimalEventReasonCode.INSEMINATION_PERFORMED.value,
    AnimalEventType.PREG_CHECK.value: AnimalEventReasonCode.PREGNANCY_CONFIRMED.value,
    AnimalEventType.CALVING.value: AnimalEventReasonCode.CALVING_NORMAL.value,
    AnimalEventType.DRY_OFF.value: AnimalEventReasonCode.DRY_PERIOD_START.value,
    AnimalEventType.TREATMENT.value: AnimalEventReasonCode.TREATMENT_PROTOCOL.value,
    AnimalEventType.CULL.value: AnimalEventReasonCode.CULL_HEALTH.value,
    AnimalEventType.DEATH.value: AnimalEventReasonCode.DEATH_ON_FARM.value,
    AnimalEventType.PEN_MOVE.value: AnimalEventReasonCode.PEN_REBALANCE.value,
    AnimalEventType.COMMENT.value: AnimalEventReasonCode.COMMENT_ADDED.value,
    AnimalEventType.MANUAL_NOTE.value: AnimalEventReasonCode.MANUAL_NOTE_ADDED.value,
    AnimalEventType.CUSTOM_OPERATIONAL_EVENT.value: AnimalEventReasonCode.CUSTOM_OTHER.value,
}
_CONFIRM_CLOSE_BLOCKED_TYPES = {
    AnimalEventType.COMMENT.value,
    AnimalEventType.MANUAL_NOTE.value,
}


@dataclass(slots=True)
class AnimalEventQuickEntryError(ValueError):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": dict(self.details or {})}



def _raise(code: str, message: str, **details: Any) -> None:
    raise AnimalEventQuickEntryError(code=code, message=message, details={k: v for k, v in details.items() if v is not None})



def _normalize_event_ts(value: Any) -> str:
    raw = str(value or '').strip()
    if not raw:
        _raise('event_ts_required', 'Нужно указать дату и время события.')
    try:
        return utc_isoformat(ensure_utc(datetime.fromisoformat(raw.replace('Z', '+00:00'))))
    except Exception as exc:
        _raise('event_ts_invalid', 'Дата и время события заполнены некорректно.', value=raw)
        raise exc  # pragma: no cover



def _normalize_event_type(value: Any) -> str:
    event_type = str(value or '').strip()
    if not event_type:
        _raise('event_type_required', 'Нужно выбрать тип события.')
    if event_type not in ANIMAL_EVENT_TYPES:
        _raise('event_type_invalid', f"Тип события '{event_type}' не поддерживается.", event_type=event_type)
    return event_type



def _normalize_reason_code(value: Any) -> Optional[str]:
    reason_code = str(value or '').strip()
    if not reason_code:
        return None
    if reason_code not in ANIMAL_EVENT_REASON_CODES:
        _raise('reason_code_invalid', f"Код причины '{reason_code}' не поддерживается.", reason_code=reason_code)
    return reason_code



def _normalize_comment(value: Any, *, required: bool = False, label: str = 'Комментарий') -> Optional[str]:
    comment = str(value or '').strip()
    if required and not comment:
        _raise('comment_required', f'{label} обязателен.')
    return comment or None



def _ensure_target_event(conn, *, tenant_id: str, event_id: str, animal_id: str | None = None) -> dict[str, Any]:
    target = get_animal_event(conn, tenant_id=tenant_id, event_id=event_id)
    if not target:
        _raise('target_event_not_found', 'Исходное событие не найдено.', event_id=event_id)
    if animal_id and str(target.get('animal_id') or '') != str(animal_id):
        _raise('target_event_mismatch', 'Событие относится к другому животному.', event_id=event_id, animal_id=animal_id)
    if str(target.get('event_type') or '') in _CONFIRM_CLOSE_BLOCKED_TYPES:
        _raise('target_event_invalid_type', 'Подтвердить или закрыть можно только operational-событие, а не комментарий/заметку.', event_type=target.get('event_type'))
    return target



def _ensure_no_duplicate_linked_action(conn, *, tenant_id: str, target_event_id: str, workflow_action: str, duplicate_code: str, duplicate_message: str) -> None:
    linked = AnimalEventsRepo(conn).list_linked(tenant_id=tenant_id, linked_object_type='animal_event', linked_object_id=target_event_id, limit=100, offset=0)
    for row in linked.get('events') or []:
        payload = dict(row.get('payload') or {})
        if str(payload.get('workflow_action') or '') == workflow_action:
            _raise(duplicate_code, duplicate_message, target_event_id=target_event_id, linked_event_id=row.get('event_id'))



def _build_common_event_payload(
    *,
    animal_id: str,
    event_type: str,
    event_ts: str,
    user_id: int,
    username: str,
    source_ref: str,
    request_id: str | None,
    data_version: str | None,
    farm_id: str | None = None,
    site_id: str | None = None,
    lactation_id: str | None = None,
    reason_code: str | None = None,
    linked_object_type: str | None = None,
    linked_object_id: str | None = None,
    linked_task_id: str | None = None,
    linked_decision_id: str | None = None,
    payload: Mapping[str, Any] | None = None,
) -> AnimalEventCreate:
    return AnimalEventCreate(
        animal_id=str(animal_id or ''),
        farm_id=(str(farm_id) if farm_id not in (None, '') else None),
        site_id=(str(site_id) if site_id not in (None, '') else None),
        lactation_id=(str(lactation_id) if lactation_id not in (None, '') else None),
        event_type=event_type,
        event_ts=event_ts,
        actor_type=AnimalEventActorType.USER.value,
        actor_user_id=int(user_id or 0),
        actor_username=str(username or ''),
        source=AnimalEventSource.MANUAL_UI.value,
        source_ref=source_ref,
        reason_code=reason_code,
        linked_object_type=linked_object_type,
        linked_object_id=linked_object_id,
        linked_task_id=(str(linked_task_id) if linked_task_id not in (None, '') else None),
        linked_decision_id=(str(linked_decision_id) if linked_decision_id not in (None, '') else None),
        request_id=(str(request_id) if request_id not in (None, '') else None),
        data_version=(str(data_version) if data_version not in (None, '') else None),
        payload=dict(payload or {}),
    )



def _write_use_case_audit(
    conn,
    *,
    tenant_id: str,
    user_id: int,
    username: str,
    role: str,
    action: str,
    event_id: str,
    data_version: str | None,
    request_id: str | None,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> None:
    write_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id or 0),
        username=str(username or ''),
        role=str(role or ''),
        action=action,
        object_type='animal_event',
        object_id=str(event_id),
        data_version=(str(data_version) if data_version not in (None, '') else None),
        run_id=None,
        before=dict(before or {}),
        after=dict(after or {}),
        status='OK',
        request_id=(str(request_id) if request_id not in (None, '') else None),
    )



def animal_event_quick_entry_catalog() -> dict[str, Any]:
    return {
        'event_types': [
            AnimalEventType.HEAT.value,
            AnimalEventType.INSEMINATION.value,
            AnimalEventType.PREG_CHECK.value,
            AnimalEventType.CALVING.value,
            AnimalEventType.DRY_OFF.value,
            AnimalEventType.TREATMENT.value,
            AnimalEventType.CULL.value,
            AnimalEventType.DEATH.value,
            AnimalEventType.PEN_MOVE.value,
            AnimalEventType.MANUAL_NOTE.value,
            AnimalEventType.CUSTOM_OPERATIONAL_EVENT.value,
        ],
        'default_reason_by_type': dict(_CREATE_DEFAULT_REASON_CODES),
        'reason_codes': sorted(ANIMAL_EVENT_REASON_CODES),
    }



def create_animal_event_use_case(
    *,
    conn,
    tenant_id: str,
    animal_id: str,
    event_type: str,
    event_ts: str,
    user_id: int,
    username: str,
    role: str,
    comment: str | None = None,
    reason_code: str | None = None,
    farm_id: str | None = None,
    site_id: str | None = None,
    lactation_id: str | None = None,
    linked_task_id: str | None = None,
    linked_decision_id: str | None = None,
    linked_object_type: str | None = None,
    linked_object_id: str | None = None,
    data_version: str | None = None,
    request_id: str | None = None,
    extra_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not str(animal_id or '').strip():
        _raise('animal_id_required', 'Нужно выбрать животное.')
    normalized_type = _normalize_event_type(event_type)
    normalized_ts = _normalize_event_ts(event_ts)
    normalized_reason = _normalize_reason_code(reason_code)
    normalized_comment = _normalize_comment(comment, required=normalized_type in {AnimalEventType.MANUAL_NOTE.value, AnimalEventType.CUSTOM_OPERATIONAL_EVENT.value}, label='Текст события')
    payload = dict(extra_payload or {})
    if normalized_comment:
        payload['comment'] = normalized_comment
    payload.setdefault('entry_mode', 'quick_entry')
    event = _build_common_event_payload(
        animal_id=str(animal_id),
        farm_id=farm_id,
        site_id=site_id,
        lactation_id=lactation_id,
        event_type=normalized_type,
        event_ts=normalized_ts,
        user_id=int(user_id or 0),
        username=str(username or ''),
        source_ref='quick_entry:create',
        request_id=request_id,
        data_version=data_version,
        reason_code=normalized_reason,
        linked_task_id=linked_task_id,
        linked_decision_id=linked_decision_id,
        linked_object_type=linked_object_type,
        linked_object_id=linked_object_id,
        payload=payload,
    )
    event_id = append_animal_event(
        conn,
        tenant_id=str(tenant_id),
        event=event,
        audit_user_id=int(user_id or 0),
        audit_username=str(username or ''),
        audit_role=str(role or ''),
    )
    after = get_animal_event(conn, tenant_id=str(tenant_id), event_id=event_id) or {}
    _write_use_case_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id or 0),
        username=str(username or ''),
        role=str(role or ''),
        action='animal_event.quick_entry.create',
        event_id=event_id,
        data_version=(after or {}).get('data_version') or data_version,
        request_id=request_id,
        before=None,
        after=after,
    )
    return {
        'ok': True,
        'operation': 'create',
        'event_id': event_id,
        'after': after,
        'notice': 'Событие добавлено в историю животного.',
        'data_version': (after or {}).get('data_version') or data_version,
    }



def confirm_animal_event_use_case(
    *,
    conn,
    tenant_id: str,
    target_event_id: str,
    user_id: int,
    username: str,
    role: str,
    event_ts: str,
    comment: str | None = None,
    request_id: str | None = None,
    data_version: str | None = None,
) -> dict[str, Any]:
    if not str(target_event_id or '').strip():
        _raise('target_event_required', 'Нужно выбрать событие для подтверждения.')
    normalized_ts = _normalize_event_ts(event_ts)
    target = _ensure_target_event(conn, tenant_id=str(tenant_id), event_id=str(target_event_id))
    _ensure_no_duplicate_linked_action(
        conn,
        tenant_id=str(tenant_id),
        target_event_id=str(target_event_id),
        workflow_action='confirm_event',
        duplicate_code='event_already_confirmed',
        duplicate_message='Это событие уже подтверждено.',
    )
    normalized_comment = _normalize_comment(comment, required=False)
    payload = {
        'entry_mode': 'quick_entry',
        'workflow_action': 'confirm_event',
        'target_event_id': str(target_event_id),
        'target_event_type': str(target.get('event_type') or ''),
        'target_event_ts': str(target.get('event_ts') or ''),
    }
    if normalized_comment:
        payload['comment'] = normalized_comment
    event = _build_common_event_payload(
        animal_id=str(target.get('animal_id') or ''),
        farm_id=(str(target.get('farm_id')) if target.get('farm_id') not in (None, '') else None),
        site_id=(str(target.get('site_id')) if target.get('site_id') not in (None, '') else None),
        lactation_id=(str(target.get('lactation_id')) if target.get('lactation_id') not in (None, '') else None),
        event_type=AnimalEventType.COMMENT.value,
        event_ts=normalized_ts,
        user_id=int(user_id or 0),
        username=str(username or ''),
        source_ref='quick_entry:confirm',
        request_id=request_id,
        data_version=(str(target.get('data_version')) if target.get('data_version') not in (None, '') else data_version),
        reason_code=AnimalEventReasonCode.COMMENT_ADDED.value,
        linked_object_type='animal_event',
        linked_object_id=str(target_event_id),
        payload=payload,
    )
    event_id = append_animal_event(
        conn,
        tenant_id=str(tenant_id),
        event=event,
        audit_user_id=int(user_id or 0),
        audit_username=str(username or ''),
        audit_role=str(role or ''),
    )
    after = get_animal_event(conn, tenant_id=str(tenant_id), event_id=event_id) or {}
    _write_use_case_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id or 0),
        username=str(username or ''),
        role=str(role or ''),
        action='animal_event.quick_entry.confirm',
        event_id=event_id,
        data_version=(after or {}).get('data_version') or target.get('data_version') or data_version,
        request_id=request_id,
        before=target,
        after=after,
    )
    return {
        'ok': True,
        'operation': 'confirm',
        'event_id': event_id,
        'target_event_id': str(target_event_id),
        'after': after,
        'notice': 'Событие подтверждено и добавлено в append-only историю.',
        'data_version': (after or {}).get('data_version') or target.get('data_version') or data_version,
    }



def close_animal_event_episode_use_case(
    *,
    conn,
    tenant_id: str,
    target_event_id: str,
    user_id: int,
    username: str,
    role: str,
    event_ts: str,
    comment: str | None = None,
    request_id: str | None = None,
    data_version: str | None = None,
) -> dict[str, Any]:
    if not str(target_event_id or '').strip():
        _raise('target_event_required', 'Нужно выбрать событие или эпизод для закрытия.')
    normalized_ts = _normalize_event_ts(event_ts)
    target = _ensure_target_event(conn, tenant_id=str(tenant_id), event_id=str(target_event_id))
    _ensure_no_duplicate_linked_action(
        conn,
        tenant_id=str(tenant_id),
        target_event_id=str(target_event_id),
        workflow_action='close_episode',
        duplicate_code='event_episode_already_closed',
        duplicate_message='Этот эпизод уже закрыт.',
    )
    normalized_comment = _normalize_comment(comment, required=False)
    payload = {
        'entry_mode': 'quick_entry',
        'workflow_action': 'close_episode',
        'target_event_id': str(target_event_id),
        'target_event_type': str(target.get('event_type') or ''),
        'episode_status': 'closed',
    }
    if normalized_comment:
        payload['comment'] = normalized_comment
    event = _build_common_event_payload(
        animal_id=str(target.get('animal_id') or ''),
        farm_id=(str(target.get('farm_id')) if target.get('farm_id') not in (None, '') else None),
        site_id=(str(target.get('site_id')) if target.get('site_id') not in (None, '') else None),
        lactation_id=(str(target.get('lactation_id')) if target.get('lactation_id') not in (None, '') else None),
        event_type=AnimalEventType.COMMENT.value,
        event_ts=normalized_ts,
        user_id=int(user_id or 0),
        username=str(username or ''),
        source_ref='quick_entry:close_episode',
        request_id=request_id,
        data_version=(str(target.get('data_version')) if target.get('data_version') not in (None, '') else data_version),
        reason_code=AnimalEventReasonCode.COMMENT_ADDED.value,
        linked_object_type='animal_event',
        linked_object_id=str(target_event_id),
        payload=payload,
    )
    event_id = append_animal_event(
        conn,
        tenant_id=str(tenant_id),
        event=event,
        audit_user_id=int(user_id or 0),
        audit_username=str(username or ''),
        audit_role=str(role or ''),
    )
    after = get_animal_event(conn, tenant_id=str(tenant_id), event_id=event_id) or {}
    _write_use_case_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id or 0),
        username=str(username or ''),
        role=str(role or ''),
        action='animal_event.quick_entry.close_episode',
        event_id=event_id,
        data_version=(after or {}).get('data_version') or target.get('data_version') or data_version,
        request_id=request_id,
        before=target,
        after=after,
    )
    return {
        'ok': True,
        'operation': 'close_episode',
        'event_id': event_id,
        'target_event_id': str(target_event_id),
        'after': after,
        'notice': 'Эпизод закрыт и записан в историю без изменения исходного события.',
        'data_version': (after or {}).get('data_version') or target.get('data_version') or data_version,
    }



def add_animal_event_comment_use_case(
    *,
    conn,
    tenant_id: str,
    animal_id: str,
    user_id: int,
    username: str,
    role: str,
    event_ts: str,
    comment: str,
    request_id: str | None = None,
    data_version: str | None = None,
    target_event_id: str | None = None,
    linked_task_id: str | None = None,
    linked_decision_id: str | None = None,
) -> dict[str, Any]:
    if not str(animal_id or '').strip():
        _raise('animal_id_required', 'Нужно выбрать животное.')
    normalized_ts = _normalize_event_ts(event_ts)
    normalized_comment = _normalize_comment(comment, required=True)
    target = None
    if str(target_event_id or '').strip():
        target = _ensure_target_event(conn, tenant_id=str(tenant_id), event_id=str(target_event_id), animal_id=str(animal_id))
    payload = {'entry_mode': 'quick_entry', 'comment': normalized_comment}
    event = _build_common_event_payload(
        animal_id=str(animal_id),
        farm_id=(str((target or {}).get('farm_id')) if (target or {}).get('farm_id') not in (None, '') else None),
        site_id=(str((target or {}).get('site_id')) if (target or {}).get('site_id') not in (None, '') else None),
        lactation_id=(str((target or {}).get('lactation_id')) if (target or {}).get('lactation_id') not in (None, '') else None),
        event_type=AnimalEventType.COMMENT.value,
        event_ts=normalized_ts,
        user_id=int(user_id or 0),
        username=str(username or ''),
        source_ref='quick_entry:comment',
        request_id=request_id,
        data_version=(str((target or {}).get('data_version')) if (target or {}).get('data_version') not in (None, '') else data_version),
        reason_code=AnimalEventReasonCode.COMMENT_ADDED.value,
        linked_object_type=('animal_event' if target else None),
        linked_object_id=(str(target_event_id) if target else None),
        linked_task_id=linked_task_id,
        linked_decision_id=linked_decision_id,
        payload=payload,
    )
    event_id = append_animal_event(
        conn,
        tenant_id=str(tenant_id),
        event=event,
        audit_user_id=int(user_id or 0),
        audit_username=str(username or ''),
        audit_role=str(role or ''),
    )
    after = get_animal_event(conn, tenant_id=str(tenant_id), event_id=event_id) or {}
    _write_use_case_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id or 0),
        username=str(username or ''),
        role=str(role or ''),
        action='animal_event.quick_entry.comment',
        event_id=event_id,
        data_version=(after or {}).get('data_version') or (target or {}).get('data_version') or data_version,
        request_id=request_id,
        before=target,
        after=after,
    )
    return {
        'ok': True,
        'operation': 'comment',
        'event_id': event_id,
        'after': after,
        'notice': 'Комментарий добавлен в историю животного.',
        'data_version': (after or {}).get('data_version') or (target or {}).get('data_version') or data_version,
    }



def list_recent_animal_events_use_case(*, conn, tenant_id: str, animal_id: str, limit: int = 25) -> list[dict[str, Any]]:
    events = list_animal_events_for_animal(conn, tenant_id=str(tenant_id), animal_id=str(animal_id), limit=int(limit), offset=0).get('events') or []
    out: list[dict[str, Any]] = []
    for row in events:
        payload = dict(row.get('payload') or {})
        display_type = str(row.get('event_type') or '')
        if str(payload.get('workflow_action') or '') == 'confirm_event':
            display_type = f"confirm → {payload.get('target_event_type') or row.get('linked_object_id') or ''}".strip()
        elif str(payload.get('workflow_action') or '') == 'close_episode':
            display_type = f"close_episode → {payload.get('target_event_type') or row.get('linked_object_id') or ''}".strip()
        note = str(payload.get('comment') or '')
        out.append({
            'event_id': str(row.get('event_id') or ''),
            'event_ts': str(row.get('event_ts') or ''),
            'event_type': str(row.get('event_type') or ''),
            'display_type': display_type,
            'reason_code': str(row.get('reason_code') or ''),
            'actor_username': str(row.get('actor_username') or row.get('actor_type') or ''),
            'source': str(row.get('source') or ''),
            'linked_event_id': str(row.get('linked_object_id') or ''),
            'comment': note,
            'payload': payload,
        })
    return out


__all__ = [
    'AnimalEventQuickEntryError',
    'add_animal_event_comment_use_case',
    'animal_event_quick_entry_catalog',
    'close_animal_event_episode_use_case',
    'confirm_animal_event_use_case',
    'create_animal_event_use_case',
    'list_recent_animal_events_use_case',
]
