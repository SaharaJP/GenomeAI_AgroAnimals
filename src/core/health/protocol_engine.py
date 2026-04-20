from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import pandas as pd
import yaml

from core.audit import write_audit
from core.common.time import ensure_utc, utc_isoformat
from core.infra import AlertsRepo, VetProtocolExecutionsRepo
from core.operational.quick_entry import create_animal_event_use_case
from core.workflow.worklists import close_worklist_use_case, create_worklist_use_case, get_worklist
from genomeai.drilldown import compute_pen_assignments

CATALOG_PATH = Path('configs/health/vet_protocols_v1.yaml')
DEFAULT_PROTOCOL_STATUS_LABELS = {
    'open': 'Открыт',
    'in_progress': 'В работе',
    'completed': 'Завершён',
    'cancelled': 'Отменён',
}
DEFAULT_STEP_STATUS_LABELS = {
    'pending': 'Ожидает',
    'done': 'Выполнен',
    'skipped': 'Пропущен',
    'cancelled': 'Отменён',
}
STEP_KIND_LABELS = {
    'observation': 'Наблюдение',
    'treatment': 'Лечение',
    'follow_up': 'Follow-up',
}
ROLE_ALLOWED_STEP_KINDS = {
    'Admin': {'observation', 'treatment', 'follow_up'},
    'Vet': {'observation', 'treatment', 'follow_up'},
    'Zootech': {'observation', 'follow_up'},
    'Operator': {'observation', 'follow_up'},
    'Director': set(),
    'Viewer': set(),
}


@dataclass(slots=True)
class VetProtocolEngineError(ValueError):
    code: str
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return self.message


def _raise(code: str, message: str, **details: Any) -> None:
    raise VetProtocolEngineError(code=code, message=message, details={k: v for k, v in details.items() if v is not None})


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _parse_dt(value: Any) -> datetime | None:
    raw = _clean(value)
    if not raw:
        return None
    try:
        return ensure_utc(datetime.fromisoformat(raw.replace('Z', '+00:00')))
    except Exception:
        try:
            ts = pd.to_datetime(raw, errors='coerce', utc=True)
            if pd.isna(ts):
                return None
            return ensure_utc(ts.to_pydatetime())
        except Exception:
            return None


def _parse_date(value: Any) -> date | None:
    dt = _parse_dt(value)
    if dt is not None:
        return dt.date()
    raw = _clean(value)
    if not raw:
        return None
    try:
        ts = pd.to_datetime(raw, errors='coerce')
        if pd.isna(ts):
            return None
        return ts.date()
    except Exception:
        return None


def _read_csv(path: Path | None) -> pd.DataFrame:
    try:
        if path and Path(path).exists():
            return pd.read_csv(path)
    except Exception:
        pass
    return pd.DataFrame()


def _catalog_file(project_root: Path | str | None) -> Path:
    root = Path(project_root or Path.cwd())
    return (root / CATALOG_PATH).resolve()


def load_vet_protocol_catalog(*, project_root: Path | str | None = None) -> dict[str, Any]:
    path = _catalog_file(project_root)
    if not path.exists():
        _raise('catalog_missing', f'Не найден каталог vet protocols: {path}')
    try:
        raw = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    except Exception as exc:
        _raise('catalog_invalid', 'Не удалось прочитать каталог vet protocols.', path=str(path), error=str(exc))
    protocols = list(raw.get('protocols') or [])
    items: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for proto in protocols:
        if not isinstance(proto, Mapping):
            continue
        item = {str(k): v for k, v in dict(proto).items()}
        key = _clean(item.get('protocol_key'))
        if not key:
            continue
        item['protocol_key'] = key
        item['protocol_version'] = int(item.get('protocol_version') or 1)
        item['title'] = _clean(item.get('title')) or key
        item['owner_role'] = _clean(item.get('owner_role')) or 'Vet'
        item['assignee_team'] = _clean(item.get('assignee_team')) or 'team-health'
        norm_steps: list[dict[str, Any]] = []
        for idx, step in enumerate(list(item.get('steps') or []), start=1):
            if not isinstance(step, Mapping):
                continue
            row = {str(k): v for k, v in dict(step).items()}
            row['step_key'] = _clean(row.get('step_key')) or f'step_{idx}'
            row['label'] = _clean(row.get('label')) or row['step_key']
            row['kind'] = _clean(row.get('kind')) or 'observation'
            row['required'] = bool(row.get('required', True))
            row['due_offset_days'] = int(row.get('due_offset_days') or 0)
            norm_steps.append(row)
        item['steps'] = norm_steps
        items.append(item)
        by_key[key] = item
    return {
        'version': int(raw.get('version') or 1),
        'catalog_version': _clean(raw.get('catalog_version')) or 'unknown',
        'path': str(path),
        'protocols': items,
        'by_key': by_key,
    }


