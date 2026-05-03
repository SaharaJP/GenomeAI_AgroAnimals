from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from core.reproduction.state_machine import DEFAULT_REPRO_CONFIG, build_reproduction_states_table
from core.reproduction.worklists import build_reproduction_worklists_snapshot
from genomeai.drilldown import compute_pen_assignments


DEFAULT_REPRO_COCKPIT_CONFIG: dict[str, Any] = {
    **DEFAULT_REPRO_CONFIG,
    'lookback_days': 60,
    'pregnancy_rate_window_days': 21,
    'repeat_breeder_services': 3,
    'max_breakdown_rows': 50,
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


def _parse_ts(value: Any) -> pd.Timestamp | pd.NaT:
    try:
        ts = pd.to_datetime(value, errors='coerce', utc=True)
        if pd.isna(ts):
            return pd.NaT
        return ts.tz_localize(None)
    except Exception:
        return pd.NaT


def _normalize_event_type(value: Any) -> str:
    raw = _clean(value).lower()
    if raw in {'ai', 'service', 'insemin', 'insemination'}:
        return 'insemination'
    if raw in {'heat', 'estrus'}:
        return 'heat'
    if raw in {'preg_check', 'pregnancy_check', 'preg check', 'diag', 'diagnosis'}:
        return 'preg_check'
    if raw in {'calving', 'freshening', 'fresh'}:
        return 'calving'
    if raw in {'dry_off', 'dryoff', 'dry'}:
        return 'dry_off'
    return raw


def _normalize_result(value: Any) -> str:
    raw = _clean(value).lower()
    if raw in {'pregnant', 'confirmed', 'positive', 'yes', 'preg', 'pos', 'true'}:
        return 'pregnant'
    if raw in {'open', 'not_pregnant', 'negative', 'no', 'neg', 'false'}:
        return 'open'
    return raw


def _current_assignment_map(input_dir: Path, *, asof_date: date) -> dict[str, dict[str, Any]]:
    assn = compute_pen_assignments(input_dir=input_dir, asof_date=asof_date)
    if assn is None or assn.empty:
        return {}
    return {str(r.get('animal_id') or ''): dict(r) for r in assn.to_dict(orient='records') if str(r.get('animal_id') or '').strip()}



def _build_service_ledger(
    *,
    animals_df: pd.DataFrame,
    lactations_df: pd.DataFrame,
    repro_events_df: pd.DataFrame,
    assignments: Mapping[str, Mapping[str, Any]],
    asof_date: date,
) -> pd.DataFrame:
    animals = animals_df.copy() if animals_df is not None else pd.DataFrame()
    lact = lactations_df.copy() if lactations_df is not None else pd.DataFrame()
    repro = repro_events_df.copy() if repro_events_df is not None else pd.DataFrame()
    if animals.empty or repro.empty:
        return pd.DataFrame()

    if 'animal_id' not in animals.columns or 'animal_id' not in repro.columns:
        return pd.DataFrame()

    repro['animal_id'] = repro['animal_id'].astype(str)
    repro['event_type_norm'] = repro.get('event_type', pd.Series(dtype=object)).map(_normalize_event_type)
    repro['result_norm'] = repro.get('result', pd.Series(dtype=object)).map(_normalize_result)
    repro['event_ts'] = repro.get('event_ts', repro.get('event_date')).map(_parse_ts)
    repro = repro[repro['event_ts'].notna()].copy()
    repro = repro[repro['event_ts'].dt.date <= asof_date].copy()

    if not lact.empty:
        lact['animal_id'] = lact.get('animal_id', pd.Series(dtype=object)).astype(str)
        lact['calving_ts'] = lact.get('calving_date', pd.Series(dtype=object)).map(_parse_ts)
        lact = lact[lact['calving_ts'].notna()].copy()
        lact = lact[lact['calving_ts'].dt.date <= asof_date].copy()

    rows: list[dict[str, Any]] = []
    animal_ids = sorted(animals['animal_id'].dropna().astype(str).unique().tolist())
    for animal_id in animal_ids:
        ev = repro[repro['animal_id'] == str(animal_id)].sort_values('event_ts').copy()
        if ev.empty:
            continue
        animal_lact = lact[lact.get('animal_id', pd.Series(dtype=object)).astype(str) == str(animal_id)] if not lact.empty else pd.DataFrame()
        last_calving_ts = animal_lact['calving_ts'].max() if not animal_lact.empty else pd.NaT
        if pd.notna(last_calving_ts):
            ev = ev[ev['event_ts'] >= last_calving_ts].copy()
        if ev.empty:
            continue
        insems = ev[ev['event_type_norm'] == 'insemination'].copy()
        if insems.empty:
            continue
        preg_checks = ev[ev['event_type_norm'] == 'preg_check'].copy()
        heat_events = ev[ev['event_type_norm'] == 'heat'].copy()
        assignment = dict(assignments.get(str(animal_id)) or {})
        for idx, (_, srv) in enumerate(insems.iterrows()):
            service_ts = srv['event_ts']
            next_service_ts = insems.iloc[idx + 1]['event_ts'] if idx + 1 < len(insems) else pd.NaT
            checks = preg_checks[preg_checks['event_ts'] >= service_ts].copy()
            if pd.notna(next_service_ts):
                checks = checks[checks['event_ts'] < next_service_ts].copy()
            checks = checks.sort_values('event_ts')
            first_check = dict(checks.iloc[0]) if not checks.empty else {}
            outcome = _clean(first_check.get('result_norm'))
            conceived = True if outcome == 'pregnant' else False if outcome == 'open' else None
            heat_before = heat_events[heat_events['event_ts'] <= service_ts].copy()
            heat_before = heat_before.sort_values('event_ts')
            last_heat = dict(heat_before.iloc[-1]) if not heat_before.empty else {}
            rows.append(
                {
                    'animal_id': str(animal_id),
                    'service_no': int(idx + 1),
                    'service_date': service_ts.date().isoformat(),
                    'service_ts': service_ts,
                    'technician': _clean(srv.get('technician')) or '—',
                    'bull_id': _clean(srv.get('bull_id')) or '—',
                    'protocol': _clean(srv.get('method') or srv.get('protocol')) or '—',
                    'conceived': conceived,
                    'preg_check_result': outcome or 'unknown',
                    'preg_check_date': _clean(first_check.get('event_ts').date().isoformat() if first_check.get('event_ts') is not None and not pd.isna(first_check.get('event_ts')) else ''),
                    'last_heat_date': _clean(last_heat.get('event_ts').date().isoformat() if last_heat.get('event_ts') is not None and not pd.isna(last_heat.get('event_ts')) else ''),
                    'current_pen_id': _clean(assignment.get('pen_id') or assignment.get('current_pen_id')),
                    'current_pen_name': _clean(assignment.get('pen_name')),
                    'farm_id': _clean(assignment.get('farm_id') or srv.get('farm_id')),
                    'site_id': _clean(assignment.get('site_id') or srv.get('site_id')),
                }
            )
    return pd.DataFrame(rows)



def _aggregate_breakdown(service_df: pd.DataFrame, *, group_col: str, label: str, repeat_animals: set[str], max_rows: int) -> list[dict[str, Any]]:
    if service_df is None or service_df.empty or group_col not in service_df.columns:
        return []
    df = service_df.copy()
    df[group_col] = df[group_col].fillna('—').astype(str).replace({'': '—'})
    out: list[dict[str, Any]] = []
    for value, grp in df.groupby(group_col, dropna=False):
        services_n = int(len(grp))
        known = grp[grp['conceived'].notna()].copy()
        conceived_n = int((known['conceived'] == True).sum())  # noqa: E712
        animals = set(grp['animal_id'].astype(str).tolist())
        repeat_n = len(animals & repeat_animals)
        row = {
            'dimension': label,
            'value': str(value or '—'),
            'animals_n': int(len(animals)),
            'services_n': services_n,
            'conceived_services_n': conceived_n,
            'conception_rate': round((conceived_n / services_n), 4) if services_n else None,
            'repeat_breeders_n': int(repeat_n),
        }
        out.append(row)
    out.sort(key=lambda r: (-int(r.get('services_n') or 0), str(r.get('value') or '')))
    return out[: max(1, int(max_rows))]



def _period_breakdown(service_df: pd.DataFrame, *, repeat_animals: set[str], max_rows: int) -> list[dict[str, Any]]:
    if service_df is None or service_df.empty:
        return []
    df = service_df.copy()
    df['period'] = df['service_ts'].dt.to_period('M').astype(str)
    out = _aggregate_breakdown(df, group_col='period', label='period', repeat_animals=repeat_animals, max_rows=max_rows)
    return out



def build_reproduction_cockpit_snapshot(
    *,
    input_dir: Path,
    asof_date: date,
    conn=None,
    tenant_id: str | None = None,
    pen_id: str | None = None,
    technician: str | None = None,
    bull_id: str | None = None,
    protocol: str | None = None,
    animal_id: str | None = None,
    period_days: int | None = None,
    config: Mapping[str, Any] | None = None,
    limit_animals: int = 200,
) -> dict[str, Any]:
    base = Path(input_dir)
    cfg = dict(DEFAULT_REPRO_COCKPIT_CONFIG)
    cfg.update(dict(config or {}))
    lookback_days = int(period_days or cfg.get('lookback_days') or 60)
    pr_days = int(cfg.get('pregnancy_rate_window_days') or 21)
    repeat_threshold = int(cfg.get('repeat_breeder_services') or 3)
    max_breakdown_rows = int(cfg.get('max_breakdown_rows') or 50)

    animals = _read_csv(base / 'dm_animals.csv')
    lact = _read_csv(base / 'dm_lactations.csv')
    repro = _read_csv(base / 'dm_repro_events.csv')
    pens = _read_csv(base / 'dm_pens.csv')
    assignments = _current_assignment_map(base, asof_date=asof_date)

    if animals.empty:
        return {
            'summary': {'animals_total': 0},
            'kpis': {},
            'breakdowns': {},
            'animals': [],
            'formulas': {},
        }

    animals = animals.copy()
    animals['animal_id'] = animals.get('animal_id', pd.Series(dtype=object)).astype(str)
    if animal_id:
        animals = animals[animals['animal_id'] == str(animal_id)].copy()
    elif pen_id:
        selected = {k for k, v in assignments.items() if _clean(v.get('pen_id')) == _clean(pen_id)}
        animals = animals[animals['animal_id'].isin(selected)].copy()

    animal_ids = sorted(animals['animal_id'].dropna().astype(str).unique().tolist())
    if not animal_ids:
        return {
            'summary': {'animals_total': 0},
            'kpis': {},
            'breakdowns': {},
            'animals': [],
            'formulas': {},
        }

    states = build_reproduction_states_table(
        animals_df=animals,
        lactations_df=lact,
        repro_events_df=repro,
        operational_events_df=pd.DataFrame(),
        animal_ids=animal_ids,
        asof_date=asof_date,
        config=cfg,
    )
    states_map = {str(r.get('animal_id') or ''): dict(r) for r in states.to_dict(orient='records')} if not states.empty else {}

    service_df = _build_service_ledger(
        animals_df=animals,
        lactations_df=lact,
        repro_events_df=repro,
        assignments=assignments,
        asof_date=asof_date,
    )
    if not service_df.empty:
        if pen_id:
            service_df = service_df[service_df['current_pen_id'].astype(str) == str(pen_id)].copy()
        if technician:
            service_df = service_df[service_df['technician'].astype(str) == str(technician)].copy()
        if bull_id:
            service_df = service_df[service_df['bull_id'].astype(str) == str(bull_id)].copy()
        if protocol:
            service_df = service_df[service_df['protocol'].astype(str) == str(protocol)].copy()
        if animal_id:
            service_df = service_df[service_df['animal_id'].astype(str) == str(animal_id)].copy()

    repro_norm = repro.copy() if repro is not None else pd.DataFrame()
    if not repro_norm.empty:
        repro_norm['animal_id'] = repro_norm.get('animal_id', pd.Series(dtype=object)).astype(str)
        repro_norm['event_type_norm'] = repro_norm.get('event_type', pd.Series(dtype=object)).map(_normalize_event_type)
        repro_norm['event_ts'] = repro_norm.get('event_ts', repro_norm.get('event_date')).map(_parse_ts)
        repro_norm = repro_norm[repro_norm['event_ts'].notna()].copy()
        repro_norm = repro_norm[repro_norm['event_ts'].dt.date <= asof_date].copy()
        if animal_ids:
            repro_norm = repro_norm[repro_norm['animal_id'].isin(set(animal_ids))].copy()

    lookback_start = pd.Timestamp(asof_date) - pd.Timedelta(days=lookback_days - 1)
    pr_start = pd.Timestamp(asof_date) - pd.Timedelta(days=pr_days - 1)
    eligible_states = {'eligible', 'heat', 'open', 'repeat'}
    eligible_animals = {aid for aid, row in states_map.items() if str(row.get('repro_state') or '') in eligible_states}
    repeat_animals = {aid for aid, row in states_map.items() if str(row.get('repro_state') or '') == 'repeat'}

    heats_df = repro_norm[repro_norm['event_type_norm'] == 'heat'].copy() if not repro_norm.empty else pd.DataFrame()
    heats_df = heats_df[heats_df['event_ts'] >= lookback_start].copy() if not heats_df.empty else heats_df
    services_lb = service_df[service_df['service_ts'] >= lookback_start].copy() if not service_df.empty else pd.DataFrame()
    services_pr = service_df[service_df['service_ts'] >= pr_start].copy() if not service_df.empty else pd.DataFrame()

    heat_animals_n = int(heats_df['animal_id'].astype(str).nunique()) if not heats_df.empty else 0
    served_animals_n = int(services_lb['animal_id'].astype(str).nunique()) if not services_lb.empty else 0
    services_n = int(len(services_lb)) if not services_lb.empty else 0
    conceived_services_n = int((services_lb['conceived'] == True).sum()) if not services_lb.empty else 0  # noqa: E712
    pregnancies_window_n = int((services_pr['conceived'] == True).sum()) if not services_pr.empty else 0  # noqa: E712

    kpis = {
        'eligible_animals_n': len(eligible_animals),
        'pregnancy_rate': round((pregnancies_window_n / len(eligible_animals)), 4) if eligible_animals else None,
        'heat_detection_rate': round((heat_animals_n / len(eligible_animals)), 4) if eligible_animals else None,
        'service_rate': round((served_animals_n / len(eligible_animals)), 4) if eligible_animals else None,
        'conception_rate': round((conceived_services_n / services_n), 4) if services_n else None,
        'repeat_breeders_n': len(repeat_animals),
        'services_n': services_n,
        'conceived_services_n': conceived_services_n,
        'pregnancies_window_n': pregnancies_window_n,
        'heat_animals_n': heat_animals_n,
    }

    breakdowns = {
        'by_technician': _aggregate_breakdown(services_lb, group_col='technician', label='technician', repeat_animals=repeat_animals, max_rows=max_breakdown_rows),
        'by_bull': _aggregate_breakdown(services_lb, group_col='bull_id', label='bull', repeat_animals=repeat_animals, max_rows=max_breakdown_rows),
        'by_protocol': _aggregate_breakdown(services_lb, group_col='protocol', label='protocol', repeat_animals=repeat_animals, max_rows=max_breakdown_rows),
        'by_group': _aggregate_breakdown(services_lb, group_col='current_pen_name', label='group', repeat_animals=repeat_animals, max_rows=max_breakdown_rows),
        'by_period': _period_breakdown(services_lb, repeat_animals=repeat_animals, max_rows=max_breakdown_rows),
    }

    worklists_snapshot = build_reproduction_worklists_snapshot(
        input_dir=base,
        asof_date=asof_date,
        conn=conn,
        tenant_id=tenant_id,
        pen_id=pen_id or None,
        animal_id=animal_id or None,
        limit=max(500, int(limit_animals)),
    )
    due_rows = list(worklists_snapshot.get('items') or [])
    due_by_animal = {str(r.get('animal_id') or ''): dict(r) for r in due_rows if str(r.get('animal_id') or '').strip()}

    animal_rows: list[dict[str, Any]] = []
    pens_map = {str(r.get('pen_id') or ''): _clean(r.get('pen_name')) for r in pens.to_dict(orient='records')} if not pens.empty else {}
    repeat_counts: dict[str, int] = {}
    if not service_df.empty:
        repeat_counts = service_df.groupby('animal_id')['service_no'].max().astype(int).to_dict()

    for aid in animal_ids:
        state = dict(states_map.get(str(aid)) or {})
        assign = dict(assignments.get(str(aid)) or {})
        due = dict(due_by_animal.get(str(aid)) or {})
        current_pen_id = _clean(assign.get('pen_id') or assign.get('current_pen_id'))
        current_pen_name = _clean(assign.get('pen_name')) or pens_map.get(current_pen_id, '')
        if technician and technician != '—':
            sub = service_df[(service_df['animal_id'].astype(str) == str(aid)) & (service_df['technician'].astype(str) == str(technician))] if not service_df.empty else pd.DataFrame()
            if sub.empty:
                continue
        if bull_id and bull_id != '—':
            sub = service_df[(service_df['animal_id'].astype(str) == str(aid)) & (service_df['bull_id'].astype(str) == str(bull_id))] if not service_df.empty else pd.DataFrame()
            if sub.empty:
                continue
        if protocol and protocol != '—':
            sub = service_df[(service_df['animal_id'].astype(str) == str(aid)) & (service_df['protocol'].astype(str) == str(protocol))] if not service_df.empty else pd.DataFrame()
            if sub.empty:
                continue
        row = {
            'animal_id': str(aid),
            'pen_id': current_pen_id,
            'pen_name': current_pen_name or current_pen_id or '—',
            'repro_state': _clean(state.get('repro_state')) or 'no_data',
            'repro_state_label': _clean(state.get('repro_state_label')) or _clean(state.get('repro_state')) or '—',
            'repro_reason_label': _clean(state.get('repro_reason_label')) or _clean(state.get('repro_reason_code')) or '—',
            'last_bred_date': _clean(state.get('last_bred_date')) or '—',
            'next_preg_check_due_date': _clean(state.get('next_preg_check_due_date')) or '—',
            'services_since_calving': int(state.get('services_since_calving') or 0),
            'repeat_breeder_flag': bool(int(repeat_counts.get(str(aid), 0)) >= repeat_threshold or str(state.get('repro_state') or '') == 'repeat'),
            'due_action': _clean(due.get('action_label')) or '—',
            'due_at': _clean(due.get('due_at')) or '—',
            'confidence': due.get('confidence') if due.get('confidence') is not None else None,
            'materialized_worklist_id': _clean(due.get('existing_worklist_id')) or '',
            'next_step_action': _clean(due.get('next_step_action')) or 'Open animal',
            'source_facts_preview': list(due.get('source_facts_preview') or []),
            'expected_effect': _clean(due.get('expected_effect')) or '',
        }
        animal_rows.append(row)

    def _animal_sort_key(row: Mapping[str, Any]) -> tuple[int, int, str]:
        due = _clean(row.get('due_at'))
        has_due = 0 if due and due != '—' else 1
        prio = 0 if bool(row.get('repeat_breeder_flag')) else 1
        return (has_due, prio, str(row.get('animal_id') or ''))

    animal_rows.sort(key=_animal_sort_key)
    animal_rows = animal_rows[: max(1, int(limit_animals))]

    summary = {
        'animals_total': len(animal_ids),
        'filtered_animals_n': len(animal_rows),
        'due_actions_n': len(due_rows),
        'materialized_worklists_n': int(sum(1 for r in due_rows if bool(r.get('materialized')))),
        'repeat_breeders_n': len(repeat_animals),
        'lookback_days': lookback_days,
        'pregnancy_rate_window_days': pr_days,
    }
    formulas = {
        'pregnancy_rate': f"pregnancies_from_services_last_{pr_days}d / eligible_animals",
        'heat_detection_rate': f"animals_with_heat_last_{lookback_days}d / eligible_animals",
        'service_rate': f"animals_served_last_{lookback_days}d / eligible_animals",
        'conception_rate': f"conceived_services_last_{lookback_days}d / total_services_last_{lookback_days}d",
        'repeat_breeders': f"animals with >= {repeat_threshold} services since calving and not pregnant",
    }
    filters = {
        'pen_id': _clean(pen_id),
        'technician': _clean(technician),
        'bull_id': _clean(bull_id),
        'protocol': _clean(protocol),
        'animal_id': _clean(animal_id),
    }
    return {
        'summary': summary,
        'kpis': kpis,
        'breakdowns': breakdowns,
        'animals': animal_rows,
        'due_actions': due_rows,
        'formulas': formulas,
        'filters': filters,
    }


__all__ = [
    'DEFAULT_REPRO_COCKPIT_CONFIG',
    'build_reproduction_cockpit_snapshot',
]
