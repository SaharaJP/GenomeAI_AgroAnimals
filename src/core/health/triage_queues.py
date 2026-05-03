from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from core.health.treatment_journal import build_treatment_journal_snapshot
from core.operational.quick_entry import create_animal_event_use_case
from core.workflow.outcomes import record_completion_outcome_use_case
from core.workflow.worklists import create_worklist_use_case, get_worklist
from genomeai.drilldown import compute_pen_assignments

QUEUE_LABELS = {
    'mastitis': 'Мастит',
    'lameness': 'Хромота',
    'ketosis': 'Кетоз',
    'metritis': 'Метрит',
    'fresh_cows': 'Fresh cows',
    'retreatment': 'Retreatment',
    'chronic_review': 'Chronic review',
}

QUEUE_NEXT_ACTIONS = {
    'mastitis': 'Осмотр вымени и проверка текущего treatment/follow-up.',
    'lameness': 'Осмотр конечностей и решение по treatment/follow-up.',
    'ketosis': 'Проверка состояния, аппетита и need-for-treatment/follow-up.',
    'metritis': 'Проверка после отёла и решение по treatment/follow-up.',
    'fresh_cows': 'Плановый осмотр fresh cow и контроль раннего post-calving периода.',
    'retreatment': 'Проверить follow-up курса и решить: продолжить / повторить / закрыть.',
    'chronic_review': 'Пересмотреть хронический кейс и определить plan / culling / protocol.',
}

QUEUE_FACT_LABELS = {
    'mastitis': 'mastitis event',
    'lameness': 'lameness event',
    'ketosis': 'ketosis event',
    'metritis': 'metritis event',
    'fresh_cows': 'fresh cow',
    'retreatment': 'treatment follow-up',
    'chronic_review': 'chronic burden',
}

QUEUE_WORKLIST_TYPE = {
    'fresh_cows': 'health_follow_up',
    'retreatment': 'health_follow_up',
}

EVENT_KEYWORDS = {
    'mastitis': {'mastitis', 'udder', 'somatic', 'scc'},
    'lameness': {'lameness', 'hoof', 'leg', 'limb', 'claw'},
    'ketosis': {'ketosis', 'acetone', 'energy'},
    'metritis': {'metritis', 'uter', 'postpartum', 'fresh'},
}

SEVERITY_RANK = {'high': 0, 'critical': 0, 'medium': 1, 'low': 2, 'unknown': 3, '': 4}
SEVERITY_LABELS = {'high': 'Высокая', 'critical': 'Критическая', 'medium': 'Средняя', 'low': 'Низкая', 'unknown': 'Не указана', '': 'Не указана'}
CONFIDENCE_BY_SEVERITY = {'critical': 0.95, 'high': 0.9, 'medium': 0.75, 'low': 0.6, 'unknown': 0.5, '': 0.5}


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _parse_date(value: Any) -> date | None:
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


def _read_csv(path: Path) -> pd.DataFrame:
    try:
        if path.exists():
            return pd.read_csv(path)
    except Exception:
        pass
    return pd.DataFrame()


