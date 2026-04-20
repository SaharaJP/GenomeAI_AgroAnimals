from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from core.audit import write_audit
from core.list_builder import _build_animals_df
from core.workflow import create_worklist_use_case

DEFAULT_CFG_PATH = Path('configs/economics/milk_quality_scc_cockpit_v1.yaml')


def _clean(value: Any) -> str:
    return str(value or '').strip()



def _read_csv(path: Path) -> pd.DataFrame:
    try:
        if Path(path).exists():
            return pd.read_csv(path)
    except Exception:
        pass
    return pd.DataFrame()



def _resolve_cfg_path(*, project_root: Path | None = None, cfg_path: str | Path | None = None) -> Path:
    if cfg_path is not None:
        p = Path(cfg_path)
        if p.is_absolute():
            return p
        return (project_root or Path.cwd()) / p
    return (project_root or Path.cwd()) / DEFAULT_CFG_PATH



def _load_cfg(*, project_root: Path | None = None, cfg_path: str | Path | None = None) -> tuple[Path, dict[str, Any]]:
    path = _resolve_cfg_path(project_root=project_root, cfg_path=cfg_path)
    try:
        import yaml  # type: ignore
        raw = yaml.safe_load(path.read_text(encoding='utf-8')) if path.exists() else {}
        cfg = dict(raw or {})
    except Exception:
        cfg = {}
    defaults = {
        'version': 'milk_quality_scc_cockpit_v1',
        'label': 'Milk quality / SCC cockpit v1',
        'target_bulk_tank_scc': 200000,
        'warning_bulk_tank_scc': 250000,
        'high_bulk_tank_scc': 350000,
        'action_scc_threshold': 200000,
        'critical_scc_threshold': 300000,
        'active_withdrawal_priority': 1,
        'mastitis_event_window_days': 30,
        'followup_due_days': 2,
        'penalty_bonus_tiers': [
            {'max_scc': 150000, 'adjustment_rub_per_kg': 0.8, 'label': 'bonus_high_quality'},
            {'max_scc': 200000, 'adjustment_rub_per_kg': 0.2, 'label': 'bonus_standard'},
            {'max_scc': 300000, 'adjustment_rub_per_kg': 0.0, 'label': 'neutral'},
            {'max_scc': 400000, 'adjustment_rub_per_kg': -0.8, 'label': 'penalty_attention'},
            {'max_scc': None, 'adjustment_rub_per_kg': -2.0, 'label': 'penalty_critical'},
        ],
    }
    defaults.update(cfg)
    return path, defaults



def describe_milk_quality_inputs_version(*, project_root: Path | None = None, cfg_path: str | Path | None = None) -> dict[str, Any]:
    path, cfg = _load_cfg(project_root=project_root, cfg_path=cfg_path)
    raw = path.read_bytes() if path.exists() else json.dumps(cfg, ensure_ascii=False).encode('utf-8')
    digest = hashlib.sha1(raw).hexdigest()[:12]
    return {
        'economics_inputs_version': f"{_clean(cfg.get('version')) or 'milk_quality_scc_cockpit_v1'}::{path.as_posix()}::{digest}",
        'config_path': path.as_posix(),
        'config_version': _clean(cfg.get('version')) or 'milk_quality_scc_cockpit_v1',
        'config_digest': digest,
        'label': _clean(cfg.get('label')) or 'Milk quality / SCC cockpit',
    }



def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, '', 'NA'):
            return None
        x = float(value)
    except Exception:
        return None
    if pd.isna(x):
        return None
    return float(x)



def _safe_int(value: Any) -> int | None:
    try:
        if value in (None, '', 'NA'):
            return None
        return int(float(value))
    except Exception:
        return None



def _select_adjustment(estimated_scc: float | None, tiers: list[dict[str, Any]]) -> dict[str, Any]:
    if estimated_scc is None:
        return {'label': 'unknown', 'adjustment_rub_per_kg': 0.0, 'max_scc': None}
    for tier in tiers:
        max_scc = tier.get('max_scc')
        if max_scc in (None, '', 'NA'):
            return dict(tier)
        try:
            if float(estimated_scc) <= float(max_scc):
                return dict(tier)
        except Exception:
            continue
    return dict(tiers[-1] if tiers else {'label': 'unknown', 'adjustment_rub_per_kg': 0.0, 'max_scc': None})



