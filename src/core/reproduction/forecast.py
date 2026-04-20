from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from core.reproduction.state_machine import DEFAULT_REPRO_CONFIG, build_reproduction_states_table
from genomeai.drilldown import compute_pen_assignments

try:
    from genomeai.economics_v2 import load_economics_v2
except Exception:  # pragma: no cover
    load_economics_v2 = None  # type: ignore[assignment]


DEFAULT_CALVING_FORECAST_CONFIG: dict[str, Any] = {
    **DEFAULT_REPRO_CONFIG,
    'assumptions_version': 'calving_forecast_v1',
    'gestation_days': 280,
    'dry_period_days': 60,
    'female_calf_ratio': 0.48,
    'calf_survival_rate': 0.92,
    'replacement_retention_rate': 0.70,
    'replacement_unit_cost_rub': 120000.0,
    'include_unconfirmed_bred_in_calving_forecast': True,
    'pregnant_calving_confidence': 0.95,
    'preg_check_due_calving_confidence': 0.70,
    'bred_calving_confidence': 0.55,
    'max_event_rows': 500,
    'weekly_weeks_default': 13,
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


def _parse_dt(value: Any) -> pd.Timestamp | pd.NaT:
    try:
        ts = pd.to_datetime(value, errors='coerce', utc=True)
        if pd.isna(ts):
            return pd.NaT
        return ts.tz_localize(None)
    except Exception:
        return pd.NaT


def _assignment_map(input_dir: Path, *, asof_date: date) -> dict[str, dict[str, Any]]:
    assn = compute_pen_assignments(input_dir=input_dir, asof_date=asof_date)
    if assn is None or assn.empty:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in assn.to_dict(orient='records'):
        animal_id = _clean(row.get('animal_id'))
        if animal_id:
            out[animal_id] = dict(row)
    return out


def _normalize_event_type(value: Any) -> str:
    raw = _clean(value).lower()
    if raw in {'ai', 'service', 'insemin', 'insemination'}:
        return 'insemination'
    if raw in {'preg_check', 'pregnancy_check', 'preg check', 'diag', 'diagnosis'}:
        return 'preg_check'
    if raw in {'heat', 'estrus'}:
        return 'heat'
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


def _service_ledger(*, repro_events_df: pd.DataFrame, animal_ids: set[str], asof_date: date) -> pd.DataFrame:
    repro = repro_events_df.copy() if repro_events_df is not None else pd.DataFrame()
    if repro.empty:
        return pd.DataFrame()
    repro['animal_id'] = repro.get('animal_id', pd.Series(dtype=object)).astype(str)
    repro = repro[repro['animal_id'].isin(animal_ids)].copy()
    repro['event_type_norm'] = repro.get('event_type', pd.Series(dtype=object)).map(_normalize_event_type)
    repro['result_norm'] = repro.get('result', pd.Series(dtype=object)).map(_normalize_result)
    repro['event_ts'] = repro.get('event_ts', repro.get('event_date')).map(_parse_dt)
    repro = repro[repro['event_ts'].notna()].copy()
    repro = repro[repro['event_ts'].dt.date <= asof_date].copy()
    if repro.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for aid, grp in repro.groupby('animal_id', dropna=False):
        grp = grp.sort_values('event_ts').copy()
        insems = grp[grp['event_type_norm'] == 'insemination'].copy()
        checks = grp[grp['event_type_norm'] == 'preg_check'].copy()
        if insems.empty:
            continue
        for idx, (_, srv) in enumerate(insems.iterrows()):
            service_ts = srv['event_ts']
            next_service_ts = insems.iloc[idx + 1]['event_ts'] if idx + 1 < len(insems) else pd.NaT
            sub = checks[checks['event_ts'] >= service_ts].copy()
            if pd.notna(next_service_ts):
                sub = sub[sub['event_ts'] < next_service_ts].copy()
            sub = sub.sort_values('event_ts')
            first_check = dict(sub.iloc[0]) if not sub.empty else {}
            rows.append(
                {
                    'animal_id': str(aid),
                    'service_no': int(idx + 1),
                    'service_ts': service_ts,
                    'service_date': service_ts.date().isoformat(),
                    'preg_check_ts': first_check.get('event_ts'),
                    'preg_check_date': first_check.get('event_ts').date().isoformat() if first_check.get('event_ts') is not None and not pd.isna(first_check.get('event_ts')) else '',
                    'preg_check_result': _clean(first_check.get('result_norm') or ''),
                    'technician': _clean(srv.get('technician')) or '—',
                    'bull_id': _clean(srv.get('bull_id')) or '—',
                    'protocol': _clean(srv.get('method') or srv.get('protocol')) or '—',
                }
            )
    return pd.DataFrame(rows)


def _bucket_label(days_to: int, buckets: Sequence[int]) -> str:
    for bucket in buckets:
        if days_to <= int(bucket):
            return f'{int(bucket)}d'
    return f'>{int(max(buckets))}d'


def _forecast_confidence(state: str, cfg: Mapping[str, Any]) -> float:
    if state == 'pregnant':
        return float(cfg.get('pregnant_calving_confidence') or 0.95)
    if state == 'preg_check_due':
        return float(cfg.get('preg_check_due_calving_confidence') or 0.70)
    return float(cfg.get('bred_calving_confidence') or 0.55)


def _build_economics_context(*, artifacts_root: Path | None, data_version: str | None, asof_date: date, replacements_by_bucket: Mapping[int, float], cfg: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        'available': False,
        'economics_run': '',
        'milk_price_rub_per_kg': None,
        'replacement_unit_cost_rub': float(cfg.get('replacement_unit_cost_rub') or 0.0),
        'projected_replacement_value_30d_rub': round(float(replacements_by_bucket.get(30, 0.0)) * float(cfg.get('replacement_unit_cost_rub') or 0.0), 2),
        'projected_replacement_value_90d_rub': round(float(replacements_by_bucket.get(90, 0.0)) * float(cfg.get('replacement_unit_cost_rub') or 0.0), 2),
    }
    if not artifacts_root or not data_version or load_economics_v2 is None:
        return out
    try:
        rid, dfs, _ = load_economics_v2(artifacts_root=Path(artifacts_root), data_version=str(data_version), economics_run=None)
    except Exception:
        return out
    daily = dfs.get('economics_daily', pd.DataFrame()) if isinstance(dfs, dict) else pd.DataFrame()
    if daily is None or daily.empty:
        out['economics_run'] = str(rid or '')
        return out
    df = daily.copy()
    if 'date' in df.columns:
        df['date_ts'] = pd.to_datetime(df['date'], errors='coerce')
        df = df[df['date_ts'].notna()].copy()
        if not df.empty:
            df['delta'] = (df['date_ts'].dt.date - asof_date).map(lambda d: abs(d.days))
            df = df.sort_values(['delta', 'date_ts'])
    row = dict(df.iloc[0]) if not df.empty else {}
    milk_price = None
    for key in ['milk_price_rub_per_kg', 'milk_price', 'price_milk_rub_per_kg']:
        value = row.get(key)
        if value is None:
            continue
        try:
            if pd.isna(value):
                continue
        except Exception:
            pass
        if str(value).strip() == '':
            continue
        try:
            milk_price = float(value)
            break
        except Exception:
            milk_price = None
    out.update({'available': True, 'economics_run': str(rid or ''), 'milk_price_rub_per_kg': milk_price})
    return out


def build_calving_forecast_snapshot(
    *,
    input_dir: Path,
    asof_date: date,
    data_version: str | None = None,
    artifacts_root: Path | None = None,
    site_id: str | None = None,
    pen_id: str | None = None,
    animal_id: str | None = None,
    bucket_days: Sequence[int] = (7, 30, 60, 90),
    weekly_weeks: int | None = None,
    config: Mapping[str, Any] | None = None,
    limit_animals: int = 300,
) -> dict[str, Any]:
    base = Path(input_dir)
    cfg = dict(DEFAULT_CALVING_FORECAST_CONFIG)
    cfg.update(dict(config or {}))
    weekly_weeks = int(weekly_weeks or cfg.get('weekly_weeks_default') or 13)
    buckets = [int(x) for x in bucket_days if int(x) > 0]
    if not buckets:
        buckets = [7, 30, 60, 90]
    buckets = sorted(set(buckets))

    animals = _read_csv(base / 'dm_animals.csv')
    lact = _read_csv(base / 'dm_lactations.csv')
    repro = _read_csv(base / 'dm_repro_events.csv')
    pens = _read_csv(base / 'dm_pens.csv')
    if animals.empty:
        return {
            'summary': {'animals_total': 0, 'filters': {}, 'assumptions_version': _clean(cfg.get('assumptions_version'))},
            'assumptions': dict(cfg),
            'formulas': {},
            'inventory': {},
            'resource_planning': {},
            'economics': {},
            'bucket_rows': [],
            'weekly_rows': [],
            'events': [],
            'animals': [],
            'breakdowns': {},
        }

    assignments = _assignment_map(base, asof_date=asof_date)
    animals = animals.copy()
    animals['animal_id'] = animals.get('animal_id', pd.Series(dtype=object)).astype(str)
    selected_ids = set(animals['animal_id'].dropna().astype(str).tolist())
    if animal_id:
        selected_ids &= {str(animal_id)}
    if pen_id:
        selected_ids &= {aid for aid, row in assignments.items() if _clean(row.get('pen_id')) == _clean(pen_id)}
    if site_id:
        selected_ids &= {aid for aid, row in assignments.items() if _clean(row.get('site_id')) == _clean(site_id)}
    if selected_ids:
        animals = animals[animals['animal_id'].isin(selected_ids)].copy()
    else:
        animals = animals.iloc[0:0].copy()

    animal_ids = sorted(animals['animal_id'].dropna().astype(str).unique().tolist())
    if not animal_ids:
        return {
            'summary': {'animals_total': 0, 'filters': {'site_id': _clean(site_id), 'pen_id': _clean(pen_id), 'animal_id': _clean(animal_id)}, 'assumptions_version': _clean(cfg.get('assumptions_version'))},
            'assumptions': dict(cfg),
            'formulas': {},
            'inventory': {},
            'resource_planning': {},
            'economics': {},
            'bucket_rows': [],
            'weekly_rows': [],
            'events': [],
            'animals': [],
            'breakdowns': {},
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
    ledger = _service_ledger(repro_events_df=repro, animal_ids=set(animal_ids), asof_date=asof_date)
    service_map: dict[str, dict[str, Any]] = {}
    if not ledger.empty:
        service_map = {str(r.get('animal_id') or ''): dict(r) for r in ledger.sort_values('service_ts').to_dict(orient='records')}

    pen_name_map = {str(r.get('pen_id') or ''): _clean(r.get('pen_name')) for r in pens.to_dict(orient='records')} if not pens.empty else {}

    events: list[dict[str, Any]] = []
    animals_rows: list[dict[str, Any]] = []
    weekly: dict[tuple[date, date], dict[str, Any]] = {}
    weeks_range = []
    week0 = asof_date - timedelta(days=asof_date.weekday())
    for idx in range(max(1, weekly_weeks)):
        start = week0 + timedelta(days=idx * 7)
        end = start + timedelta(days=6)
        weekly[(start, end)] = {'week_start': start.isoformat(), 'week_end': end.isoformat(), 'calvings_n': 0, 'dry_offs_n': 0, 'replacements_est': 0.0}
        weeks_range.append((start, end))

    include_unconfirmed = bool(cfg.get('include_unconfirmed_bred_in_calving_forecast', True))
    gestation_days = int(cfg.get('gestation_days') or 280)
    dry_period_days = int(cfg.get('dry_period_days') or 60)
    replacement_factor = float(cfg.get('female_calf_ratio') or 0.0) * float(cfg.get('calf_survival_rate') or 0.0) * float(cfg.get('replacement_retention_rate') or 0.0)

    for aid in animal_ids:
        state = dict(states_map.get(aid) or {})
        repro_state = _clean(state.get('repro_state')).lower()
        if repro_state not in {'pregnant', 'preg_check_due', 'bred'}:
            continue
        if repro_state != 'pregnant' and not include_unconfirmed:
            continue
        last_bred_date = _clean(state.get('last_bred_date'))
        if not last_bred_date:
            continue
        bred_dt = _parse_dt(last_bred_date)
        if pd.isna(bred_dt):
            continue
        calving_dt = (bred_dt + pd.Timedelta(days=gestation_days)).date()
        dry_off_dt = (bred_dt + pd.Timedelta(days=gestation_days - dry_period_days)).date()
        days_to_calving = (calving_dt - asof_date).days
        days_to_dry = (dry_off_dt - asof_date).days
        confidence = _forecast_confidence(repro_state, cfg)
        assignment = dict(assignments.get(aid) or {})
        current_pen_id = _clean(assignment.get('pen_id'))
        current_pen_name = _clean(assignment.get('pen_name')) or pen_name_map.get(current_pen_id, '')
        service = dict(service_map.get(aid) or {})
        facts = [
            {'label': 'Repro state', 'text': _clean(state.get('repro_state_label')) or repro_state},
            {'label': 'Reason', 'text': _clean(state.get('repro_reason_label')) or '—'},
            {'label': 'Last bred', 'text': last_bred_date},
            {'label': 'Projected calving', 'text': calving_dt.isoformat()},
            {'label': 'Projected dry-off', 'text': dry_off_dt.isoformat()},
        ]
        if _clean(service.get('bull_id')):
            facts.append({'label': 'Bull', 'text': _clean(service.get('bull_id'))})
        if _clean(service.get('technician')):
            facts.append({'label': 'Technician', 'text': _clean(service.get('technician'))})
        if _clean(service.get('protocol')):
            facts.append({'label': 'Protocol', 'text': _clean(service.get('protocol'))})

        animal_row = {
            'animal_id': aid,
            'site_id': _clean(assignment.get('site_id')),
            'pen_id': current_pen_id,
            'pen_name': current_pen_name or current_pen_id or '—',
            'repro_state': repro_state,
            'repro_state_label': _clean(state.get('repro_state_label')) or repro_state,
            'repro_reason_label': _clean(state.get('repro_reason_label')) or '—',
            'last_bred_date': last_bred_date,
            'projected_calving_date': calving_dt.isoformat(),
            'projected_dry_off_date': dry_off_dt.isoformat(),
            'days_to_calving': int(days_to_calving),
            'days_to_dry_off': int(days_to_dry),
            'forecast_confidence': confidence,
            'next_step_action': 'Open animal',
            'source_facts_preview': [str(f['text']) for f in facts[:4] if str(f['text']).strip()],
        }
        animals_rows.append(animal_row)

        if 0 <= days_to_calving <= max(buckets):
            bucket = _bucket_label(days_to_calving, buckets)
            events.append(
                {
                    'animal_id': aid,
                    'site_id': _clean(assignment.get('site_id')),
                    'pen_id': current_pen_id,
                    'pen_name': current_pen_name or current_pen_id or '—',
                    'event_type': 'calving',
                    'event_label': 'Projected calving',
                    'due_date': calving_dt.isoformat(),
                    'days_to_due': int(days_to_calving),
                    'bucket': bucket,
                    'week_start': '',
                    'week_end': '',
                    'confidence': confidence,
                    'repro_state_label': _clean(state.get('repro_state_label')) or repro_state,
                    'repro_reason_label': _clean(state.get('repro_reason_label')) or '—',
                    'expected_effect': 'Подготовить calving resources и ближайший fresh load.',
                    'source_facts_preview': [str(f['text']) for f in facts[:4] if str(f['text']).strip()],
                }
            )
            for start, end in weeks_range:
                if start <= calving_dt <= end:
                    weekly[(start, end)]['calvings_n'] += 1
                    weekly[(start, end)]['replacements_est'] += replacement_factor
                    break
        if 0 <= days_to_dry <= max(buckets):
            bucket = _bucket_label(days_to_dry, buckets)
            events.append(
                {
                    'animal_id': aid,
                    'site_id': _clean(assignment.get('site_id')),
                    'pen_id': current_pen_id,
                    'pen_name': current_pen_name or current_pen_id or '—',
                    'event_type': 'dry_off',
                    'event_label': 'Projected dry-off',
                    'due_date': dry_off_dt.isoformat(),
                    'days_to_due': int(days_to_dry),
                    'bucket': bucket,
                    'week_start': '',
                    'week_end': '',
                    'confidence': confidence,
                    'repro_state_label': _clean(state.get('repro_state_label')) or repro_state,
                    'repro_reason_label': _clean(state.get('repro_reason_label')) or '—',
                    'expected_effect': 'Подготовить dry-off planning и dry pen capacity.',
                    'source_facts_preview': [str(f['text']) for f in facts[:4] if str(f['text']).strip()],
                }
            )
            for start, end in weeks_range:
                if start <= dry_off_dt <= end:
                    weekly[(start, end)]['dry_offs_n'] += 1
                    break

    events.sort(key=lambda r: (str(r.get('due_date') or ''), str(r.get('event_type') or ''), str(r.get('animal_id') or '')))
    max_rows = max(1, int(cfg.get('max_event_rows') or 500))
    events = events[:max_rows]
    animals_rows.sort(key=lambda r: (int(r.get('days_to_calving') or 999999), str(r.get('animal_id') or '')))
    animals_rows = animals_rows[: max(1, int(limit_animals))]

    calving_by_bucket = {bucket: 0 for bucket in buckets}
    dry_by_bucket = {bucket: 0 for bucket in buckets}
    replacements_by_bucket = {bucket: 0.0 for bucket in buckets}
    for row in events:
        days_to = int(row.get('days_to_due') or 0)
        for bucket in buckets:
            if days_to <= bucket:
                if row.get('event_type') == 'calving':
                    calving_by_bucket[bucket] += 1
                    replacements_by_bucket[bucket] += replacement_factor
                elif row.get('event_type') == 'dry_off':
                    dry_by_bucket[bucket] += 1

    weekly_rows: list[dict[str, Any]] = []
    for start, end in weeks_range:
        row = dict(weekly[(start, end)])
        row['replacements_est'] = round(float(row.get('replacements_est') or 0.0), 2)
        weekly_rows.append(row)

    states_counts: dict[str, int] = {}
    if not states.empty:
        for value, grp in states.groupby('repro_state', dropna=False):
            states_counts[str(value or 'no_data')] = int(len(grp))

    by_group: dict[str, dict[str, Any]] = {}
    by_site: dict[str, dict[str, Any]] = {}
    for row in events:
        grp_key = _clean(row.get('pen_name') or row.get('pen_id')) or '—'
        site_key = _clean(row.get('site_id')) or '—'
        for bucket_name, store in ((grp_key, by_group), (site_key, by_site)):
            cur = store.setdefault(bucket_name, {'value': bucket_name, 'calvings_n': 0, 'dry_offs_n': 0, 'replacements_est': 0.0})
            if row.get('event_type') == 'calving':
                cur['calvings_n'] += 1
                cur['replacements_est'] += replacement_factor
            elif row.get('event_type') == 'dry_off':
                cur['dry_offs_n'] += 1
    breakdowns = {
        'by_group': sorted([{**v, 'replacements_est': round(float(v.get('replacements_est') or 0.0), 2)} for v in by_group.values()], key=lambda r: (-int(r.get('calvings_n') or 0), str(r.get('value') or ''))),
        'by_site': sorted([{**v, 'replacements_est': round(float(v.get('replacements_est') or 0.0), 2)} for v in by_site.values()], key=lambda r: (-int(r.get('calvings_n') or 0), str(r.get('value') or ''))),
    }

    resource_planning = {
        'calving_watch_7d': int(calving_by_bucket.get(7, 0)),
        'maternity_pen_load_30d': int(calving_by_bucket.get(30, 0)),
        'dry_pen_load_30d': int(dry_by_bucket.get(30, 0)),
        'replacement_pipeline_90d': round(float(replacements_by_bucket.get(90, 0.0)), 2),
    }
    inventory = {
        'current_by_repro_state': states_counts,
        'projected_fresh_entries_by_bucket': {str(k): int(v) for k, v in calving_by_bucket.items()},
        'projected_dry_entries_by_bucket': {str(k): int(v) for k, v in dry_by_bucket.items()},
        'projected_replacements_by_bucket': {str(k): round(float(v), 2) for k, v in replacements_by_bucket.items()},
    }

    economics = _build_economics_context(
        artifacts_root=artifacts_root,
        data_version=data_version,
        asof_date=asof_date,
        replacements_by_bucket=replacements_by_bucket,
        cfg=cfg,
    )

    summary = {
        'animals_total': len(animal_ids),
        'events_total': len(events),
        'projected_calvings_7d': int(calving_by_bucket.get(7, 0)),
        'projected_calvings_30d': int(calving_by_bucket.get(30, 0)),
        'projected_calvings_60d': int(calving_by_bucket.get(60, 0)),
        'projected_calvings_90d': int(calving_by_bucket.get(90, 0)),
        'projected_dry_offs_30d': int(dry_by_bucket.get(30, 0)),
        'projected_replacements_90d': round(float(replacements_by_bucket.get(90, 0.0)), 2),
        'filters': {'site_id': _clean(site_id), 'pen_id': _clean(pen_id), 'animal_id': _clean(animal_id)},
        'assumptions_version': _clean(cfg.get('assumptions_version')),
    }
    formulas = {
        'projected_calving_date': 'last_bred_date + gestation_days',
        'projected_dry_off_date': 'projected_calving_date - dry_period_days',
        'projected_replacements_est': 'projected_calvings * female_calf_ratio * calf_survival_rate * replacement_retention_rate',
    }
    return {
        'summary': summary,
        'assumptions': dict(cfg),
        'formulas': formulas,
        'inventory': inventory,
        'resource_planning': resource_planning,
        'economics': economics,
        'bucket_rows': [
            {
                'bucket_days': int(bucket),
                'projected_calvings_n': int(calving_by_bucket.get(bucket, 0)),
                'projected_dry_offs_n': int(dry_by_bucket.get(bucket, 0)),
                'projected_replacements_est': round(float(replacements_by_bucket.get(bucket, 0.0)), 2),
            }
            for bucket in buckets
        ],
        'weekly_rows': weekly_rows,
        'events': events,
        'animals': animals_rows,
        'breakdowns': breakdowns,
    }
