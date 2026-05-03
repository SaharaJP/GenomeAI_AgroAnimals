
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from core.audit import write_audit
from core.common.time import ensure_utc, utc_isoformat
from core.health.treatment_journal import get_treatment_course, list_treatment_courses
from core.infra import DrugUseComplianceRepo
from genomeai.drilldown import compute_pen_assignments

ACTION_LABELS = {
    'prescribed': 'Назначено',
    'approved': 'Подтверждено',
    'executed': 'Выполнено',
    'rejected': 'Отклонено',
}
APPROVAL_STATE_LABELS = {
    'not_required': 'Не требуется',
    'pending': 'Ожидает',
    'approved': 'Подтверждено',
    'rejected': 'Отклонено',
}
PRESCRIBE_ROLES = {'Admin', 'Vet'}
APPROVE_ROLES = {'Admin', 'Director', 'Vet'}
EXECUTE_ROLES = {'Admin', 'Vet', 'Zootech', 'Operator'}


@dataclass(slots=True)
class DrugUseComplianceError(ValueError):
    code: str
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return self.message


def _raise(code: str, message: str, **details: Any) -> None:
    raise DrugUseComplianceError(code=code, message=message, details={k: v for k, v in details.items() if v is not None})


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _parse_date(value: Any) -> date | None:
    raw = _clean(value)
    if not raw:
        return None
    try:
        ts = pd.to_datetime(raw, errors='coerce', utc=False)
        if pd.isna(ts):
            return None
        if isinstance(ts, pd.Timestamp):
            return ts.date()
        return ts
    except Exception:
        return None


def _read_csv(path: Path | None) -> pd.DataFrame:
    try:
        if path and Path(path).exists():
            return pd.read_csv(path)
    except Exception:
        pass
    return pd.DataFrame()


def _ensure_role(role: str, allowed: set[str], *, action: str) -> None:
    if _clean(role) not in allowed:
        _raise('role_not_allowed', f'Роль не может выполнить действие: {action}.', role=role, action=action)


def _write_audit(conn, *, tenant_id: str, user_id: int, username: str, role: str, action: str, entry_id: str, data_version: str | None, request_id: str | None, before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> None:
    write_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id or 0),
        username=str(username or ''),
        role=str(role or ''),
        action=action,
        object_type='drug_use_entry',
        object_id=str(entry_id),
        data_version=(str(data_version) if data_version not in (None, '') else None),
        request_id=(str(request_id) if request_id not in (None, '') else None),
        before=dict(before or {}) or None,
        after=dict(after or {}) or None,
    )


def _pen_assignment_map(input_dir: Path, *, asof_date: date) -> dict[str, dict[str, Any]]:
    try:
        assn = compute_pen_assignments(input_dir=input_dir, asof_date=asof_date)
    except Exception:
        assn = pd.DataFrame()
    if assn.empty:
        animals = _read_csv(input_dir / 'dm_animals.csv')
        if animals.empty:
            return {}
        out = {}
        for row in animals.to_dict(orient='records'):
            aid = _clean(row.get('animal_id'))
            if aid:
                out[aid] = {
                    'animal_id': aid,
                    'farm_id': _clean(row.get('farm_id')),
                    'site_id': _clean(row.get('site_id')),
                    'pen_id': _clean(row.get('current_pen_id') or row.get('pen_id')),
                    'pen_name': _clean(row.get('current_pen_name') or row.get('pen_name')),
                }
        return out
    return {str(r.get('animal_id') or ''): dict(r) for r in assn.to_dict(orient='records') if str(r.get('animal_id') or '').strip()}


def _copy_context_from_course(course: Mapping[str, Any], *, linked_object_type: str | None = None, linked_object_id: str | None = None) -> dict[str, Any]:
    animal_id = _clean(course.get('animal_id'))
    return {
        'course_id': _clean(course.get('course_id')),
        'animal_id': animal_id,
        'farm_id': _clean(course.get('farm_id')),
        'site_id': _clean(course.get('site_id')),
        'pen_id': _clean(course.get('pen_id')),
        'linked_object_type': _clean(linked_object_type) or 'animal',
        'linked_object_id': _clean(linked_object_id) or animal_id,
        'linked_alert_id': _clean(course.get('linked_alert_id')),
        'linked_health_event_id': _clean(course.get('linked_health_event_id')),
        'linked_protocol_execution_id': _clean(course.get('linked_protocol_execution_id')),
        'linked_worklist_id': _clean(course.get('linked_worklist_id')),
        'protocol_reference': _clean(course.get('linked_protocol_execution_id')),
        'drug_name': _clean(course.get('drug_name')),
        'drug_code': _clean(course.get('drug_code')),
        'route': _clean(course.get('route')),
        'dose_value': course.get('dose_value'),
        'dose_unit': _clean(course.get('dose_unit')),
        'source_versions': dict(course.get('source_versions') or {}),
        'metadata': {'treatment_type': _clean(course.get('treatment_type')), 'diagnosis_label': _clean(course.get('diagnosis_label'))},
    }