def _latest_daily_rows(*, input_dir: Path, asof_date: date) -> tuple[pd.DataFrame, str | None, list[str]]:
    milk = _read_csv(Path(input_dir) / 'dm_milkings_daily.csv')
    caveats: list[str] = []
    if milk.empty:
        caveats.append('Отсутствует dm_milkings_daily.csv: cockpit не может оценить bulk tank SCC без суточных milk/SCC данных.')
        return pd.DataFrame(), None, caveats
    if 'date' not in milk.columns or 'animal_id' not in milk.columns:
        caveats.append('В dm_milkings_daily нет обязательных колонок date/animal_id.')
        return pd.DataFrame(), None, caveats
    milk = milk.copy()
    milk['date_ts'] = pd.to_datetime(milk['date'], errors='coerce')
    milk['milk_kg'] = pd.to_numeric(milk.get('milk_kg'), errors='coerce')
    milk['scc_cells_ml'] = pd.to_numeric(milk.get('scc_cells_ml'), errors='coerce')
    milk = milk[(milk['date_ts'].notna()) & (milk['date_ts'].dt.date <= asof_date)]
    if milk.empty:
        caveats.append('Нет dm_milkings_daily записей на выбранную дату или раньше.')
        return pd.DataFrame(), None, caveats
    snapshot_date = milk['date_ts'].dt.date.max()
    day = milk[milk['date_ts'].dt.date == snapshot_date].copy()
    missing_scc = int(day['scc_cells_ml'].isna().sum()) if 'scc_cells_ml' in day.columns else len(day)
    missing_milk = int(day['milk_kg'].isna().sum()) if 'milk_kg' in day.columns else len(day)
    if missing_scc > 0:
        caveats.append(f'На snapshot date есть строки без SCC: {missing_scc}. Они исключены из bulk tank estimation.')
    if missing_milk > 0:
        caveats.append(f'На snapshot date есть строки без milk_kg: {missing_milk}. Они исключены из bulk tank estimation.')
    day = day[day['milk_kg'].notna() & day['scc_cells_ml'].notna()].copy()
    if day.empty:
        caveats.append('После исключения строк без milk/SCC snapshot пуст.')
    return day, snapshot_date.isoformat() if snapshot_date else None, caveats



def _health_flags(*, input_dir: Path, asof_date: date) -> pd.DataFrame:
    health = _read_csv(Path(input_dir) / 'dm_health_events.csv')
    if health.empty or 'animal_id' not in health.columns:
        return pd.DataFrame(columns=['animal_id', 'recent_health_events_30d', 'mastitis_events_30d'])
    health = health.copy()
    health['event_ts'] = pd.to_datetime(health.get('event_date'), errors='coerce')
    start = pd.Timestamp(asof_date) - pd.Timedelta(days=29)
    health = health[(health['event_ts'].notna()) & (health['event_ts'] >= start) & (health['event_ts'] <= pd.Timestamp(asof_date) + pd.Timedelta(days=1))]
    if health.empty:
        return pd.DataFrame(columns=['animal_id', 'recent_health_events_30d', 'mastitis_events_30d'])
    et = health.get('event_type', pd.Series(dtype=object)).astype(str).str.lower()
    out = health.groupby('animal_id', as_index=False).agg(recent_health_events_30d=('animal_id', 'size'))
    mast = health[et.str.contains('mastitis|scc|somatic', na=False)].groupby('animal_id', as_index=False).agg(mastitis_events_30d=('animal_id', 'size'))
    return out.merge(mast, on='animal_id', how='left').fillna({'mastitis_events_30d': 0})



def _current_animals_context(*, input_dir: Path, asof_date: date) -> pd.DataFrame:
    df = _build_animals_df(input_dir=Path(input_dir), asof_date=asof_date)
    if df.empty:
        return pd.DataFrame(columns=['animal_id', 'farm_id', 'site_id', 'pen_id', 'pen_name', 'status', 'active_treatments', 'recent_health_events', 'latest_scc_cells_ml'])
    out = df.copy()
    if 'pen_id' not in out.columns and 'current_pen_id' in out.columns:
        out['pen_id'] = out['current_pen_id']
    if 'pen_name' not in out.columns and 'current_pen_name' in out.columns:
        out['pen_name'] = out['current_pen_name']
    return out



