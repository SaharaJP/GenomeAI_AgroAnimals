from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from core.domain.enums import REPRODUCTION_REASON_CODES, REPRODUCTION_STATES


DEFAULT_REPRO_CONFIG: dict[str, Any] = {
    'fresh_days': 30,
    'eligible_after_calving_days': 45,
    'preg_check_due_days': 35,
}

STATE_LABELS: dict[str, str] = {
    'eligible': 'Eligible',
    'heat': 'Heat',
    'bred': 'Bred',
    'preg_check_due': 'Preg check due',
    'pregnant': 'Pregnant',
    'open': 'Open',
    'repeat': 'Repeat',
    'fresh': 'Fresh',
    'dry': 'Dry',
    'cull_candidate': 'Cull candidate',
    'no_data': 'No data',
}

REASON_LABELS: dict[str, str] = {
    'REPRO_HEAT_EVENT': 'Есть событие heat.',
    'REPRO_BRED_EVENT': 'Есть событие insemination.',
    'REPRO_PREG_CHECK_DUE': 'После осеменения наступил срок preg_check.',
    'REPRO_PREGNANT_CONFIRMED': 'Стельность подтверждена положительным preg_check.',
    'REPRO_OPEN_AFTER_NEGATIVE_CHECK': 'Получен отрицательный preg_check после осеменения.',
    'REPRO_REPEAT_AFTER_MULTIPLE_SERVICES': 'Есть повторные осеменения/отрицательные проверки после предыдущих сервисов.',
    'REPRO_FRESH_AFTER_CALVING': 'Животное находится в fresh-периоде после отёла.',
    'REPRO_ELIGIBLE_AFTER_VWP': 'Животное прошло fresh/VWP и готово к воспроизводительному циклу.',
    'REPRO_DRY_OFF_EVENT': 'Зафиксирован dry-off.',
    'REPRO_CULL_EVENT': 'Зафиксировано выбытие/cull/death.',
    'REPRO_NO_DATA': 'Недостаточно воспроизводственных событий для уверенного статуса.',
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


def _lower(value: Any) -> str:
    return _clean(value).lower()


def _normalize_event_type(value: Any) -> str:
    raw = _lower(value)
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
    if raw in {'cull', 'culled'}:
        return 'cull'
    if raw in {'death', 'dead'}:
        return 'death'
    return raw


def _normalize_result(value: Any) -> str:
    raw = _lower(value)
    if raw in {'pregnant', 'confirmed', 'positive', 'yes', 'preg', 'pos', 'true'}:
        return 'pregnant'
    if raw in {'open', 'not_pregnant', 'negative', 'no', 'neg', 'false'}:
        return 'open'
    return raw


def _latest_row(df: pd.DataFrame, date_col: str) -> dict[str, Any]:
    if df is None or df.empty or date_col not in df.columns:
        return {}
    out = df.copy()
    out['_ts'] = pd.to_datetime(out[date_col], errors='coerce')
    out = out.dropna(subset=['_ts']).sort_values('_ts', ascending=False)
    if out.empty:
        return {}
    row = dict(out.iloc[0].drop(labels=['_ts']))
    return row


def _normalize_repro_source_rows(
    *,
    repro_events: pd.DataFrame | None,
    operational_events: pd.DataFrame | Sequence[Mapping[str, Any]] | None,
    latest_lactation: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if repro_events is not None and not repro_events.empty:
        for _, row in repro_events.iterrows():
            evt = _normalize_event_type(row.get('event_type'))
            ts = _parse_dt(row.get('event_ts') or row.get('event_date'))
            if pd.isna(ts) or not evt:
                continue
            rows.append({
                'source': 'dm_repro_events',
                'event_type': evt,
                'event_ts': ts,
                'result': _normalize_result(row.get('result')),
                'reason_code': _clean(row.get('reason_code')),
                'bull_id': _clean(row.get('bull_id')),
            })
    if operational_events is not None:
        if isinstance(operational_events, pd.DataFrame):
            op_rows = operational_events.to_dict(orient='records')
        else:
            op_rows = [dict(r) for r in operational_events]
        for row in op_rows:
            evt = _normalize_event_type(row.get('event_type'))
            if evt not in {'heat', 'insemination', 'preg_check', 'calving', 'dry_off', 'cull', 'death'}:
                continue
            ts = _parse_dt(row.get('event_ts') or row.get('event_date') or row.get('created_at'))
            if pd.isna(ts):
                continue
            payload = dict(row.get('payload') or {})
            rows.append({
                'source': 'animal_events_v1',
                'event_type': evt,
                'event_ts': ts,
                'result': _normalize_result(payload.get('result') or row.get('result')),
                'reason_code': _clean(row.get('reason_code')),
                'bull_id': _clean(payload.get('bull_id') or row.get('linked_object_id')),
            })
    if latest_lactation:
        calving_date = _parse_dt(latest_lactation.get('calving_date'))
        if pd.notna(calving_date):
            rows.append({
                'source': 'dm_lactations',
                'event_type': 'calving',
                'event_ts': calving_date,
                'result': _normalize_result(latest_lactation.get('calving_outcome') or 'normal'),
                'reason_code': '',
                'bull_id': '',
            })
        dryoff_date = _parse_dt(latest_lactation.get('dryoff_date') or latest_lactation.get('dry_off_date'))
        if pd.notna(dryoff_date):
            rows.append({
                'source': 'dm_lactations',
                'event_type': 'dry_off',
                'event_ts': dryoff_date,
                'result': '',
                'reason_code': '',
                'bull_id': '',
            })
    rows.sort(key=lambda r: r['event_ts'])
    return rows


def compute_reproduction_state(
    *,
    animal_row: Mapping[str, Any] | None,
    lactation_rows: pd.DataFrame | None,
    repro_event_rows: pd.DataFrame | None,
    operational_event_rows: pd.DataFrame | Sequence[Mapping[str, Any]] | None,
    asof_date: date,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = dict(DEFAULT_REPRO_CONFIG)
    cfg.update(dict(config or {}))
    asof = pd.to_datetime(asof_date, errors='coerce')
    if pd.isna(asof):
        asof = pd.Timestamp.utcnow().normalize()

    latest_lact = _latest_row(lactation_rows if lactation_rows is not None else pd.DataFrame(), 'calving_date')
    events = _normalize_repro_source_rows(
        repro_events=repro_event_rows,
        operational_events=operational_event_rows,
        latest_lactation=latest_lact,
    )

    status_raw = _lower((animal_row or {}).get('status'))
    if status_raw in {'culled', 'cull_candidate', 'dead', 'death'}:
        events.append({'source': 'dm_animals', 'event_type': 'cull', 'event_ts': asof, 'result': status_raw, 'reason_code': '', 'bull_id': ''})
        events.sort(key=lambda r: r['event_ts'])

    last_calving = max((e['event_ts'] for e in events if e['event_type'] == 'calving' and e['event_ts'] <= asof), default=pd.NaT)
    last_dry = max((e['event_ts'] for e in events if e['event_type'] == 'dry_off' and e['event_ts'] <= asof), default=pd.NaT)
    insems_since_calving = [e for e in events if e['event_type'] == 'insemination' and e['event_ts'] <= asof and (pd.isna(last_calving) or e['event_ts'] >= last_calving)]
    last_insem = insems_since_calving[-1] if insems_since_calving else None
    preg_checks_after_last_insem = [
        e for e in events if e['event_type'] == 'preg_check' and e['event_ts'] <= asof and last_insem is not None and e['event_ts'] >= last_insem['event_ts']
    ]
    last_preg_check = preg_checks_after_last_insem[-1] if preg_checks_after_last_insem else None
    last_heat = max((e for e in events if e['event_type'] == 'heat' and e['event_ts'] <= asof), key=lambda x: x['event_ts'], default=None)
    last_cull = max((e for e in events if e['event_type'] in {'cull', 'death'} and e['event_ts'] <= asof), key=lambda x: x['event_ts'], default=None)

    state = 'no_data'
    reason_code = 'REPRO_NO_DATA'
    source_events: list[dict[str, Any]] = []

    if last_cull is not None:
        state = 'cull_candidate'
        reason_code = 'REPRO_CULL_EVENT'
        source_events = [last_cull]
    elif pd.notna(last_dry) and (pd.isna(last_calving) or last_dry >= last_calving):
        state = 'dry'
        reason_code = 'REPRO_DRY_OFF_EVENT'
        source_events = [e for e in events if e['event_type'] == 'dry_off' and e['event_ts'] == last_dry]
    elif last_preg_check is not None and last_preg_check.get('result') == 'pregnant':
        state = 'pregnant'
        reason_code = 'REPRO_PREGNANT_CONFIRMED'
        source_events = [last_insem, last_preg_check] if last_insem is not None else [last_preg_check]
    elif pd.notna(last_calving):
        days_since_calving = int((asof.normalize() - last_calving.normalize()).days)
        if days_since_calving < int(cfg['eligible_after_calving_days']):
            state = 'fresh'
            reason_code = 'REPRO_FRESH_AFTER_CALVING'
            source_events = [e for e in events if e['event_type'] == 'calving' and e['event_ts'] == last_calving]
        elif last_insem is not None:
            days_since_insem = int((asof.normalize() - last_insem['event_ts'].normalize()).days)
            if last_preg_check is None:
                if days_since_insem >= int(cfg['preg_check_due_days']):
                    state = 'preg_check_due'
                    reason_code = 'REPRO_PREG_CHECK_DUE'
                else:
                    state = 'bred'
                    reason_code = 'REPRO_BRED_EVENT'
                source_events = [last_insem]
            elif last_preg_check.get('result') == 'open':
                if len(insems_since_calving) >= 2:
                    state = 'repeat'
                    reason_code = 'REPRO_REPEAT_AFTER_MULTIPLE_SERVICES'
                else:
                    state = 'open'
                    reason_code = 'REPRO_OPEN_AFTER_NEGATIVE_CHECK'
                source_events = [last_insem, last_preg_check]
            else:
                state = 'bred'
                reason_code = 'REPRO_BRED_EVENT'
                source_events = [last_insem]
        elif last_heat is not None and (pd.isna(last_calving) or last_heat['event_ts'] >= last_calving):
            state = 'heat'
            reason_code = 'REPRO_HEAT_EVENT'
            source_events = [last_heat]
        else:
            state = 'eligible'
            reason_code = 'REPRO_ELIGIBLE_AFTER_VWP'
            source_events = [e for e in events if e['event_type'] == 'calving' and e['event_ts'] == last_calving]
    elif last_heat is not None:
        state = 'heat'
        reason_code = 'REPRO_HEAT_EVENT'
        source_events = [last_heat]
    elif last_insem is not None:
        days_since_insem = int((asof.normalize() - last_insem['event_ts'].normalize()).days)
        if last_preg_check is None and days_since_insem >= int(cfg['preg_check_due_days']):
            state = 'preg_check_due'
            reason_code = 'REPRO_PREG_CHECK_DUE'
        else:
            state = 'bred'
            reason_code = 'REPRO_BRED_EVENT'
        source_events = [last_insem]
    else:
        state = 'eligible' if _clean((animal_row or {}).get('animal_id')) else 'no_data'
        reason_code = 'REPRO_ELIGIBLE_AFTER_VWP' if state == 'eligible' else 'REPRO_NO_DATA'
        source_events = []

    if state not in REPRODUCTION_STATES:
        state = 'no_data'
        reason_code = 'REPRO_NO_DATA'

    last_heat_date = last_heat['event_ts'].date().isoformat() if last_heat is not None else None
    last_bred_date = last_insem['event_ts'].date().isoformat() if last_insem is not None else None
    last_preg_check_date = last_preg_check['event_ts'].date().isoformat() if last_preg_check is not None else None
    next_preg_check_due_date = None
    if last_insem is not None and last_preg_check is None:
        next_preg_check_due_date = (last_insem['event_ts'] + pd.Timedelta(days=int(cfg['preg_check_due_days']))).date().isoformat()

    services_since_calving = len(insems_since_calving)
    days_in_milk = int((asof.normalize() - last_calving.normalize()).days) if pd.notna(last_calving) else None
    days_since_bred = int((asof.normalize() - last_insem['event_ts'].normalize()).days) if last_insem is not None else None
    attention_required = state in {'heat', 'preg_check_due', 'open', 'repeat', 'cull_candidate'}

    rendered_source_events = []
    for row in source_events[:5]:
        rendered_source_events.append({
            'event_type': row.get('event_type'),
            'event_ts': row.get('event_ts').date().isoformat() if pd.notna(row.get('event_ts')) else None,
            'result': row.get('result') or None,
            'source': row.get('source') or None,
            'reason_code': row.get('reason_code') or None,
        })

    return {
        'animal_id': _clean((animal_row or {}).get('animal_id')),
        'state': state,
        'state_label': STATE_LABELS.get(state, state),
        'reason_code': reason_code,
        'reason_label': REASON_LABELS.get(reason_code, reason_code),
        'attention_required': bool(attention_required),
        'source_events': rendered_source_events,
        'dates': {
            'last_heat_date': last_heat_date,
            'last_bred_date': last_bred_date,
            'last_preg_check_date': last_preg_check_date,
            'last_calving_date': (last_calving.date().isoformat() if pd.notna(last_calving) else None),
            'last_dry_off_date': (last_dry.date().isoformat() if pd.notna(last_dry) else None),
            'next_preg_check_due_date': next_preg_check_due_date,
        },
        'metrics': {
            'services_since_calving': services_since_calving,
            'days_in_milk': days_in_milk,
            'days_since_bred': days_since_bred,
        },
    }


def build_reproduction_states_table(
    *,
    animals_df: pd.DataFrame | None,
    lactations_df: pd.DataFrame | None,
    repro_events_df: pd.DataFrame | None,
    operational_events_df: pd.DataFrame | None,
    animal_ids: Sequence[str],
    asof_date: date,
    config: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    animals_df = animals_df if animals_df is not None else pd.DataFrame()
    lactations_df = lactations_df if lactations_df is not None else pd.DataFrame()
    repro_events_df = repro_events_df if repro_events_df is not None else pd.DataFrame()
    operational_events_df = operational_events_df if operational_events_df is not None else pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for animal_id in [str(a) for a in animal_ids if _clean(a)]:
        animal_row = {}
        if not animals_df.empty and 'animal_id' in animals_df.columns:
            sub = animals_df[animals_df['animal_id'].astype(str) == animal_id]
            if not sub.empty:
                animal_row = dict(sub.iloc[0])
        lact_sub = lactations_df[lactations_df.get('animal_id', pd.Series(dtype=object)).astype(str) == animal_id].copy() if not lactations_df.empty else pd.DataFrame()
        repro_sub = repro_events_df[repro_events_df.get('animal_id', pd.Series(dtype=object)).astype(str) == animal_id].copy() if not repro_events_df.empty else pd.DataFrame()
        op_sub = operational_events_df[operational_events_df.get('animal_id', pd.Series(dtype=object)).astype(str) == animal_id].copy() if not operational_events_df.empty else pd.DataFrame()
        state = compute_reproduction_state(
            animal_row=animal_row,
            lactation_rows=lact_sub,
            repro_event_rows=repro_sub,
            operational_event_rows=op_sub,
            asof_date=asof_date,
            config=config,
        )
        rows.append({
            'animal_id': animal_id,
            'repro_state': state['state'],
            'repro_state_label': state['state_label'],
            'repro_reason_code': state['reason_code'],
            'repro_reason_label': state['reason_label'],
            'repro_attention': state['attention_required'],
            'last_bred_date': state['dates'].get('last_bred_date'),
            'next_preg_check_due_date': state['dates'].get('next_preg_check_due_date'),
            'services_since_calving': state['metrics'].get('services_since_calving'),
            'days_in_milk': state['metrics'].get('days_in_milk'),
            'days_since_bred': state['metrics'].get('days_since_bred'),
        })
    return pd.DataFrame(rows)


def load_reproduction_state_snapshot(
    *,
    input_dir: Path,
    animal_id: str,
    asof_date: date,
    operational_events: Sequence[Mapping[str, Any]] | pd.DataFrame | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    base = Path(input_dir)
    animals = _read_csv(base / 'dm_animals.csv')
    lact = _read_csv(base / 'dm_lactations.csv')
    repro = _read_csv(base / 'dm_repro_events.csv')
    animal_id = str(animal_id or '').strip()
    animals_sub = animals[animals.get('animal_id', pd.Series(dtype=object)).astype(str) == animal_id].copy() if not animals.empty else pd.DataFrame()
    lact_sub = lact[lact.get('animal_id', pd.Series(dtype=object)).astype(str) == animal_id].copy() if not lact.empty else pd.DataFrame()
    repro_sub = repro[repro.get('animal_id', pd.Series(dtype=object)).astype(str) == animal_id].copy() if not repro.empty else pd.DataFrame()
    animal_row = dict(animals_sub.iloc[0]) if not animals_sub.empty else {'animal_id': animal_id}
    return compute_reproduction_state(
        animal_row=animal_row,
        lactation_rows=lact_sub,
        repro_event_rows=repro_sub,
        operational_event_rows=operational_events,
        asof_date=asof_date,
        config=config,
    )


def reproduction_state_options() -> tuple[str, ...]:
    return tuple(sorted(REPRODUCTION_STATES))


def reproduction_reason_code_options() -> tuple[str, ...]:
    return tuple(sorted(REPRODUCTION_REASON_CODES))


__all__ = [
    'DEFAULT_REPRO_CONFIG',
    'STATE_LABELS',
    'REASON_LABELS',
    'build_reproduction_states_table',
    'compute_reproduction_state',
    'load_reproduction_state_snapshot',
    'reproduction_state_options',
    'reproduction_reason_code_options',
]
