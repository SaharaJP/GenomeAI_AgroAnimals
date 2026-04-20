from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

import pandas as pd

from core.workflow.alerts import list_alerts
from core.workflow.tasks import _derive_worklist_type
from core.workflow.worklists import list_worklists


_BUCKET_ORDER = {
    'overdue': 0,
    'today': 1,
    'tomorrow': 2,
    'this_week': 3,
    'later': 4,
    'undated': 5,
}

_BUCKET_LABELS = {
    'overdue': 'Просрочено',
    'today': 'Сегодня',
    'tomorrow': 'Завтра',
    'this_week': 'На этой неделе',
    'later': 'Позже',
    'undated': 'Без срока',
}

_ROLE_TEAM_MAP: dict[str, set[str]] = {
    'Operator': {'team-data', 'team-qc'},
    'Zootech': {'team-repro', 'team-econ'},
    'Vet': {'team-health'},
    'Director': {'team-econ'},
    'Admin': {'team-data', 'team-qc'},
}

_ROLE_TYPES_MAP: dict[str, set[str]] = {
    'Operator': {'data_cleanup', 'movement', 'milk_quality'},
    'Zootech': {'reproduction', 'movement', 'culling_review', 'manager_review'},
    'Vet': {'vet', 'health_follow_up', 'milk_quality'},
    'Director': {'manager_review', 'culling_review', 'milk_quality'},
    'Admin': {'data_cleanup', 'manager_review'},
}


def _parse_dateish(value: Any) -> date | None:
    raw = str(value or '').strip()
    if not raw:
        return None
    raw = raw[:10]
    try:
        return date.fromisoformat(raw)
    except Exception:
        return None


def _bucket_for_due_date(due_dt: date | None, *, today: date) -> str:
    if due_dt is None:
        return 'undated'
    if due_dt < today:
        return 'overdue'
    if due_dt == today:
        return 'today'
    if due_dt == (today + timedelta(days=1)):
        return 'tomorrow'
    week_end = today + timedelta(days=max(0, 6 - today.weekday()))
    if due_dt <= week_end:
        return 'this_week'
    return 'later'


def _fact_text(item: Mapping[str, Any]) -> str:
    for key in ('label', 'text', 'message', 'summary', 'title', 'fact', 'reason', 'description'):
        value = str(item.get(key) or '').strip()
        if value:
            return value
    code = str(item.get('code') or item.get('reason_code') or '').strip()
    value = str(item.get('value') or '').strip()
    if code and value:
        return f'{code}: {value}'
    return code or value


def _expected_effect(row: Mapping[str, Any], *, fallback: str = '') -> str:
    why = dict(row.get('why') or {})
    for key in ('expected_effect', 'expected_effect_text', 'effect', 'effect_text', 'impact', 'impact_text'):
        value = str(why.get(key) or '').strip()
        if value:
            return value
    for item in list(row.get('what_to_do') or []):
        if not isinstance(item, Mapping):
            continue
        for key in ('expected_effect', 'effect', 'impact', 'benefit'):
            value = str(item.get(key) or '').strip()
            if value:
                return value
    for item in list(row.get('linked_source_facts') or []):
        if not isinstance(item, Mapping):
            continue
        for key in ('expected_effect', 'effect', 'impact', 'effect_text', 'impact_text'):
            value = str(item.get(key) or '').strip()
            if value:
                return value
    return str(fallback or '').strip()


def _linked_facts_preview(items: Iterable[Any], *, limit: int = 3) -> list[str]:
    out: list[str] = []
    for item in list(items or []):
        if not isinstance(item, Mapping):
            continue
        text = _fact_text(item)
        if text:
            out.append(text)
        if len(out) >= max(1, int(limit)):
            break
    return out


def _type_to_role_team(kind: str) -> tuple[str | None, str | None]:
    key = str(kind or '').strip().lower()
    if key in {'reproduction'}:
        return 'Zootech', 'team-repro'
    if key in {'vet', 'health_follow_up'}:
        return 'Vet', 'team-health'
    if key in {'movement'}:
        return 'Operator', 'team-qc'
    if key in {'milk_quality'}:
        return 'Vet', 'team-health'
    if key in {'data_cleanup'}:
        return 'Operator', 'team-data'
    if key in {'culling_review', 'manager_review'}:
        return 'Director', 'team-econ'
    return None, None