def _build_base_rows(*, input_dir: Path, asof_date: date, farm_id: str | None = None, site_id: str | None = None, pen_id: str | None = None) -> tuple[pd.DataFrame, str | None, list[str]]:
    day, snapshot_date, caveats = _latest_daily_rows(input_dir=Path(input_dir), asof_date=asof_date)
    if day.empty:
        return pd.DataFrame(), snapshot_date, caveats
    animals = _current_animals_context(input_dir=Path(input_dir), asof_date=asof_date)
    health = _health_flags(input_dir=Path(input_dir), asof_date=asof_date)
    rows = day.merge(animals, on='animal_id', how='left', suffixes=('', '_animal')).merge(health, on='animal_id', how='left')
    rows['farm_id'] = rows.get('farm_id', pd.Series(dtype=object)).fillna('')
    rows['site_id'] = rows.get('site_id', pd.Series(dtype=object)).fillna('')
    rows['pen_id'] = rows.get('pen_id', pd.Series(dtype=object)).fillna('')
    rows['pen_name'] = rows.get('pen_name', pd.Series(dtype=object)).fillna(rows.get('current_pen_name', pd.Series(dtype=object)).fillna(''))
    rows['status'] = rows.get('status', pd.Series(dtype=object)).fillna('active')
    rows['active_treatments'] = pd.to_numeric(rows.get('active_treatments'), errors='coerce').fillna(0).astype(int)
    rows['recent_health_events_30d'] = pd.to_numeric(rows.get('recent_health_events_30d'), errors='coerce').fillna(0).astype(int)
    rows['mastitis_events_30d'] = pd.to_numeric(rows.get('mastitis_events_30d'), errors='coerce').fillna(0).astype(int)
    if farm_id:
        rows = rows[rows['farm_id'].astype(str).str.lower() == str(farm_id).strip().lower()].copy()
    if site_id:
        rows = rows[rows['site_id'].astype(str).str.lower() == str(site_id).strip().lower()].copy()
    if pen_id:
        rows = rows[rows['pen_id'].astype(str).str.lower() == str(pen_id).strip().lower()].copy()
    return rows, snapshot_date, caveats



def _economic_adjustment(*, total_milk_kg: float, estimated_bulk_tank_scc: float | None, cfg: Mapping[str, Any]) -> dict[str, Any]:
    tier = _select_adjustment(estimated_bulk_tank_scc, list(cfg.get('penalty_bonus_tiers') or []))
    adj = float(tier.get('adjustment_rub_per_kg') or 0.0)
    return {
        'label': _clean(tier.get('label')) or 'unknown',
        'adjustment_rub_per_kg': adj,
        'total_adjustment_rub': round(adj * float(total_milk_kg or 0.0), 2),
        'estimated_bulk_tank_scc': round(float(estimated_bulk_tank_scc), 2) if estimated_bulk_tank_scc is not None else None,
    }



