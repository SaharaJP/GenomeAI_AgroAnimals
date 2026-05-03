from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from core.audit import write_audit
from core.economics.cow_value_culling import _read_csv, _clean, _safe_float, _safe_int
from core.list_builder import _build_animals_df
from core.reproduction import build_reproduction_states_table
from core.workflow import create_worklist_use_case

DEFAULT_CFG_PATH = Path("configs/economics/fresh_cows_transition_economics_v1.yaml")


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
        'version': 'fresh_cows_transition_economics_v1',
        'label': 'Fresh cows / transition economics v1',
        'fresh_days': 30,
        'weekly_bucket_days': 7,
        'repro_watch_dim_start': 14,
        'min_avg_milk_7d_kg': 28.0,
        'warning_scc_threshold': 200000,
        'critical_scc_threshold': 400000,
        'base_transition_risk_cost_rub': 1800.0,
        'low_milk_penalty_rub': 2800.0,
        'health_event_penalty_rub': 1100.0,
        'active_treatment_penalty_rub': 2200.0,
        'high_scc_penalty_rub': 1600.0,
        'high_parity_penalty_rub': 700.0,
        'vet_action_cost_rub': 1200.0,
        'repro_action_cost_rub': 700.0,
        'quality_action_cost_rub': 850.0,
        'monitor_action_cost_rub': 450.0,
        'vet_mitigation_rate': 0.55,
        'repro_mitigation_rate': 0.40,
        'quality_mitigation_rate': 0.35,
        'monitor_mitigation_rate': 0.20,
        'delay_window_days': 7,
        'high_risk_threshold': 0.65,
        'medium_risk_threshold': 0.40,
        'group_high_risk_share_threshold_pct': 25.0,
        'followup_due_days': 2,
    }
    defaults.update(cfg)
    return path, defaults


def describe_fresh_transition_inputs_version(*, project_root: Path | None = None, cfg_path: str | Path | None = None) -> dict[str, Any]:
    path, cfg = _load_cfg(project_root=project_root, cfg_path=cfg_path)
    raw = path.read_bytes() if path.exists() else json.dumps(cfg, ensure_ascii=False).encode('utf-8')
    digest = hashlib.sha1(raw).hexdigest()[:12]
    return {
        'economics_inputs_version': f"{_clean(cfg.get('version')) or 'fresh_cows_transition_economics_v1'}::{path.as_posix()}::{digest}",
        'config_path': path.as_posix(),
        'config_version': _clean(cfg.get('version')) or 'fresh_cows_transition_economics_v1',
        'config_digest': digest,
        'label': _clean(cfg.get('label')) or 'Fresh cows / transition economics',
    }


def _build_base_rows(*, input_dir: Path, asof_date: date, animal_id: str | None = None, farm_id: str | None = None, site_id: str | None = None, pen_id: str | None = None, cfg: Mapping[str, Any]) -> tuple[pd.DataFrame, list[str]]:
    caveats: list[str] = []
    animals_ctx = _build_animals_df(input_dir=input_dir, asof_date=asof_date)
    animals_raw = _read_csv(input_dir / 'dm_animals.csv')
    lact = _read_csv(input_dir / 'dm_lactations.csv')
    repro = _read_csv(input_dir / 'dm_repro_events.csv')
    if animals_ctx.empty or animals_raw.empty:
        return pd.DataFrame(), ['Нет dm_animals.csv: fresh cows / transition слой недоступен.']
    states = build_reproduction_states_table(
        animals_df=animals_raw,
        lactations_df=lact,
        repro_events_df=repro,
        operational_events_df=pd.DataFrame(),
        asof_date=asof_date,
        animal_ids=[str(x) for x in animals_raw.get('animal_id', pd.Series(dtype=object)).dropna().astype(str).tolist()],
        config={},
    )
    rows = animals_ctx.merge(states, on='animal_id', how='left')
    rows['days_in_milk'] = pd.to_numeric(rows.get('days_in_milk'), errors='coerce')
    rows['avg_milk_7d'] = pd.to_numeric(rows.get('avg_milk_7d'), errors='coerce')
    rows['latest_scc_cells_ml'] = pd.to_numeric(rows.get('latest_scc_cells_ml'), errors='coerce')
    rows['parity'] = pd.to_numeric(rows.get('parity'), errors='coerce')
    fresh_days = int(cfg.get('fresh_days') or 30)
    rows = rows[(rows['days_in_milk'].notna()) & (rows['days_in_milk'] >= 0) & (rows['days_in_milk'] <= fresh_days)].copy()
    if animal_id:
        rows = rows[rows['animal_id'].astype(str) == str(animal_id)].copy()
    if farm_id:
        rows = rows[rows['farm_id'].astype(str).str.lower() == str(farm_id).strip().lower()].copy()
    if site_id:
        rows = rows[rows['site_id'].astype(str).str.lower() == str(site_id).strip().lower()].copy()
    if pen_id:
        rows = rows[rows['pen_id'].astype(str).str.lower() == str(pen_id).strip().lower()].copy()
    if rows.empty:
        caveats.append(f'Нет животных в fresh/transition окне 0..{fresh_days} DIM для выбранного среза.')
        return rows, caveats
    if rows['avg_milk_7d'].isna().sum() > 0:
        caveats.append(f"Для {int(rows['avg_milk_7d'].isna().sum())} fresh cows нет avg_milk_7d; low-milk penalty не применяется к этим строкам.")
    if rows['latest_scc_cells_ml'].isna().sum() > 0:
        caveats.append(f"Для {int(rows['latest_scc_cells_ml'].isna().sum())} fresh cows нет latest SCC; quality contribution считается как NA.")
    return rows, caveats