def _role_sort_weight(role: str | None) -> int:
    mapping = {'Operator': 1, 'Zootech': 2, 'Vet': 3, 'Director': 4, 'Admin': 5}
    return mapping.get(str(role or ''), 9)


def _load_units(*, source_kind: str, priority: int, confidence: float | None = None) -> float:
    base = {
        'worklist': 1.0,
        'alert': 0.8,
        'follow_up': 0.7,
        'reproduction_cycle': 0.9,
        'treatment': 1.1,
    }.get(str(source_kind or ''), 1.0)
    priority_factor = {1: 1.8, 2: 1.5, 3: 1.2, 4: 1.0, 5: 0.8}.get(int(priority or 3), 1.0)
    confidence_factor = 1.0 if confidence is None else max(0.6, min(1.2, 0.8 + float(confidence) * 0.4))
    return round(base * priority_factor * confidence_factor, 2)


def _read_csv(path: Path | None) -> pd.DataFrame:
    if not path:
        return pd.DataFrame()
    try:
        if Path(path).exists():
            return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame()


def _load_open_worklist_items(conn, *, tenant_id: str, today: date, data_version: str | None = None) -> list[dict[str, Any]]:
    res = list_worklists(conn, tenant_id=tenant_id, limit=1000)
    items: list[dict[str, Any]] = []
    for row in list(res.get('worklists') or []):
        status = str(row.get('status') or '').strip()
        if status in {'done', 'cancelled'}:
            continue
        if data_version and str(row.get('data_version') or '').strip() not in {'', str(data_version)}:
            continue
        wl_type = str(row.get('worklist_type') or '')
        assignee_role, fallback_team = _type_to_role_team(wl_type)
        due_dt = _parse_dateish(row.get('due_at'))
        bucket = _bucket_for_due_date(due_dt, today=today)
        confidence = row.get('confidence')
        try:
            conf = float(confidence) if confidence not in (None, '') else None
        except Exception:
            conf = None
        priority = int(row.get('priority') or 3)
        items.append({
            'planner_item_id': f"worklist:{row.get('worklist_id') or row.get('task_id')}",
            'source_kind': 'worklist',
            'source_id': str(row.get('worklist_id') or row.get('task_id') or ''),
            'bucket': bucket,
            'bucket_label': _BUCKET_LABELS[bucket],
            'due_at': str(row.get('due_at') or ''),
            'title': str(row.get('title') or row.get('worklist_id') or 'Worklist'),
            'status': status or 'open',
            'priority': priority,
            'confidence': conf,
            'expected_effect': _expected_effect(row),
            'linked_facts_preview': list(row.get('linked_facts_preview') or []),
            'owner_user_id': row.get('owner_user_id'),
            'owner_username': row.get('owner_username'),
            'assignee_team': row.get('assignee_team') or fallback_team,
            'assignee_role': assignee_role,
            'object_type': row.get('object_type'),
            'object_id': row.get('object_id'),
            'linked_alert_id': row.get('linked_alert_id') or row.get('related_alert'),
            'linked_decision_id': row.get('linked_decision_id'),
            'linked_task_id': row.get('linked_task_id') or row.get('task_id'),
            'linked_worklist_id': row.get('worklist_id') or row.get('task_id'),
            'worklist_type': wl_type,
            'load_units': _load_units(source_kind='worklist', priority=priority, confidence=conf),
            'source_chain': {'worklist': dict(row)},
        })
    return items


def _alert_type_text(row: Mapping[str, Any]) -> str:
    return ' '.join([
        str(row.get('alert_type') or ''),
        str(row.get('source') or ''),
        str(row.get('title') or ''),
        str(row.get('cause') or ''),
    ]).lower()


def _alert_expected_effect(row: Mapping[str, Any]) -> str:
    wt = list(row.get('what_to_do') or [])
    if wt and isinstance(wt[0], Mapping):
        for key in ('expected_effect', 'effect', 'impact', 'benefit', 'text', 'action'):
            value = str(wt[0].get(key) or '').strip()
            if value:
                return value
    why = dict(row.get('why') or {})
    for key in ('expected_effect', 'effect', 'impact', 'reason'):
        value = str(why.get(key) or '').strip()
        if value:
            return value
    return ''