def _pen_assignment_maps(input_dir: Path, *, asof_date: date) -> tuple[dict[str, dict[str, Any]], dict[str, str], dict[str, str]]:
    try:
        assn = compute_pen_assignments(input_dir=input_dir, asof_date=asof_date)
        if not assn.empty:
            by_animal = {str(r.get('animal_id') or ''): dict(r) for r in assn.to_dict(orient='records')}
            pen_names = {str(r.get('pen_id') or ''): _clean(r.get('pen_name')) for r in assn.to_dict(orient='records')}
            site_names = {str(r.get('site_id') or ''): _clean(r.get('site_name')) for r in assn.to_dict(orient='records')}
            return by_animal, pen_names, site_names
    except Exception:
        pass
    animals = _load_animals(input_dir)
    pens = _read_csv(input_dir / 'dm_pens.csv')
    moves = _read_csv(input_dir / 'dm_pen_moves.csv')
    by_animal: dict[str, dict[str, Any]] = {}
    pen_name_map = {str(r.get('pen_id') or ''): _clean(r.get('pen_name')) for r in pens.to_dict(orient='records')} if not pens.empty else {}
    site_name_map = {str(r.get('site_id') or ''): _clean(r.get('site_name')) for r in pens.to_dict(orient='records')} if not pens.empty else {}
    base_animals = animals.to_dict(orient='records') if not animals.empty else []
    move_df = moves.copy() if not moves.empty else pd.DataFrame()
    if not move_df.empty:
        if 'move_date' not in move_df.columns and 'move_datetime' in move_df.columns:
            move_df['move_date'] = move_df['move_datetime']
        move_df['move_date'] = pd.to_datetime(move_df.get('move_date'), errors='coerce').dt.date
        move_df = move_df.dropna(subset=['animal_id', 'move_date'])
        move_df = move_df[move_df['move_date'] <= asof_date].sort_values(['animal_id', 'move_date'])
    latest_move = {}
    if not move_df.empty:
        for r in move_df.groupby(move_df['animal_id'].astype(str), as_index=False).tail(1).to_dict(orient='records'):
            latest_move[str(r.get('animal_id') or '')] = dict(r)
    for row in base_animals:
        animal = _clean(row.get('animal_id'))
        if not animal:
            continue
        mv = latest_move.get(animal) or {}
        pen_id = _clean(mv.get('to_pen_id') or row.get('current_pen_id') or row.get('pen_id')) or None
        site_id = _clean(row.get('site_id') or '') or None
        farm_id = _clean(row.get('farm_id') or '') or None
        by_animal[animal] = {
            'animal_id': animal,
            'farm_id': farm_id,
            'site_id': site_id,
            'pen_id': pen_id,
            'pen_name': pen_name_map.get(str(pen_id or ''), ''),
            'site_name': site_name_map.get(str(site_id or ''), ''),
        }
    return by_animal, pen_name_map, site_name_map


def _load_animals(input_dir: Path) -> pd.DataFrame:
    df = _read_csv(input_dir / 'dm_animals.csv')
    if df.empty:
        return df
    for col in ('animal_id', 'farm_id', 'site_id', 'status'):
        if col not in df.columns:
            df[col] = ''
    return df


def _load_health_events(input_dir: Path) -> pd.DataFrame:
    df = _read_csv(input_dir / 'dm_health_events.csv')
    if df.empty:
        return df
    for col in ('animal_id', 'farm_id', 'lactation_id', 'event_id', 'event_date', 'event_type', 'condition_code', 'severity', 'notes'):
        if col not in df.columns:
            df[col] = ''
    return df


def _load_lactations(input_dir: Path) -> pd.DataFrame:
    df = _read_csv(input_dir / 'dm_lactations.csv')
    if df.empty:
        return df
    for col in ('animal_id', 'farm_id', 'lactation_id', 'calving_date', 'parity', 'lactation_status'):
        if col not in df.columns:
            df[col] = ''
    return df


def _event_text(row: Mapping[str, Any]) -> str:
    parts = [
        _clean(row.get('event_type')),
        _clean(row.get('condition_code')),
        _clean(row.get('notes')),
    ]
    return ' '.join([p.lower() for p in parts if p])


def _norm_severity(value: Any) -> str:
    raw = _clean(value).lower()
    if raw in {'high', 'critical'}:
        return 'high' if raw == 'high' else 'critical'
    if raw in {'medium', 'med'}:
        return 'medium'
    if raw in {'low'}:
        return 'low'
    return 'unknown'


def _priority_from_severity(severity: str, *, follow_up_due: bool = False) -> int:
    sev = _norm_severity(severity)
    if follow_up_due:
        return 1
    return {'critical': 1, 'high': 1, 'medium': 2, 'low': 3}.get(sev, 3)


def _confidence_from_inputs(*, severity: str, alert_confidence: Any = None, active_follow_up: bool = False) -> float:
    base = CONFIDENCE_BY_SEVERITY.get(_norm_severity(severity), 0.5)
    if active_follow_up:
        base = max(base, 0.85)
    try:
        if alert_confidence not in (None, ''):
            base = max(base, float(alert_confidence))
    except Exception:
        pass
    return round(min(0.99, max(0.3, base)), 3)


def _queue_due(queue_type: str, *, event_date: date | None, asof_date: date, calving_date: date | None = None, follow_up_due: date | None = None) -> date:
    if queue_type == 'fresh_cows' and calving_date is not None:
        return max(asof_date, calving_date + timedelta(days=1))
    if queue_type == 'retreatment' and follow_up_due is not None:
        return follow_up_due
    return event_date or asof_date