def _contribution_rows(rows: pd.DataFrame, *, level: str, cfg: Mapping[str, Any], economic: Mapping[str, Any]) -> list[dict[str, Any]]:
    target = int(cfg.get('target_bulk_tank_scc') or 200000)
    critical = int(cfg.get('critical_scc_threshold') or 300000)
    if rows.empty:
        return []
    work = rows.copy()
    work['scc_load'] = work['milk_kg'] * work['scc_cells_ml']
    work['excess_load'] = work['milk_kg'] * (work['scc_cells_ml'] - target).clip(lower=0)
    work['bonus_weight'] = work['milk_kg'] * (target - work['scc_cells_ml'].clip(upper=target)).clip(lower=0)
    if level == 'group':
        group_cols = ['farm_id', 'site_id', 'pen_id', 'pen_name']
    else:
        group_cols = ['animal_id', 'farm_id', 'site_id', 'pen_id', 'pen_name', 'status', 'active_treatments', 'recent_health_events_30d', 'mastitis_events_30d']
    agg = work.groupby(group_cols, dropna=False, as_index=False).agg(
        milk_kg=('milk_kg', 'sum'),
        scc_load=('scc_load', 'sum'),
        excess_load=('excess_load', 'sum'),
        bonus_weight=('bonus_weight', 'sum'),
        max_scc_cells_ml=('scc_cells_ml', 'max'),
        avg_scc_cells_ml=('scc_cells_ml', 'mean'),
        animals_n=('animal_id', 'nunique'),
    )
    total_load = float(agg['scc_load'].sum() or 0.0)
    total_excess = float(agg['excess_load'].sum() or 0.0)
    total_bonus_weight = float(agg['bonus_weight'].sum() or 0.0)
    total_adj = float(economic.get('total_adjustment_rub') or 0.0)
    out: list[dict[str, Any]] = []
    for rec in agg.to_dict(orient='records'):
        share_total = float(rec.get('scc_load') or 0.0) / total_load if total_load > 0 else 0.0
        if total_adj < 0 and total_excess > 0:
            share_adj = float(rec.get('excess_load') or 0.0) / total_excess
        elif total_adj > 0 and total_bonus_weight > 0:
            share_adj = float(rec.get('bonus_weight') or 0.0) / total_bonus_weight
        else:
            share_adj = float(rec.get('milk_kg') or 0.0) / float(agg['milk_kg'].sum() or 1.0)
        attributed = round(total_adj * share_adj, 2)
        max_scc = _safe_int(rec.get('max_scc_cells_ml')) or 0
        active_tx = _safe_int(rec.get('active_treatments')) or 0
        mastitis_events = _safe_int(rec.get('mastitis_events_30d')) or 0
        if active_tx > 0:
            action = 'review_withdrawal_and_treatment'
            priority = 1
        elif max_scc >= critical or mastitis_events > 0:
            action = 'inspect_and_sample'
            priority = 1
        elif max_scc >= int(cfg.get('action_scc_threshold') or target):
            action = 'recheck_scc_and_milk_routine'
            priority = 2
        else:
            action = 'monitor'
            priority = 3
        object_type = 'group' if level == 'group' else 'animal'
        object_id = _clean(rec.get('pen_id') if level == 'group' else rec.get('animal_id'))
        facts = [
            {'fact': 'avg_scc_cells_ml', 'value': round(float(rec.get('avg_scc_cells_ml') or 0.0), 2)},
            {'fact': 'max_scc_cells_ml', 'value': max_scc},
            {'fact': 'milk_kg', 'value': round(float(rec.get('milk_kg') or 0.0), 2)},
            {'fact': 'attributed_economic_adjustment_rub', 'value': attributed},
        ]
        if level != 'group':
            facts.extend([
                {'fact': 'active_treatments', 'value': active_tx},
                {'fact': 'mastitis_events_30d', 'value': mastitis_events},
            ])
        out.append({
            'level': level,
            'object_type': object_type,
            'object_id': object_id,
            'animal_id': _clean(rec.get('animal_id')) if level != 'group' else '',
            'farm_id': _clean(rec.get('farm_id')),
            'site_id': _clean(rec.get('site_id')),
            'pen_id': _clean(rec.get('pen_id')),
            'pen_name': _clean(rec.get('pen_name')),
            'status': _clean(rec.get('status')) if level != 'group' else '',
            'animals_n': int(rec.get('animals_n') or 0),
            'milk_kg': round(float(rec.get('milk_kg') or 0.0), 2),
            'avg_scc_cells_ml': round(float(rec.get('avg_scc_cells_ml') or 0.0), 2),
            'max_scc_cells_ml': max_scc,
            'share_of_total_scc_load_pct': round(share_total * 100.0, 2),
            'attributed_economic_adjustment_rub': attributed,
            'suggested_action': action,
            'action_priority': priority,
            'linked_source_facts': facts,
        })
    sort_cols = ['action_priority', 'attributed_economic_adjustment_rub', 'max_scc_cells_ml']
    out_df = pd.DataFrame(out)
    if out_df.empty:
        return []
    out_df = out_df.sort_values(sort_cols, ascending=[True, True, False], na_position='last')
    return out_df.to_dict(orient='records')