def _risk_and_action(row: Mapping[str, Any], cfg: Mapping[str, Any]) -> tuple[float, str, str, int, list[dict[str, Any]], float, float, float]:
    dim = _safe_int(row.get('days_in_milk')) or 0
    milk = _safe_float(row.get('avg_milk_7d'))
    scc = _safe_int(row.get('latest_scc_cells_ml'))
    health_events = _safe_int(row.get('recent_health_events')) or 0
    active_tx = _safe_int(row.get('active_treatments')) or 0
    parity = _safe_int(row.get('parity')) or 0
    risk = 0.15
    factors: list[dict[str, Any]] = []
    if dim <= 7:
        risk += 0.18
        factors.append({'factor': 'days_in_milk', 'value': dim, 'effect_direction': 'risk_up', 'note': 'Ранняя свежая корова: первый недельный window повышает transition risk.'})
    else:
        factors.append({'factor': 'days_in_milk', 'value': dim, 'effect_direction': 'neutral', 'note': 'Животное находится в fresh/transition окне.'})
    min_milk = float(cfg.get('min_avg_milk_7d_kg') or 28.0)
    if milk is not None and milk < min_milk:
        risk += 0.22
        factors.append({'factor': 'avg_milk_7d', 'value': milk, 'effect_direction': 'risk_up', 'note': f'Надой ниже порога {min_milk:.1f} кг в fresh-периоде.'})
    else:
        factors.append({'factor': 'avg_milk_7d', 'value': milk if milk is not None else 'NA', 'effect_direction': 'neutral', 'note': 'Последний 7-дневный надой.'})
    if health_events > 0:
        risk += min(0.22, 0.12 * health_events)
        factors.append({'factor': 'recent_health_events_30d', 'value': health_events, 'effect_direction': 'risk_up', 'note': 'Недавние health events повышают transition risk.'})
    else:
        factors.append({'factor': 'recent_health_events_30d', 'value': 0, 'effect_direction': 'neutral', 'note': 'Нет недавних health events.'})
    if active_tx > 0:
        risk += 0.20
        factors.append({'factor': 'active_treatments', 'value': active_tx, 'effect_direction': 'risk_up', 'note': 'Активное лечение в fresh-периоде требует vet follow-up.'})
    else:
        factors.append({'factor': 'active_treatments', 'value': 0, 'effect_direction': 'neutral', 'note': 'Активных лечений нет.'})
    warn_scc = int(cfg.get('warning_scc_threshold') or 200000)
    crit_scc = int(cfg.get('critical_scc_threshold') or 400000)
    if scc is not None and scc >= crit_scc:
        risk += 0.25
        factors.append({'factor': 'latest_scc_cells_ml', 'value': scc, 'effect_direction': 'risk_up', 'note': 'Critical SCC в fresh-периоде.'})
    elif scc is not None and scc >= warn_scc:
        risk += 0.15
        factors.append({'factor': 'latest_scc_cells_ml', 'value': scc, 'effect_direction': 'risk_up', 'note': 'Повышенный SCC: нужен quality follow-up.'})
    else:
        factors.append({'factor': 'latest_scc_cells_ml', 'value': scc if scc is not None else 'NA', 'effect_direction': 'neutral', 'note': 'Последний доступный SCC.'})
    if parity >= 3:
        risk += 0.05
        factors.append({'factor': 'parity', 'value': parity, 'effect_direction': 'risk_up', 'note': 'Более высокая лактация увеличивает нагрузку в fresh-периоде.'})
    else:
        factors.append({'factor': 'parity', 'value': parity if parity else 'NA', 'effect_direction': 'neutral', 'note': 'Номер лактации.'})
    risk = max(0.0, min(1.0, risk))
    lane = 'monitor'
    action = 'weekly_transition_check'
    if active_tx > 0 or health_events > 0:
        lane = 'vet'
        action = 'inspect_fresh_health'
    elif scc is not None and scc >= warn_scc:
        lane = 'quality'
        action = 'review_scc_and_milk_protocol'
    elif dim >= int(cfg.get('repro_watch_dim_start') or 14):
        lane = 'repro'
        action = 'schedule_transition_repro_check'
    if risk >= float(cfg.get('high_risk_threshold') or 0.65):
        priority = 1
    elif risk >= float(cfg.get('medium_risk_threshold') or 0.40):
        priority = 2
    else:
        priority = 3

    base_loss = float(cfg.get('base_transition_risk_cost_rub') or 0.0)
    if milk is not None and milk < min_milk:
        base_loss += float(cfg.get('low_milk_penalty_rub') or 0.0)
    base_loss += health_events * float(cfg.get('health_event_penalty_rub') or 0.0)
    base_loss += active_tx * float(cfg.get('active_treatment_penalty_rub') or 0.0)
    if scc is not None and scc >= warn_scc:
        base_loss += float(cfg.get('high_scc_penalty_rub') or 0.0)
    if parity >= 3:
        base_loss += float(cfg.get('high_parity_penalty_rub') or 0.0)
    expected_loss = round(base_loss * risk, 2)
    action_cost = {
        'vet': float(cfg.get('vet_action_cost_rub') or 0.0),
        'repro': float(cfg.get('repro_action_cost_rub') or 0.0),
        'quality': float(cfg.get('quality_action_cost_rub') or 0.0),
        'monitor': float(cfg.get('monitor_action_cost_rub') or 0.0),
    }[lane]
    mitigation = {
        'vet': float(cfg.get('vet_mitigation_rate') or 0.0),
        'repro': float(cfg.get('repro_mitigation_rate') or 0.0),
        'quality': float(cfg.get('quality_mitigation_rate') or 0.0),
        'monitor': float(cfg.get('monitor_mitigation_rate') or 0.0),
    }[lane]
    expected_gain = round(expected_loss * mitigation, 2)
    delay = round(expected_loss / max(1, int(cfg.get('delay_window_days') or 7)), 2)
    return risk, lane, action, priority, factors, expected_loss, expected_gain, delay