def _why(queue_type: str, facts: list[dict[str, Any]], *, severity: str, confidence: float) -> dict[str, Any]:
    return {
        'summary': f"{QUEUE_LABELS.get(queue_type, queue_type)} требует осмотра/triage.",
        'severity': severity,
        'confidence': confidence,
        'expected_effect': f"Своевременный осмотр и follow-up по очереди {QUEUE_LABELS.get(queue_type, queue_type).lower()}.",
        'facts_n': len(facts),
    }


def _what_to_do(queue_type: str) -> list[dict[str, Any]]:
    return [{'action': QUEUE_NEXT_ACTIONS.get(queue_type, 'Провести vet triage.'), 'expected_effect': f"Снизить риск пропуска follow-up по {QUEUE_LABELS.get(queue_type, queue_type).lower()}."}]


def _base_row(*, queue_type: str, animal_id: str, farm_id: str | None, site_id: str | None, pen_id: str | None, pen_name: str | None, title: str, due_at: str, severity: str, confidence: float, source_facts: list[dict[str, Any]], reason: str, expected_effect: str | None = None, related_alert: str | None = None, linked_health_event_id: str | None = None, linked_treatment_course_id: str | None = None) -> dict[str, Any]:
    return {
        'queue_type': queue_type,
        'queue_label': QUEUE_LABELS.get(queue_type, queue_type),
        'animal_id': animal_id,
        'farm_id': farm_id,
        'site_id': site_id,
        'pen_id': pen_id,
        'pen_name': pen_name,
        'title': title,
        'due_at': due_at,
        'severity': _norm_severity(severity),
        'severity_label': SEVERITY_LABELS.get(_norm_severity(severity), 'Не указана'),
        'priority': _priority_from_severity(severity, follow_up_due=(queue_type == 'retreatment')),
        'confidence': confidence,
        'reason': reason,
        'next_step_action': QUEUE_NEXT_ACTIONS.get(queue_type, 'Провести vet triage.'),
        'linked_source_facts': source_facts,
        'expected_effect': expected_effect or f"Требуется vet triage по очереди {QUEUE_LABELS.get(queue_type, queue_type).lower()}.",
        'related_alert': related_alert,
        'linked_health_event_id': linked_health_event_id,
        'linked_treatment_course_id': linked_treatment_course_id,
        'worklist_type': QUEUE_WORKLIST_TYPE.get(queue_type, 'vet'),
        'task_type': f'vet_queue.{queue_type}',
        'domain': 'health',
        'dedupe_key': f'vetqueue:{queue_type}:{animal_id}',
        'materialized': False,
        'existing_worklist_id': None,
    }


def _filter_common(rows: list[dict[str, Any]], *, animal_id: str | None, pen_id: str | None, site_id: str | None, farm_id: str | None, queue_types: Sequence[str] | None) -> list[dict[str, Any]]:
    wanted = {str(x) for x in (queue_types or []) if _clean(x)}
    out = []
    for row in rows:
        if animal_id and _clean(row.get('animal_id')) != _clean(animal_id):
            continue
        if pen_id and _clean(row.get('pen_id')) != _clean(pen_id):
            continue
        if site_id and _clean(row.get('site_id')) != _clean(site_id):
            continue
        if farm_id and _clean(row.get('farm_id')) != _clean(farm_id):
            continue
        if wanted and _clean(row.get('queue_type')) not in wanted:
            continue
        out.append(row)
    return out


def _attach_alerts(conn, *, tenant_id: str, rows: list[dict[str, Any]]) -> None:
    if conn is None or not rows:
        return
    animal_ids = sorted({_clean(r.get('animal_id')) for r in rows if _clean(r.get('animal_id'))})
    if not animal_ids:
        return
    ph = ','.join(['?'] * len(animal_ids))
    sql = f"""
        SELECT alert_id, object_id, alert_type, title, confidence, status
        FROM alerts_v2
        WHERE tenant_id=? AND object_type='animal' AND object_id IN ({ph}) AND status IN ('new','acknowledged')
        ORDER BY id DESC
    """
    fetched = conn.execute(sql, tuple([tenant_id] + animal_ids)).fetchall()
    by_animal: dict[str, list[dict[str, Any]]] = {}
    for row in fetched:
        d = dict(row)
        by_animal.setdefault(_clean(d.get('object_id')), []).append(d)
    for item in rows:
        matches = list(by_animal.get(_clean(item.get('animal_id')), []))
        if not matches:
            continue
        best = matches[0]
        item['related_alert'] = item.get('related_alert') or _clean(best.get('alert_id')) or None
        item['alert_ids'] = [_clean(x.get('alert_id')) for x in matches if _clean(x.get('alert_id'))]
        item['confidence'] = _confidence_from_inputs(severity=item.get('severity'), alert_confidence=best.get('confidence'), active_follow_up=(item.get('queue_type') == 'retreatment'))
        if _clean(best.get('title')):
            item['linked_source_facts'].append({'label': 'alert', 'text': _clean(best.get('title'))})


