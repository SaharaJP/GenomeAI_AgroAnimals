from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd
import yaml

from core.health.treatment_journal import build_treatment_journal_snapshot
from genomeai.drilldown import compute_pen_assignments

RULES_PATH = Path('configs/health/health_episode_rules.yaml')
STATE_LABELS_DEFAULT = {
    'active': 'Активный',
    'monitoring': 'Под наблюдением',
    'resolved': 'Завершён',
    'blocked': 'Заблокирован',
}
SEVERITY_RANK = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3, 'unknown': 4, '': 4}
SEVERITY_LABELS = {'critical': 'Критическая', 'high': 'Высокая', 'medium': 'Средняя', 'low': 'Низкая', 'unknown': 'Не указана', '': 'Не указана'}


@dataclass(slots=True)
class HealthEpisodeError(ValueError):
    code: str
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return self.message


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


def load_health_episode_rules(path: Path | None = None) -> dict[str, Any]:
    cfg_path = Path(path or RULES_PATH)
    if not cfg_path.exists():
        return {
            'version': '1.0',
            'max_gap_days_same_family': 21,
            'acute_active_days': 14,
            'alert_link_window_days': 14,
            'decision_link_window_days': 21,
            'worklist_link_window_days': 21,
            'treatment_link_buffer_days': 7,
            'outcome_link_window_days': 21,
            'family_keywords': {},
            'family_labels': {'other': 'Прочий health episode'},
            'state_labels': dict(STATE_LABELS_DEFAULT),
        }
    with cfg_path.open('r', encoding='utf-8') as fh:
        cfg = yaml.safe_load(fh) or {}
    cfg.setdefault('version', '1.0')
    cfg.setdefault('max_gap_days_same_family', 21)
    cfg.setdefault('acute_active_days', 14)
    cfg.setdefault('alert_link_window_days', 14)
    cfg.setdefault('decision_link_window_days', 21)
    cfg.setdefault('worklist_link_window_days', 21)
    cfg.setdefault('treatment_link_buffer_days', 7)
    cfg.setdefault('outcome_link_window_days', 21)
    cfg.setdefault('family_keywords', {})
    cfg.setdefault('family_labels', {'other': 'Прочий health episode'})
    cfg.setdefault('state_labels', dict(STATE_LABELS_DEFAULT))
    return cfg


def _norm_severity(value: Any) -> str:
    raw = _clean(value).lower()
    if raw in {'critical', 'crit'}:
        return 'critical'
    if raw in {'high'}:
        return 'high'
    if raw in {'medium', 'med'}:
        return 'medium'
    if raw in {'low'}:
        return 'low'
    return 'unknown'


def _family_from_text(text: str, *, family_keywords: Mapping[str, Sequence[str]]) -> str:
    low = str(text or '').lower()
    if not low:
        return 'other'
    for family, kws in dict(family_keywords or {}).items():
        for kw in list(kws or []):
            if str(kw or '').lower() and str(kw).lower() in low:
                return str(family)
    return 'other'


def normalize_health_family(*, event_type: Any = None, condition_code: Any = None, notes: Any = None, treatment_type: Any = None, diagnosis_label: Any = None, family_keywords: Mapping[str, Sequence[str]] | None = None) -> str:
    family_keywords = dict(family_keywords or {})
    direct = _clean(event_type).lower() or _clean(condition_code).lower() or _clean(treatment_type).lower()
    if direct in family_keywords:
        return direct
    text = ' '.join([_clean(event_type), _clean(condition_code), _clean(notes), _clean(treatment_type), _clean(diagnosis_label)]).strip()
    return _family_from_text(text, family_keywords=family_keywords)


def _pen_assignment_map(input_dir: Path, *, asof_date: date) -> dict[str, dict[str, Any]]:
    try:
        assn = compute_pen_assignments(input_dir=input_dir, asof_date=asof_date)
        if assn is not None and not assn.empty:
            return {str(r.get('animal_id') or ''): dict(r) for r in assn.to_dict(orient='records') if str(r.get('animal_id') or '').strip()}
    except Exception:
        pass
    animals = _read_csv(input_dir / 'dm_animals.csv')
    if animals.empty:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in animals.to_dict(orient='records'):
        aid = _clean(row.get('animal_id'))
        if not aid:
            continue
        out[aid] = {
            'animal_id': aid,
            'farm_id': _clean(row.get('farm_id')),
            'site_id': _clean(row.get('site_id')),
            'pen_id': _clean(row.get('current_pen_id') or row.get('pen_id')),
            'pen_name': _clean(row.get('current_pen_name') or row.get('pen_name')),
        }
    return out