def build_milk_quality_scc_snapshot(*, input_dir: Path, asof_date: date, project_root: Path | None = None, cfg_path: str | Path | None = None, farm_id: str | None = None, site_id: str | None = None, pen_id: str | None = None, data_version: str | None = None) -> dict[str, Any]:
    cfg_path_resolved, cfg = _load_cfg(project_root=project_root, cfg_path=cfg_path)
    version = describe_milk_quality_inputs_version(project_root=project_root, cfg_path=cfg_path)
    rows, snapshot_date, caveats = _build_base_rows(input_dir=Path(input_dir), asof_date=asof_date, farm_id=farm_id, site_id=site_id, pen_id=pen_id)
    if rows.empty:
        return {
            'schema': 'genomeai.milk_quality_scc_cockpit.v1',
            'asof_date': asof_date.isoformat(),
            'snapshot_date': snapshot_date,
            'data_version': _clean(data_version),
            'farm_id': _clean(farm_id),
            'site_id': _clean(site_id),
            'pen_id': _clean(pen_id),
            **version,
            'bulk_tank': {},
            'animal_contributions': [],
            'group_contributions': [],
            'action_lists': {'animals': [], 'groups': []},
            'formula_rows': [
                {'metric': 'estimated_bulk_tank_scc', 'formula': 'sum(milk_kg * scc_cells_ml) / sum(milk_kg) on snapshot_date'},
                {'metric': 'economic_adjustment_rub', 'formula': 'tier(adjustment_rub_per_kg by estimated_bulk_tank_scc) * total_milk_kg'},
                {'metric': 'attributed_economic_adjustment_rub', 'formula': 'share of excess SCC load for penalties; share of bonus weight for bonuses'},
            ],
            'quality_caveats': caveats,
            'source_links': [{'source': 'dm_milkings_daily.csv', 'snapshot_date': snapshot_date or 'NA'}],
        }
    rows = rows.copy()
    rows['scc_load'] = rows['milk_kg'] * rows['scc_cells_ml']
    total_milk_kg = float(rows['milk_kg'].sum() or 0.0)
    estimated_bulk = float(rows['scc_load'].sum() / total_milk_kg) if total_milk_kg > 0 else None
    economic = _economic_adjustment(total_milk_kg=total_milk_kg, estimated_bulk_tank_scc=estimated_bulk, cfg=cfg)
    target = int(cfg.get('target_bulk_tank_scc') or 200000)
    bulk_status = 'ok'
    if estimated_bulk is None:
        bulk_status = 'no_data'
    elif estimated_bulk >= int(cfg.get('high_bulk_tank_scc') or 350000):
        bulk_status = 'critical'
    elif estimated_bulk >= int(cfg.get('warning_bulk_tank_scc') or 250000):
        bulk_status = 'warning'
    animal_rows = _contribution_rows(rows, level='animal', cfg=cfg, economic=economic)
    group_rows = _contribution_rows(rows, level='group', cfg=cfg, economic=economic)
    return {
        'schema': 'genomeai.milk_quality_scc_cockpit.v1',
        'asof_date': asof_date.isoformat(),
        'snapshot_date': snapshot_date,
        'data_version': _clean(data_version),
        'farm_id': _clean(farm_id) or _clean(rows['farm_id'].mode().iloc[0] if 'farm_id' in rows.columns and not rows['farm_id'].dropna().empty else ''),
        'site_id': _clean(site_id),
        'pen_id': _clean(pen_id),
        **version,
        'bulk_tank': {
            'estimated_bulk_tank_scc': round(estimated_bulk, 2) if estimated_bulk is not None else None,
            'total_milk_kg': round(total_milk_kg, 2),
            'animals_with_data_n': int(rows['animal_id'].nunique()),
            'status': bulk_status,
            'target_bulk_tank_scc': target,
            'economic_adjustment': economic,
        },
        'animal_contributions': animal_rows,
        'group_contributions': group_rows,
        'action_lists': {
            'animals': [r for r in animal_rows if int(r.get('action_priority') or 9) <= 2][:30],
            'groups': [r for r in group_rows if int(r.get('action_priority') or 9) <= 2][:20],
        },
        'formula_rows': [
            {'metric': 'estimated_bulk_tank_scc', 'formula': 'sum(milk_kg * scc_cells_ml) / sum(milk_kg) on snapshot_date'},
            {'metric': 'economic_adjustment_rub', 'formula': 'tier(adjustment_rub_per_kg by estimated_bulk_tank_scc) * total_milk_kg'},
            {'metric': 'animal/group contribution', 'formula': 'share_of_total_scc_load_pct = scc_load / total_scc_load * 100'},
            {'metric': 'attributed_economic_adjustment_rub', 'formula': 'share of excess SCC load for penalties; share of bonus weight for bonuses'},
        ],
        'quality_caveats': caveats,
        'source_links': [
            {'source': 'dm_milkings_daily.csv', 'snapshot_date': snapshot_date or 'NA'},
            {'source': 'dm_health_events.csv', 'window_days': int(cfg.get('mastitis_event_window_days') or 30)},
            {'source': 'dm_treatments.csv', 'usage': 'active_treatments from current animals context'},
        ],
    }