def _mark_materialized(conn, *, tenant_id: str, rows: list[dict[str, Any]]) -> None:
    if conn is None:
        return
    for row in rows:
        dk = _clean(row.get('dedupe_key'))
        if not dk:
            continue
        found = conn.execute(
            "SELECT task_id FROM tasks_v1 WHERE tenant_id=? AND dedupe_key=? AND status IN ('open','in_progress') ORDER BY id DESC LIMIT 1",
            (tenant_id, dk),
        ).fetchone()
        if found:
            row['materialized'] = True
            row['existing_worklist_id'] = str(dict(found).get('task_id') if not isinstance(found, tuple) else found[0])


def _disease_rows(*, events_df: pd.DataFrame, assn_map: Mapping[str, Mapping[str, Any]], asof_date: date) -> list[dict[str, Any]]:
    if events_df.empty:
        return []
    rows: list[dict[str, Any]] = []
    events_df = events_df.copy()
    events_df['event_date_parsed'] = pd.to_datetime(events_df['event_date'], errors='coerce')
    for queue_type, keywords in EVENT_KEYWORDS.items():
        mask = events_df.apply(lambda r: any(k in _event_text(r) for k in keywords), axis=1)
        sub = events_df[mask].copy()
        if sub.empty:
            continue
        sub = sub.sort_values(['animal_id', 'event_date_parsed'], ascending=[True, False])
        latest = sub.drop_duplicates(subset=['animal_id'], keep='first')
        for row in latest.to_dict(orient='records'):
            animal = _clean(row.get('animal_id'))
            assn = dict(assn_map.get(animal) or {})
            ev_date = _parse_date(row.get('event_date')) or asof_date
            sev = _norm_severity(row.get('severity'))
            facts = [
                {'label': QUEUE_FACT_LABELS.get(queue_type, 'health event'), 'text': f"{_clean(row.get('event_type') or row.get('condition_code'))} @ {ev_date.isoformat()}"},
            ]
            if _clean(row.get('notes')):
                facts.append({'label': 'notes', 'text': _clean(row.get('notes'))})
            rows.append(_base_row(
                queue_type=queue_type,
                animal_id=animal,
                farm_id=_clean(row.get('farm_id')) or _clean(assn.get('farm_id')) or None,
                site_id=_clean(assn.get('site_id')) or None,
                pen_id=_clean(assn.get('pen_id')) or None,
                pen_name=_clean(assn.get('pen_name')) or None,
                title=f"{QUEUE_LABELS.get(queue_type)}: осмотреть {animal}",
                due_at=_queue_due(queue_type, event_date=ev_date, asof_date=asof_date).isoformat(),
                severity=sev,
                confidence=_confidence_from_inputs(severity=sev),
                source_facts=facts,
                reason=f"Последнее событие {QUEUE_LABELS.get(queue_type).lower()}.",
                expected_effect=f"Приоритизированный осмотр по очереди {QUEUE_LABELS.get(queue_type).lower()}.",
                linked_health_event_id=_clean(row.get('event_id')) or None,
            ))
    return rows


