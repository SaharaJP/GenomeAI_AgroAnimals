from __future__ import annotations

import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any, Mapping, Optional

from core.audit import write_audit
from core.common.time import ensure_utc, utc_isoformat
from core.domain import (
    AnimalEvent,
    AnimalEventActorType,
    AnimalEventCreate,
    AnimalEventSource,
    AnimalEventType,
    model_dump_compat,
)
from core.infra import AnimalEventsRepo


def _as_payload_dict(payload: AnimalEventCreate | AnimalEvent | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(payload, Mapping):
        return dict(payload)
    if is_dataclass(payload):
        return asdict(payload)
    return model_dump_compat(payload)


def _parse_event_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return ensure_utc(value)
    raw = str(value or '').strip()
    if not raw:
        raise ValueError('event_ts is required')
    raw = raw.replace('Z', '+00:00')
    try:
        return ensure_utc(datetime.fromisoformat(raw))
    except Exception as exc:
        raise ValueError(f'invalid event_ts: {value!r}') from exc


def build_animal_event(payload: AnimalEventCreate | AnimalEvent | Mapping[str, Any], *, tenant_id: str = 'default') -> AnimalEvent:
    data = _as_payload_dict(payload)
    event_ts = _parse_event_ts(data.get('event_ts'))
    event_id = str(data.get('event_id') or f'aevt_{uuid.uuid4().hex[:24]}')
    return AnimalEvent(
        tenant_id=str(data.get('tenant_id') or tenant_id or 'default'),
        created_at=event_ts,
        updated_at=event_ts,
        event_id=event_id,
        animal_id=str(data.get('animal_id') or ''),
        farm_id=(str(data.get('farm_id')) if data.get('farm_id') not in (None, '') else None),
        site_id=(str(data.get('site_id')) if data.get('site_id') not in (None, '') else None),
        lactation_id=(str(data.get('lactation_id')) if data.get('lactation_id') not in (None, '') else None),
        event_type=str(data.get('event_type') or AnimalEventType.CUSTOM_OPERATIONAL_EVENT.value),
        event_ts=event_ts,
        event_date=data.get('event_date'),
        actor_type=str(data.get('actor_type') or AnimalEventActorType.UNKNOWN.value),
        actor_user_id=(int(data.get('actor_user_id')) if data.get('actor_user_id') not in (None, '') else None),
        actor_username=(str(data.get('actor_username')) if data.get('actor_username') not in (None, '') else None),
        source=str(data.get('source') or AnimalEventSource.UNKNOWN.value),
        source_ref=(str(data.get('source_ref')) if data.get('source_ref') not in (None, '') else None),
        reason_code=(str(data.get('reason_code')) if data.get('reason_code') not in (None, '') else None),
        linked_object_type=(str(data.get('linked_object_type')) if data.get('linked_object_type') not in (None, '') else None),
        linked_object_id=(str(data.get('linked_object_id')) if data.get('linked_object_id') not in (None, '') else None),
        linked_decision_id=(str(data.get('linked_decision_id')) if data.get('linked_decision_id') not in (None, '') else None),
        linked_task_id=(str(data.get('linked_task_id')) if data.get('linked_task_id') not in (None, '') else None),
        request_id=(str(data.get('request_id')) if data.get('request_id') not in (None, '') else None),
        job_id=(str(data.get('job_id')) if data.get('job_id') not in (None, '') else None),
        data_version=(str(data.get('data_version')) if data.get('data_version') not in (None, '') else None),
        qc_run=(str(data.get('qc_run')) if data.get('qc_run') not in (None, '') else None),
        model_version=(str(data.get('model_version')) if data.get('model_version') not in (None, '') else None),
        scoring_run=(str(data.get('scoring_run')) if data.get('scoring_run') not in (None, '') else None),
        report_version=(str(data.get('report_version')) if data.get('report_version') not in (None, '') else None),
        payload=dict(data.get('payload') or {}),
        schema_version=int(data.get('schema_version') or 1),
    )


def append_animal_event(
    conn,
    *,
    tenant_id: str,
    event: AnimalEventCreate | AnimalEvent | Mapping[str, Any],
    audit_user_id: Optional[int] = None,
    audit_username: Optional[str] = None,
    audit_role: str = 'system',
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> str:
    built = build_animal_event(event, tenant_id=tenant_id)
    payload = model_dump_compat(built)
    repo = AnimalEventsRepo(conn)
    event_id = repo.append(tenant_id=str(tenant_id), created_at=utc_isoformat(built.created_at), payload=payload)
    write_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(audit_user_id if audit_user_id is not None else (built.actor_user_id or 0)),
        username=str(audit_username or built.actor_username or built.actor_type or 'system'),
        role=str(audit_role or 'system'),
        action='animal_event.append',
        object_type='animal_event',
        object_id=event_id,
        data_version=built.data_version,
        run_id=built.job_id,
        after=payload,
        ip=ip,
        user_agent=user_agent,
        status='OK',
        request_id=built.request_id,
    )
    return event_id


def get_animal_event(conn, *, tenant_id: str, event_id: str) -> Optional[dict[str, Any]]:
    return AnimalEventsRepo(conn).get(tenant_id=tenant_id, event_id=event_id)


def list_animal_events_for_animal(
    conn,
    *,
    tenant_id: str,
    animal_id: str,
    limit: int = 100,
    offset: int = 0,
    event_types: list[str] | None = None,
) -> dict[str, Any]:
    return AnimalEventsRepo(conn).list_for_animal(
        tenant_id=tenant_id,
        animal_id=animal_id,
        limit=limit,
        offset=offset,
        event_types=event_types,
    )


def normalize_legacy_operational_event(
    *,
    source_table: str,
    row: Mapping[str, Any],
    tenant_id: str = 'default',
    source: str = AnimalEventSource.MIGRATION.value,
) -> AnimalEventCreate:
    table = str(source_table).strip().lower()
    record = dict(row)
    if table == 'dm_repro_events':
        raw_type = str(record.get('event_type') or 'custom_operational_event').strip().lower()
        normalized_type = {
            'dryoff': AnimalEventType.DRY_OFF.value,
            'dry_off': AnimalEventType.DRY_OFF.value,
            'ai': AnimalEventType.INSEMINATION.value,
            'pregnancy_check': AnimalEventType.PREG_CHECK.value,
            'preg_check': AnimalEventType.PREG_CHECK.value,
        }.get(raw_type, raw_type or AnimalEventType.CUSTOM_OPERATIONAL_EVENT.value)
        return AnimalEventCreate(
            event_id=(str(record.get('repro_event_id')) if record.get('repro_event_id') not in (None, '') else None),
            animal_id=str(record.get('animal_id') or ''),
            farm_id=(str(record.get('farm_id')) if record.get('farm_id') not in (None, '') else None),
            lactation_id=(str(record.get('lactation_id')) if record.get('lactation_id') not in (None, '') else None),
            event_type=normalized_type,
            event_ts=str(record.get('event_ts') or record.get('event_date') or ''),
            actor_type=AnimalEventActorType.IMPORT.value,
            source=source,
            source_ref=f'{table}:{record.get("repro_event_id") or record.get("event_type") or "row"}',
            linked_object_type=('bull' if record.get('bull_id') else None),
            linked_object_id=(str(record.get('bull_id')) if record.get('bull_id') not in (None, '') else None),
            payload={k: v for k, v in record.items() if k not in {'animal_id', 'farm_id', 'lactation_id', 'event_type', 'event_date', 'event_ts'}},
        )
    if table == 'dm_treatments':
        return AnimalEventCreate(
            event_id=(str(record.get('treatment_id')) if record.get('treatment_id') not in (None, '') else None),
            animal_id=str(record.get('animal_id') or ''),
            farm_id=(str(record.get('farm_id')) if record.get('farm_id') not in (None, '') else None),
            lactation_id=(str(record.get('lactation_id')) if record.get('lactation_id') not in (None, '') else None),
            event_type=AnimalEventType.TREATMENT.value,
            event_ts=str(record.get('event_ts') or record.get('start_date') or ''),
            actor_type=AnimalEventActorType.IMPORT.value,
            source=source,
            source_ref=f'{table}:{record.get("treatment_id") or record.get("treatment_type") or "row"}',
            reason_code=(str(record.get('reason_code')) if record.get('reason_code') not in (None, '') else None),
            linked_object_type=('health_event' if record.get('reason_event_id') else None),
            linked_object_id=(str(record.get('reason_event_id')) if record.get('reason_event_id') not in (None, '') else None),
            payload={k: v for k, v in record.items() if k not in {'animal_id', 'farm_id', 'lactation_id', 'start_date', 'event_ts'}},
        )
    if table == 'dm_pen_moves':
        return AnimalEventCreate(
            event_id=(str(record.get('move_id')) if record.get('move_id') not in (None, '') else None),
            animal_id=str(record.get('animal_id') or ''),
            farm_id=(str(record.get('farm_id')) if record.get('farm_id') not in (None, '') else None),
            event_type=AnimalEventType.PEN_MOVE.value,
            event_ts=str(record.get('event_ts') or record.get('move_date') or ''),
            actor_type=AnimalEventActorType.IMPORT.value,
            source=source,
            source_ref=f'{table}:{record.get("move_id") or record.get("to_pen_id") or "row"}',
            reason_code=(str(record.get('reason_code')) if record.get('reason_code') not in (None, '') else None),
            linked_object_type=('pen' if record.get('to_pen_id') else None),
            linked_object_id=(str(record.get('to_pen_id')) if record.get('to_pen_id') not in (None, '') else None),
            payload={k: v for k, v in record.items() if k not in {'animal_id', 'farm_id', 'move_date', 'event_ts'}},
        )
    raise ValueError(f'unsupported legacy operational source_table: {source_table!r}')


__all__ = [
    'append_animal_event',
    'build_animal_event',
    'get_animal_event',
    'list_animal_events_for_animal',
    'normalize_legacy_operational_event',
]