def _load_health_events(input_dir: Path) -> pd.DataFrame:
    df = _read_csv(input_dir / 'dm_health_events.csv')
    if df.empty:
        return df
    for col in ('tenant_id', 'event_id', 'animal_id', 'farm_id', 'lactation_id', 'event_date', 'event_type', 'condition_code', 'severity', 'notes'):
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


def _load_animals(input_dir: Path) -> pd.DataFrame:
    df = _read_csv(input_dir / 'dm_animals.csv')
    if df.empty:
        return df
    for col in ('animal_id', 'farm_id', 'site_id', 'status'):
        if col not in df.columns:
            df[col] = ''
    return df


def _load_alerts(conn, *, tenant_id: str, animal_ids: Sequence[str]) -> list[dict[str, Any]]:
    if conn is None or not animal_ids:
        return []
    ph = ','.join(['?'] * len(animal_ids))
    sql = f"""
        SELECT alert_id, object_id, title, alert_type, cause, confidence, status, created_at
        FROM alerts_v2
        WHERE tenant_id=? AND object_type='animal' AND object_id IN ({ph})
        ORDER BY created_at DESC, id DESC
    """
    rows = conn.execute(sql, tuple([tenant_id] + list(animal_ids))).fetchall()
    return [dict(r) for r in rows if r]


def _load_decisions(conn, *, tenant_id: str, animal_ids: Sequence[str]) -> list[dict[str, Any]]:
    if conn is None or not animal_ids:
        return []
    ph = ','.join(['?'] * len(animal_ids))
    sql = f"""
        SELECT decision_id, object_id, object_type, related_alert, action, reason, comment, created_at, metadata_json
        FROM decision_log_v2
        WHERE tenant_id=? AND object_type='animal' AND object_id IN ({ph})
        ORDER BY created_at DESC, id DESC
    """
    rows = conn.execute(sql, tuple([tenant_id] + list(animal_ids))).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        try:
            d['metadata'] = json.loads(d.get('metadata_json') or '{}')
        except Exception:
            d['metadata'] = {}
        d.pop('metadata_json', None)
        out.append(d)
    return out


def _load_worklists(conn, *, tenant_id: str, animal_ids: Sequence[str]) -> list[dict[str, Any]]:
    if conn is None or not animal_ids:
        return []
    ph = ','.join(['?'] * len(animal_ids))
    sql = f"""
        SELECT task_id, object_id, object_type, related_alert, worklist_type, status, title, due_at, created_at, why_json, what_to_do_json
        FROM tasks_v1
        WHERE tenant_id=? AND object_type='animal' AND object_id IN ({ph})
        ORDER BY created_at DESC, id DESC
    """
    rows = conn.execute(sql, tuple([tenant_id] + list(animal_ids))).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        for key, default in (('why_json', {}), ('what_to_do_json', [])):
            try:
                d[key[:-5]] = json.loads(d.get(key) or json.dumps(default, ensure_ascii=False))
            except Exception:
                d[key[:-5]] = default
            d.pop(key, None)
        out.append(d)
    return out


def _load_outcomes(conn, *, tenant_id: str, animal_ids: Sequence[str]) -> list[dict[str, Any]]:
    if conn is None or not animal_ids:
        return []
    ph = ','.join(['?'] * len(animal_ids))
    sql = f"""
        SELECT outcome_id, object_id, object_type, task_id, worklist_id, related_alert, outcome_status, reason_code, comment, created_at
        FROM completion_outcomes_v1
        WHERE tenant_id=? AND object_type='animal' AND object_id IN ({ph})
        ORDER BY created_at DESC, id DESC
    """
    rows = conn.execute(sql, tuple([tenant_id] + list(animal_ids))).fetchall()
    return [dict(r) for r in rows if r]