def _fresh_cow_rows(*, lact_df: pd.DataFrame, animals_df: pd.DataFrame, assn_map: Mapping[str, Mapping[str, Any]], asof_date: date, fresh_days: int = 14) -> list[dict[str, Any]]:
    if lact_df.empty:
        return []
    df = lact_df.copy()
    df['calving_date_parsed'] = pd.to_datetime(df['calving_date'], errors='coerce')
    df = df.dropna(subset=['calving_date_parsed']).sort_values(['animal_id', 'calving_date_parsed'], ascending=[True, False]).drop_duplicates(subset=['animal_id'], keep='first')
    rows: list[dict[str, Any]] = []
    animal_status = { _clean(r.get('animal_id')): _clean(r.get('status')).lower() for r in animals_df.to_dict(orient='records')} if not animals_df.empty else {}
    for row in df.to_dict(orient='records'):
        animal = _clean(row.get('animal_id'))
        calving = _parse_date(row.get('calving_date'))
        if calving is None:
            continue
        days = (asof_date - calving).days
        if days < 0 or days > fresh_days:
            continue
        if animal_status.get(animal) in {'culled', 'dead'}:
            continue
        assn = dict(assn_map.get(animal) or {})
        sev = 'high' if days <= 7 else 'medium'
        facts = [{'label': 'fresh cow', 'text': f'Отёл {calving.isoformat()} · {days}d fresh'}]
        rows.append(_base_row(
            queue_type='fresh_cows',
            animal_id=animal,
            farm_id=_clean(row.get('farm_id')) or _clean(assn.get('farm_id')) or None,
            site_id=_clean(assn.get('site_id')) or None,
            pen_id=_clean(assn.get('pen_id')) or None,
            pen_name=_clean(assn.get('pen_name')) or None,
            title=f"Fresh cow: осмотреть {animal}",
            due_at=_queue_due('fresh_cows', event_date=None, asof_date=asof_date, calving_date=calving).isoformat(),
            severity=sev,
            confidence=_confidence_from_inputs(severity=sev),
            source_facts=facts,
            reason='Животное в fresh period после отёла.',
            expected_effect='Ранний post-calving контроль и быстрый follow-up по fresh cows.',
        ))
    return rows


def _retreatment_rows(*, treatment_snapshot: Mapping[str, Any], asof_date: date) -> list[dict[str, Any]]:
    items = list(treatment_snapshot.get('items') or [])
    by_animal: dict[str, dict[str, Any]] = {}
    for row in items:
        animal = _clean(row.get('animal_id'))
        if not animal:
            continue
        is_due = bool(row.get('follow_up_due_active'))
        if not is_due and _clean(row.get('course_status')) != 'active':
            continue
        current = by_animal.get(animal)
        rank = 0 if is_due else 1
        cur_rank = 9 if current is None else (0 if current.get('follow_up_due_active') else 1)
        due = _parse_date(row.get('follow_up_due_at')) or _parse_date(row.get('start_date')) or date.today()
        cur_due = _parse_date(current.get('follow_up_due_at')) if current else None
        if current is None or rank < cur_rank or (rank == cur_rank and (cur_due is None or due < cur_due)):
            by_animal[animal] = dict(row)
    rows: list[dict[str, Any]] = []
    for row in by_animal.values():
        sev = 'high' if bool(row.get('follow_up_due_active')) else 'medium'
        facts = [
            {'label': 'treatment', 'text': f"{_clean(row.get('drug_name') or row.get('treatment_type') or 'course')} · status={_clean(row.get('course_status')) or '—'}"},
        ]
        if _clean(row.get('withdrawal_end_date_effective')):
            facts.append({'label': 'withdrawal_until', 'text': _clean(row.get('withdrawal_end_date_effective'))})
        if _clean(row.get('follow_up_due_at')):
            facts.append({'label': 'follow_up_due', 'text': _clean(row.get('follow_up_due_at'))})
        rows.append(_base_row(
            queue_type='retreatment',
            animal_id=_clean(row.get('animal_id')),
            farm_id=_clean(row.get('farm_id')) or None,
            site_id=_clean(row.get('site_id')) or None,
            pen_id=_clean(row.get('pen_id')) or None,
            pen_name=_clean(row.get('pen_name')) or None,
            title=f"Retreatment / follow-up: осмотреть {_clean(row.get('animal_id'))}",
            due_at=_queue_due('retreatment', event_date=None, asof_date=asof_date, follow_up_due=_parse_date(row.get('follow_up_due_at')) or asof_date).isoformat(),
            severity=sev,
            confidence=_confidence_from_inputs(severity=sev, active_follow_up=True),
            source_facts=facts,
            reason='Активный treatment follow-up или повторный осмотр после курса.',
            expected_effect='Не пропустить follow-up и повторное решение по курсу лечения.',
            linked_treatment_course_id=_clean(row.get('course_id')) or None,
            related_alert=_clean(row.get('linked_alert_id')) or None,
        ))
    return rows