def protocol_options(*, project_root: Path | str | None = None) -> list[str]:
    return [str(p.get('protocol_key')) for p in load_vet_protocol_catalog(project_root=project_root).get('protocols') or []]


def _protocol_or_raise(*, project_root: Path | str | None, protocol_key: str) -> tuple[dict[str, Any], dict[str, Any]]:
    catalog = load_vet_protocol_catalog(project_root=project_root)
    proto = dict(catalog.get('by_key', {}).get(str(protocol_key)) or {})
    if not proto:
        _raise('protocol_not_found', f"Протокол '{protocol_key}' не найден.", protocol_key=protocol_key)
    return catalog, proto


def _clone_steps(protocol: Mapping[str, Any], *, start_date: date) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for idx, step in enumerate(list(protocol.get('steps') or []), start=1):
        row = dict(step)
        due_date = start_date + timedelta(days=int(row.get('due_offset_days') or 0))
        steps.append({
            'idx': idx,
            'step_key': _clean(row.get('step_key')) or f'step_{idx}',
            'label': _clean(row.get('label')) or _clean(row.get('step_key')) or f'Step {idx}',
            'kind': _clean(row.get('kind')) or 'observation',
            'required': bool(row.get('required', True)),
            'due_offset_days': int(row.get('due_offset_days') or 0),
            'due_at': due_date.isoformat(),
            'status': 'pending',
            'completed_at': None,
            'completed_by': None,
            'completed_by_username': None,
            'comment': None,
            'linked_treatment_id': None,
            'observation_event_id': None,
        })
    return steps


