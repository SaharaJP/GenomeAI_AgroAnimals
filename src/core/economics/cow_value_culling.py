from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from core.audit import write_audit
from core.reproduction import load_reproduction_state_snapshot
from core.workflow import DecisionCreate, append_decision_use_case, create_worklist_use_case
from core.list_builder import _build_animals_df

DEFAULT_CFG_PATH = Path('configs/economics/cow_value_culling_v1.yaml')


@dataclass(frozen=True)
class CowValueContext:
    animal_id: str
    farm_id: str
    site_id: str
    pen_id: str
    pen_name: str
    status: str
    breed: str
    parity: int | None
    avg_milk_7d: float | None
    latest_scc_cells_ml: int | None
    recent_health_events_30d: int
    active_treatments: int
    repro_state: str
    repro_state_label: str
    days_open: int | None
    last_event_date: str


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
        'version': 'cow_value_culling_v1',
        'label': 'Cow value / culling decision engine v1',
        'horizon_days': 30,
        'milk_price_per_kg_rub': 18.0,
        'daily_feed_cost_rub': 135.0,
        'daily_other_cost_rub': 55.0,
        'high_scc_threshold': 200000,
        'high_scc_penalty_rub': 1800.0,
        'health_event_penalty_rub': 900.0,
        'active_treatment_penalty_rub': 2500.0,
        'treatment_followup_cost_rub': 3500.0,
        'treatment_recovery_bonus_rub': 4800.0,
        'repro_open_penalty_rub': 1600.0,
        'repeat_breeder_penalty_rub': 2600.0,
        'breed_expected_bonus_rub': 3200.0,
        'insemination_cost_rub': 750.0,
        'defer_penalty_rub': 1200.0,
        'high_parity_threshold': 4,
        'high_parity_penalty_rub': 1100.0,
        'cull_salvage_value_rub': 28000.0,
        'cull_transaction_cost_rub': 4000.0,
        'replacement_purchase_cost_rub': 72000.0,
        'replacement_expected_daily_margin_rub': 380.0,
        'cull_min_advantage_rub': 5000.0,
        'max_days_open_for_penalty': 120,
    }
    defaults.update(cfg)
    return path, defaults


