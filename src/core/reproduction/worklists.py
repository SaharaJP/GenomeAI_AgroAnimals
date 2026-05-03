from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from core.audit import write_audit
from core.operational.quick_entry import add_animal_event_comment_use_case
from core.reproduction.state_machine import DEFAULT_REPRO_CONFIG, build_reproduction_states_table
from core.workflow.worklists import create_worklist_use_case, get_worklist
from core.workflow.outcomes import record_completion_outcome_use_case
from genomeai.drilldown import compute_pen_assignments


DEFAULT_REPRO_WORKLIST_CONFIG: dict[str, Any] = {
    **DEFAULT_REPRO_CONFIG,
    'gestation_days': 280,
    'dry_period_days': 60,
    'dry_off_lookahead_days': 14,
}

_ACTION_LABELS: dict[str, str] = {
    'watch_heat': 'Смотреть на охоту',
    'inseminate': 'Осеменять',
    'preg_check': 'Проверять на стельность',
    'recheck': 'Recheck / повторно проверить',
    'dry_off': 'Dry-off',
}

_EXPECTED_EFFECTS: dict[str, str] = {
    'watch_heat': 'Снизить пропуск цикла и не потерять окно для осеменения.',
    'inseminate': 'Своевременно закрыть окно по охоте и перевести животное в bred.',
    'preg_check': 'Подтвердить или снять стельность в нормативный срок.',
    'recheck': 'Вернуть животное в управляемый repro-цикл после повторного сервиса/отрицательной проверки.',
    'dry_off': 'Подготовить животное к dry period и следующему calving cycle.',
}

_CONFIDENCE: dict[str, float] = {
    'watch_heat': 0.70,
    'inseminate': 0.92,
    'preg_check': 0.96,
    'recheck': 0.84,
    'dry_off': 0.76,
}

_PRIORITY: dict[str, int] = {
    'inseminate': 1,
    'preg_check': 1,
    'recheck': 2,
    'dry_off': 2,
    'watch_heat': 3,
}


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _read_csv(path: Path) -> pd.DataFrame:
    try:
        if path.exists():
            return pd.read_csv(path)
    except Exception:
        pass
    return pd.DataFrame()