def _metrics_from_steps(steps: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    required_total = sum(1 for s in steps if bool(s.get('required')))
    required_done = sum(1 for s in steps if bool(s.get('required')) and _clean(s.get('status')) == 'done')
    optional_total = sum(1 for s in steps if not bool(s.get('required')))
    optional_done = sum(1 for s in steps if not bool(s.get('required')) and _clean(s.get('status')) == 'done')
    total = max(1, len(list(steps)))
    done = sum(1 for s in steps if _clean(s.get('status')) == 'done')
    return {
        'required_total': required_total,
        'required_done': required_done,
        'optional_total': optional_total,
        'optional_done': optional_done,
        'completion_pct': round(done / total, 4),
    }


def _derive_exec_status(steps: Sequence[Mapping[str, Any]], *, current_status: str | None = None) -> str:
    if _clean(current_status) == 'cancelled':
        return 'cancelled'
    if steps and all((not bool(s.get('required'))) or _clean(s.get('status')) == 'done' for s in steps):
        return 'completed'
    if any(_clean(s.get('status')) == 'done' for s in steps):
        return 'in_progress'
    return 'open'


def _next_follow_up_due_at(steps: Sequence[Mapping[str, Any]]) -> str | None:
    due_dates: list[date] = []
    for step in steps:
        if _clean(step.get('status')) != 'pending':
            continue
        dt = _parse_date(step.get('due_at'))
        if dt is not None:
            due_dates.append(dt)
    if not due_dates:
        return None
    return min(due_dates).isoformat()


def _ensure_role_allowed_for_step(*, role: str, step_kind: str) -> None:
    allowed = ROLE_ALLOWED_STEP_KINDS.get(_clean(role), set())
    if _clean(step_kind) not in allowed:
        _raise('role_not_allowed', 'Эта роль не может выполнять данный шаг протокола.', role=role, step_kind=step_kind)


def _dedupe_open_execution(repo: VetProtocolExecutionsRepo, *, tenant_id: str, animal_id: str, protocol_key: str) -> dict[str, Any] | None:
    res = repo.list_rows(tenant_id=tenant_id, filters={'animal_id': animal_id, 'protocol_key': protocol_key}, limit=50, offset=0)
    for item in list(res.get('items') or []):
        if _clean(item.get('status')) in {'open', 'in_progress'}:
            return item
    return None


def _facts_preview(*, protocol: Mapping[str, Any], linked_alert_id: str | None, linked_health_event_id: str | None) -> list[dict[str, Any]]:
    out = [
        {'label': 'Protocol', 'text': _clean(protocol.get('title'))},
        {'label': 'Protocol version', 'text': str(protocol.get('protocol_version') or 1)},
    ]
    if _clean(linked_alert_id):
        out.append({'label': 'Alert', 'text': _clean(linked_alert_id)})
    if _clean(linked_health_event_id):
        out.append({'label': 'Health event', 'text': _clean(linked_health_event_id)})
    return out


def _write_protocol_audit(conn, *, tenant_id: str, user_id: int, username: str, role: str, action: str, execution_id: str, data_version: str | None, request_id: str | None, before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> None:
    write_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id or 0),
        username=str(username or ''),
        role=str(role or ''),
        action=action,
        object_type='vet_protocol_execution',
        object_id=str(execution_id),
        data_version=(str(data_version) if data_version not in (None, '') else None),
        before=dict(before or {}),
        after=dict(after or {}),
        status='OK',
        request_id=(str(request_id) if request_id not in (None, '') else None),
    )