def _build_anchor_records(*, health_events_df: pd.DataFrame, treatments: Sequence[Mapping[str, Any]], animal_ids: Sequence[str], family_keywords: Mapping[str, Sequence[str]]) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    if health_events_df is not None and not health_events_df.empty:
        for row in health_events_df.to_dict(orient='records'):
            animal_id = _clean(row.get('animal_id'))
            if animal_ids and animal_id not in set(animal_ids):
                continue
            event_date = _parse_date(row.get('event_date'))
            if event_date is None:
                continue
            family = normalize_health_family(
                event_type=row.get('event_type'),
                condition_code=row.get('condition_code'),
                notes=row.get('notes'),
                family_keywords=family_keywords,
            )
            anchors.append({
                'anchor_kind': 'health_event',
                'anchor_id': _clean(row.get('event_id')) or f"he:{animal_id}:{event_date.isoformat()}",
                'animal_id': animal_id,
                'anchor_date': event_date,
                'family': family,
                'severity': _norm_severity(row.get('severity')),
                'title': _clean(row.get('event_type') or row.get('condition_code')) or family,
                'notes': _clean(row.get('notes')),
                'linked_health_event_id': _clean(row.get('event_id')),
                'linked_treatment_course_id': '',
            })
    for row in list(treatments or []):
        animal_id = _clean(row.get('animal_id'))
        if animal_ids and animal_id not in set(animal_ids):
            continue
        start_date = _parse_date(row.get('start_date')) or _parse_date(row.get('created_at'))
        if start_date is None:
            continue
        family = normalize_health_family(
            event_type=row.get('treatment_type'),
            diagnosis_label=row.get('diagnosis_label'),
            treatment_type=row.get('treatment_type'),
            family_keywords=family_keywords,
        )
        anchors.append({
            'anchor_kind': 'treatment',
            'anchor_id': _clean(row.get('course_id')) or f"tr:{animal_id}:{start_date.isoformat()}",
            'animal_id': animal_id,
            'anchor_date': start_date,
            'family': family,
            'severity': 'medium' if _clean(row.get('course_status')) == 'active' else 'low',
            'title': _clean(row.get('diagnosis_label') or row.get('treatment_type') or row.get('drug_name')) or family,
            'notes': _clean(row.get('drug_name')),
            'linked_health_event_id': _clean(row.get('linked_health_event_id')),
            'linked_treatment_course_id': _clean(row.get('course_id')),
        })
    anchors.sort(key=lambda x: (x['animal_id'], x['family'], x['anchor_date'], x['anchor_kind'], x['anchor_id']))
    return anchors


def _make_episode_id(*, animal_id: str, family: str, start_date: date, seq: int) -> str:
    return f"hep:{animal_id}:{family}:{start_date.isoformat()}:{seq}"


def _group_anchors_to_episodes(anchors: Sequence[Mapping[str, Any]], *, max_gap_days: int) -> list[dict[str, Any]]:
    grouped: list[dict[str, Any]] = []
    seq_map: dict[tuple[str, str], int] = {}
    current: dict[str, Any] | None = None
    for anchor in list(anchors or []):
        animal_id = _clean(anchor.get('animal_id'))
        family = _clean(anchor.get('family')) or 'other'
        anchor_date = anchor.get('anchor_date')
        if not isinstance(anchor_date, date):
            continue
        if current is None or current['animal_id'] != animal_id or current['family'] != family or (anchor_date - current['last_anchor_date']).days > max_gap_days:
            key = (animal_id, family)
            seq_map[key] = int(seq_map.get(key) or 0) + 1
            current = {
                'episode_id': _make_episode_id(animal_id=animal_id, family=family, start_date=anchor_date, seq=seq_map[key]),
                'animal_id': animal_id,
                'family': family,
                'start_date': anchor_date,
                'last_anchor_date': anchor_date,
                'anchors': [dict(anchor)],
            }
            grouped.append(current)
        else:
            current['last_anchor_date'] = anchor_date
            current['anchors'].append(dict(anchor))
    return grouped


def _matches_family(text: str, family: str, family_keywords: Mapping[str, Sequence[str]]) -> bool:
    fam = _clean(family)
    if not fam or fam == 'other':
        return True
    low = str(text or '').lower()
    if fam in low:
        return True
    for kw in list(dict(family_keywords or {}).get(fam) or []):
        if str(kw or '').lower() and str(kw).lower() in low:
            return True
    return False


def _severity_from_items(items: Sequence[Mapping[str, Any]]) -> str:
    if not items:
        return 'unknown'
    vals = [_norm_severity(x.get('severity')) for x in items]
    vals.sort(key=lambda x: SEVERITY_RANK.get(x, 9))
    return vals[0] if vals else 'unknown'