def _load_open_alert_items(conn, *, tenant_id: str, today: date, data_version: str | None = None) -> list[dict[str, Any]]:
    res = list_alerts(conn, tenant_id=tenant_id, status=None, limit=1000, offset=0)
    items: list[dict[str, Any]] = []
    for row in list(res.get('alerts') or []):
        status = str(row.get('status') or '').strip().lower()
        if status not in {'new', 'acknowledged'}:
            continue
        if data_version and str(row.get('data_version') or '').strip() not in {'', str(data_version)}:
            continue
        due_dt = _parse_dateish(row.get('deadline') or row.get('created_at'))
        bucket = _bucket_for_due_date(due_dt, today=today)
        kind = _derive_worklist_type(task_type=str(row.get('alert_type') or ''), domain=None, related_alert=str(row.get('alert_type') or ''))
        assignee_role, fallback_team = _type_to_role_team(kind)
        facts: list[dict[str, Any]] = []
        cause = str(row.get('cause') or '').strip()
        if cause:
            facts.append({'label': 'Cause', 'text': cause})
        facts.extend([x for x in list(row.get('what_to_do') or []) if isinstance(x, Mapping)])
        confidence = row.get('confidence')
        try:
            conf = float(confidence) if confidence not in (None, '') else None
        except Exception:
            conf = None
        priority = 1 if bucket == 'overdue' else 2
        items.append({
            'planner_item_id': f"alert:{row.get('alert_id')}",
            'source_kind': 'alert',
            'source_id': str(row.get('alert_id') or ''),
            'bucket': bucket,
            'bucket_label': _BUCKET_LABELS[bucket],
            'due_at': str(row.get('deadline') or row.get('created_at') or ''),
            'title': str(row.get('title') or row.get('alert_type') or 'Alert'),
            'status': status,
            'priority': priority,
            'confidence': conf,
            'expected_effect': _alert_expected_effect(row),
            'linked_facts_preview': _linked_facts_preview(facts),
            'owner_user_id': row.get('owner_user_id'),
            'owner_username': None,
            'assignee_team': fallback_team,
            'assignee_role': assignee_role,
            'object_type': row.get('object_type'),
            'object_id': row.get('object_id'),
            'linked_alert_id': row.get('alert_id'),
            'linked_decision_id': None,
            'linked_task_id': None,
            'linked_worklist_id': None,
            'worklist_type': kind,
            'load_units': _load_units(source_kind='alert', priority=priority, confidence=conf),
            'source_chain': {'alert': dict(row)},
        })
    return items


def _load_follow_up_items(conn: sqlite3.Connection, *, tenant_id: str, today: date, data_version: str | None = None) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM animal_events_v1 WHERE tenant_id=? ORDER BY event_ts DESC, id DESC LIMIT 1000",
        (tenant_id,),
    ).fetchall()
    items: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        if data_version and str(row.get('data_version') or '').strip() not in {'', str(data_version)}:
            continue
        try:
            payload = json.loads(row.get('payload_json') or '{}')
        except Exception:
            payload = {}
        due_value = payload.get('due_date') or payload.get('due_at')
        if not due_value:
            continue
        kind = str(payload.get('follow_up_kind') or payload.get('workflow_action') or '').strip().lower()
        if not kind and str(row.get('reason_code') or '').strip().lower() != 'follow_up_assigned':
            continue
        due_dt = _parse_dateish(due_value)
        bucket = _bucket_for_due_date(due_dt, today=today)
        assignee_role = str(payload.get('assignee_role') or '') or None
        if assignee_role and assignee_role not in _ROLE_TEAM_MAP:
            assignee_role = None
        fallback_role, fallback_team = _type_to_role_team('health_follow_up' if 'follow' in kind or 'preg' in kind else 'reproduction')
        role = assignee_role or fallback_role
        title = 'Follow-up'
        if 'preg' in kind:
            title = 'Контроль preg_check'
        elif kind:
            title = f"Follow-up: {kind}"
        items.append({
            'planner_item_id': f"follow_up:{row.get('event_id')}",
            'source_kind': 'follow_up',
            'source_id': str(row.get('event_id') or ''),
            'bucket': bucket,
            'bucket_label': _BUCKET_LABELS[bucket],
            'due_at': str(due_value),
            'title': title,
            'status': 'planned',
            'priority': 2 if bucket in {'overdue', 'today'} else 3,
            'confidence': None,
            'expected_effect': str(payload.get('expected_effect') or payload.get('comment') or ''),
            'linked_facts_preview': [x for x in [str(payload.get('comment') or '').strip(), str(payload.get('workflow_action') or '').strip()] if x][:3],
            'owner_user_id': None,
            'owner_username': None,
            'assignee_team': fallback_team,
            'assignee_role': role,
            'object_type': 'animal',
            'object_id': row.get('animal_id'),
            'linked_alert_id': None,
            'linked_decision_id': row.get('linked_decision_id'),
            'linked_task_id': row.get('linked_task_id'),
            'linked_worklist_id': None,
            'worklist_type': 'health_follow_up' if role == 'Vet' else 'reproduction',
            'load_units': _load_units(source_kind='follow_up', priority=(2 if bucket in {'overdue', 'today'} else 3), confidence=None),
            'source_chain': {'animal_event': {**row, 'payload': payload}},
        })
    return items