def _chronic_rows(*, events_df: pd.DataFrame, assn_map: Mapping[str, Mapping[str, Any]], asof_date: date) -> list[dict[str, Any]]:
    if events_df.empty:
        return []
    df = events_df.copy()
    df['event_date_parsed'] = pd.to_datetime(df['event_date'], errors='coerce')
    cutoff = pd.Timestamp(asof_date - timedelta(days=90))
    df = df[df['event_date_parsed'].notna() & (df['event_date_parsed'] >= cutoff)]
    if df.empty:
        return []
    rows: list[dict[str, Any]] = []
    for animal, grp in df.groupby(df['animal_id'].astype(str)):
        total = len(grp)
        if total < 3:
            continue
        latest = grp.sort_values('event_date_parsed', ascending=False).iloc[0].to_dict()
        assn = dict(assn_map.get(str(animal)) or {})
        top_type = str(grp.get('event_type', pd.Series(dtype=object)).astype(str).value_counts().idxmax()) if 'event_type' in grp.columns else 'health'
        sev = 'high' if total >= 4 else 'medium'
        facts = [
            {'label': 'chronic burden', 'text': f'{total} health events / 90d'},
            {'label': 'dominant_type', 'text': top_type or '—'},
        ]
        rows.append(_base_row(
            queue_type='chronic_review',
            animal_id=str(animal),
            farm_id=_clean(latest.get('farm_id')) or _clean(assn.get('farm_id')) or None,
            site_id=_clean(assn.get('site_id')) or None,
            pen_id=_clean(assn.get('pen_id')) or None,
            pen_name=_clean(assn.get('pen_name')) or None,
            title=f"Chronic review: пересмотреть {animal}",
            due_at=asof_date.isoformat(),
            severity=sev,
            confidence=_confidence_from_inputs(severity=sev),
            source_facts=facts,
            reason='Повторяющиеся health events за 90 дней.',
            expected_effect='Пересмотр хронического кейса и решение по protocol / culling / long-term plan.',
            linked_health_event_id=_clean(latest.get('event_id')) or None,
        ))
    return rows


def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda r: (int(r.get('priority') or 3), SEVERITY_RANK.get(_clean(r.get('severity')), 9), _clean(r.get('due_at')) or '9999-12-31', _clean(r.get('animal_id'))))