def create_milk_quality_followup_worklist_use_case(
    *,
    conn,
    tenant_id: str,
    user_id: int,
    username: str,
    role: str,
    snapshot: Mapping[str, Any],
    target_level: str,
    target_id: str,
    due_at: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    level = _clean(target_level).lower()
    object_id = _clean(target_id)
    if level not in {'animal', 'group'}:
        raise ValueError(f'invalid_target_level: {target_level}')
    rows = list(snapshot.get('animal_contributions') or []) if level == 'animal' else list(snapshot.get('group_contributions') or [])
    row = next((dict(r) for r in rows if _clean(r.get('object_id') or r.get('animal_id') or r.get('pen_id')) == object_id), None)
    if not row:
        raise ValueError(f'milk_quality_target_not_found: {target_level}:{target_id}')
    asof_raw = _clean(snapshot.get('asof_date'))
    try:
        base_date = date.fromisoformat(asof_raw[:10]) if asof_raw else date.today()
    except Exception:
        base_date = date.today()
    cfg = _load_cfg()[1]
    due_iso = _clean(due_at) or (base_date + timedelta(days=int(cfg.get('followup_due_days') or 2))).isoformat()
    bulk = dict(snapshot.get('bulk_tank') or {})
    why = {
        'summary': f"Milk quality / SCC follow-up · {row.get('suggested_action')}",
        'bulk_tank_scc': bulk.get('estimated_bulk_tank_scc'),
        'economic_adjustment_rub': (bulk.get('economic_adjustment') or {}).get('total_adjustment_rub'),
        'economics_inputs_version': snapshot.get('economics_inputs_version'),
        'engine': 'milk_quality_scc_cockpit_v1',
    }
    what = [
        {'action': 'Review SCC contribution and milk quality context'},
        {'action': str(row.get('suggested_action') or 'review_milk_quality')},
    ]
    object_type = 'animal' if level == 'animal' else 'group'
    object_id_final = _clean(row.get('animal_id') if level == 'animal' else row.get('pen_id') or row.get('object_id'))
    res = create_worklist_use_case(
        conn=conn,
        tenant_id=str(tenant_id),
        worklist_type='milk_quality',
        user_id=int(user_id),
        username=str(username),
        role=str(role),
        title=f"Milk quality follow-up · {object_id_final}",
        priority=int(row.get('action_priority') or 2),
        due_at=due_iso,
        object_type=object_type,
        object_id=object_id_final,
        assignee_team='team-health',
        linked_source_facts=list(row.get('linked_source_facts') or []),
        why=why,
        what_to_do=what,
        data_version=_clean(snapshot.get('data_version')) or None,
        request_id=request_id,
    )
    write_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id),
        username=str(username),
        role=str(role),
        action='milk_quality.worklist.create',
        object_type='worklist',
        object_id=str(res.get('worklist_id') or ''),
        data_version=_clean(snapshot.get('data_version')) or None,
        run_id=None,
        after={
            'worklist_id': res.get('worklist_id'),
            'target_level': level,
            'target_id': object_id_final,
            'economics_inputs_version': snapshot.get('economics_inputs_version'),
        },
        request_id=request_id,
    )
    return {'worklist_id': res.get('worklist_id'), 'worklist': res.get('after') or {}, 'why': why}