def _latest_repro_by_animal(repro: pd.DataFrame) -> pd.DataFrame:
    if repro.empty or 'animal_id' not in repro.columns or 'event_date' not in repro.columns:
        return pd.DataFrame()
    df = repro.copy()
    df['event_date'] = pd.to_datetime(df['event_date'], errors='coerce')
    df = df.dropna(subset=['animal_id', 'event_date']).sort_values(['animal_id', 'event_date'], ascending=[True, False])
    if df.empty:
        return pd.DataFrame()
    return df.groupby('animal_id', as_index=False).first()


def _load_reproduction_cycle_items(*, input_dir: Path | None, today: date) -> list[dict[str, Any]]:
    repro = _read_csv((Path(input_dir) / 'dm_repro_events.csv') if input_dir else None)
    if repro.empty or 'animal_id' not in repro.columns:
        return []
    latest = _latest_repro_by_animal(repro)
    items: list[dict[str, Any]] = []
    for _, row in latest.iterrows():
        event_type = str(row.get('event_type') or '').strip().lower()
        result = str(row.get('result') or '').strip().lower()
        event_dt = _parse_dateish(row.get('event_date'))
        if event_dt is None:
            continue
        due_dt: date | None = None
        title = None
        expected = ''
        priority = 3
        if event_type == 'heat':
            due_dt = event_dt
            title = 'Окно осеменения'
            expected = 'Не пропустить осеменение по текущему циклу.'
            priority = 1 if due_dt <= today else 2
        elif event_type == 'insemination' and result not in {'pregnant', 'positive', 'confirmed'}:
            due_dt = event_dt + timedelta(days=35)
            title = 'Проверить стельность'
            expected = 'Подтвердить исход цикла и скорректировать follow-up.'
            priority = 2
        if not due_dt or not title:
            continue
        bucket = _bucket_for_due_date(due_dt, today=today)
        items.append({
            'planner_item_id': f"repro_cycle:{row.get('animal_id')}:{title}",
            'source_kind': 'reproduction_cycle',
            'source_id': str(row.get('animal_id') or ''),
            'bucket': bucket,
            'bucket_label': _BUCKET_LABELS[bucket],
            'due_at': due_dt.isoformat(),
            'title': title,
            'status': 'derived',
            'priority': priority,
            'confidence': 0.65,
            'expected_effect': expected,
            'linked_facts_preview': [str(row.get('event_type') or '').strip(), str(row.get('event_date') or '').strip()],
            'owner_user_id': None,
            'owner_username': None,
            'assignee_team': 'team-repro',
            'assignee_role': 'Zootech',
            'object_type': 'animal',
            'object_id': str(row.get('animal_id') or ''),
            'linked_alert_id': None,
            'linked_decision_id': None,
            'linked_task_id': None,
            'linked_worklist_id': None,
            'worklist_type': 'reproduction',
            'load_units': _load_units(source_kind='reproduction_cycle', priority=priority, confidence=0.65),
            'source_chain': {'repro_event': row.to_dict()},
        })
    return items