def _episode_state(*, asof_date: date, episode: Mapping[str, Any], treatments: Sequence[Mapping[str, Any]], alerts: Sequence[Mapping[str, Any]], worklists: Sequence[Mapping[str, Any]], outcomes: Sequence[Mapping[str, Any]], rules: Mapping[str, Any]) -> tuple[str, str, str | None]:
    linked_treatment_ids = set(episode.get('linked_treatment_course_ids') or [])
    linked_alert_ids = set(episode.get('linked_alert_ids') or [])
    linked_worklist_ids = set(episode.get('linked_worklist_ids') or [])
    linked_outcome_ids = set(episode.get('linked_outcome_ids') or [])
    acute_active_days = int(rules.get('acute_active_days') or 14)
    last_event_date = episode.get('last_event_date')
    if linked_treatment_ids:
        active_treat = [t for t in treatments if _clean(t.get('course_id')) in linked_treatment_ids and _clean(t.get('course_status')) in {'planned', 'active'}]
        if active_treat:
            return 'active', 'Есть активный treatment course.', None
    if linked_alert_ids:
        open_alerts = [a for a in alerts if _clean(a.get('alert_id')) in linked_alert_ids and _clean(a.get('status')) in {'new', 'acknowledged'}]
        if open_alerts:
            return 'blocked', 'Есть открытый alert, требующий triage/решения.', None
    if linked_worklist_ids:
        open_wl = [w for w in worklists if _clean(w.get('task_id')) in linked_worklist_ids and _clean(w.get('status')) in {'open', 'in_progress'}]
        if open_wl:
            due = sorted([_clean(w.get('due_at')) for w in open_wl if _clean(w.get('due_at'))])
            return 'monitoring', 'Есть открытый follow-up/worklist по эпизоду.', (due[0] if due else None)
    if linked_outcome_ids or outcomes:
        latest = sorted(outcomes, key=lambda x: _clean(x.get('created_at')), reverse=True)
        if latest:
            st = _clean(latest[0].get('outcome_status'))
            if st in {'done', 'cancelled', 'no_effect'}:
                return 'resolved', f'Есть formal outcome: {st}.', None
    if isinstance(last_event_date, date) and (asof_date - last_event_date).days <= acute_active_days:
        return 'active', f'Последнее событие эпизода было {last_event_date.isoformat()}, эпизод ещё в active window.', None
    return 'monitoring', 'Эпизод без активного лечения, но история ещё релевантна для follow-up.', None