def _weekly_rows(df: pd.DataFrame, cfg: Mapping[str, Any]) -> list[dict[str, Any]]:
    if df.empty:
        return []
    bucket_days = max(1, int(cfg.get('weekly_bucket_days') or 7))
    work = df.copy()
    work['dim_week'] = ((pd.to_numeric(work.get('days_in_milk'), errors='coerce').fillna(0).astype(int)) // bucket_days) + 1
    agg = work.groupby('dim_week', as_index=False).agg(
        cows_n=('animal_id', 'nunique'),
        high_risk_n=('risk_band', lambda s: int((pd.Series(s).astype(str) == 'high').sum())),
        expected_loss_rub=('expected_loss_rub', 'sum'),
        expected_gain_rub=('expected_gain_rub', 'sum'),
    )
    return agg.to_dict(orient='records')


def _group_rows(df: pd.DataFrame, cfg: Mapping[str, Any]) -> list[dict[str, Any]]:
    if df.empty:
        return []
    work = df.copy()
    grp = work.groupby(['farm_id','site_id','pen_id','pen_name'], as_index=False).agg(
        cows_n=('animal_id','nunique'),
        high_risk_n=('risk_band', lambda s: int((pd.Series(s).astype(str) == 'high').sum())),
        avg_risk_score=('risk_score','mean'),
        expected_loss_rub=('expected_loss_rub','sum'),
        expected_gain_rub=('expected_gain_rub','sum'),
    )
    out=[]
    threshold = float(cfg.get('group_high_risk_share_threshold_pct') or 25.0)
    for rec in grp.to_dict(orient='records'):
        cows_n = int(rec.get('cows_n') or 0)
        high_n = int(rec.get('high_risk_n') or 0)
        share = (high_n / cows_n * 100.0) if cows_n else 0.0
        lane = 'vet' if high_n > 0 else 'monitor'
        if share >= threshold:
            action='conduct_transition_round'
            priority=1
        elif float(rec.get('avg_risk_score') or 0.0) >= float(cfg.get('medium_risk_threshold') or 0.40):
            action='review_transition_group'
            priority=2
        else:
            action='monitor_group_transition'
            priority=3
        out.append({
            'level':'group','object_type':'group','object_id':_clean(rec.get('pen_id')),'farm_id':_clean(rec.get('farm_id')),'site_id':_clean(rec.get('site_id')),
            'pen_id':_clean(rec.get('pen_id')),'pen_name':_clean(rec.get('pen_name')),'cows_n':cows_n,'high_risk_n':high_n,
            'high_risk_share_pct':round(share,2),'avg_risk_score':round(float(rec.get('avg_risk_score') or 0.0),4),
            'expected_loss_rub':round(float(rec.get('expected_loss_rub') or 0.0),2),'expected_gain_rub':round(float(rec.get('expected_gain_rub') or 0.0),2),
            'workflow_lane':lane,'suggested_action':action,'action_priority':priority,
            'linked_source_facts':[{'fact':'high_risk_n','value':high_n},{'fact':'high_risk_share_pct','value':round(share,2)},{'fact':'expected_loss_rub','value':round(float(rec.get('expected_loss_rub') or 0.0),2)}],
        })
    out.sort(key=lambda r: (int(r.get('action_priority') or 9), -float(r.get('expected_loss_rub') or 0.0), -float(r.get('high_risk_share_pct') or 0.0)))
    return out


def build_fresh_cows_transition_snapshot(*, input_dir: Path, asof_date: date, project_root: Path | None = None, cfg_path: str | Path | None = None, animal_id: str | None = None, farm_id: str | None = None, site_id: str | None = None, pen_id: str | None = None, data_version: str | None = None) -> dict[str, Any]:
    _, cfg = _load_cfg(project_root=project_root, cfg_path=cfg_path)
    version = describe_fresh_transition_inputs_version(project_root=project_root, cfg_path=cfg_path)
    rows, caveats = _build_base_rows(input_dir=Path(input_dir), asof_date=asof_date, animal_id=animal_id, farm_id=farm_id, site_id=site_id, pen_id=pen_id, cfg=cfg)
    if rows.empty:
        return {
            'schema':'genomeai.fresh_cows_transition_economics.v1',
            'asof_date':asof_date.isoformat(),
            'data_version':_clean(data_version),
            'animal_id':_clean(animal_id), 'farm_id':_clean(farm_id), 'site_id':_clean(site_id), 'pen_id':_clean(pen_id),
            **version,
            'summary_metrics':{},'weekly_monitoring':[],'animal_rows':[],'group_rows':[],'action_lists':{'vet':[],'repro':[],'quality':[],'monitor':[],'groups':[]},
            'formula_rows':[
                {'metric':'fresh_scope','formula':f"0 <= DIM <= {int(cfg.get('fresh_days') or 30)}"},
                {'metric':'risk_score','formula':'bounded additive score from DIM, avg_milk_7d, recent_health_events, active_treatments, SCC and parity'},
                {'metric':'expected_loss_rub','formula':'risk_score * base_transition_risk_cost and visible penalties'},
                {'metric':'expected_gain_rub','formula':'expected_loss_rub * workflow mitigation rate'},
            ],
            'quality_caveats':caveats,
            'source_links':[{'source':'dm_animals.csv'},{'source':'dm_lactations.csv'},{'source':'dm_repro_events.csv'},{'source':'dm_health_events.csv'},{'source':'dm_treatments.csv'},{'source':'dm_testday.csv or latest lactation SCC'}],
        }
    animal_rows=[]
    for rec in rows.to_dict(orient='records'):
        risk, lane, action, priority, factors, exp_loss, exp_gain, delay = _risk_and_action(rec, cfg)
        band = 'high' if risk >= float(cfg.get('high_risk_threshold') or 0.65) else ('medium' if risk >= float(cfg.get('medium_risk_threshold') or 0.40) else 'low')
        animal_rows.append({
            'level':'animal','object_type':'animal','object_id':_clean(rec.get('animal_id')),'animal_id':_clean(rec.get('animal_id')),
            'farm_id':_clean(rec.get('farm_id')),'site_id':_clean(rec.get('site_id')),'pen_id':_clean(rec.get('pen_id')),'pen_name':_clean(rec.get('pen_name')),
            'status':_clean(rec.get('status')) or 'active','parity':_safe_int(rec.get('parity')),'days_in_milk':_safe_int(rec.get('days_in_milk')),
            'avg_milk_7d':_safe_float(rec.get('avg_milk_7d')),'latest_scc_cells_ml':_safe_int(rec.get('latest_scc_cells_ml')),
            'recent_health_events_30d':_safe_int(rec.get('recent_health_events')) or 0,'active_treatments':_safe_int(rec.get('active_treatments')) or 0,
            'repro_state':_clean(rec.get('repro_state')),'repro_state_label':_clean(rec.get('repro_state_label')),
            'risk_score':round(risk,4),'risk_band':band,'workflow_lane':lane,'suggested_action':action,'action_priority':priority,
            'expected_loss_rub':exp_loss,'expected_gain_rub':exp_gain,'cost_of_delay_per_day_rub':delay,
            'linked_source_facts':[{'fact':'days_in_milk','value':_safe_int(rec.get('days_in_milk'))},{'fact':'avg_milk_7d','value':_safe_float(rec.get('avg_milk_7d'))},{'fact':'latest_scc_cells_ml','value':_safe_int(rec.get('latest_scc_cells_ml'))},{'fact':'recent_health_events_30d','value':_safe_int(rec.get('recent_health_events')) or 0},{'fact':'active_treatments','value':_safe_int(rec.get('active_treatments')) or 0}],
            'factors':factors,
        })
    adf = pd.DataFrame(animal_rows)
    group_rows = _group_rows(adf, cfg)
    weekly = _weekly_rows(adf, cfg)
    summary = {
        'fresh_cows_n': int(adf['animal_id'].nunique()),
        'high_risk_n': int((adf['risk_band'] == 'high').sum()),
        'expected_loss_rub': round(float(adf['expected_loss_rub'].sum() or 0.0),2),
        'expected_gain_rub': round(float(adf['expected_gain_rub'].sum() or 0.0),2),
        'avg_risk_score': round(float(adf['risk_score'].mean() or 0.0),4),
    }
    action_lists = {
        'vet': [r for r in animal_rows if r.get('workflow_lane') == 'vet' and int(r.get('action_priority') or 9) <= 2][:30],
        'repro': [r for r in animal_rows if r.get('workflow_lane') == 'repro' and int(r.get('action_priority') or 9) <= 2][:30],
        'quality': [r for r in animal_rows if r.get('workflow_lane') == 'quality' and int(r.get('action_priority') or 9) <= 2][:30],
        'monitor': [r for r in animal_rows if r.get('workflow_lane') == 'monitor' and int(r.get('action_priority') or 9) <= 2][:30],
        'groups': [r for r in group_rows if int(r.get('action_priority') or 9) <= 2][:20],
    }
    return {
        'schema':'genomeai.fresh_cows_transition_economics.v1',
        'asof_date':asof_date.isoformat(),'data_version':_clean(data_version),
        'animal_id':_clean(animal_id),'farm_id':_clean(farm_id) or _clean(adf['farm_id'].mode().iloc[0] if not adf.empty and not adf['farm_id'].dropna().empty else ''),
        'site_id':_clean(site_id),'pen_id':_clean(pen_id),
        **version,
        'summary_metrics':summary,
        'weekly_monitoring':weekly,
        'animal_rows':animal_rows,
        'group_rows':group_rows,
        'action_lists':action_lists,
        'formula_rows':[
            {'metric':'fresh_scope','formula':f"0 <= DIM <= {int(cfg.get('fresh_days') or 30)}"},
            {'metric':'risk_score','formula':'0.15 base + DIM week + low milk + health events + active treatments + SCC + parity, clipped to 0..1'},
            {'metric':'expected_loss_rub','formula':'risk_score * (base_transition_risk_cost + visible penalties)'},
            {'metric':'expected_gain_rub','formula':'expected_loss_rub * workflow mitigation rate'},
            {'metric':'cost_of_delay_per_day_rub','formula':'expected_loss_rub / delay_window_days'},
        ],
        'quality_caveats':caveats,
        'source_links':[{'source':'dm_animals.csv'},{'source':'dm_lactations.csv'},{'source':'dm_repro_events.csv'},{'source':'dm_health_events.csv','window_days':30},{'source':'dm_treatments.csv'},{'source':'dm_testday.csv or latest lactation SCC'}],
    }


def create_fresh_transition_followup_worklist_use_case(*, conn, tenant_id: str, user_id: int, username: str, role: str, snapshot: Mapping[str, Any], target_level: str, target_id: str, due_at: str | None = None, request_id: str | None = None) -> dict[str, Any]:
    level = _clean(target_level).lower()
    object_id = _clean(target_id)
    if level not in {'animal','group'}:
        raise ValueError(f'invalid_target_level: {target_level}')
    rows = list(snapshot.get('animal_rows') or []) if level == 'animal' else list(snapshot.get('group_rows') or [])
    row = next((dict(r) for r in rows if _clean(r.get('object_id') or r.get('animal_id') or r.get('pen_id')) == object_id), None)
    if not row:
        raise ValueError(f'fresh_transition_target_not_found: {level}:{object_id}')
    _, cfg = _load_cfg()
    try:
        asof = date.fromisoformat(_clean(snapshot.get('asof_date'))[:10]) if _clean(snapshot.get('asof_date')) else date.today()
    except Exception:
        asof = date.today()
    due_iso = _clean(due_at) or (asof + timedelta(days=int(cfg.get('followup_due_days') or 2))).isoformat()
    lane = _clean(row.get('workflow_lane')) or 'monitor'
    if lane == 'repro':
        wl_type, team = 'reproduction', 'team-repro'
    elif lane == 'quality':
        wl_type, team = 'milk_quality', 'team-health'
    elif lane == 'monitor':
        wl_type, team = 'manager_review', 'team-health'
    else:
        wl_type, team = 'health_follow_up', 'team-health'
    why = {
        'summary': f"Fresh cows / transition follow-up · {row.get('suggested_action')}",
        'engine': 'fresh_cows_transition_economics_v1',
        'workflow_lane': lane,
        'risk_score': row.get('risk_score'),
        'risk_band': row.get('risk_band'),
        'expected_loss_rub': row.get('expected_loss_rub'),
        'expected_gain_rub': row.get('expected_gain_rub'),
        'economics_inputs_version': snapshot.get('economics_inputs_version'),
    }
    todo = [
        {'action':'Review fresh/transition risk context'},
        {'action':str(row.get('suggested_action') or 'review_transition_case')},
    ]
    res = create_worklist_use_case(
        conn=conn, tenant_id=str(tenant_id), worklist_type=wl_type, user_id=int(user_id), username=str(username), role=str(role),
        title=f"Fresh transition follow-up · {object_id}", priority=int(row.get('action_priority') or 2), due_at=due_iso,
        object_type='animal' if level == 'animal' else 'group', object_id=object_id, assignee_team=team,
        linked_source_facts=list(row.get('linked_source_facts') or []), why=why, what_to_do=todo,
        data_version=_clean(snapshot.get('data_version')) or None, request_id=request_id,
    )
    write_audit(
        conn, tenant_id=str(tenant_id), user_id=int(user_id), username=str(username), role=str(role),
        action='fresh_transition.worklist.create', object_type='worklist', object_id=str(res.get('worklist_id') or ''),
        data_version=_clean(snapshot.get('data_version')) or None, run_id=None,
        after={'worklist_id': res.get('worklist_id'), 'target_level': level, 'target_id': object_id, 'workflow_lane': lane, 'economics_inputs_version': snapshot.get('economics_inputs_version')},
        request_id=request_id,
    )
    return {'worklist_id': res.get('worklist_id'), 'worklist': res.get('after') or {}, 'why': why}


__all__ = [
    'DEFAULT_CFG_PATH',
    'describe_fresh_transition_inputs_version',
    'build_fresh_cows_transition_snapshot',
    'create_fresh_transition_followup_worklist_use_case',
]