def start_vet_protocol_execution_use_case(
    *,
    conn,
    tenant_id: str,
    project_root: Path | str,
    protocol_key: str,
    animal_id: str,
    user_id: int,
    username: str,
    role: str,
    start_date: str,
    farm_id: str | None = None,
    site_id: str | None = None,
    linked_alert_id: str | None = None,
    linked_health_event_id: str | None = None,
    linked_worklist_id: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    create_worklist_if_missing: bool = True,
    data_version: str | None = None,
    qc_run: str | None = None,
    model_version: str | None = None,
    scoring_run: str | None = None,
    report_version: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    aid = _clean(animal_id)
    if not aid:
        _raise('animal_id_required', 'Нужно выбрать животное.')
    start_dt = _parse_date(start_date)
    if start_dt is None:
        _raise('start_date_invalid', 'Дата старта протокола заполнена некорректно.', start_date=start_date)
    catalog, protocol = _protocol_or_raise(project_root=project_root, protocol_key=protocol_key)
    repo = VetProtocolExecutionsRepo(conn)
    existing = _dedupe_open_execution(repo, tenant_id=str(tenant_id), animal_id=aid, protocol_key=_clean(protocol_key))
    if existing:
        return {'execution_id': existing.get('execution_id'), 'after': existing, 'worklist_id': existing.get('linked_worklist_id'), 'deduped': True}

    steps = _clone_steps(protocol, start_date=start_dt)
    next_due = _next_follow_up_due_at(steps)
    worklist_id = _clean(linked_worklist_id) or None
    if create_worklist_if_missing and not worklist_id:
        first_step = steps[0] if steps else {}
        wl = create_worklist_use_case(
            conn=conn,
            tenant_id=str(tenant_id),
            worklist_type='vet',
            user_id=int(user_id or 0),
            username=str(username or ''),
            role=str(role or ''),
            title=f"{_clean(protocol.get('title'))} · {aid}",
            task_type=f"vet.protocol.{_clean(protocol.get('protocol_key'))}",
            domain='health',
            priority=2,
            due_at=next_due,
            owner_user_id=int(user_id or 0),
            assignee_team=_clean(protocol.get('assignee_team')) or 'team-health',
            confidence=0.88,
            object_type=str(object_type or 'animal'),
            object_id=str(object_id or aid),
            related_alert=_clean(linked_alert_id) or None,
            linked_source_facts=_facts_preview(protocol=protocol, linked_alert_id=linked_alert_id, linked_health_event_id=linked_health_event_id),
            why={'protocol_key': _clean(protocol.get('protocol_key')), 'protocol_version': int(protocol.get('protocol_version') or 1)},
            what_to_do=[{'action': _clean(first_step.get('label')) or 'Начать протокол', 'due_at': next_due}],
            data_version=data_version,
            qc_run=qc_run,
            model_version=model_version,
            scoring_run=scoring_run,
            report_version=report_version,
            dedupe_key=f"vet_protocol:{_clean(protocol.get('protocol_key'))}:{aid}:{start_dt.isoformat()}",
            request_id=request_id,
        )
        worklist_id = _clean(wl.get('worklist_id')) or None

    execution_id = f'vpe_{uuid.uuid4().hex[:24]}'
    payload = {
        'protocol_key': _clean(protocol.get('protocol_key')),
        'protocol_version': int(protocol.get('protocol_version') or 1),
        'protocol_title': _clean(protocol.get('title')) or _clean(protocol.get('protocol_key')),
        'catalog_version': _clean(catalog.get('catalog_version')),
        'status': 'open',
        'animal_id': aid,
        'farm_id': _clean(farm_id) or None,
        'site_id': _clean(site_id) or None,
        'linked_alert_id': _clean(linked_alert_id) or None,
        'linked_health_event_id': _clean(linked_health_event_id) or None,
        'linked_worklist_id': worklist_id,
        'object_type': _clean(object_type) or 'animal',
        'object_id': _clean(object_id) or aid,
        'owner_user_id': int(user_id or 0),
        'assignee_team': _clean(protocol.get('assignee_team')) or 'team-health',
        'owner_role': _clean(protocol.get('owner_role')) or 'Vet',
        'started_by': int(user_id or 0),
        'started_by_username': _clean(username),
        'started_role': _clean(role),
        'next_follow_up_due_at': next_due,
        'request_id': _clean(request_id) or None,
        'data_version': _clean(data_version) or None,
        'qc_run': _clean(qc_run) or None,
        'model_version': _clean(model_version) or None,
        'scoring_run': _clean(scoring_run) or None,
        'report_version': _clean(report_version) or None,
        'steps': steps,
        'linked_treatments': [],
        'linked_observations': [],
        'source_versions': {
            'catalog_version': _clean(catalog.get('catalog_version')),
            'protocol_version': int(protocol.get('protocol_version') or 1),
            'data_version': _clean(data_version) or None,
            'qc_run': _clean(qc_run) or None,
            'model_version': _clean(model_version) or None,
            'scoring_run': _clean(scoring_run) or None,
            'report_version': _clean(report_version) or None,
        },
        'metrics': _metrics_from_steps(steps),
        'metadata': {'description': _clean(protocol.get('description')), 'applicable_event_types': list(protocol.get('applicable_event_types') or [])},
    }
    repo.insert(tenant_id=str(tenant_id), execution_id=execution_id, created_at=utc_isoformat(ensure_utc(datetime.now(UTC))), payload=payload)
    after = repo.get(tenant_id=str(tenant_id), execution_id=execution_id) or {}
    _write_protocol_audit(conn, tenant_id=str(tenant_id), user_id=int(user_id or 0), username=str(username or ''), role=str(role or ''), action='vet_protocol.execution.start', execution_id=execution_id, data_version=after.get('data_version') or data_version, request_id=request_id, before=None, after=after)
    return {'execution_id': execution_id, 'after': after, 'worklist_id': worklist_id, 'deduped': False}


def get_vet_protocol_execution(conn, *, tenant_id: str, execution_id: str) -> dict[str, Any] | None:
    return VetProtocolExecutionsRepo(conn).get(tenant_id=str(tenant_id), execution_id=str(execution_id))


def list_vet_protocol_executions(
    conn,
    *,
    tenant_id: str,
    protocol_key: str | None = None,
    status: str | None = None,
    animal_id: str | None = None,
    farm_id: str | None = None,
    site_id: str | None = None,
    linked_alert_id: str | None = None,
    linked_health_event_id: str | None = None,
    linked_worklist_id: str | None = None,
    assignee_team: str | None = None,
    owner_role: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    data_version: str | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    return VetProtocolExecutionsRepo(conn).list_rows(
        tenant_id=str(tenant_id),
        filters={
            'protocol_key': _clean(protocol_key) or None,
            'status': _clean(status) or None,
            'animal_id': _clean(animal_id) or None,
            'farm_id': _clean(farm_id) or None,
            'site_id': _clean(site_id) or None,
            'linked_alert_id': _clean(linked_alert_id) or None,
            'linked_health_event_id': _clean(linked_health_event_id) or None,
            'linked_worklist_id': _clean(linked_worklist_id) or None,
            'assignee_team': _clean(assignee_team) or None,
            'owner_role': _clean(owner_role) or None,
            'object_type': _clean(object_type) or None,
            'object_id': _clean(object_id) or None,
            'data_version': _clean(data_version) or None,
            'q': _clean(q) or None,
        },
        limit=int(limit),
        offset=int(offset),
    )


def record_vet_protocol_step_use_case(
    *,
    conn,
    tenant_id: str,
    execution_id: str,
    step_key: str,
    user_id: int,
    username: str,
    role: str,
    step_status: str = 'done',
    completed_at: str | None = None,
    comment: str | None = None,
    linked_treatment_id: str | None = None,
    create_observation_event: bool = False,
    data_version: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    repo = VetProtocolExecutionsRepo(conn)
    before = repo.get(tenant_id=str(tenant_id), execution_id=str(execution_id))
    if not before:
        _raise('execution_not_found', 'Протокол не найден.', execution_id=execution_id)
    if _clean(before.get('status')) in {'completed', 'cancelled'}:
        _raise('execution_closed', 'Протокол уже закрыт и не может быть изменён.', status=before.get('status'))
    steps = [dict(x) for x in list(before.get('steps') or [])]
    target = None
    for step in steps:
        if _clean(step.get('step_key')) == _clean(step_key):
            target = step
            break
    if not target:
        _raise('step_not_found', 'Шаг протокола не найден.', step_key=step_key)
    _ensure_role_allowed_for_step(role=str(role or ''), step_kind=_clean(target.get('kind')))
    normalized_status = _clean(step_status) or 'done'
    if normalized_status not in {'done', 'skipped', 'cancelled'}:
        _raise('step_status_invalid', 'Неподдерживаемый статус шага.', step_status=step_status)
    done_at = utc_isoformat(ensure_utc(datetime.now(UTC))) if not _clean(completed_at) else utc_isoformat(ensure_utc(datetime.fromisoformat(str(completed_at).replace('Z', '+00:00'))))
    target['status'] = normalized_status
    target['completed_at'] = done_at
    target['completed_by'] = int(user_id or 0)
    target['completed_by_username'] = _clean(username)
    target['comment'] = _clean(comment) or None
    if _clean(linked_treatment_id):
        target['linked_treatment_id'] = _clean(linked_treatment_id)
    linked_treatments = list(before.get('linked_treatments') or [])
    if _clean(linked_treatment_id) and _clean(linked_treatment_id) not in {str(x) for x in linked_treatments}:
        linked_treatments.append(_clean(linked_treatment_id))
    linked_observations = list(before.get('linked_observations') or [])
    observation_event_id = None
    if create_observation_event and _clean(comment):
        event_res = create_animal_event_use_case(
            conn=conn,
            tenant_id=str(tenant_id),
            animal_id=_clean(before.get('animal_id')),
            event_type='manual_note',
            event_ts=done_at,
            user_id=int(user_id or 0),
            username=str(username or ''),
            role=str(role or ''),
            comment=_clean(comment),
            farm_id=_clean(before.get('farm_id')) or None,
            site_id=_clean(before.get('site_id')) or None,
            linked_task_id=_clean(before.get('linked_worklist_id')) or None,
            linked_object_type='vet_protocol_execution',
            linked_object_id=str(execution_id),
            data_version=_clean(data_version) or _clean(before.get('data_version')) or None,
            request_id=request_id,
            extra_payload={'protocol_key': _clean(before.get('protocol_key')), 'step_key': _clean(step_key), 'workflow_action': 'protocol_step_observation'},
        )
        observation_event_id = _clean(event_res.get('event_id')) or None
        target['observation_event_id'] = observation_event_id
        if observation_event_id and observation_event_id not in {str(x) for x in linked_observations}:
            linked_observations.append(observation_event_id)

    status = _derive_exec_status(steps, current_status=_clean(before.get('status')))
    metrics = _metrics_from_steps(steps)
    updated = dict(before)
    updated.update({
        'status': status,
        'steps': steps,
        'linked_treatments': linked_treatments,
        'linked_observations': linked_observations,
        'next_follow_up_due_at': _next_follow_up_due_at(steps),
        'metrics': metrics,
        'request_id': _clean(request_id) or before.get('request_id'),
        'data_version': _clean(data_version) or before.get('data_version'),
    })
    repo.update(tenant_id=str(tenant_id), execution_id=str(execution_id), updated_at=done_at, payload=updated)
    after = repo.get(tenant_id=str(tenant_id), execution_id=str(execution_id)) or {}
    _write_protocol_audit(conn, tenant_id=str(tenant_id), user_id=int(user_id or 0), username=str(username or ''), role=str(role or ''), action='vet_protocol.execution.step', execution_id=str(execution_id), data_version=after.get('data_version') or data_version, request_id=request_id, before=before, after=after)
    return {'execution_id': execution_id, 'after': after, 'observation_event_id': observation_event_id}


def complete_vet_protocol_execution_use_case(
    *,
    conn,
    tenant_id: str,
    execution_id: str,
    user_id: int,
    username: str,
    role: str,
    comment: str | None = None,
    close_linked_worklist: bool = True,
    request_id: str | None = None,
) -> dict[str, Any]:
    repo = VetProtocolExecutionsRepo(conn)
    before = repo.get(tenant_id=str(tenant_id), execution_id=str(execution_id))
    if not before:
        _raise('execution_not_found', 'Протокол не найден.', execution_id=execution_id)
    steps = list(before.get('steps') or [])
    missing = [str(s.get('step_key')) for s in steps if bool(s.get('required')) and _clean(s.get('status')) != 'done']
    if missing:
        _raise('required_steps_pending', 'Нельзя завершить протокол: есть обязательные невыполненные шаги.', missing_steps=missing)
    now_iso = utc_isoformat(ensure_utc(datetime.now(UTC)))
    updated = dict(before)
    updated.update({
        'status': 'completed',
        'completed_at': now_iso,
        'completed_by': int(user_id or 0),
        'completed_by_username': _clean(username),
        'next_follow_up_due_at': None,
        'metrics': _metrics_from_steps(steps),
    })
    metadata = dict(updated.get('metadata') or {})
    if _clean(comment):
        metadata['completion_comment'] = _clean(comment)
    updated['metadata'] = metadata
    repo.update(tenant_id=str(tenant_id), execution_id=str(execution_id), updated_at=now_iso, payload=updated)
    auto = None
    linked_worklist_id = _clean(before.get('linked_worklist_id')) or None
    if close_linked_worklist and linked_worklist_id:
        wl = get_worklist(conn, tenant_id=str(tenant_id), worklist_id=linked_worklist_id)
        if wl and _clean(wl.get('status')) not in {'done', 'cancelled'}:
            auto = close_worklist_use_case(
                conn=conn,
                tenant_id=str(tenant_id),
                worklist_id=linked_worklist_id,
                user_id=int(user_id or 0),
                username=str(username or ''),
                role=str(role or ''),
                status='done',
                reason='COMPLETED',
                comment=_clean(comment) or 'Protocol completed',
                resolve_related_alert=False,
                request_id=request_id,
            )
    after = repo.get(tenant_id=str(tenant_id), execution_id=str(execution_id)) or {}
    _write_protocol_audit(conn, tenant_id=str(tenant_id), user_id=int(user_id or 0), username=str(username or ''), role=str(role or ''), action='vet_protocol.execution.complete', execution_id=str(execution_id), data_version=after.get('data_version'), request_id=request_id, before=before, after=after)
    return {'execution_id': execution_id, 'after': after, 'auto': auto}


def cancel_vet_protocol_execution_use_case(
    *,
    conn,
    tenant_id: str,
    execution_id: str,
    user_id: int,
    username: str,
    role: str,
    comment: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    repo = VetProtocolExecutionsRepo(conn)
    before = repo.get(tenant_id=str(tenant_id), execution_id=str(execution_id))
    if not before:
        _raise('execution_not_found', 'Протокол не найден.', execution_id=execution_id)
    now_iso = utc_isoformat(ensure_utc(datetime.now(UTC)))
    updated = dict(before)
    updated.update({'status': 'cancelled', 'completed_at': now_iso, 'completed_by': int(user_id or 0), 'completed_by_username': _clean(username), 'next_follow_up_due_at': None})
    metadata = dict(updated.get('metadata') or {})
    if _clean(comment):
        metadata['cancel_comment'] = _clean(comment)
    updated['metadata'] = metadata
    repo.update(tenant_id=str(tenant_id), execution_id=str(execution_id), updated_at=now_iso, payload=updated)
    auto = None
    linked_worklist_id = _clean(before.get('linked_worklist_id')) or None
    if linked_worklist_id:
        wl = get_worklist(conn, tenant_id=str(tenant_id), worklist_id=linked_worklist_id)
        if wl and _clean(wl.get('status')) not in {'done', 'cancelled'}:
            auto = close_worklist_use_case(
                conn=conn,
                tenant_id=str(tenant_id),
                worklist_id=linked_worklist_id,
                user_id=int(user_id or 0),
                username=str(username or ''),
                role=str(role or ''),
                status='cancelled',
                reason='CANCELLED_OTHER',
                comment=_clean(comment) or 'Protocol cancelled',
                resolve_related_alert=False,
                request_id=request_id,
            )
    after = repo.get(tenant_id=str(tenant_id), execution_id=str(execution_id)) or {}
    _write_protocol_audit(conn, tenant_id=str(tenant_id), user_id=int(user_id or 0), username=str(username or ''), role=str(role or ''), action='vet_protocol.execution.cancel', execution_id=str(execution_id), data_version=after.get('data_version'), request_id=request_id, before=before, after=after)
    return {'execution_id': execution_id, 'after': after, 'auto': auto}


def build_vet_protocol_engine_snapshot(
    *,
    project_root: Path | str,
    input_dir: Path | str | None,
    conn,
    tenant_id: str,
    asof_date: date,
    animal_id: str | None = None,
    pen_id: str | None = None,
    status: str | None = None,
    protocol_key: str | None = None,
    linked_alert_id: str | None = None,
    linked_worklist_id: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    catalog = load_vet_protocol_catalog(project_root=project_root)
    base = Path(input_dir) if input_dir else None
    animals = _read_csv((base / 'dm_animals.csv') if base else None)
    events = _read_csv((base / 'dm_health_events.csv') if base else None)
    assn = compute_pen_assignments(input_dir=base, asof_date=asof_date) if base and base.exists() else pd.DataFrame()
    animal_filter = _clean(animal_id)
    pen_filter = _clean(pen_id)
    if animal_filter and not events.empty:
        events = events[events.get('animal_id', pd.Series(dtype=object)).astype(str) == animal_filter].copy()
    if pen_filter and not events.empty and not assn.empty:
        selected = set(assn[assn.get('pen_id', pd.Series(dtype=object)).astype(str) == pen_filter].get('animal_id', pd.Series(dtype=object)).astype(str).tolist())
        events = events[events.get('animal_id', pd.Series(dtype=object)).astype(str).isin(selected)].copy()
    if not events.empty and 'event_date' in events.columns:
        events['event_date'] = pd.to_datetime(events['event_date'], errors='coerce')
        events = events.sort_values('event_date', ascending=False).head(max(20, int(limit)))
    candidate_health_events = [] if events.empty else [
        {
            'event_id': _clean(r.get('event_id')) or _clean(r.get('health_event_id')) or f"{_clean(r.get('animal_id'))}:{_clean(r.get('event_date'))}",
            'animal_id': _clean(r.get('animal_id')),
            'event_type': _clean(r.get('event_type') or r.get('condition_code')) or 'health_event',
            'event_date': (_parse_date(r.get('event_date')) or asof_date).isoformat() if r.get('event_date') is not None else asof_date.isoformat(),
            'severity': _clean(r.get('severity')) or '—',
            'notes': _clean(r.get('notes')) or '—',
        }
        for r in events.to_dict(orient='records')
    ]
    if animal_filter and not animals.empty:
        animals = animals[animals.get('animal_id', pd.Series(dtype=object)).astype(str) == animal_filter].copy()
    animal_options = sorted(set(animals.get('animal_id', pd.Series(dtype=object)).astype(str).tolist())) if not animals.empty else []

    execs = list_vet_protocol_executions(
        conn,
        tenant_id=str(tenant_id),
        protocol_key=_clean(protocol_key) or None,
        status=_clean(status) or None,
        animal_id=animal_filter or None,
        linked_alert_id=_clean(linked_alert_id) or None,
        linked_worklist_id=_clean(linked_worklist_id) or None,
        limit=int(limit),
        offset=0,
    )
    items = list(execs.get('items') or [])
    if pen_filter and not assn.empty:
        selected = set(assn[assn.get('pen_id', pd.Series(dtype=object)).astype(str) == pen_filter].get('animal_id', pd.Series(dtype=object)).astype(str).tolist())
        items = [x for x in items if _clean(x.get('animal_id')) in selected]
    worklist_ids = [_clean(x.get('linked_worklist_id')) for x in items if _clean(x.get('linked_worklist_id'))]
    open_alert_ids = [_clean(x.get('linked_alert_id')) for x in items if _clean(x.get('linked_alert_id'))]
    preview_worklists = {}
    for wid in worklist_ids[:20]:
        preview_worklists[wid] = get_worklist(conn, tenant_id=str(tenant_id), worklist_id=wid)
    preview_alerts = {}
    alert_repo = AlertsRepo(conn)
    for aid in open_alert_ids[:20]:
        preview_alerts[aid] = alert_repo.get(tenant_id=str(tenant_id), alert_id=aid)
    return {
        'catalog': {'version': catalog.get('version'), 'catalog_version': catalog.get('catalog_version'), 'protocols': catalog.get('protocols') or []},
        'animal_options': animal_options,
        'candidate_health_events': candidate_health_events,
        'executions': items,
        'preview_worklists': preview_worklists,
        'preview_alerts': preview_alerts,
        'summary': {
            'total_executions': len(items),
            'open_n': sum(1 for x in items if _clean(x.get('status')) == 'open'),
            'in_progress_n': sum(1 for x in items if _clean(x.get('status')) == 'in_progress'),
            'completed_n': sum(1 for x in items if _clean(x.get('status')) == 'completed'),
            'cancelled_n': sum(1 for x in items if _clean(x.get('status')) == 'cancelled'),
            'candidate_health_events_n': len(candidate_health_events),
        },
    }


__all__ = [
    'CATALOG_PATH',
    'DEFAULT_PROTOCOL_STATUS_LABELS',
    'DEFAULT_STEP_STATUS_LABELS',
    'STEP_KIND_LABELS',
    'VetProtocolEngineError',
    'build_vet_protocol_engine_snapshot',
    'cancel_vet_protocol_execution_use_case',
    'complete_vet_protocol_execution_use_case',
    'get_vet_protocol_execution',
    'list_vet_protocol_executions',
    'load_vet_protocol_catalog',
    'protocol_options',
    'record_vet_protocol_step_use_case',
    'start_vet_protocol_execution_use_case',
]