def _load_treatment_items(*, input_dir: Path | None, today: date) -> list[dict[str, Any]]:
    tr = _read_csv((Path(input_dir) / 'dm_treatments.csv') if input_dir else None)
    if tr.empty or 'animal_id' not in tr.columns:
        return []
    items: list[dict[str, Any]] = []
    for _, row in tr.iterrows():
        end_dt = _parse_dateish(row.get('milk_withdrawal_end') or row.get('withdrawal_end_date') or row.get('end_date'))
        start_dt = _parse_dateish(row.get('start_date'))
        if end_dt is None and start_dt is None:
            continue
        if end_dt is None and start_dt is not None:
            end_dt = start_dt + timedelta(days=int(row.get('duration_days') or 1))
        if end_dt is None:
            continue
        if end_dt < (today - timedelta(days=7)):
            continue
        bucket = _bucket_for_due_date(end_dt, today=today)
        treatment_type = str(row.get('treatment_type') or row.get('diagnosis') or row.get('drug_name') or 'treatment').strip()
        items.append({
            'planner_item_id': f"treatment:{row.get('treatment_id') or row.get('animal_id')}:{end_dt.isoformat()}",
            'source_kind': 'treatment',
            'source_id': str(row.get('treatment_id') or row.get('animal_id') or ''),
            'bucket': bucket,
            'bucket_label': _BUCKET_LABELS[bucket],
            'due_at': end_dt.isoformat(),
            'title': f'Контроль лечения: {treatment_type}',
            'status': 'active' if end_dt >= today else 'overdue',
            'priority': 2 if end_dt <= today else 3,
            'confidence': 0.7,
            'expected_effect': 'Завершить курс, проверить withdrawal и клинический исход.',
            'linked_facts_preview': [x for x in [str(row.get('diagnosis') or '').strip(), str(row.get('drug_name') or '').strip()] if x][:3],
            'owner_user_id': None,
            'owner_username': None,
            'assignee_team': 'team-health',
            'assignee_role': 'Vet',
            'object_type': 'animal',
            'object_id': str(row.get('animal_id') or ''),
            'linked_alert_id': None,
            'linked_decision_id': None,
            'linked_task_id': None,
            'linked_worklist_id': None,
            'worklist_type': 'vet',
            'load_units': _load_units(source_kind='treatment', priority=(2 if end_dt <= today else 3), confidence=0.7),
            'source_chain': {'treatment': row.to_dict()},
        })
    return items


def _matches_planner_filters(
    row: Mapping[str, Any],
    *,
    role: str | None,
    owner_user_id: int | None,
    assignee_team: str | None,
    view_mode: str,
) -> bool:
    if role and str(role).strip() not in {'', 'All'}:
        wanted_role = str(role).strip()
        if view_mode == 'executor':
            if str(row.get('assignee_role') or '').strip() not in {'', wanted_role}:
                role_types = _ROLE_TYPES_MAP.get(wanted_role, set())
                if str(row.get('worklist_type') or '').strip() not in role_types:
                    return False
        else:
            if str(row.get('assignee_role') or '').strip() not in {'', wanted_role} and str(row.get('worklist_type') or '').strip() not in _ROLE_TYPES_MAP.get(wanted_role, set()):
                return False
    if owner_user_id is not None and row.get('owner_user_id') not in (owner_user_id, str(owner_user_id)):
        return False
    if assignee_team and str(row.get('assignee_team') or '').strip() != str(assignee_team).strip():
        return False
    return True


def _sort_planner_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda r: (
            _BUCKET_ORDER.get(str(r.get('bucket') or ''), 99),
            int(r.get('priority') or 3),
            str(r.get('due_at') or '9999-12-31'),
            _role_sort_weight(r.get('assignee_role')),
            str(r.get('title') or ''),
        ),
    )