def describe_cow_value_inputs_version(*, project_root: Path | None = None, cfg_path: str | Path | None = None) -> dict[str, Any]:
    path, cfg = _load_cfg(project_root=project_root, cfg_path=cfg_path)
    raw = path.read_bytes() if path.exists() else json.dumps(cfg, ensure_ascii=False).encode('utf-8')
    digest = hashlib.sha1(raw).hexdigest()[:12]
    return {
        'economics_inputs_version': f"{_clean(cfg.get('version')) or 'cow_value_culling_v1'}::{path.as_posix()}::{digest}",
        'config_path': path.as_posix(),
        'config_version': _clean(cfg.get('version')) or 'cow_value_culling_v1',
        'config_digest': digest,
        'label': _clean(cfg.get('label')) or 'Cow value / culling decision engine',
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
        x = int(float(value))
    except Exception:
        return None
    return x


def _latest_testday_scc(*, input_dir: Path, animal_id: str, asof_date: date) -> int | None:
    td = _read_csv(Path(input_dir) / 'dm_testday.csv')
    if td.empty or 'animal_id' not in td.columns or 'scc_cells_ml' not in td.columns:
        return None
    sub = td[td['animal_id'].astype(str) == str(animal_id)].copy()
    if sub.empty:
        return None
    sub['test_ts'] = pd.to_datetime(sub.get('test_date'), errors='coerce')
    sub = sub.dropna(subset=['test_ts'])
    sub = sub[sub['test_ts'].dt.date <= asof_date]
    if sub.empty:
        return None
    sub = sub.sort_values('test_ts', ascending=False)
    return _safe_int(sub.iloc[0].get('scc_cells_ml'))


def _build_context(*, input_dir: Path, asof_date: date, animal_id: str) -> CowValueContext:
    animals_df = _build_animals_df(input_dir=Path(input_dir), asof_date=asof_date)
    row_df = animals_df[animals_df.get('animal_id', pd.Series(dtype=object)).astype(str) == str(animal_id)].copy()
    if row_df.empty:
        raise ValueError(f'animal_not_found: {animal_id}')
    row = row_df.iloc[0].to_dict()
    latest_scc = _safe_int(row.get('latest_scc_cells_ml'))
    latest_test_scc = _latest_testday_scc(input_dir=Path(input_dir), animal_id=str(animal_id), asof_date=asof_date)
    if latest_test_scc is not None:
        latest_scc = latest_test_scc
    repro = load_reproduction_state_snapshot(input_dir=Path(input_dir), animal_id=str(animal_id), asof_date=asof_date)
    repro_state = _clean(repro.get('state')) or 'no_data'
    repro_state_label = _clean(repro.get('state_label')) or repro_state
    days_open = _safe_int((repro.get('metrics') or {}).get('days_open'))
    last_dates = dict(repro.get('dates') or {})
    last_event_date = _clean(row.get('latest_event_date')) or _clean(last_dates.get('last_bred_date')) or _clean(last_dates.get('last_calving_date')) or '—'
    return CowValueContext(
        animal_id=str(animal_id),
        farm_id=_clean(row.get('farm_id')),
        site_id=_clean(row.get('site_id')),
        pen_id=_clean(row.get('pen_id')),
        pen_name=_clean(row.get('pen_name')),
        status=_clean(row.get('status')) or 'active',
        breed=_clean(row.get('breed')),
        parity=_safe_int(row.get('parity')),
        avg_milk_7d=_safe_float(row.get('avg_milk_7d') if 'avg_milk_7d' in row else None) or _safe_float(row.get('milk_7d_avg')),
        latest_scc_cells_ml=latest_scc,
        recent_health_events_30d=_safe_int(row.get('recent_health_events')) or 0,
        active_treatments=_safe_int(row.get('active_treatments')) or 0,
        repro_state=repro_state,
        repro_state_label=repro_state_label,
        days_open=days_open,
        last_event_date=last_event_date,
    )


def _penalty_breakdown(ctx: CowValueContext, cfg: Mapping[str, Any]) -> tuple[float, float, float, list[dict[str, Any]]]:
    high_scc_threshold = int(cfg.get('high_scc_threshold') or 200000)
    health_penalty = float(ctx.recent_health_events_30d) * float(cfg.get('health_event_penalty_rub') or 0.0)
    health_penalty += float(ctx.active_treatments) * float(cfg.get('active_treatment_penalty_rub') or 0.0)
    if (ctx.latest_scc_cells_ml or 0) >= high_scc_threshold:
        health_penalty += float(cfg.get('high_scc_penalty_rub') or 0.0)

    repro_penalty = 0.0
    if ctx.repro_state in {'open', 'repeat', 'eligible', 'heat', 'preg_check_due'}:
        repro_penalty += float(cfg.get('repro_open_penalty_rub') or 0.0)
    if ctx.repro_state == 'repeat':
        repro_penalty += float(cfg.get('repeat_breeder_penalty_rub') or 0.0)
    if ctx.days_open is not None:
        max_days = int(cfg.get('max_days_open_for_penalty') or 120)
        repro_penalty += max(0.0, min(float(ctx.days_open), float(max_days)) * 10.0)

    parity_penalty = 0.0
    high_parity_threshold = int(cfg.get('high_parity_threshold') or 4)
    if ctx.parity is not None and ctx.parity >= high_parity_threshold:
        parity_penalty += float((ctx.parity - high_parity_threshold + 1) * float(cfg.get('high_parity_penalty_rub') or 0.0))

    factors = [
        {
            'factor': 'avg_milk_7d',
            'value': ctx.avg_milk_7d if ctx.avg_milk_7d is not None else 'NA',
            'effect_direction': 'positive' if (ctx.avg_milk_7d or 0) > 0 else 'neutral',
            'economic_effect_rub': round((ctx.avg_milk_7d or 0.0) * float(cfg.get('milk_price_per_kg_rub') or 0.0) * int(cfg.get('horizon_days') or 30), 2),
            'note': 'Последний 7-дневный надой определяет выручку в горизонте решения.',
        },
        {
            'factor': 'recent_health_events_30d',
            'value': ctx.recent_health_events_30d,
            'effect_direction': 'negative' if ctx.recent_health_events_30d > 0 else 'neutral',
            'economic_effect_rub': round(-float(ctx.recent_health_events_30d) * float(cfg.get('health_event_penalty_rub') or 0.0), 2),
            'note': 'Недавние health events увеличивают риск затрат и снижают ожидаемую ценность.',
        },
        {
            'factor': 'active_treatments',
            'value': ctx.active_treatments,
            'effect_direction': 'negative' if ctx.active_treatments > 0 else 'neutral',
            'economic_effect_rub': round(-float(ctx.active_treatments) * float(cfg.get('active_treatment_penalty_rub') or 0.0), 2),
            'note': 'Активные курсы лечения учитываются как риск затрат и operational burden.',
        },
        {
            'factor': 'latest_scc_cells_ml',
            'value': ctx.latest_scc_cells_ml if ctx.latest_scc_cells_ml is not None else 'NA',
            'effect_direction': 'negative' if (ctx.latest_scc_cells_ml or 0) >= high_scc_threshold else 'neutral',
            'economic_effect_rub': round(-float(cfg.get('high_scc_penalty_rub') or 0.0) if (ctx.latest_scc_cells_ml or 0) >= high_scc_threshold else 0.0, 2),
            'note': f'Порог high SCC = {high_scc_threshold}.',
        },
        {
            'factor': 'repro_state',
            'value': ctx.repro_state_label,
            'effect_direction': 'negative' if ctx.repro_state in {'open', 'repeat', 'eligible', 'heat', 'preg_check_due'} else 'positive' if ctx.repro_state in {'pregnant', 'bred'} else 'neutral',
            'economic_effect_rub': round(-repro_penalty, 2),
            'note': 'Repro state влияет на вероятность keep/breed vs defer/cull.',
        },
        {
            'factor': 'parity',
            'value': ctx.parity if ctx.parity is not None else 'NA',
            'effect_direction': 'negative' if (ctx.parity or 0) >= high_parity_threshold else 'neutral',
            'economic_effect_rub': round(-parity_penalty, 2),
            'note': f'High parity threshold = {high_parity_threshold}.',
        },
    ]
    return health_penalty, repro_penalty, parity_penalty, factors


def _scenario_rows(ctx: CowValueContext, cfg: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    horizon = int(cfg.get('horizon_days') or 30)
    milk_price = float(cfg.get('milk_price_per_kg_rub') or 0.0)
    daily_feed = float(cfg.get('daily_feed_cost_rub') or 0.0)
    daily_other = float(cfg.get('daily_other_cost_rub') or 0.0)
    keep_base = (float(ctx.avg_milk_7d or 0.0) * milk_price - daily_feed - daily_other) * horizon
    health_penalty, repro_penalty, parity_penalty, factors = _penalty_breakdown(ctx, cfg)
    keep_value = keep_base - health_penalty - repro_penalty - parity_penalty
    replacement_value = float(cfg.get('replacement_expected_daily_margin_rub') or 0.0) * horizon - float(cfg.get('replacement_purchase_cost_rub') or 0.0) + float(cfg.get('cull_salvage_value_rub') or 0.0) - float(cfg.get('cull_transaction_cost_rub') or 0.0)
    cull_value = replacement_value
    treat_enabled = bool(ctx.recent_health_events_30d or ctx.active_treatments or ((ctx.latest_scc_cells_ml or 0) >= int(cfg.get('high_scc_threshold') or 200000)))
    treat_value = keep_value + (float(cfg.get('treatment_recovery_bonus_rub') or 0.0) if treat_enabled else -500.0) - float(cfg.get('treatment_followup_cost_rub') or 0.0)
    breed_enabled = ctx.repro_state in {'open', 'repeat', 'eligible', 'heat', 'preg_check_due', 'fresh'}
    breed_value = keep_value + (float(cfg.get('breed_expected_bonus_rub') or 0.0) if breed_enabled else -750.0) - float(cfg.get('insemination_cost_rub') or 0.0)
    defer_value = keep_value - float(cfg.get('defer_penalty_rub') or 0.0)

    def mk(action: str, label: str, value_rub: float, enabled: bool, requires_confirmation: bool, why: str) -> dict[str, Any]:
        return {
            'action': action,
            'action_label': label,
            'projected_value_rub': round(float(value_rub), 2),
            'delta_vs_keep_rub': round(float(value_rub - keep_value), 2),
            'enabled': bool(enabled),
            'requires_confirmation': bool(requires_confirmation),
            'why': why,
        }

    rows = [
        mk('keep', 'Keep', keep_value, True, False, 'Сохранить корову в стаде с текущим plan-of-care.'),
        mk('breed', 'Breed', breed_value, breed_enabled, False, 'Продолжить keep-path и инвестировать в reproduction step.'),
        mk('treat', 'Treat', treat_value, treat_enabled, False, 'Продолжить keep-path и инвестировать в treatment / follow-up.'),
        mk('cull', 'Cull', cull_value, True, True, 'Сравнить salvage + replacement against keep economics.'),
        mk('defer', 'Defer', defer_value, True, False, 'Отложить решение и пересмотреть позже.'),
    ]
    cull_min_advantage = float(cfg.get('cull_min_advantage_rub') or 5000.0)
    best = max(rows, key=lambda x: float(x['projected_value_rub']))
    if best['action'] == 'cull' and float(best['delta_vs_keep_rub']) < cull_min_advantage:
        best = max([r for r in rows if r['action'] != 'cull'], key=lambda x: float(x['projected_value_rub']))
    if best['action'] == 'keep' and ctx.repro_state in {'open', 'repeat', 'eligible', 'heat', 'preg_check_due'} and breed_enabled and breed_value >= keep_value:
        best = next(r for r in rows if r['action'] == 'breed')
    if best['action'] == 'keep' and treat_enabled and treat_value > keep_value:
        best = next(r for r in rows if r['action'] == 'treat')
    reasoning = {
        'keep_value_rub': round(keep_value, 2),
        'replacement_value_rub': round(replacement_value, 2),
        'delta_keep_vs_replace_rub': round(keep_value - replacement_value, 2),
        'health_penalty_rub': round(health_penalty, 2),
        'repro_penalty_rub': round(repro_penalty, 2),
        'parity_penalty_rub': round(parity_penalty, 2),
        'factors': factors,
        'recommended_action': best['action'],
        'recommended_label': best['action_label'],
        'decision_required': bool(best['requires_confirmation']),
        'recommended_projected_value_rub': round(float(best['projected_value_rub']), 2),
        'recommended_delta_vs_keep_rub': round(float(best['delta_vs_keep_rub']), 2),
    }
    return rows, reasoning


def build_cow_value_snapshot(
    *,
    input_dir: Path,
    asof_date: date,
    animal_id: str,
    project_root: Path | None = None,
    cfg_path: str | Path | None = None,
    data_version: str | None = None,
    report_version: str | None = None,
    model_version: str | None = None,
    scoring_run: str | None = None,
    qc_run: str | None = None,
) -> dict[str, Any]:
    cfg_path_resolved, cfg = _load_cfg(project_root=project_root, cfg_path=cfg_path)
    inputs_version = describe_cow_value_inputs_version(project_root=project_root, cfg_path=cfg_path_resolved)
    ctx = _build_context(input_dir=Path(input_dir), asof_date=asof_date, animal_id=str(animal_id))
    scenarios, reasoning = _scenario_rows(ctx, cfg)
    recommended = next((row for row in scenarios if row['action'] == reasoning['recommended_action']), scenarios[0])
    formula_rows = [
        {'metric': 'keep_value_rub', 'formula': '(avg_milk_7d * milk_price_per_kg_rub - daily_feed_cost_rub - daily_other_cost_rub) * horizon_days - health_penalty - repro_penalty - parity_penalty'},
        {'metric': 'replacement_value_rub', 'formula': 'replacement_expected_daily_margin_rub * horizon_days - replacement_purchase_cost_rub + cull_salvage_value_rub - cull_transaction_cost_rub'},
        {'metric': 'delta_keep_vs_replace_rub', 'formula': 'keep_value_rub - replacement_value_rub'},
        {'metric': 'treat_value_rub', 'formula': 'keep_value_rub + treatment_recovery_bonus_rub - treatment_followup_cost_rub'},
        {'metric': 'breed_value_rub', 'formula': 'keep_value_rub + breed_expected_bonus_rub - insemination_cost_rub'},
        {'metric': 'defer_value_rub', 'formula': 'keep_value_rub - defer_penalty_rub'},
    ]
    source_facts = []
    for item in reasoning['factors']:
        source_facts.append({
            'label': str(item.get('factor') or ''),
            'text': f"{item.get('factor')}: {item.get('value')} · effect={item.get('economic_effect_rub')} RUB",
            'effect_direction': item.get('effect_direction'),
        })
    summary_rows = [
        {'metric': 'keep_value_rub', 'value': reasoning['keep_value_rub']},
        {'metric': 'replacement_value_rub', 'value': reasoning['replacement_value_rub']},
        {'metric': 'delta_keep_vs_replace_rub', 'value': reasoning['delta_keep_vs_replace_rub']},
        {'metric': 'recommended_action', 'value': reasoning['recommended_label']},
        {'metric': 'recommended_delta_vs_keep_rub', 'value': reasoning['recommended_delta_vs_keep_rub']},
    ]
    return {
        'schema': 'genomeai.cow_value_culling.v1',
        'asof_date': asof_date.isoformat(),
        'animal_id': ctx.animal_id,
        'farm_id': ctx.farm_id,
        'site_id': ctx.site_id,
        'pen_id': ctx.pen_id,
        'pen_name': ctx.pen_name,
        'status': ctx.status,
        'breed': ctx.breed,
        'parity': ctx.parity,
        'avg_milk_7d': ctx.avg_milk_7d,
        'latest_scc_cells_ml': ctx.latest_scc_cells_ml,
        'recent_health_events_30d': ctx.recent_health_events_30d,
        'active_treatments': ctx.active_treatments,
        'repro_state': ctx.repro_state,
        'repro_state_label': ctx.repro_state_label,
        'days_open': ctx.days_open,
        'last_event_date': ctx.last_event_date,
        'inputs_version': inputs_version,
        'economics_inputs_version': inputs_version['economics_inputs_version'],
        'config_path': inputs_version['config_path'],
        'config_version': inputs_version['config_version'],
        'config_digest': inputs_version['config_digest'],
        'data_version': _clean(data_version),
        'report_version': _clean(report_version),
        'model_version': _clean(model_version),
        'scoring_run': _clean(scoring_run),
        'qc_run': _clean(qc_run),
        'scenarios': scenarios,
        'factors': reasoning['factors'],
        'summary_rows': summary_rows,
        'formula_rows': formula_rows,
        'replacement_comparison': {
            'keep_value_rub': reasoning['keep_value_rub'],
            'replacement_value_rub': reasoning['replacement_value_rub'],
            'delta_keep_vs_replace_rub': reasoning['delta_keep_vs_replace_rub'],
        },
        'recommended_action': reasoning['recommended_action'],
        'recommended_label': reasoning['recommended_label'],
        'decision_required': reasoning['decision_required'],
        'recommended_projected_value_rub': reasoning['recommended_projected_value_rub'],
        'recommended_delta_vs_keep_rub': reasoning['recommended_delta_vs_keep_rub'],
        'explanation_short': f"{reasoning['recommended_label']} · Δ vs keep {reasoning['recommended_delta_vs_keep_rub']:.0f} ₽ · keep vs replacement {reasoning['delta_keep_vs_replace_rub']:.0f} ₽",
        'linked_source_facts': source_facts,
        'linked_objects': [
            {'object_type': 'animal', 'object_id': ctx.animal_id},
            {'object_type': 'group', 'object_id': ctx.pen_id} if ctx.pen_id else {'object_type': 'group', 'object_id': ''},
        ],
    }


def list_cow_value_candidate_animals(*, input_dir: Path, asof_date: date, filters: Mapping[str, Any] | None = None) -> pd.DataFrame:
    df = _build_animals_df(input_dir=Path(input_dir), asof_date=asof_date)
    if df.empty:
        return pd.DataFrame(columns=['animal_id'])
    out = df.copy()
    filters = dict(filters or {})
    for name in ('farm_id', 'site_id', 'pen_id', 'status', 'breed', 'animal_id'):
        raw = filters.get(name)
        if raw in (None, '', []):
            continue
        out = out[out.get(name, pd.Series(dtype=object)).astype(str).str.lower() == str(raw).strip().lower()]
    q = _clean(filters.get('q')).lower()
    if q:
        mask = pd.Series([False] * len(out), index=out.index)
        for col in [c for c in ('animal_id', 'breed', 'pen_name', 'status') if c in out.columns]:
            mask = mask | out[col].astype(str).str.lower().str.contains(q, na=False)
        out = out[mask]
    return out


def build_cow_value_population_table(
    *,
    input_dir: Path,
    asof_date: date,
    project_root: Path | None = None,
    cfg_path: str | Path | None = None,
    filters: Mapping[str, Any] | None = None,
    limit: int = 200,
    data_version: str | None = None,
) -> pd.DataFrame:
    candidates = list_cow_value_candidate_animals(input_dir=Path(input_dir), asof_date=asof_date, filters=filters)
    rows: list[dict[str, Any]] = []
    for animal_id in candidates.get('animal_id', pd.Series(dtype=object)).astype(str).tolist()[: max(1, int(limit or 200))]:
        snap = build_cow_value_snapshot(input_dir=Path(input_dir), asof_date=asof_date, animal_id=str(animal_id), project_root=project_root, cfg_path=cfg_path, data_version=data_version)
        rows.append({
            'animal_id': snap['animal_id'],
            'farm_id': snap['farm_id'],
            'site_id': snap['site_id'],
            'pen_id': snap['pen_id'],
            'pen_name': snap['pen_name'],
            'status': snap['status'],
            'breed': snap['breed'],
            'parity': snap['parity'],
            'avg_milk_7d': snap['avg_milk_7d'],
            'latest_scc_cells_ml': snap['latest_scc_cells_ml'],
            'recent_health_events_30d': snap['recent_health_events_30d'],
            'active_treatments': snap['active_treatments'],
            'repro_state': snap['repro_state_label'],
            'keep_value_rub': snap['replacement_comparison']['keep_value_rub'],
            'replacement_value_rub': snap['replacement_comparison']['replacement_value_rub'],
            'delta_keep_vs_replace_rub': snap['replacement_comparison']['delta_keep_vs_replace_rub'],
            'recommended_action': snap['recommended_label'],
            'recommended_action_code': snap['recommended_action'],
            'expected_impact_rub': snap['recommended_delta_vs_keep_rub'],
            'decision_required': 'yes' if snap['decision_required'] else 'no',
            'economics_inputs_version': snap['economics_inputs_version'],
            'explanation_short': snap['explanation_short'],
            'last_event_date': snap['last_event_date'],
            'object_type': 'animal',
            'object_id': snap['animal_id'],
            'open_target': 'animal',
        })
    return pd.DataFrame(rows)


def record_cow_value_decision_use_case(
    *,
    conn,
    tenant_id: str,
    user_id: int,
    username: str,
    role: str,
    snapshot: Mapping[str, Any],
    action: str,
    reason: str | None,
    comment: str | None,
    request_id: str | None = None,
) -> dict[str, Any]:
    action_s = _clean(action).lower()
    if action_s not in {'keep', 'breed', 'treat', 'cull', 'defer'}:
        raise ValueError(f'invalid_action: {action}')
    metadata = {
        'engine': 'cow_value_culling_v1',
        'economics_inputs_version': _clean(snapshot.get('economics_inputs_version')),
        'recommended_action': _clean(snapshot.get('recommended_action')),
        'recommended_label': _clean(snapshot.get('recommended_label')),
        'recommended_delta_vs_keep_rub': snapshot.get('recommended_delta_vs_keep_rub'),
        'replacement_comparison': dict(snapshot.get('replacement_comparison') or {}),
        'linked_source_facts': list(snapshot.get('linked_source_facts') or []),
    }
    res = append_decision_use_case(
        conn=conn,
        tenant_id=str(tenant_id),
        d=DecisionCreate(
            recommendation_id=None,
            action=action_s,
            user_id=int(user_id),
            username=str(username),
            reason=_clean(reason) or action_s,
            comment=_clean(comment) or None,
            related_alert=None,
            object_type='animal',
            object_id=_clean(snapshot.get('animal_id')),
            farm_id=_clean(snapshot.get('farm_id')) or None,
            group_id=_clean(snapshot.get('pen_id')) or None,
            data_version=_clean(snapshot.get('data_version')) or None,
            model_version=_clean(snapshot.get('model_version')) or None,
            report_version=_clean(snapshot.get('report_version')) or None,
            qc_run=_clean(snapshot.get('qc_run')) or None,
            scoring_run=_clean(snapshot.get('scoring_run')) or None,
            metadata=metadata,
        ),
    )
    after = dict(res.get('after') or {})
    write_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id),
        username=str(username),
        role=str(role),
        action='cow_value.decision.create',
        object_type='decision',
        object_id=str(res.get('decision_id') or ''),
        data_version=_clean(snapshot.get('data_version')) or None,
        run_id=_clean(snapshot.get('scoring_run')) or _clean(snapshot.get('report_version')) or None,
        after={
            'decision_id': res.get('decision_id'),
            'animal_id': snapshot.get('animal_id'),
            'action': action_s,
            'economics_inputs_version': snapshot.get('economics_inputs_version'),
        },
        request_id=request_id,
    )
    return {'decision_id': res.get('decision_id'), 'decision': after, 'metadata': metadata}


