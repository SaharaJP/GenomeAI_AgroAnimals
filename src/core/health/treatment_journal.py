from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd
import yaml

from core.audit import write_audit
from core.common.time import ensure_utc, utc_isoformat
from core.infra import AlertsRepo, TreatmentJournalRepo
from genomeai.dashboard_vet import compute_withdrawal_windows, load_withdrawal_rules
from genomeai.drilldown import compute_pen_assignments

WITHDRAWAL_RULES_PATH = Path('configs/health/withdrawal_rules.yaml')
COURSE_STATUSES = ('planned', 'active', 'completed', 'cancelled')
FOLLOW_UP_STATUSES = ('none', 'due', 'done', 'cancelled')

STATUS_LABELS = {
    'planned': 'Запланирован',
    'active': 'Активный',
    'completed': 'Завершён',
    'cancelled': 'Отменён',
}
FOLLOW_UP_STATUS_LABELS = {
    'none': 'Нет',
    'due': 'Нужно follow-up',
    'done': 'Сделан',
    'cancelled': 'Отменён',
}


@dataclass(slots=True)
class TreatmentJournalError(ValueError):
    code: str
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return self.message



def _raise(code: str, message: str, **details: Any) -> None:
    raise TreatmentJournalError(code=code, message=message, details={k: v for k, v in details.items() if v is not None})



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



def _read_csv(path: Path) -> pd.DataFrame:
    try:
        if path.exists():
            return pd.read_csv(path)
    except Exception:
        pass
    return pd.DataFrame()



def _pen_assignment_maps(input_dir: Path, *, asof_date: date) -> tuple[dict[str, dict[str, Any]], dict[str, str], dict[str, str]]:
    assn = compute_pen_assignments(input_dir=input_dir, asof_date=asof_date)
    if assn.empty:
        return {}, {}, {}
    by_animal = {str(r.get('animal_id') or ''): dict(r) for r in assn.to_dict(orient='records')}
    pen_name = {str(r.get('pen_id') or ''): _clean(r.get('pen_name')) for r in assn.to_dict(orient='records')}
    site_name = {str(r.get('site_id') or ''): _clean(r.get('site_name')) for r in assn.to_dict(orient='records')}
    return by_animal, pen_name, site_name



def _load_runtime_rows(repo: TreatmentJournalRepo, *, tenant_id: str, animal_id: str | None, status: str | None, limit: int) -> list[dict[str, Any]]:
    return list(repo.list_rows(tenant_id=tenant_id, filters={
        'animal_id': animal_id,
        'course_status': status,
    }, limit=limit, offset=0).get('items') or [])