def _course_or_raise(conn, *, tenant_id: str, course_id: str) -> dict[str, Any]:
    course = get_treatment_course(conn, tenant_id=tenant_id, course_id=course_id)
    if not course:
        _raise('course_not_found', 'Курс лечения не найден или доступен только как legacy read-only.', course_id=course_id)
    return dict(course)


def _rows_for_course(repo: DrugUseComplianceRepo, *, tenant_id: str, course_id: str) -> list[dict[str, Any]]:
    res = repo.list_rows(tenant_id=tenant_id, filters={'course_id': course_id}, limit=500, offset=0)
    items = list(res.get('items') or [])
    items.sort(key=lambda x: (_clean(x.get('event_at')), int(x.get('id') or 0), _clean(x.get('entry_id'))))
    return items


def _latest_by_action(rows: Sequence[Mapping[str, Any]], action_type: str) -> dict[str, Any] | None:
    cand = [dict(r) for r in rows if _clean(r.get('action_type')) == action_type]
    return cand[-1] if cand else None


def _build_course_summary(*, course: Mapping[str, Any] | None, rows: Sequence[Mapping[str, Any]], assn_map: Mapping[str, Mapping[str, Any]], asof_date: date) -> dict[str, Any]:
    rows_l = [dict(r) for r in rows]
    latest = rows_l[-1] if rows_l else {}
    prescribed = _latest_by_action(rows_l, 'prescribed') or {}
    approved = _latest_by_action(rows_l, 'approved') or {}
    executed = _latest_by_action(rows_l, 'executed') or {}
    rejected = _latest_by_action(rows_l, 'rejected') or {}
    base = dict(course or {})
    animal_id = _clean(latest.get('animal_id') or base.get('animal_id'))
    assn = dict(assn_map.get(animal_id) or {})
    withdrawal_until = _clean(base.get('withdrawal_end_date_effective'))
    wd_date = _parse_date(withdrawal_until)
    approval_required = bool(latest.get('approval_required')) if latest else False
    approval_state = _clean(latest.get('approval_state')) or ('pending' if approval_required else 'not_required')
    if executed:
        current_stage = 'executed'
    elif approved:
        current_stage = 'approved'
    elif rejected:
        current_stage = 'rejected'
    elif prescribed:
        current_stage = 'prescribed'
    else:
        current_stage = '—'
    return {
        'course_id': _clean(latest.get('course_id') or base.get('course_id')),
        'animal_id': animal_id,
        'farm_id': _clean(latest.get('farm_id') or base.get('farm_id') or assn.get('farm_id')),
        'site_id': _clean(latest.get('site_id') or base.get('site_id') or assn.get('site_id')),
        'pen_id': _clean(latest.get('pen_id') or base.get('pen_id') or assn.get('pen_id')),
        'pen_name': _clean(assn.get('pen_name')),
        'linked_object_type': _clean(latest.get('linked_object_type')) or 'animal',
        'linked_object_id': _clean(latest.get('linked_object_id') or animal_id),
        'linked_alert_id': _clean(latest.get('linked_alert_id') or base.get('linked_alert_id')),
        'linked_health_event_id': _clean(latest.get('linked_health_event_id') or base.get('linked_health_event_id')),
        'linked_protocol_execution_id': _clean(latest.get('linked_protocol_execution_id') or base.get('linked_protocol_execution_id')),
        'linked_worklist_id': _clean(latest.get('linked_worklist_id') or base.get('linked_worklist_id')),
        'protocol_reference': _clean(latest.get('protocol_reference') or base.get('linked_protocol_execution_id')),
        'drug_name': _clean(latest.get('drug_name') or base.get('drug_name')),
        'drug_code': _clean(latest.get('drug_code') or base.get('drug_code')),
        'route': _clean(latest.get('route') or base.get('route')),
        'dose_value': latest.get('dose_value') if latest.get('dose_value') not in (None, '') else base.get('dose_value'),
        'dose_unit': _clean(latest.get('dose_unit') or base.get('dose_unit')),
        'approval_required': approval_required,
        'approval_state': approval_state,
        'approval_state_label': APPROVAL_STATE_LABELS.get(approval_state, approval_state or '—'),
        'current_stage': current_stage,
        'current_stage_label': ACTION_LABELS.get(current_stage, current_stage),
        'prescribed_at': _clean(prescribed.get('prescribed_at') or prescribed.get('event_at')),
        'prescribed_by': _clean(prescribed.get('prescribed_by_username')),
        'approved_at': _clean(approved.get('approved_at') or approved.get('event_at')),
        'approved_by': _clean(approved.get('approved_by_username')),
        'executed_at': _clean(executed.get('executed_at') or executed.get('event_at')),
        'executed_by': _clean(executed.get('executed_by_username')),
        'reason_code': _clean(latest.get('action_reason_code')),
        'reason_text': _clean(latest.get('action_comment') or latest.get('approval_comment')),
        'withdrawal_until': withdrawal_until,
        'withdrawal_active_asof': bool(wd_date is not None and wd_date >= asof_date and _clean(base.get('course_status')) != 'cancelled'),
        'course_status': _clean(base.get('course_status')),
        'data_version': _clean(latest.get('data_version') or base.get('data_version')),
        'history_n': len(rows_l),
        'latest_entry_id': _clean(latest.get('entry_id')),
    }