def build_vet_triage_snapshot(
    *,
    input_dir: Path,
    conn,
    tenant_id: str,
    asof_date: date,
    animal_id: str | None = None,
    pen_id: str | None = None,
    site_id: str | None = None,
    farm_id: str | None = None,
    queue_types: Sequence[str] | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    input_dir = Path(input_dir)
    assn_map, _, _ = _pen_assignment_maps(input_dir, asof_date=asof_date)
    animals_df = _load_animals(input_dir)
    health_df = _load_health_events(input_dir)
    lact_df = _load_lactations(input_dir)
    treatment_snapshot = build_treatment_journal_snapshot(
        input_dir=input_dir,
        conn=conn,
        tenant_id=tenant_id,
        asof_date=asof_date,
        animal_id=animal_id or None,
        pen_id=pen_id or None,
        site_id=site_id or None,
        farm_id=farm_id or None,
        status=None,
        limit=max(int(limit) * 2, 200),
    )

    rows = []
    rows.extend(_disease_rows(events_df=health_df, assn_map=assn_map, asof_date=asof_date))
    rows.extend(_fresh_cow_rows(lact_df=lact_df, animals_df=animals_df, assn_map=assn_map, asof_date=asof_date))
    rows.extend(_retreatment_rows(treatment_snapshot=treatment_snapshot, asof_date=asof_date))
    rows.extend(_chronic_rows(events_df=health_df, assn_map=assn_map, asof_date=asof_date))

    rows = _filter_common(rows, animal_id=animal_id, pen_id=pen_id, site_id=site_id, farm_id=farm_id, queue_types=queue_types)
    _attach_alerts(conn, tenant_id=tenant_id, rows=rows)
    _mark_materialized(conn, tenant_id=tenant_id, rows=rows)
    rows = _sort_rows(rows)[: max(1, int(limit))]

    summary = {
        'total': len(rows),
        'materialized_n': sum(1 for r in rows if bool(r.get('materialized'))),
        'high_priority_n': sum(1 for r in rows if int(r.get('priority') or 3) <= 1),
        'with_alert_n': sum(1 for r in rows if bool(r.get('related_alert'))),
        'by_queue': {},
        'by_severity': {},
    }
    for r in rows:
        qt = _clean(r.get('queue_type')) or '—'
        summary['by_queue'][qt] = summary['by_queue'].get(qt, 0) + 1
        sev = _clean(r.get('severity')) or 'unknown'
        summary['by_severity'][sev] = summary['by_severity'].get(sev, 0) + 1

    return {
        'asof_date': asof_date.isoformat(),
        'summary': summary,
        'items': rows,
        'treatment_summary': dict(treatment_snapshot.get('summary') or {}),
    }


def materialize_vet_triage_worklists_use_case(
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
    created: list[str] = []
    existing: list[str] = []
    for row in rows or []:
        dedupe_key = _clean(row.get('dedupe_key'))
        found = None
        if dedupe_key:
            found = conn.execute(
                "SELECT task_id FROM tasks_v1 WHERE tenant_id=? AND dedupe_key=? AND status IN ('open','in_progress') ORDER BY id DESC LIMIT 1",
                (tenant_id, dedupe_key),
            ).fetchone()
        active = str(dict(found).get('task_id') if found and not isinstance(found, tuple) else (found[0] if found else '')) or None
        if active:
            existing.append(str(active))
            continue
        wl = create_worklist_use_case(
            conn=conn,
            tenant_id=tenant_id,
            worklist_type=str(row.get('worklist_type') or 'vet'),
            user_id=int(user_id or 0),
            username=str(username or ''),
            role=str(role or ''),
            title=str(row.get('title') or 'Vet triage'),
            task_type=str(row.get('task_type') or 'vet_queue.follow_up'),
            domain='health',
            priority=int(row.get('priority') or 3),
            due_at=str(row.get('due_at') or ''),
            assignee_team='team-health',
            confidence=float(row.get('confidence') or 0.5),
            object_type='animal',
            object_id=str(row.get('animal_id') or ''),
            related_alert=_clean(row.get('related_alert')) or None,
            linked_source_facts=list(row.get('linked_source_facts') or []),
            why=_why(str(row.get('queue_type') or ''), list(row.get('linked_source_facts') or []), severity=str(row.get('severity') or ''), confidence=float(row.get('confidence') or 0.5)),
            what_to_do=_what_to_do(str(row.get('queue_type') or '')),
            data_version=data_version,
            dedupe_key=dedupe_key or None,
            request_id=request_id,
        )
        created.append(str(wl.get('worklist_id') or ''))
    return {'summary': {'created_n': len(created), 'existing_n': len(existing)}, 'created_worklist_ids': created, 'existing_worklist_ids': existing}


def batch_complete_vet_triage_worklists_use_case(
    *,
    conn,
    tenant_id: str,
    worklist_ids: Sequence[str],
    user_id: int,
    username: str,
    role: str,
    outcome_status: str,
    reason_code: str,
    comment: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    results = []
    for wid in [str(x) for x in worklist_ids or [] if _clean(x)]:
        res = record_completion_outcome_use_case(
            conn=conn,
            tenant_id=tenant_id,
            worklist_id=wid,
            user_id=int(user_id or 0),
            username=str(username or ''),
            role=str(role or ''),
            outcome_status=str(outcome_status),
            reason_code=str(reason_code),
            comment=(str(comment) if comment else None),
            auto_link_decision=True,
            auto_resolve_related_alert=False,
            request_id=request_id,
        )
        results.append({'worklist_id': wid, 'outcome': dict(res.get('outcome') or {})})
    return {'summary': {'completed_n': len(results)}, 'results': results}


def bulk_comment_vet_triage_animals_use_case(
    *,
    conn,
    tenant_id: str,
    animal_ids: Sequence[str],
    user_id: int,
    username: str,
    role: str,
    comment: str,
    data_version: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    created = []
    for animal_id in [str(x) for x in animal_ids or [] if _clean(x)]:
        res = create_animal_event_use_case(
            conn=conn,
            tenant_id=tenant_id,
            animal_id=animal_id,
            event_type='comment',
            event_ts=pd.Timestamp.utcnow().isoformat(),
            user_id=int(user_id or 0),
            username=str(username or ''),
            role=str(role or ''),
            comment=str(comment),
            data_version=data_version,
            request_id=request_id,
            extra_payload={'entry_mode': 'vet_triage_bulk_comment'},
        )
        created.append(str(res.get('event_id') or ''))
    return {'summary': {'created_n': len(created)}, 'event_ids': created}


__all__ = [
    'QUEUE_LABELS',
    'build_vet_triage_snapshot',
    'materialize_vet_triage_worklists_use_case',
    'batch_complete_vet_triage_worklists_use_case',
    'bulk_comment_vet_triage_animals_use_case',
]