def _enrich_runtime_rows(rows: Sequence[Mapping[str, Any]], *, asof_date: date, assn_map: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows or []:
        item = dict(row)
        animal_id = _clean(item.get('animal_id'))
        assn = dict(assn_map.get(animal_id) or {})
        effective = _parse_date(item.get('withdrawal_end_date_effective'))
        follow_due = _parse_date(item.get('follow_up_due_at'))
        item['source'] = 'runtime'
        item['farm_id'] = item.get('farm_id') or assn.get('farm_id')
        item['site_id'] = item.get('site_id') or assn.get('site_id')
        item['pen_id'] = item.get('pen_id') or assn.get('pen_id')
        item['pen_name'] = item.get('pen_name') or assn.get('pen_name')
        item['withdrawal_active_asof'] = bool(effective is not None and effective >= asof_date and _clean(item.get('course_status')) != 'cancelled')
        item['follow_up_due_active'] = bool(follow_due is not None and follow_due <= asof_date and _clean(item.get('follow_up_status')) == 'due')
        item['status_label'] = STATUS_LABELS.get(_clean(item.get('course_status')), _clean(item.get('course_status')) or '—')
        item['follow_up_status_label'] = FOLLOW_UP_STATUS_LABELS.get(_clean(item.get('follow_up_status')), _clean(item.get('follow_up_status')) or '—')
        out.append(item)
    return out



def _legacy_status(row: Mapping[str, Any]) -> str:
    end_date = _parse_date(row.get('end_date'))
    start_date = _parse_date(row.get('start_date'))
    if end_date:
        return 'completed'
    if start_date:
        return 'active'
    return 'planned'



def _load_legacy_treatments(*, input_dir: Path, asof_date: date, animal_id: str | None, pen_id: str | None, assn_map: Mapping[str, Mapping[str, Any]], withdrawal_rules: Mapping[str, Any]) -> list[dict[str, Any]]:
    treatments = _read_csv(input_dir / 'dm_treatments.csv')
    if treatments.empty:
        return []
    if animal_id:
        treatments = treatments[treatments.get('animal_id', pd.Series(dtype=object)).astype(str) == str(animal_id)].copy()
    if pen_id:
        selected = {aid for aid, row in assn_map.items() if _clean(row.get('pen_id')) == str(pen_id)}
        treatments = treatments[treatments.get('animal_id', pd.Series(dtype=object)).astype(str).isin(selected)].copy()
    if treatments.empty:
        return []
    enr = compute_withdrawal_windows(treatments, asof_date=asof_date, rules=dict(withdrawal_rules))
    out: list[dict[str, Any]] = []
    for row in enr.to_dict(orient='records'):
        animal = _clean(row.get('animal_id'))
        assn = dict(assn_map.get(animal) or {})
        out.append({
            'course_id': _clean(row.get('treatment_id')) or f"legacy:{animal}:{_clean(row.get('start_date'))}",
            'tenant_id': _clean(row.get('tenant_id')) or 'default',
            'source': 'legacy',
            'course_status': _legacy_status(row),
            'status_label': STATUS_LABELS.get(_legacy_status(row), _legacy_status(row)),
            'animal_id': animal,
            'farm_id': assn.get('farm_id') or row.get('farm_id'),
            'site_id': assn.get('site_id') or row.get('site_id'),
            'pen_id': assn.get('pen_id'),
            'pen_name': assn.get('pen_name'),
            'linked_alert_id': None,
            'linked_health_event_id': _clean(row.get('reason_event_id')),
            'linked_protocol_execution_id': None,
            'linked_worklist_id': None,
            'treatment_type': _clean(row.get('treatment_type')),
            'diagnosis_label': _clean(row.get('diagnosis')),
            'drug_name': _clean(row.get('drug_name')),
            'drug_code': _clean(row.get('drug_code')),
            'route': _clean(row.get('route')),
            'dose_value': row.get('dose_value'),
            'dose_unit': _clean(row.get('dose_unit')),
            'frequency_per_day': row.get('frequency_per_day'),
            'duration_days': row.get('duration_days'),
            'start_date': _clean(row.get('start_date')),
            'end_date': _clean(row.get('end_date')),
            'follow_up_due_at': None,
            'follow_up_status': 'none',
            'follow_up_status_label': FOLLOW_UP_STATUS_LABELS['none'],
            'withdrawal_rule_version': _clean(withdrawal_rules.get('version')) or '1',
            'withdrawal_days_rule': row.get('withdrawal_days_rule'),
            'withdrawal_end_date_source': _clean(row.get('withdrawal_end_date')),
            'withdrawal_end_date_calc': _clean(row.get('withdrawal_end_date_calc')),
            'withdrawal_end_date_effective': _clean(row.get('withdrawal_end_date_effective')),
            'withdrawal_active_asof': bool(row.get('withdrawal_active_asof')),
            'withdrawal_mismatch': bool(row.get('withdrawal_mismatch')),
            'milk_sale_restriction_active': bool(row.get('withdrawal_active_asof')),
            'source_versions': {'withdrawal_rules_version': _clean(withdrawal_rules.get('version')) or '1'},
            'metadata': {},
            'created_at': None,
            'updated_at': None,
            'created_by_username': None,
            'created_by_role': None,
            'completed_at': _clean(row.get('end_date')),
            'completed_by_username': None,
            'alert_ids': [],
        })
    return out



def _attach_alerts(*, conn, tenant_id: str, rows: list[dict[str, Any]]) -> None:
    if conn is None or not rows:
        return
    animal_ids = sorted({str(r.get('animal_id') or '') for r in rows if str(r.get('animal_id') or '').strip()})
    if not animal_ids:
        return
    ph = ','.join(['?'] * len(animal_ids))
    sql = f"""
        SELECT alert_id, object_id, alert_type, title, status
        FROM alerts_v2
        WHERE tenant_id=? AND object_type='animal' AND object_id IN ({ph}) AND status IN ('new','acknowledged')
        ORDER BY id DESC
    """
    rows_db = conn.execute(sql, tuple([tenant_id] + animal_ids)).fetchall()
    by_animal: dict[str, list[dict[str, Any]]] = {}
    for r in rows_db:
        d = dict(r)
        by_animal.setdefault(str(d.get('object_id') or ''), []).append(d)
    for item in rows:
        arr = list(by_animal.get(str(item.get('animal_id') or ''), []))
        item['alert_ids'] = [str(x.get('alert_id') or '') for x in arr if str(x.get('alert_id') or '').strip()]
        item['withdrawal_alert_active'] = any('withdrawal' in str(x.get('alert_type') or '').lower() for x in arr)



def _compute_aggregates(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    active = [r for r in rows if bool(r.get('withdrawal_active_asof'))]
    by_group: dict[str, int] = {}
    by_farm: dict[str, int] = {}
    by_animal: list[dict[str, Any]] = []
    for r in active:
        group = _clean(r.get('pen_name') or r.get('pen_id')) or '—'
        farm = _clean(r.get('farm_id')) or '—'
        by_group[group] = by_group.get(group, 0) + 1
        by_farm[farm] = by_farm.get(farm, 0) + 1
        by_animal.append({
            'animal_id': r.get('animal_id') or '—',
            'group': group,
            'farm_id': farm,
            'until': r.get('withdrawal_end_date_effective') or '—',
            'drug_name': r.get('drug_name') or '—',
            'treatment_type': r.get('treatment_type') or '—',
            'source': r.get('source') or '—',
            'course_id': r.get('course_id') or '—',
            'alert_ids': ', '.join(r.get('alert_ids') or []) or '—',
        })
    group_rows = [{'group': k, 'active_withdrawals_n': v} for k, v in sorted(by_group.items(), key=lambda kv: (-kv[1], kv[0]))]
    farm_rows = [{'farm_id': k, 'active_withdrawals_n': v} for k, v in sorted(by_farm.items(), key=lambda kv: (-kv[1], kv[0]))]
    return {
        'active_by_animal': by_animal,
        'active_by_group': group_rows,
        'active_by_farm': farm_rows,
    }



def build_treatment_journal_snapshot(
    *,
    input_dir: Path,
    conn,
    tenant_id: str,
    asof_date: date,
    animal_id: str | None = None,
    pen_id: str | None = None,
    site_id: str | None = None,
    farm_id: str | None = None,
    status: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    input_dir = Path(input_dir)
    assn_map, _pen_name_map, _site_name_map = _pen_assignment_maps(input_dir, asof_date=asof_date)
    rules = load_withdrawal_rules(path=WITHDRAWAL_RULES_PATH)
    repo = TreatmentJournalRepo(conn)
    runtime_rows = _enrich_runtime_rows(_load_runtime_rows(repo, tenant_id=tenant_id, animal_id=animal_id, status=status, limit=limit), asof_date=asof_date, assn_map=assn_map)
    legacy_rows = _load_legacy_treatments(input_dir=input_dir, asof_date=asof_date, animal_id=animal_id, pen_id=pen_id, assn_map=assn_map, withdrawal_rules=rules)
    rows = runtime_rows + legacy_rows
    if pen_id:
        rows = [r for r in rows if _clean(r.get('pen_id')) == _clean(pen_id)]
    if site_id:
        rows = [r for r in rows if _clean(r.get('site_id')) == _clean(site_id)]
    if farm_id:
        rows = [r for r in rows if _clean(r.get('farm_id')) == _clean(farm_id)]
    if status:
        rows = [r for r in rows if _clean(r.get('course_status')) == _clean(status)]
    rows = sorted(rows, key=lambda r: (_clean(r.get('withdrawal_end_date_effective')) or '9999-12-31', _clean(r.get('animal_id'))))[: int(limit)]
    _attach_alerts(conn=conn, tenant_id=tenant_id, rows=rows)
    aggs = _compute_aggregates(rows)
    summary = {
        'total_courses': len(rows),
        'runtime_n': sum(1 for r in rows if r.get('source') == 'runtime'),
        'legacy_n': sum(1 for r in rows if r.get('source') == 'legacy'),
        'active_withdrawals_n': sum(1 for r in rows if bool(r.get('withdrawal_active_asof'))),
        'follow_up_due_n': sum(1 for r in rows if bool(r.get('follow_up_due_active'))),
        'by_status': {},
    }
    for r in rows:
        st = _clean(r.get('course_status')) or '—'
        summary['by_status'][st] = summary['by_status'].get(st, 0) + 1
    return {
        'asof_date': asof_date.isoformat(),
        'withdrawal_rules_version': _clean(rules.get('version')) or '1',
        'summary': summary,
        'items': rows,
        **aggs,
    }



def _recompute_withdrawal_fields(payload: dict[str, Any], *, rules: Mapping[str, Any]) -> dict[str, Any]:
    df = pd.DataFrame([{
        'treatment_type': payload.get('treatment_type'),
        'start_date': payload.get('start_date'),
        'end_date': payload.get('end_date'),
        'withdrawal_end_date': payload.get('withdrawal_end_date_source'),
    }])
    enr = compute_withdrawal_windows(df, asof_date=date.today(), rules=dict(rules))
    if enr.empty:
        return payload
    row = enr.to_dict(orient='records')[0]
    payload['withdrawal_rule_version'] = _clean(rules.get('version')) or '1'
    payload['withdrawal_days_rule'] = row.get('withdrawal_days_rule')
    calc = _parse_date(row.get('withdrawal_end_date_calc'))
    eff = _parse_date(row.get('withdrawal_end_date_effective'))
    payload['withdrawal_end_date_calc'] = calc.isoformat() if calc else ''
    payload['withdrawal_end_date_effective'] = eff.isoformat() if eff else ''
    return payload



def _write_treatment_audit(conn, *, tenant_id: str, user_id: int, username: str, role: str, action: str, course_id: str, data_version: str | None, request_id: str | None, before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> None:
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=user_id,
        username=username,
        role=role,
        action=action,
        object_type='treatment_course',
        object_id=course_id,
        data_version=data_version,
        request_id=request_id,
        before=dict(before or {}) or None,
        after=dict(after or {}) or None,
    )



def start_treatment_course_use_case(
    conn,
    *,
    tenant_id: str,
    user_id: int,
    username: str,
    role: str,
    animal_id: str,
    treatment_type: str,
    start_date: str,
    drug_name: str | None = None,
    drug_code: str | None = None,
    route: str | None = None,
    dose_value: float | None = None,
    dose_unit: str | None = None,
    frequency_per_day: int | None = None,
    duration_days: int | None = None,
    diagnosis_label: str | None = None,
    follow_up_due_at: str | None = None,
    linked_alert_id: str | None = None,
    linked_health_event_id: str | None = None,
    linked_protocol_execution_id: str | None = None,
    linked_worklist_id: str | None = None,
    farm_id: str | None = None,
    site_id: str | None = None,
    pen_id: str | None = None,
    data_version: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    if not _clean(animal_id):
        _raise('animal_id_required', 'Нужно выбрать животное.', animal_id=animal_id)
    if not _clean(treatment_type):
        _raise('treatment_type_required', 'Нужно указать treatment type.', treatment_type=treatment_type)
    if not _parse_date(start_date):
        _raise('start_date_invalid', 'Нужно указать корректную дату начала курса.', start_date=start_date)
    now = utc_isoformat()
    rules = load_withdrawal_rules(path=WITHDRAWAL_RULES_PATH)
    repo = TreatmentJournalRepo(conn)
    course_id = f"TC-{uuid.uuid4().hex[:10]}"
    payload: dict[str, Any] = {
        'course_status': 'active',
        'animal_id': _clean(animal_id),
        'farm_id': _clean(farm_id),
        'site_id': _clean(site_id),
        'pen_id': _clean(pen_id),
        'linked_alert_id': _clean(linked_alert_id),
        'linked_health_event_id': _clean(linked_health_event_id),
        'linked_protocol_execution_id': _clean(linked_protocol_execution_id),
        'linked_worklist_id': _clean(linked_worklist_id),
        'treatment_type': _clean(treatment_type),
        'diagnosis_label': _clean(diagnosis_label),
        'drug_name': _clean(drug_name),
        'drug_code': _clean(drug_code),
        'route': _clean(route),
        'dose_value': dose_value,
        'dose_unit': _clean(dose_unit),
        'frequency_per_day': int(frequency_per_day or 0) or None,
        'duration_days': int(duration_days or 0) or None,
        'start_date': _clean(start_date),
        'end_date': None,
        'follow_up_due_at': _clean(follow_up_due_at),
        'follow_up_status': 'due' if _clean(follow_up_due_at) else 'none',
        'follow_up_comment': None,
        'withdrawal_end_date_source': None,
        'source_versions': {'withdrawal_rules_version': _clean(rules.get('version')) or '1'},
        'metadata': {},
        'created_by': int(user_id),
        'created_by_username': _clean(username),
        'created_by_role': _clean(role),
        'completed_at': None,
        'completed_by': None,
        'completed_by_username': None,
        'request_id': _clean(request_id),
        'data_version': _clean(data_version),
    }
    payload = _recompute_withdrawal_fields(payload, rules=rules)
    repo.insert(tenant_id=tenant_id, course_id=course_id, created_at=now, payload=payload)
    out = repo.get(tenant_id=tenant_id, course_id=course_id) or {'course_id': course_id}
    _write_treatment_audit(conn, tenant_id=tenant_id, user_id=user_id, username=username, role=role, action='treatment_journal.start', course_id=course_id, data_version=data_version, request_id=request_id, before=None, after=out)
    return out



def update_treatment_course_use_case(
    conn,
    *,
    tenant_id: str,
    course_id: str,
    user_id: int,
    username: str,
    role: str,
    patch: Mapping[str, Any],
    data_version: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    repo = TreatmentJournalRepo(conn)
    before = repo.get(tenant_id=tenant_id, course_id=course_id)
    if not before:
        _raise('course_not_found', 'Курс лечения не найден.', course_id=course_id)
    payload = dict(before)
    for key in (
        'course_status', 'linked_alert_id', 'linked_health_event_id', 'linked_protocol_execution_id', 'linked_worklist_id',
        'treatment_type', 'diagnosis_label', 'drug_name', 'drug_code', 'route', 'dose_value', 'dose_unit',
        'frequency_per_day', 'duration_days', 'start_date', 'end_date', 'follow_up_due_at', 'follow_up_status',
        'follow_up_comment', 'withdrawal_end_date_source', 'farm_id', 'site_id', 'pen_id', 'data_version', 'request_id',
        'completed_at', 'completed_by', 'completed_by_username',
    ):
        if key in patch:
            payload[key] = patch.get(key)
    rules = load_withdrawal_rules(path=WITHDRAWAL_RULES_PATH)
    payload = _recompute_withdrawal_fields(payload, rules=rules)
    repo.update(tenant_id=tenant_id, course_id=course_id, updated_at=utc_isoformat(), payload=payload)
    after = repo.get(tenant_id=tenant_id, course_id=course_id) or {'course_id': course_id}
    _write_treatment_audit(conn, tenant_id=tenant_id, user_id=user_id, username=username, role=role, action='treatment_journal.update', course_id=course_id, data_version=data_version, request_id=request_id, before=before, after=after)
    return after



def complete_treatment_course_use_case(
    conn,
    *,
    tenant_id: str,
    course_id: str,
    user_id: int,
    username: str,
    role: str,
    completed_at: str | None = None,
    end_date: str | None = None,
    follow_up_due_at: str | None = None,
    follow_up_comment: str | None = None,
    data_version: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    when = ensure_utc(datetime.fromisoformat((completed_at or utc_isoformat()).replace('Z', '+00:00')))
    return update_treatment_course_use_case(
        conn,
        tenant_id=tenant_id,
        course_id=course_id,
        user_id=user_id,
        username=username,
        role=role,
        patch={
            'course_status': 'completed',
            'completed_at': when.replace(microsecond=0).isoformat(),
            'completed_by': int(user_id),
            'completed_by_username': _clean(username),
            'end_date': _clean(end_date) or when.date().isoformat(),
            'follow_up_due_at': _clean(follow_up_due_at),
            'follow_up_status': 'due' if _clean(follow_up_due_at) else 'none',
            'follow_up_comment': _clean(follow_up_comment),
            'data_version': _clean(data_version),
            'request_id': _clean(request_id),
        },
        data_version=data_version,
        request_id=request_id,
    )



def get_treatment_course(conn, *, tenant_id: str, course_id: str) -> dict[str, Any] | None:
    return TreatmentJournalRepo(conn).get(tenant_id=tenant_id, course_id=course_id)



def list_treatment_courses(conn, *, tenant_id: str, filters: Mapping[str, Any], limit: int = 200, offset: int = 0) -> dict[str, Any]:
    return TreatmentJournalRepo(conn).list_rows(tenant_id=tenant_id, filters=dict(filters), limit=int(limit), offset=int(offset))


__all__ = [
    'COURSE_STATUSES',
    'FOLLOW_UP_STATUSES',
    'FOLLOW_UP_STATUS_LABELS',
    'STATUS_LABELS',
    'TreatmentJournalError',
    'build_treatment_journal_snapshot',
    'complete_treatment_course_use_case',
    'get_treatment_course',
    'list_treatment_courses',
    'start_treatment_course_use_case',
    'update_treatment_course_use_case',
]