def _get_active_task_by_dedupe(conn, *, tenant_id: str, dedupe_key: str) -> str | None:
    row = conn.execute(
        """
        SELECT task_id FROM tasks_v1
        WHERE tenant_id=? AND dedupe_key=? AND status IN ('open','in_progress')
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (str(tenant_id), str(dedupe_key)),
    ).fetchone()
    if not row:
        return None
    return str(row[0])

def _parse_date(value: Any) -> date | None:
    try:
        ts = pd.to_datetime(value, errors='coerce')
        if pd.isna(ts):
            return None
        return ts.date()
    except Exception:
        return None


def _state_to_action(*, row: Mapping[str, Any], asof_date: date, cfg: Mapping[str, Any]) -> dict[str, Any] | None:
    state = _clean(row.get('repro_state')).lower()
    reason_code = _clean(row.get('repro_reason_code')) or 'REPRO_NO_DATA'
    reason_label = _clean(row.get('repro_reason_label')) or '—'
    animal_id = _clean(row.get('animal_id'))
    if not animal_id or not state or state == 'no_data':
        return None

    action_type: str | None = None
    due_date: date | None = None
    next_step = ''

    if state in {'eligible', 'open'}:
        action_type = 'watch_heat'
        due_date = asof_date
        next_step = 'Проверить животное на охоту и при сигнале зафиксировать heat.'
    elif state == 'heat':
        action_type = 'inseminate'
        due_date = asof_date
        next_step = 'Подтвердить heat и зафиксировать insemination.'
    elif state == 'preg_check_due':
        action_type = 'preg_check'
        due_date = _parse_date(row.get('next_preg_check_due_date')) or asof_date
        next_step = 'Провести preg_check и записать результат.'
    elif state == 'repeat':
        action_type = 'recheck'
        due_date = asof_date
        next_step = 'Сделать recheck цикла и назначить follow-up.'
    elif state == 'pregnant':
        last_bred_date = _parse_date(row.get('last_bred_date'))
        if last_bred_date is not None:
            gestation_days = int(cfg.get('gestation_days') or 280)
            dry_period_days = int(cfg.get('dry_period_days') or 60)
            lookahead = int(cfg.get('dry_off_lookahead_days') or 14)
            dry_due = last_bred_date + timedelta(days=gestation_days - dry_period_days)
            if dry_due <= (asof_date + timedelta(days=lookahead)):
                action_type = 'dry_off'
                due_date = dry_due
                next_step = 'Подготовить и зафиксировать dry-off.'

    if not action_type or due_date is None:
        return None

    linked_facts = [
        {'label': 'Repro state', 'text': _clean(row.get('repro_state_label')) or state},
        {'label': 'Reason', 'text': reason_label},
    ]
    for key, label in (
        ('last_bred_date', 'Last bred'),
        ('next_preg_check_due_date', 'Preg check due'),
        ('services_since_calving', 'Services since calving'),
        ('days_since_bred', 'Days since bred'),
        ('days_in_milk', 'DIM'),
    ):
        value = row.get(key)
        text = _clean(value)
        if text:
            linked_facts.append({'label': label, 'text': text})

    return {
        'animal_id': animal_id,
        'action_type': action_type,
        'action_label': _ACTION_LABELS[action_type],
        'title': f"{_ACTION_LABELS[action_type]} · {animal_id}",
        'due_at': due_date.isoformat(),
        'priority': _PRIORITY[action_type],
        'confidence': _CONFIDENCE[action_type],
        'expected_effect': _EXPECTED_EFFECTS[action_type],
        'next_step_action': next_step,
        'reason_code': reason_code,
        'reason_label': reason_label,
        'linked_source_facts': linked_facts,
        'worklist_type': 'reproduction',
        'task_type': f'repro.{action_type}',
        'assignee_team': 'team-repro',
        'owner_role': 'Zootech',
        'dedupe_key': f"repro:{action_type}:{animal_id}:{due_date.isoformat()}",
    }


def build_reproduction_worklists_snapshot(
    *,
    input_dir: Path,
    asof_date: date,
    conn=None,
    tenant_id: str | None = None,
    animal_id: str | None = None,
    pen_id: str | None = None,
    action_types: Sequence[str] | None = None,
    limit: int | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    base = Path(input_dir)
    cfg = dict(DEFAULT_REPRO_WORKLIST_CONFIG)
    cfg.update(dict(config or {}))

    animals = _read_csv(base / 'dm_animals.csv')
    lact = _read_csv(base / 'dm_lactations.csv')
    repro = _read_csv(base / 'dm_repro_events.csv')
    pens = _read_csv(base / 'dm_pens.csv')
    assn = compute_pen_assignments(input_dir=base, asof_date=asof_date)

    if animals.empty:
        return {'summary': {'total': 0, 'by_action': {}, 'by_pen': {}}, 'items': []}

    animal_filter = _clean(animal_id)
    pen_filter = _clean(pen_id)
    if animal_filter:
        animals = animals[animals.get('animal_id', pd.Series(dtype=object)).astype(str) == animal_filter].copy()
    if pen_filter and not assn.empty:
        selected = set(assn[assn.get('pen_id', pd.Series(dtype=object)).astype(str) == pen_filter].get('animal_id', pd.Series(dtype=object)).astype(str).tolist())
        animals = animals[animals.get('animal_id', pd.Series(dtype=object)).astype(str).isin(selected)].copy()

    animal_ids = [str(x) for x in animals.get('animal_id', pd.Series(dtype=object)).dropna().astype(str).tolist()]
    states = build_reproduction_states_table(
        animals_df=animals,
        lactations_df=lact,
        repro_events_df=repro,
        operational_events_df=pd.DataFrame(),
        animal_ids=animal_ids,
        asof_date=asof_date,
        config=cfg,
    )
    if states.empty:
        return {'summary': {'total': 0, 'by_action': {}, 'by_pen': {}}, 'items': []}

    action_filter = {str(x).strip().lower() for x in (action_types or []) if str(x).strip()}

    assn_map = {str(r.get('animal_id') or ''): dict(r) for r in assn.to_dict(orient='records')} if not assn.empty else {}
    pen_name_map = {str(r.get('pen_id') or ''): _clean(r.get('pen_name')) for r in pens.to_dict(orient='records')} if not pens.empty else {}

    items: list[dict[str, Any]] = []
    for row in states.to_dict(orient='records'):
        action = _state_to_action(row=row, asof_date=asof_date, cfg=cfg)
        if not action:
            continue
        if action_filter and action['action_type'] not in action_filter:
            continue
        assignment = dict(assn_map.get(action['animal_id']) or {})
        row_out = dict(action)
        row_out.update({
            'tenant_id': _clean(assignment.get('tenant_id')) or 'default',
            'farm_id': _clean(assignment.get('farm_id')),
            'site_id': _clean(assignment.get('site_id')),
            'object_type': 'animal',
            'object_id': action['animal_id'],
            'pen_id': _clean(assignment.get('pen_id')),
            'pen_name': _clean(assignment.get('pen_name')) or pen_name_map.get(_clean(assignment.get('pen_id')), ''),
            'repro_state': _clean(row.get('repro_state')),
            'repro_state_label': _clean(row.get('repro_state_label')),
            'repro_reason_code': _clean(row.get('repro_reason_code')),
            'repro_reason_label': _clean(row.get('repro_reason_label')),
            'last_bred_date': _clean(row.get('last_bred_date')),
            'next_preg_check_due_date': _clean(row.get('next_preg_check_due_date')),
            'services_since_calving': row.get('services_since_calving'),
            'days_in_milk': row.get('days_in_milk'),
            'days_since_bred': row.get('days_since_bred'),
            'source_facts_preview': [str(f.get('text') or '').strip() for f in action['linked_source_facts'][:3] if str(f.get('text') or '').strip()],
        })
        if conn is not None and tenant_id:
            existing_task_id = _get_active_task_by_dedupe(conn, tenant_id=str(tenant_id), dedupe_key=row_out['dedupe_key'])
            if existing_task_id:
                existing = get_worklist(conn, tenant_id=str(tenant_id), worklist_id=str(existing_task_id)) or {}
                row_out['existing_worklist_id'] = str(existing_task_id)
                row_out['existing_status'] = str(existing.get('status') or '')
                row_out['existing_stage'] = str(existing.get('stage') or '')
                row_out['materialized'] = True
            else:
                row_out['existing_worklist_id'] = ''
                row_out['existing_status'] = ''
                row_out['existing_stage'] = ''
                row_out['materialized'] = False
        items.append(row_out)

    items.sort(key=lambda r: (str(r.get('due_at') or ''), int(r.get('priority') or 9), str(r.get('animal_id') or '')))
    if limit is not None:
        items = items[: max(1, int(limit))]

    by_action: dict[str, int] = {}
    by_pen: dict[str, int] = {}
    for row in items:
        by_action[row['action_type']] = by_action.get(row['action_type'], 0) + 1
        pen_key = _clean(row.get('pen_id')) or '—'
        by_pen[pen_key] = by_pen.get(pen_key, 0) + 1

    return {
        'summary': {
            'total': len(items),
            'by_action': by_action,
            'by_pen': by_pen,
            'materialized_n': sum(1 for row in items if bool(row.get('materialized'))),
        },
        'items': items,
    }


def sync_reproduction_worklists_use_case(
    *,
    conn,
    tenant_id: str,
    rows: Sequence[Mapping[str, Any]],
    user_id: int,
    username: str,
    role: str,
    data_version: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    created: list[dict[str, Any]] = []
    existing: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        animal_id = _clean(row.get('animal_id'))
        if not animal_id:
            invalid.append({'animal_id': '', 'error': 'animal_id_required'})
            continue
        dedupe_key = _clean(row.get('dedupe_key'))
        if dedupe_key:
            existing_task_id = _get_active_task_by_dedupe(conn, tenant_id=str(tenant_id), dedupe_key=dedupe_key)
            if existing_task_id:
                existing.append({'animal_id': animal_id, 'worklist_id': str(existing_task_id)})
                continue
        res = create_worklist_use_case(
            conn=conn,
            tenant_id=str(tenant_id),
            worklist_type='reproduction',
            user_id=int(user_id or 0),
            username=str(username or ''),
            role=str(role or ''),
            title=str(row.get('title') or f'Repro action · {animal_id}'),
            task_type=str(row.get('task_type') or 'repro.action'),
            domain='repro',
            priority=int(row.get('priority') or 3),
            due_at=str(row.get('due_at') or ''),
            owner_user_id=(int(user_id) if str(role or '').strip() in {'Operator', 'Zootech'} else None),
            assignee_team='team-repro',
            confidence=float(row.get('confidence') or 0.0),
            object_type='animal',
            object_id=animal_id,
            linked_source_facts=list(row.get('linked_source_facts') or []),
            why={
                'repro_state': row.get('repro_state'),
                'repro_reason_code': row.get('repro_reason_code'),
                'repro_reason_label': row.get('repro_reason_label'),
                'action_type': row.get('action_type'),
            },
            what_to_do=[{'action': row.get('action_type'), 'label': row.get('next_step_action') or row.get('action_label') or 'Сделать repro action'}],
            data_version=str(data_version or row.get('data_version') or ''),
            dedupe_key=dedupe_key or None,
            request_id=request_id,
        )
        created.append({'animal_id': animal_id, 'worklist_id': str(res.get('worklist_id') or '')})

    write_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id or 0),
        username=str(username or ''),
        role=str(role or ''),
        action='repro_worklists.sync',
        object_type='worklist',
        object_id='batch',
        data_version=(str(data_version) if data_version not in (None, '') else None),
        before={},
        after={'created': created, 'existing': existing, 'invalid': invalid},
        status='OK',
        request_id=(str(request_id) if request_id not in (None, '') else None),
    )
    return {'created': created, 'existing': existing, 'invalid': invalid, 'summary': {'created_n': len(created), 'existing_n': len(existing), 'invalid_n': len(invalid)}}


def batch_complete_reproduction_worklists_use_case(
    *,
    conn,
    tenant_id: str,
    worklist_ids: Sequence[str],
    user_id: int,
    username: str,
    role: str,
    outcome_status: str,
    reason: str,
    comment: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    completed: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for worklist_id in [str(x).strip() for x in worklist_ids if str(x).strip()]:
        try:
            res = record_completion_outcome_use_case(
                conn=conn,
                tenant_id=str(tenant_id),
                worklist_id=worklist_id,
                user_id=int(user_id or 0),
                username=str(username or ''),
                role=str(role or ''),
                outcome_status=str(outcome_status or 'done'),
                reason_code=str(reason or 'done'),
                comment=(str(comment) if comment else None),
                auto_link_decision=False,
                auto_resolve_related_alert=False,
                request_id=request_id,
            )
            completed.append({'worklist_id': worklist_id, 'outcome': dict(res.get('outcome') or {})})
        except Exception as exc:
            errors.append({'worklist_id': worklist_id, 'error': str(exc)})
    write_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id or 0),
        username=str(username or ''),
        role=str(role or ''),
        action='repro_worklists.batch_complete',
        object_type='worklist',
        object_id='batch',
        before={},
        after={'completed': completed, 'errors': errors, 'outcome_status': outcome_status, 'reason': reason},
        status='OK',
        request_id=(str(request_id) if request_id not in (None, '') else None),
    )
    return {'completed': completed, 'errors': errors, 'summary': {'completed_n': len(completed), 'errors_n': len(errors)}}


def bulk_comment_reproduction_animals_use_case(
    *,
    conn,
    tenant_id: str,
    animal_ids: Sequence[str],
    comment: str,
    user_id: int,
    username: str,
    role: str,
    event_ts: str,
    data_version: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    added: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for animal_id in [str(x).strip() for x in animal_ids if str(x).strip()]:
        try:
            res = add_animal_event_comment_use_case(
                conn=conn,
                tenant_id=str(tenant_id),
                animal_id=animal_id,
                user_id=int(user_id or 0),
                username=str(username or ''),
                role=str(role or ''),
                event_ts=str(event_ts),
                comment=str(comment),
                request_id=request_id,
                data_version=(str(data_version) if data_version else None),
            )
            added.append({'animal_id': animal_id, 'event_id': str((res.get('after') or {}).get('event_id') or '')})
        except Exception as exc:
            errors.append({'animal_id': animal_id, 'error': str(exc)})
    write_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id or 0),
        username=str(username or ''),
        role=str(role or ''),
        action='repro_worklists.bulk_comment',
        object_type='animal',
        object_id='batch',
        data_version=(str(data_version) if data_version not in (None, '') else None),
        before={},
        after={'added': added, 'errors': errors, 'comment': str(comment or '')},
        status='OK',
        request_id=(str(request_id) if request_id not in (None, '') else None),
    )
    return {'added': added, 'errors': errors, 'summary': {'added_n': len(added), 'errors_n': len(errors)}}


__all__ = [
    'DEFAULT_REPRO_WORKLIST_CONFIG',
    'build_reproduction_worklists_snapshot',
    'sync_reproduction_worklists_use_case',
    'batch_complete_reproduction_worklists_use_case',
    'bulk_comment_reproduction_animals_use_case',
]