def _summaries(items: list[dict[str, Any]]) -> dict[str, Any]:
    by_bucket = Counter(str(r.get('bucket') or 'undated') for r in items)
    by_team_counts = Counter(str(r.get('assignee_team') or 'unassigned') for r in items)
    by_role_counts = Counter(str(r.get('assignee_role') or 'unassigned') for r in items)
    by_team_load: dict[str, float] = defaultdict(float)
    for row in items:
        by_team_load[str(row.get('assignee_team') or 'unassigned')] += float(row.get('load_units') or 0.0)

    expected_load = {
        'items_total': len(items),
        'load_units_total': round(sum(float(r.get('load_units') or 0.0) for r in items), 2),
        'by_bucket': {
            bucket: {
                'count': int(by_bucket.get(bucket, 0)),
                'load_units': round(sum(float(r.get('load_units') or 0.0) for r in items if str(r.get('bucket')) == bucket), 2),
            }
            for bucket in ['overdue', 'today', 'tomorrow', 'this_week', 'later', 'undated']
        },
        'by_team': [
            {'assignee_team': team, 'count': int(by_team_counts.get(team, 0)), 'load_units': round(load, 2)}
            for team, load in sorted(by_team_load.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        'by_role': [
            {'assignee_role': role, 'count': int(count)}
            for role, count in sorted(by_role_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
    }

    bottlenecks: list[dict[str, Any]] = []
    for team, load in sorted(by_team_load.items(), key=lambda kv: (-kv[1], kv[0]))[:5]:
        team_items = [r for r in items if str(r.get('assignee_team') or 'unassigned') == team]
        overdue_n = sum(1 for r in team_items if str(r.get('bucket')) == 'overdue')
        today_n = sum(1 for r in team_items if str(r.get('bucket')) == 'today')
        high_n = sum(1 for r in team_items if int(r.get('priority') or 3) <= 2)
        if overdue_n or today_n or load >= 3.5:
            bottlenecks.append({
                'assignee_team': team,
                'load_units': round(load, 2),
                'overdue': overdue_n,
                'today': today_n,
                'high_priority': high_n,
                'hint': f"{team}: overdue={overdue_n}, today={today_n}, load={round(load,2)}",
            })
    return {'expected_load': expected_load, 'bottlenecks': bottlenecks}


def build_operational_planner_snapshot(
    conn,
    *,
    tenant_id: str,
    today_iso: str | None = None,
    data_version: str | None = None,
    input_dir: Path | None = None,
    role: str | None = None,
    owner_user_id: int | None = None,
    assignee_team: str | None = None,
    view_mode: str = 'executor',
    include_sources: Iterable[str] | None = None,
    q: str | None = None,
    limit_per_bucket: int = 50,
) -> dict[str, Any]:
    today = _parse_dateish(today_iso) or date.today()
    sources = set(str(x).strip() for x in (include_sources or ['alerts', 'worklists', 'follow_ups', 'reproduction_cycles', 'treatments']) if str(x).strip())

    items: list[dict[str, Any]] = []
    if 'worklists' in sources:
        items.extend(_load_open_worklist_items(conn, tenant_id=tenant_id, today=today, data_version=data_version))
    if 'alerts' in sources:
        items.extend(_load_open_alert_items(conn, tenant_id=tenant_id, today=today, data_version=data_version))
    if 'follow_ups' in sources:
        items.extend(_load_follow_up_items(conn, tenant_id=tenant_id, today=today, data_version=data_version))
    if 'reproduction_cycles' in sources:
        items.extend(_load_reproduction_cycle_items(input_dir=input_dir, today=today))
    if 'treatments' in sources:
        items.extend(_load_treatment_items(input_dir=input_dir, today=today))

    if q:
        needle = str(q).strip().lower()
        items = [
            row for row in items
            if needle in ' '.join([
                str(row.get('title') or ''),
                str(row.get('expected_effect') or ''),
                str(row.get('object_id') or ''),
                str(row.get('source_kind') or ''),
                ' '.join(list(row.get('linked_facts_preview') or [])),
            ]).lower()
        ]

    items = [
        row for row in items
        if _matches_planner_filters(row, role=role, owner_user_id=owner_user_id, assignee_team=assignee_team, view_mode=str(view_mode or 'executor'))
    ]
    items = _sort_planner_items(items)

    buckets: dict[str, list[dict[str, Any]]] = {}
    for bucket in ['overdue', 'today', 'tomorrow', 'this_week']:
        bucket_items = [dict(r) for r in items if str(r.get('bucket')) == bucket][: max(1, int(limit_per_bucket))]
        buckets[bucket] = bucket_items

    extra = _summaries(items)
    summary = {
        'today': today.isoformat(),
        'view_mode': str(view_mode or 'executor'),
        'role': str(role or ''),
        'owner_user_id': owner_user_id,
        'assignee_team': assignee_team,
        'sources': sorted(sources),
        'items_total': len(items),
        'overdue': len([1 for r in items if str(r.get('bucket')) == 'overdue']),
        'today_count': len([1 for r in items if str(r.get('bucket')) == 'today']),
        'tomorrow_count': len([1 for r in items if str(r.get('bucket')) == 'tomorrow']),
        'this_week_count': len([1 for r in items if str(r.get('bucket')) == 'this_week']),
        'by_source': dict(Counter(str(r.get('source_kind') or 'unknown') for r in items)),
    }
    return {
        'summary': summary,
        'buckets': buckets,
        'all_items': items,
        'expected_load': extra['expected_load'],
        'bottlenecks': extra['bottlenecks'],
    }


__all__ = [
    'build_operational_planner_snapshot',
]