def build_health_episode_snapshot(*, input_dir: Path, conn, tenant_id: str, asof_date: date, animal_id: str | None = None, pen_id: str | None = None, site_id: str | None = None, farm_id: str | None = None, family: str | None = None, state: str | None = None, limit: int = 200, rules_path: Path | None = None) -> dict[str, Any]:
    input_dir = Path(input_dir)
    rules = load_health_episode_rules(rules_path)
    family_keywords = dict(rules.get('family_keywords') or {})
    family_labels = dict(rules.get('family_labels') or {})
    state_labels = dict(STATE_LABELS_DEFAULT | dict(rules.get('state_labels') or {}))
    animals = _load_animals(input_dir)
    lact = _load_lactations(input_dir)
    health = _load_health_events(input_dir)
    assn_map = _pen_assignment_map(input_dir, asof_date=asof_date)

    animal_ids: list[str]
    if animal_id:
        animal_ids = [str(animal_id)]
    else:
        animal_ids = sorted({str(a) for a in list(health.get('animal_id', pd.Series(dtype=object)).dropna().astype(str).unique())} | {str(a) for a in list(animals.get('animal_id', pd.Series(dtype=object)).dropna().astype(str).unique())})
    if pen_id:
        allowed = {aid for aid, row in assn_map.items() if _clean(row.get('pen_id')) == str(pen_id)}
        animal_ids = [aid for aid in animal_ids if aid in allowed]
    if site_id:
        allowed = {aid for aid, row in assn_map.items() if _clean(row.get('site_id')) == str(site_id)}
        animal_ids = [aid for aid in animal_ids if aid in allowed]
    if farm_id:
        allowed = {aid for aid, row in assn_map.items() if _clean(row.get('farm_id')) == str(farm_id)}
        animal_ids = [aid for aid in animal_ids if aid in allowed]
    health = health[health.get('animal_id', pd.Series(dtype=object)).astype(str).isin(animal_ids)].copy() if not health.empty else pd.DataFrame()

    treatment_snapshot = build_treatment_journal_snapshot(
        input_dir=input_dir,
        conn=conn,
        tenant_id=str(tenant_id),
        asof_date=asof_date,
        animal_id=animal_id or None,
        pen_id=pen_id or None,
        site_id=site_id or None,
        farm_id=farm_id or None,
        limit=max(300, int(limit) * 5),
    )
    treatments = list(treatment_snapshot.get('items') or [])
    treatments = [t for t in treatments if _clean(t.get('animal_id')) in set(animal_ids)]

    anchors = _build_anchor_records(health_events_df=health, treatments=treatments, animal_ids=animal_ids, family_keywords=family_keywords)
    if family:
        anchors = [a for a in anchors if _clean(a.get('family')) == str(family)]
    grouped = _group_anchors_to_episodes(anchors, max_gap_days=int(rules.get('max_gap_days_same_family') or 21))

    alerts = _load_alerts(conn, tenant_id=str(tenant_id), animal_ids=animal_ids)
    decisions = _load_decisions(conn, tenant_id=str(tenant_id), animal_ids=animal_ids)
    worklists = _load_worklists(conn, tenant_id=str(tenant_id), animal_ids=animal_ids)
    outcomes = _load_outcomes(conn, tenant_id=str(tenant_id), animal_ids=animal_ids)

    out: list[dict[str, Any]] = []
    for grp in grouped:
        aid = _clean(grp.get('animal_id'))
        fam = _clean(grp.get('family')) or 'other'
        if family and fam != str(family):
            continue
        assn = dict(assn_map.get(aid) or {})
        family_label = family_labels.get(fam, fam or 'other')
        start_date = grp.get('start_date')
        last_event_date = grp.get('last_anchor_date')
        linked_health_event_ids = [a.get('linked_health_event_id') for a in grp.get('anchors') or [] if _clean(a.get('linked_health_event_id'))]
        linked_treatment_ids = [a.get('linked_treatment_course_id') for a in grp.get('anchors') or [] if _clean(a.get('linked_treatment_course_id'))]
        start = start_date if isinstance(start_date, date) else asof_date
        end_bound = asof_date + timedelta(days=int(rules.get('treatment_link_buffer_days') or 7))
        treatment_buf = int(rules.get('treatment_link_buffer_days') or 7)
        family_treat = []
        for t in treatments:
            if _clean(t.get('animal_id')) != aid:
                continue
            t_family = normalize_health_family(
                treatment_type=t.get('treatment_type'),
                diagnosis_label=t.get('diagnosis_label'),
                family_keywords=family_keywords,
            )
            t_start = _parse_date(t.get('start_date')) or _parse_date(t.get('created_at'))
            if _clean(t.get('linked_health_event_id')) in set(linked_health_event_ids):
                family_treat.append(t)
                continue
            if t_family == fam and t_start and start - timedelta(days=treatment_buf) <= t_start <= end_bound:
                family_treat.append(t)
        linked_treatment_ids = sorted(set(linked_treatment_ids) | {_clean(x.get('course_id')) for x in family_treat if _clean(x.get('course_id'))})

        alert_window_days = int(rules.get('alert_link_window_days') or 14)
        family_alerts = []
        for a in alerts:
            if _clean(a.get('object_id')) != aid:
                continue
            created = _parse_date(a.get('created_at'))
            text = ' '.join([_clean(a.get('alert_type')), _clean(a.get('title')), _clean(a.get('cause'))])
            if created and start - timedelta(days=alert_window_days) <= created <= asof_date and _matches_family(text, fam, family_keywords):
                family_alerts.append(a)
        linked_alert_ids = sorted({_clean(a.get('alert_id')) for a in family_alerts if _clean(a.get('alert_id'))})

        wl_window_days = int(rules.get('worklist_link_window_days') or 21)
        family_worklists = []
        for w in worklists:
            if _clean(w.get('object_id')) != aid:
                continue
            created = _parse_date(w.get('created_at'))
            why_txt = json.dumps(w.get('why') or {}, ensure_ascii=False) + ' ' + json.dumps(w.get('what_to_do') or [], ensure_ascii=False) + ' ' + _clean(w.get('title'))
            if _clean(w.get('related_alert')) in set(linked_alert_ids):
                family_worklists.append(w)
                continue
            if created and start - timedelta(days=wl_window_days) <= created <= asof_date and (_clean(w.get('worklist_type')) in {'vet', 'health_follow_up'} or _matches_family(why_txt, fam, family_keywords)):
                family_worklists.append(w)
        linked_worklist_ids = sorted({_clean(w.get('task_id')) for w in family_worklists if _clean(w.get('task_id'))})

        dec_window_days = int(rules.get('decision_link_window_days') or 21)
        family_decisions = []
        for d in decisions:
            if _clean(d.get('object_id')) != aid:
                continue
            created = _parse_date(d.get('created_at'))
            txt = ' '.join([_clean(d.get('action')), _clean(d.get('reason')), _clean(d.get('comment')), json.dumps(d.get('metadata') or {}, ensure_ascii=False)])
            if _clean(d.get('related_alert')) in set(linked_alert_ids):
                family_decisions.append(d)
                continue
            if created and start - timedelta(days=dec_window_days) <= created <= asof_date and _matches_family(txt, fam, family_keywords):
                family_decisions.append(d)
        linked_decision_ids = sorted({_clean(d.get('decision_id')) for d in family_decisions if _clean(d.get('decision_id'))})

        out_window_days = int(rules.get('outcome_link_window_days') or 21)
        family_outcomes = []
        for o in outcomes:
            if _clean(o.get('object_id')) != aid:
                continue
            created = _parse_date(o.get('created_at'))
            if _clean(o.get('worklist_id')) in set(linked_worklist_ids):
                family_outcomes.append(o)
                continue
            if created and start - timedelta(days=out_window_days) <= created <= asof_date:
                family_outcomes.append(o)
        linked_outcome_ids = sorted({_clean(o.get('outcome_id')) for o in family_outcomes if _clean(o.get('outcome_id'))})

        sev_items = [{'severity': a.get('severity')} for a in grp.get('anchors') or []]
        for alert in family_alerts:
            sev_items.append({'severity': 'high' if _clean(alert.get('status')) in {'new', 'acknowledged'} else 'medium'})
        severity = _severity_from_items(sev_items)
        state_code, state_reason, due_at = _episode_state(asof_date=asof_date, episode={
            'linked_treatment_course_ids': linked_treatment_ids,
            'linked_alert_ids': linked_alert_ids,
            'linked_worklist_ids': linked_worklist_ids,
            'linked_outcome_ids': linked_outcome_ids,
            'last_event_date': last_event_date,
        }, treatments=family_treat, alerts=family_alerts, worklists=family_worklists, outcomes=family_outcomes, rules=rules)
        if state and state_code != str(state):
            continue

        timeline: list[dict[str, Any]] = []
        for a in grp.get('anchors') or []:
            timeline.append({'ts': a.get('anchor_date').isoformat() if isinstance(a.get('anchor_date'), date) else '', 'kind': a.get('anchor_kind'), 'label': a.get('title') or a.get('family'), 'status': a.get('severity') or '—', 'ref_id': a.get('anchor_id')})
        for t in family_treat:
            timeline.append({'ts': _clean(t.get('start_date') or t.get('created_at')), 'kind': 'treatment', 'label': _clean(t.get('drug_name') or t.get('treatment_type') or t.get('diagnosis_label')) or 'treatment', 'status': _clean(t.get('course_status')) or '—', 'ref_id': _clean(t.get('course_id'))})
        for a in family_alerts:
            timeline.append({'ts': _clean(a.get('created_at')), 'kind': 'alert', 'label': _clean(a.get('title') or a.get('alert_type')) or 'alert', 'status': _clean(a.get('status')) or '—', 'ref_id': _clean(a.get('alert_id'))})
        for w in family_worklists:
            timeline.append({
                'ts': _clean(w.get('created_at')),
                'kind': 'worklist',
                'label': _clean(w.get('title')) or _clean(w.get('worklist_type')) or 'worklist',
                'status': _clean(w.get('status')) or _clean(w.get('due_at')) or '—',
                'ref_id': _clean(w.get('task_id')),
            })
        for d in family_decisions:
            timeline.append({'ts': _clean(d.get('created_at')), 'kind': 'decision', 'label': _clean(d.get('action')) or 'decision', 'status': _clean(d.get('reason')) or '—', 'ref_id': _clean(d.get('decision_id'))})
        for o in family_outcomes:
            timeline.append({'ts': _clean(o.get('created_at')), 'kind': 'outcome', 'label': _clean(o.get('outcome_status')) or 'outcome', 'status': _clean(o.get('reason_code')) or '—', 'ref_id': _clean(o.get('outcome_id'))})
        def _timeline_sort_key(item: Mapping[str, Any]) -> tuple[int, str, str]:
            raw_ts = _clean(item.get('ts'))
            ts = pd.to_datetime(raw_ts, errors='coerce', utc=True)
            if pd.isna(ts):
                return (pd.Timestamp.max.value, _clean(item.get('kind')), _clean(item.get('ref_id')))
            return (int(ts.value), _clean(item.get('kind')), _clean(item.get('ref_id')))
        timeline.sort(key=_timeline_sort_key)

        links_explanation = []
        if linked_health_event_ids:
            links_explanation.append('health events объединены по animal + family')
        if family_treat:
            links_explanation.append('treatments связаны по reason_event_id или окну around episode')
        if family_alerts:
            links_explanation.append('alerts связаны по animal + family keywords + time window')
        if family_worklists:
            links_explanation.append('worklists связаны по animal + health/vet type или related alert')
        if family_decisions:
            links_explanation.append('decisions связаны по animal + alert/time window')
        if family_outcomes:
            links_explanation.append('outcomes связаны по worklist или object/time window')

        latest_outcome_status = _clean(family_outcomes[0].get('outcome_status')) if family_outcomes else ''
        latest_outcome_reason = _clean(family_outcomes[0].get('reason_code')) if family_outcomes else ''
        out.append({
            'episode_id': grp.get('episode_id'),
            'animal_id': aid,
            'farm_id': _clean(assn.get('farm_id')),
            'site_id': _clean(assn.get('site_id')),
            'pen_id': _clean(assn.get('pen_id')),
            'pen_name': _clean(assn.get('pen_name')),
            'family': fam,
            'family_label': family_label,
            'title': f"{family_label}: {aid}",
            'state': state_code,
            'state_label': state_labels.get(state_code, state_code or '—'),
            'state_reason': state_reason,
            'severity': severity,
            'severity_label': SEVERITY_LABELS.get(severity, severity or '—'),
            'start_date': start.isoformat() if isinstance(start, date) else '',
            'last_event_date': last_event_date.isoformat() if isinstance(last_event_date, date) else '',
            'end_date': '',
            'due_at': due_at or '',
            'latest_outcome_status': latest_outcome_status,
            'latest_outcome_reason': latest_outcome_reason,
            'linked_health_event_ids': linked_health_event_ids,
            'linked_treatment_course_ids': linked_treatment_ids,
            'linked_alert_ids': linked_alert_ids,
            'linked_decision_ids': linked_decision_ids,
            'linked_worklist_ids': linked_worklist_ids,
            'linked_outcome_ids': linked_outcome_ids,
            'timeline': timeline,
            'timeline_n': len(timeline),
            'linking_explanation': links_explanation,
            'source_versions': {'rules_version': _clean(rules.get('version')) or '1.0'},
        })
    out.sort(key=lambda x: (_clean(x.get('state')), _clean(x.get('due_at') or '9999-12-31'), _clean(x.get('start_date') or '9999-12-31'), _clean(x.get('animal_id'))))
    out = out[: int(limit)]
    summary = {
        'episodes_n': len(out),
        'active_n': sum(1 for x in out if _clean(x.get('state')) == 'active'),
        'monitoring_n': sum(1 for x in out if _clean(x.get('state')) == 'monitoring'),
        'resolved_n': sum(1 for x in out if _clean(x.get('state')) == 'resolved'),
        'blocked_n': sum(1 for x in out if _clean(x.get('state')) == 'blocked'),
        'by_family': {family_labels.get(k, k): v for k, v in pd.Series([_clean(x.get('family')) for x in out]).value_counts().to_dict().items()},
        'rules_version': _clean(rules.get('version')) or '1.0',
    }
    return {
        'asof_date': asof_date.isoformat(),
        'rules': rules,
        'summary': summary,
        'episodes': out,
    }


def get_health_episode(snapshot: Mapping[str, Any], episode_id: str) -> dict[str, Any] | None:
    for item in list(snapshot.get('episodes') or []):
        if _clean(item.get('episode_id')) == str(episode_id):
            return dict(item)
    return None