def create_culling_review_worklist_use_case(
    *,
    conn,
    tenant_id: str,
    user_id: int,
    username: str,
    role: str,
    snapshot: Mapping[str, Any],
    due_at: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    asof_raw = _clean(snapshot.get('asof_date'))
    try:
        base_date = date.fromisoformat(asof_raw[:10]) if asof_raw else date.today()
    except Exception:
        base_date = date.today()
    due_iso = _clean(due_at) or (base_date + timedelta(days=3)).isoformat()
    recommended = _clean(snapshot.get('recommended_label')) or _clean(snapshot.get('recommended_action')) or 'review'
    why = {
        'summary': f"Cow value / culling review · {recommended}",
        'expected_effect': f"Ожидаемый экономический эффект: {float(snapshot.get('recommended_delta_vs_keep_rub') or 0.0):.0f} ₽ vs keep",
        'engine': 'cow_value_culling_v1',
        'economics_inputs_version': _clean(snapshot.get('economics_inputs_version')),
    }
    todo = [
        {'action': 'Review cow value recommendation'},
        {'action': f"Recommended scenario: {recommended}"},
    ]
    res = create_worklist_use_case(
        conn=conn,
        tenant_id=str(tenant_id),
        worklist_type='culling_review',
        user_id=int(user_id),
        username=str(username),
        role=str(role),
        title=f"Culling review · {snapshot.get('animal_id')}",
        priority=1 if _clean(snapshot.get('recommended_action')) == 'cull' else 2,
        due_at=due_iso,
        object_type='animal',
        object_id=_clean(snapshot.get('animal_id')),
        assignee_team='team-econ',
        linked_source_facts=list(snapshot.get('linked_source_facts') or []),
        why=why,
        what_to_do=todo,
        data_version=_clean(snapshot.get('data_version')) or None,
        qc_run=_clean(snapshot.get('qc_run')) or None,
        model_version=_clean(snapshot.get('model_version')) or None,
        scoring_run=_clean(snapshot.get('scoring_run')) or None,
        report_version=_clean(snapshot.get('report_version')) or None,
        request_id=request_id,
    )
    after = dict(res.get('after') or {})
    write_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id),
        username=str(username),
        role=str(role),
        action='cow_value.worklist.create',
        object_type='worklist',
        object_id=str(res.get('worklist_id') or ''),
        data_version=_clean(snapshot.get('data_version')) or None,
        run_id=_clean(snapshot.get('scoring_run')) or _clean(snapshot.get('report_version')) or None,
        after={
            'worklist_id': res.get('worklist_id'),
            'animal_id': snapshot.get('animal_id'),
            'recommended_action': snapshot.get('recommended_action'),
            'economics_inputs_version': snapshot.get('economics_inputs_version'),
        },
        request_id=request_id,
    )
    return {'worklist_id': res.get('worklist_id'), 'worklist': after, 'why': why}