def _group_counts(rows: Sequence[Mapping[str, Any]], *, key_fn) -> list[dict[str, Any]]:
    agg: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = key_fn(row) or '—'
        item = agg.setdefault(key, {'key': key, 'events': 0, 'prescribed': 0, 'approved': 0, 'executed': 0, 'rejected': 0, 'pending_approvals': 0})
        item['events'] += 1
        act = _clean(row.get('action_type'))
        if act in item:
            item[act] += 1
        if _clean(row.get('approval_state')) == 'pending':
            item['pending_approvals'] += 1
    return list(agg.values())


def record_drug_prescription_use_case(
    conn,
    *,
    tenant_id: str,
    course_id: str,
    user_id: int,
    username: str,
    role: str,
    administration_date: str | None = None,
    dose_value: float | None = None,
    dose_unit: str | None = None,
    protocol_reference: str | None = None,
    linked_object_type: str | None = None,
    linked_object_id: str | None = None,
    approval_required: bool = True,
    reason_code: str | None = None,
    comment: str | None = None,
    data_version: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    _ensure_role(role, PRESCRIBE_ROLES, action='prescribe')
    course = _course_or_raise(conn, tenant_id=tenant_id, course_id=_clean(course_id))
    repo = DrugUseComplianceRepo(conn)
    now = utc_isoformat()
    ctx = _copy_context_from_course(course, linked_object_type=linked_object_type, linked_object_id=linked_object_id)
    entry_id = f"DGU-{uuid.uuid4().hex[:10]}"
    payload = {
        **ctx,
        'action_type': 'prescribed',
        'action_reason_code': _clean(reason_code),
        'action_comment': _clean(comment),
        'administration_date': _clean(administration_date) or _clean(course.get('start_date')),
        'approval_required': bool(approval_required),
        'approval_state': 'pending' if approval_required else 'not_required',
        'protocol_reference': _clean(protocol_reference) or ctx.get('protocol_reference'),
        'dose_value': dose_value if dose_value is not None else ctx.get('dose_value'),
        'dose_unit': _clean(dose_unit) or ctx.get('dose_unit'),
        'prescribed_by': int(user_id or 0),
        'prescribed_by_username': _clean(username),
        'prescribed_by_role': _clean(role),
        'prescribed_at': now,
        'request_id': _clean(request_id),
        'data_version': _clean(data_version) or _clean(course.get('data_version')),
    }
    repo.insert(tenant_id=tenant_id, entry_id=entry_id, created_at=now, payload=payload)
    after = repo.get(tenant_id=tenant_id, entry_id=entry_id) or {'entry_id': entry_id}
    _write_audit(conn, tenant_id=tenant_id, user_id=user_id, username=username, role=role, action='drug_use.prescribed', entry_id=entry_id, data_version=data_version, request_id=request_id, before=None, after=after)
    return after


def approve_drug_use_use_case(
    conn,
    *,
    tenant_id: str,
    course_id: str,
    user_id: int,
    username: str,
    role: str,
    comment: str | None = None,
    data_version: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    _ensure_role(role, APPROVE_ROLES, action='approve')
    course = _course_or_raise(conn, tenant_id=tenant_id, course_id=_clean(course_id))
    repo = DrugUseComplianceRepo(conn)
    rows = _rows_for_course(repo, tenant_id=tenant_id, course_id=_clean(course_id))
    latest = rows[-1] if rows else None
    if not latest or _clean(latest.get('action_type')) not in {'prescribed', 'approved'}:
        _raise('prescription_required', 'Сначала нужно зафиксировать назначение препарата.', course_id=course_id)
    if not bool(latest.get('approval_required')):
        _raise('approval_not_required', 'Для этого назначения подтверждение не требуется.', course_id=course_id)
    now = utc_isoformat()
    entry_id = f"DGU-{uuid.uuid4().hex[:10]}"
    payload = dict(latest)
    payload.update({
        'action_type': 'approved',
        'approval_state': 'approved',
        'approval_comment': _clean(comment),
        'approved_by': int(user_id or 0),
        'approved_by_username': _clean(username),
        'approved_by_role': _clean(role),
        'approved_at': now,
        'request_id': _clean(request_id),
        'data_version': _clean(data_version) or _clean(latest.get('data_version')) or _clean(course.get('data_version')),
    })
    repo.insert(tenant_id=tenant_id, entry_id=entry_id, created_at=now, payload=payload)
    after = repo.get(tenant_id=tenant_id, entry_id=entry_id) or {'entry_id': entry_id}
    _write_audit(conn, tenant_id=tenant_id, user_id=user_id, username=username, role=role, action='drug_use.approved', entry_id=entry_id, data_version=data_version, request_id=request_id, before=latest, after=after)
    return after


def execute_drug_use_use_case(
    conn,
    *,
    tenant_id: str,
    course_id: str,
    user_id: int,
    username: str,
    role: str,
    executed_at: str | None = None,
    administration_date: str | None = None,
    dose_value: float | None = None,
    dose_unit: str | None = None,
    comment: str | None = None,
    data_version: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    _ensure_role(role, EXECUTE_ROLES, action='execute')
    course = _course_or_raise(conn, tenant_id=tenant_id, course_id=_clean(course_id))
    repo = DrugUseComplianceRepo(conn)
    rows = _rows_for_course(repo, tenant_id=tenant_id, course_id=_clean(course_id))
    latest = rows[-1] if rows else None
    if not latest or _clean(latest.get('action_type')) not in {'prescribed', 'approved', 'executed'}:
        _raise('prescription_required', 'Сначала нужно зафиксировать назначение препарата.', course_id=course_id)
    if bool(latest.get('approval_required')) and _clean(latest.get('approval_state')) != 'approved':
        _raise('approval_pending', 'Нельзя отметить применение препарата без подтверждения.', course_id=course_id)
    when = ensure_utc(datetime.fromisoformat((_clean(executed_at) or utc_isoformat()).replace('Z', '+00:00')))
    entry_id = f"DGU-{uuid.uuid4().hex[:10]}"
    payload = dict(latest)
    payload.update({
        'action_type': 'executed',
        'action_comment': _clean(comment),
        'administration_date': _clean(administration_date) or when.date().isoformat(),
        'dose_value': dose_value if dose_value is not None else latest.get('dose_value') or course.get('dose_value'),
        'dose_unit': _clean(dose_unit) or _clean(latest.get('dose_unit')) or _clean(course.get('dose_unit')),
        'executed_by': int(user_id or 0),
        'executed_by_username': _clean(username),
        'executed_by_role': _clean(role),
        'executed_at': when.replace(microsecond=0).isoformat(),
        'request_id': _clean(request_id),
        'data_version': _clean(data_version) or _clean(latest.get('data_version')) or _clean(course.get('data_version')),
    })
    repo.insert(tenant_id=tenant_id, entry_id=entry_id, created_at=when.replace(microsecond=0).isoformat(), payload=payload)
    after = repo.get(tenant_id=tenant_id, entry_id=entry_id) or {'entry_id': entry_id}
    _write_audit(conn, tenant_id=tenant_id, user_id=user_id, username=username, role=role, action='drug_use.executed', entry_id=entry_id, data_version=data_version, request_id=request_id, before=latest, after=after)
    return after


def list_drug_use_entries(conn, *, tenant_id: str, filters: Mapping[str, Any], limit: int = 200, offset: int = 0) -> dict[str, Any]:
    return DrugUseComplianceRepo(conn).list_rows(tenant_id=tenant_id, filters=dict(filters), limit=int(limit), offset=int(offset))


def get_drug_use_entry(conn, *, tenant_id: str, entry_id: str) -> dict[str, Any] | None:
    return DrugUseComplianceRepo(conn).get(tenant_id=tenant_id, entry_id=entry_id)


def build_drug_use_compliance_snapshot(
    *,
    input_dir: Path,
    conn,
    tenant_id: str,
    asof_date: date,
    animal_id: str | None = None,
    pen_id: str | None = None,
    site_id: str | None = None,
    farm_id: str | None = None,
    course_id: str | None = None,
    limit: int = 300,
) -> dict[str, Any]:
    input_dir = Path(input_dir)
    assn_map = _pen_assignment_map(input_dir, asof_date=asof_date)
    repo = DrugUseComplianceRepo(conn)
    raw = list(repo.list_rows(tenant_id=tenant_id, filters={
        'animal_id': animal_id,
        'pen_id': pen_id,
        'site_id': site_id,
        'farm_id': farm_id,
        'course_id': course_id,
    }, limit=limit, offset=0).get('items') or [])
    raw.sort(key=lambda x: (_clean(x.get('event_at')), int(x.get('id') or 0), _clean(x.get('entry_id'))))
    runtime_courses = list_treatment_courses(conn, tenant_id=tenant_id, filters={'animal_id': animal_id, 'pen_id': pen_id, 'site_id': site_id, 'farm_id': farm_id}, limit=500, offset=0).get('items') or []
    courses_by_id = {str(c.get('course_id') or ''): dict(c) for c in runtime_courses if str(c.get('course_id') or '').strip()}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in raw:
        grouped.setdefault(_clean(row.get('course_id')), []).append(dict(row))
    course_summaries: list[dict[str, Any]] = []
    for cid, rows in grouped.items():
        course_summaries.append(_build_course_summary(course=courses_by_id.get(cid), rows=rows, assn_map=assn_map, asof_date=asof_date))
    course_summaries.sort(key=lambda r: (_clean(r.get('executed_at') or r.get('approved_at') or r.get('prescribed_at')) or '0000', _clean(r.get('course_id'))), reverse=True)
    history_rows: list[dict[str, Any]] = []
    for row in raw:
        item = dict(row)
        aid = _clean(item.get('animal_id'))
        assn = dict(assn_map.get(aid) or {})
        item['pen_name'] = _clean(item.get('pen_name') or assn.get('pen_name'))
        item['approval_state_label'] = APPROVAL_STATE_LABELS.get(_clean(item.get('approval_state')), _clean(item.get('approval_state')) or '—')
        item['action_label'] = ACTION_LABELS.get(_clean(item.get('action_type')), _clean(item.get('action_type')) or '—')
        history_rows.append(item)
    summary = {
        'entries_n': len(history_rows),
        'courses_n': len(course_summaries),
        'pending_approvals_n': sum(1 for c in course_summaries if _clean(c.get('approval_state')) == 'pending'),
        'executed_n': sum(1 for c in course_summaries if _clean(c.get('current_stage')) == 'executed'),
        'active_withdrawals_n': sum(1 for c in course_summaries if bool(c.get('withdrawal_active_asof'))),
    }
    return {
        'asof_date': asof_date.isoformat(),
        'summary': summary,
        'courses': course_summaries,
        'history': list(reversed(history_rows[-int(limit):])),
        'history_by_animal': _group_counts(history_rows, key_fn=lambda r: _clean(r.get('animal_id'))),
        'history_by_group': _group_counts(history_rows, key_fn=lambda r: _clean(r.get('pen_name') or r.get('pen_id'))),
        'history_by_farm': _group_counts(history_rows, key_fn=lambda r: _clean(r.get('farm_id'))),
    }


__all__ = [
    'ACTION_LABELS',
    'APPROVAL_STATE_LABELS',
    'DrugUseComplianceError',
    'approve_drug_use_use_case',
    'build_drug_use_compliance_snapshot',
    'execute_drug_use_use_case',
    'get_drug_use_entry',
    'list_drug_use_entries',
    'record_drug_prescription_use_case',
]
