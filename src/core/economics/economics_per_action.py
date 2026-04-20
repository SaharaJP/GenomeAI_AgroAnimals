from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from core.audit import write_audit
from core.economics.cow_value_culling import DEFAULT_CFG_PATH as COW_VALUE_CFG_PATH, _build_animals_df, build_cow_value_snapshot
from core.economics.milk_quality_scc import DEFAULT_CFG_PATH as MILK_QUALITY_CFG_PATH, build_milk_quality_scc_snapshot
from core.reproduction import load_reproduction_state_snapshot
from core.workflow import DecisionCreate, append_decision_use_case

DEFAULT_CFG_PATH = Path('configs/economics/economics_per_action_v1.yaml')


@dataclass(frozen=True)
class ActionEconomicsContext:
    worklist_id: str
    worklist_type: str
    title: str
    object_type: str
    object_id: str
    farm_id: str
    site_id: str
    pen_id: str
    status: str
    due_at: str
    due_bucket: str
    priority: int | None
    confidence: float | None
    data_version: str
    qc_run: str
    model_version: str
    scoring_run: str
    report_version: str
    linked_source_facts: list[dict[str, Any]]
    why: dict[str, Any]


def _clean(value: Any) -> str:
    return str(value or '').strip()


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
        'version': 'economics_per_action_v1',
        'label': 'Economics per action / decision / worklist v1',
        'horizon_days': 30,
        'default_confidence_weight': 0.7,
        'default_action_cost_rub': 400.0,
        'default_delay_window_days': 7,
        'culling_review_action_cost_rub': 550.0,
        'milk_quality_action_cost_rub': 750.0,
        'reproduction_action_cost_rub': 900.0,
        'health_action_cost_rub': 1100.0,
        'movement_action_cost_rub': 450.0,
        'data_cleanup_action_cost_rub': 300.0,
        'manager_review_action_cost_rub': 500.0,
        'manual_review_action_cost_rub': 400.0,
        'repro_expected_gain_base_rub': 5200.0,
        'repro_repeat_penalty_rub': 1800.0,
        'repro_day_open_cost_rub': 120.0,
        'health_expected_gain_base_rub': 4800.0,
        'health_event_penalty_rub': 900.0,
        'health_active_treatment_penalty_rub': 1200.0,
        'health_delay_cost_rub': 260.0,
        'movement_expected_gain_rub': 1400.0,
        'data_cleanup_expected_gain_rub': 800.0,
        'manager_review_expected_gain_rub': 1000.0,
        'manual_review_expected_gain_rub': 600.0,
        'due_bucket_delay_multiplier': {'overdue': 1.5, 'today': 1.0, 'upcoming': 0.5, 'undated': 0.75},
    }
    defaults.update(cfg)
    return path, defaults


def describe_action_economics_inputs_version(*, project_root: Path | None = None, cfg_path: str | Path | None = None) -> dict[str, Any]:
    path, cfg = _load_cfg(project_root=project_root, cfg_path=cfg_path)
    raw = path.read_bytes() if path.exists() else json.dumps(cfg, ensure_ascii=False).encode('utf-8')
    digest = hashlib.sha1(raw).hexdigest()[:12]
    return {
        'economics_inputs_version': f"{_clean(cfg.get('version')) or 'economics_per_action_v1'}::{path.as_posix()}::{digest}",
        'config_path': path.as_posix(),
        'config_version': _clean(cfg.get('version')) or 'economics_per_action_v1',
        'config_digest': digest,
        'label': _clean(cfg.get('label')) or 'Economics per action',
    }


def _context_from_worklist(worklist: Mapping[str, Any]) -> ActionEconomicsContext:
    linked = dict(worklist.get('linked_object') or {})
    return ActionEconomicsContext(
        worklist_id=_clean(worklist.get('worklist_id') or worklist.get('task_id')),
        worklist_type=_clean(worklist.get('worklist_type') or worklist.get('task_type')) or 'worklist',
        title=_clean(worklist.get('title')) or 'Work item',
        object_type=_clean(worklist.get('object_type') or linked.get('object_type')),
        object_id=_clean(worklist.get('object_id') or linked.get('object_id')),
        farm_id=_clean(worklist.get('farm_id')),
        site_id=_clean(worklist.get('site_id')),
        pen_id=_clean(worklist.get('group_id') or worklist.get('pen_id')),
        status=_clean(worklist.get('status')) or 'open',
        due_at=_clean(worklist.get('due_at')),
        due_bucket=_clean(worklist.get('due_bucket')) or 'undated',
        priority=_safe_int(worklist.get('priority')),
        confidence=_safe_float(worklist.get('confidence')),
        data_version=_clean(worklist.get('data_version')),
        qc_run=_clean(worklist.get('qc_run')),
        model_version=_clean(worklist.get('model_version')),
        scoring_run=_clean(worklist.get('scoring_run')),
        report_version=_clean(worklist.get('report_version')),
        linked_source_facts=[dict(x) for x in list(worklist.get('linked_source_facts') or []) if isinstance(x, Mapping)],
        why=dict(worklist.get('why') or {}),
    )


def _due_delay_multiplier(bucket: str, cfg: Mapping[str, Any]) -> float:
    mp = dict(cfg.get('due_bucket_delay_multiplier') or {})
    return float(mp.get(str(bucket or 'undated'), mp.get('undated', 0.75)) or 0.75)


def _resolve_animal_context(*, input_dir: Path, asof_date: date, animal_id: str) -> dict[str, Any]:
    df = _build_animals_df(input_dir=input_dir, asof_date=asof_date)
    sub = df[df.get('animal_id', pd.Series(dtype=object)).astype(str) == str(animal_id)].copy()
    if sub.empty:
        return {}
    row = dict(sub.iloc[0].to_dict())
    return {
        'animal_id': _clean(row.get('animal_id')),
        'farm_id': _clean(row.get('farm_id')),
        'site_id': _clean(row.get('site_id')),
        'pen_id': _clean(row.get('pen_id')),
        'pen_name': _clean(row.get('pen_name')),
        'parity': _safe_int(row.get('parity')),
        'avg_milk_7d': _safe_float(row.get('avg_milk_7d') if 'avg_milk_7d' in row else row.get('milk_7d_avg')),
        'latest_scc_cells_ml': _safe_int(row.get('latest_scc_cells_ml')),
        'recent_health_events_30d': _safe_int(row.get('recent_health_events')) or 0,
        'active_treatments': _safe_int(row.get('active_treatments')) or 0,
        'status': _clean(row.get('status')) or 'active',
    }


def _economics_summary(*, expected_gain_rub: float, expected_loss_rub: float, action_cost_rub: float, cost_of_delay_per_day_rub: float, delay_days: int) -> dict[str, Any]:
    cost_of_delay_rub = float(cost_of_delay_per_day_rub) * int(delay_days)
    expected_net_value_rub = float(expected_gain_rub) - float(action_cost_rub)
    expected_roi = None
    if float(action_cost_rub) > 0:
        expected_roi = round((expected_net_value_rub / float(action_cost_rub)), 4)
    return {
        'expected_gain_rub': round(float(expected_gain_rub), 2),
        'expected_loss_rub': round(float(expected_loss_rub), 2),
        'action_cost_rub': round(float(action_cost_rub), 2),
        'cost_of_delay_per_day_rub': round(float(cost_of_delay_per_day_rub), 2),
        'delay_days': int(delay_days),
        'cost_of_delay_rub': round(float(cost_of_delay_rub), 2),
        'expected_net_value_rub': round(float(expected_net_value_rub), 2),
        'expected_roi': expected_roi,
    }


def _build_culling_worklist_economics(*, input_dir: Path, asof_date: date, ctx: ActionEconomicsContext, cfg: Mapping[str, Any], project_root: Path | None, data_version: str) -> dict[str, Any]:
    snap = build_cow_value_snapshot(input_dir=input_dir, asof_date=asof_date, animal_id=ctx.object_id, project_root=project_root, data_version=data_version)
    rec = next((dict(x) for x in list(snap.get('scenarios') or []) if _clean(x.get('action')) == _clean(snap.get('recommended_action'))), {})
    base_gain = max(float(rec.get('delta_vs_keep_rub') or 0.0), 0.0)
    base_loss = max(float(-(float(rec.get('delta_vs_keep_rub') or 0.0))), 0.0)
    conf = ctx.confidence if ctx.confidence is not None else float(cfg.get('default_confidence_weight') or 0.7)
    horizon_days = int((snap.get('replacement_comparison') or {}).get('horizon_days') or cfg.get('horizon_days') or 30)
    delay_cost = (abs(float(rec.get('delta_vs_keep_rub') or 0.0)) / max(1, horizon_days)) * _due_delay_multiplier(ctx.due_bucket, cfg)
    action_cost = float(cfg.get('culling_review_action_cost_rub') or cfg.get('default_action_cost_rub') or 0.0)
    econ = _economics_summary(
        expected_gain_rub=base_gain * conf,
        expected_loss_rub=base_loss * conf,
        action_cost_rub=action_cost,
        cost_of_delay_per_day_rub=delay_cost,
        delay_days=int(cfg.get('default_delay_window_days') or 7),
    )
    factors = list(snap.get('factors') or [])[:5]
    formula_rows = list(snap.get('formula_rows') or []) + [
        {'metric': 'expected_gain_rub', 'formula': 'max(delta_vs_keep_rub, 0) * confidence_weight'},
        {'metric': 'cost_of_delay_per_day_rub', 'formula': 'abs(delta_vs_keep_rub) / horizon_days * due_bucket_delay_multiplier'},
        {'metric': 'expected_roi', 'formula': '(expected_gain_rub - action_cost_rub) / action_cost_rub'},
    ]
    return {
        'engine': 'cow_value_culling_v1',
        'recommended_action': _clean(snap.get('recommended_action')),
        'recommended_label': _clean(snap.get('recommended_label')),
        'why_now': _clean(snap.get('explanation_short')),
        'factors': factors,
        'formula_rows': formula_rows,
        'linked_source_facts': list(snap.get('linked_source_facts') or []) + ctx.linked_source_facts,
        'source_versions': {
            'economics_inputs_version': _clean(snap.get('economics_inputs_version')),
            'worklist_data_version': ctx.data_version,
        },
        'summary_metrics': econ,
    }


def _build_milk_quality_worklist_economics(*, input_dir: Path, asof_date: date, ctx: ActionEconomicsContext, cfg: Mapping[str, Any], project_root: Path | None, data_version: str) -> dict[str, Any]:
    snap = build_milk_quality_scc_snapshot(input_dir=input_dir, asof_date=asof_date, project_root=project_root, data_version=data_version, farm_id=ctx.farm_id or None, pen_id=(ctx.object_id if ctx.object_type in {'group', 'pen'} else ctx.pen_id) or None)
    level = 'animal' if ctx.object_type == 'animal' else 'group'
    rows = list(snap.get('animal_contributions') or []) if level == 'animal' else list(snap.get('group_contributions') or [])
    row = next((dict(x) for x in rows if _clean(x.get('animal_id') or x.get('pen_id') or x.get('object_id')) == ctx.object_id), {})
    attributed = float(row.get('attributed_economic_adjustment_rub') or 0.0)
    base_gain = max(-attributed, 0.0)
    conf = ctx.confidence if ctx.confidence is not None else float(cfg.get('default_confidence_weight') or 0.7)
    action_cost = float(cfg.get('milk_quality_action_cost_rub') or cfg.get('default_action_cost_rub') or 0.0)
    delay_cost = (base_gain / max(1, int(cfg.get('default_delay_window_days') or 7))) * _due_delay_multiplier(ctx.due_bucket, cfg)
    econ = _economics_summary(
        expected_gain_rub=base_gain * conf,
        expected_loss_rub=base_gain * conf,
        action_cost_rub=action_cost,
        cost_of_delay_per_day_rub=delay_cost,
        delay_days=int(cfg.get('default_delay_window_days') or 7),
    )
    formula_rows = list(snap.get('formula_rows') or []) + [
        {'metric': 'expected_gain_rub', 'formula': 'max(-attributed_economic_adjustment_rub, 0) * confidence_weight'},
        {'metric': 'cost_of_delay_per_day_rub', 'formula': 'expected_gain_rub / default_delay_window_days * due_bucket_delay_multiplier'},
    ]
    factors = [
        {'factor': 'estimated_bulk_tank_scc', 'value': (snap.get('bulk_tank') or {}).get('estimated_bulk_tank_scc'), 'effect_direction': 'negative', 'note': 'Оценка по batch snapshot.'},
        {'factor': 'target_share_of_total_scc_load_pct', 'value': row.get('share_of_total_scc_load_pct'), 'effect_direction': 'negative', 'note': 'Вклад объекта в общий SCC load.'},
        {'factor': 'suggested_action', 'value': row.get('suggested_action'), 'effect_direction': 'action', 'note': 'Operational follow-up по качеству молока.'},
    ]
    return {
        'engine': 'milk_quality_scc_cockpit_v1',
        'recommended_action': _clean(row.get('suggested_action')) or 'review_milk_quality',
        'recommended_label': _clean(row.get('suggested_action')) or 'review_milk_quality',
        'why_now': f"Bulk tank SCC={(snap.get('bulk_tank') or {}).get('estimated_bulk_tank_scc')} · attributed={round(attributed, 2)} ₽",
        'factors': factors,
        'formula_rows': formula_rows,
        'linked_source_facts': list(row.get('linked_source_facts') or []) + ctx.linked_source_facts,
        'source_versions': {
            'economics_inputs_version': _clean(snap.get('economics_inputs_version')),
            'worklist_data_version': ctx.data_version,
        },
        'summary_metrics': econ,
        'quality_caveats': list(snap.get('quality_caveats') or []),
    }


def _build_repro_worklist_economics(*, input_dir: Path, asof_date: date, ctx: ActionEconomicsContext, cfg: Mapping[str, Any]) -> dict[str, Any]:
    repro = load_reproduction_state_snapshot(input_dir=input_dir, animal_id=ctx.object_id, asof_date=asof_date) if ctx.object_type == 'animal' and ctx.object_id else {}
    metrics = dict(repro.get('metrics') or {})
    days_open = _safe_int(metrics.get('days_open')) or 0
    repro_state = _clean(repro.get('state')) or 'no_data'
    base_gain = float(cfg.get('repro_expected_gain_base_rub') or 0.0)
    if repro_state == 'repeat':
        base_gain += float(cfg.get('repro_repeat_penalty_rub') or 0.0)
    if days_open > 0:
        base_gain += min(days_open, 60) * float(cfg.get('repro_day_open_cost_rub') or 0.0)
    conf = ctx.confidence if ctx.confidence is not None else float(cfg.get('default_confidence_weight') or 0.7)
    action_cost = float(cfg.get('reproduction_action_cost_rub') or cfg.get('default_action_cost_rub') or 0.0)
    delay_cost = float(cfg.get('repro_day_open_cost_rub') or 0.0) * _due_delay_multiplier(ctx.due_bucket, cfg)
    econ = _economics_summary(expected_gain_rub=base_gain * conf, expected_loss_rub=base_gain * conf, action_cost_rub=action_cost, cost_of_delay_per_day_rub=delay_cost, delay_days=int(cfg.get('default_delay_window_days') or 7))
    factors = [
        {'factor': 'repro_state', 'value': repro_state, 'effect_direction': 'negative' if repro_state in {'open','repeat','preg_check_due','eligible'} else 'neutral', 'note': 'Состояние воспроизводства из repro snapshot.'},
        {'factor': 'days_open', 'value': days_open, 'effect_direction': 'negative' if days_open > 0 else 'neutral', 'note': 'Каждый день задержки увеличивает operational cost.'},
    ]
    return {
        'engine': 'reproduction_action_economics_v1',
        'recommended_action': 'execute_repro_followup',
        'recommended_label': 'Execute repro follow-up',
        'why_now': f'repro_state={repro_state} · days_open={days_open}',
        'factors': factors,
        'formula_rows': [
            {'metric': 'expected_gain_rub', 'formula': 'repro_expected_gain_base_rub + repro_repeat_penalty_rub(if repeat) + min(days_open, 60) * repro_day_open_cost_rub; then * confidence_weight'},
            {'metric': 'cost_of_delay_per_day_rub', 'formula': 'repro_day_open_cost_rub * due_bucket_delay_multiplier'},
        ],
        'linked_source_facts': ctx.linked_source_facts,
        'source_versions': {'worklist_data_version': ctx.data_version},
        'summary_metrics': econ,
    }


def _build_health_worklist_economics(*, input_dir: Path, asof_date: date, ctx: ActionEconomicsContext, cfg: Mapping[str, Any]) -> dict[str, Any]:
    animal = _resolve_animal_context(input_dir=input_dir, asof_date=asof_date, animal_id=ctx.object_id) if ctx.object_type == 'animal' and ctx.object_id else {}
    recent_health_events = int(animal.get('recent_health_events_30d') or 0)
    active_treatments = int(animal.get('active_treatments') or 0)
    latest_scc = _safe_int(animal.get('latest_scc_cells_ml')) or 0
    base_gain = float(cfg.get('health_expected_gain_base_rub') or 0.0)
    base_gain += recent_health_events * float(cfg.get('health_event_penalty_rub') or 0.0)
    base_gain += active_treatments * float(cfg.get('health_active_treatment_penalty_rub') or 0.0)
    if latest_scc >= 200000:
        base_gain += 800.0
    conf = ctx.confidence if ctx.confidence is not None else float(cfg.get('default_confidence_weight') or 0.7)
    action_cost = float(cfg.get('health_action_cost_rub') or cfg.get('default_action_cost_rub') or 0.0)
    delay_cost = float(cfg.get('health_delay_cost_rub') or 0.0) * (1 + min(recent_health_events, 3) * 0.2 + min(active_treatments, 2) * 0.25) * _due_delay_multiplier(ctx.due_bucket, cfg)
    econ = _economics_summary(expected_gain_rub=base_gain * conf, expected_loss_rub=base_gain * conf, action_cost_rub=action_cost, cost_of_delay_per_day_rub=delay_cost, delay_days=int(cfg.get('default_delay_window_days') or 7))
    factors = [
        {'factor': 'recent_health_events_30d', 'value': recent_health_events, 'effect_direction': 'negative' if recent_health_events > 0 else 'neutral', 'note': 'Недавние health events увеличивают ожидаемые потери.'},
        {'factor': 'active_treatments', 'value': active_treatments, 'effect_direction': 'negative' if active_treatments > 0 else 'neutral', 'note': 'Активные лечения повышают cost of delay.'},
        {'factor': 'latest_scc_cells_ml', 'value': latest_scc or 'NA', 'effect_direction': 'negative' if latest_scc >= 200000 else 'neutral', 'note': 'Высокий SCC усиливает operational риск.'},
    ]
    return {
        'engine': 'health_action_economics_v1',
        'recommended_action': 'execute_health_followup',
        'recommended_label': 'Execute health follow-up',
        'why_now': f'health_events={recent_health_events} · active_treatments={active_treatments}',
        'factors': factors,
        'formula_rows': [
            {'metric': 'expected_gain_rub', 'formula': 'health_expected_gain_base_rub + recent_health_events_30d * health_event_penalty_rub + active_treatments * health_active_treatment_penalty_rub; then * confidence_weight'},
            {'metric': 'cost_of_delay_per_day_rub', 'formula': 'health_delay_cost_rub * severity_factor * due_bucket_delay_multiplier'},
        ],
        'linked_source_facts': ctx.linked_source_facts,
        'source_versions': {'worklist_data_version': ctx.data_version},
        'summary_metrics': econ,
    }


def _build_simple_worklist_economics(*, ctx: ActionEconomicsContext, cfg: Mapping[str, Any]) -> dict[str, Any]:
    wt = ctx.worklist_type.lower()
    if wt == 'movement':
        base_gain = float(cfg.get('movement_expected_gain_rub') or 0.0)
        action_cost = float(cfg.get('movement_action_cost_rub') or 0.0)
    elif wt == 'data_cleanup':
        base_gain = float(cfg.get('data_cleanup_expected_gain_rub') or 0.0)
        action_cost = float(cfg.get('data_cleanup_action_cost_rub') or 0.0)
    elif wt == 'manager_review':
        base_gain = float(cfg.get('manager_review_expected_gain_rub') or 0.0)
        action_cost = float(cfg.get('manager_review_action_cost_rub') or 0.0)
    else:
        base_gain = float(cfg.get('manual_review_expected_gain_rub') or 0.0)
        action_cost = float(cfg.get('manual_review_action_cost_rub') or 0.0)
    conf = ctx.confidence if ctx.confidence is not None else float(cfg.get('default_confidence_weight') or 0.7)
    delay_cost = (base_gain / max(1, int(cfg.get('default_delay_window_days') or 7))) * _due_delay_multiplier(ctx.due_bucket, cfg)
    econ = _economics_summary(expected_gain_rub=base_gain * conf, expected_loss_rub=base_gain * conf, action_cost_rub=action_cost, cost_of_delay_per_day_rub=delay_cost, delay_days=int(cfg.get('default_delay_window_days') or 7))
    return {
        'engine': 'generic_action_economics_v1',
        'recommended_action': 'review_and_execute',
        'recommended_label': 'Review and execute',
        'why_now': 'Operational work item with bounded economics heuristic.',
        'factors': [{'factor': 'worklist_type', 'value': ctx.worklist_type, 'effect_direction': 'context', 'note': 'Generic bounded economics heuristic.'}],
        'formula_rows': [
            {'metric': 'expected_gain_rub', 'formula': 'configured_expected_gain_rub * confidence_weight'},
            {'metric': 'cost_of_delay_per_day_rub', 'formula': 'expected_gain_rub / default_delay_window_days * due_bucket_delay_multiplier'},
        ],
        'linked_source_facts': ctx.linked_source_facts,
        'source_versions': {'worklist_data_version': ctx.data_version},
        'summary_metrics': econ,
        'quality_caveats': ['Используется bounded operational heuristic: strategic what-if сюда не включается.'],
    }


def build_action_economics_snapshot(*, input_dir: Path, asof_date: date, worklist: Mapping[str, Any], project_root: Path | None = None, cfg_path: str | Path | None = None) -> dict[str, Any]:
    path, cfg = _load_cfg(project_root=project_root, cfg_path=cfg_path)
    version = describe_action_economics_inputs_version(project_root=project_root, cfg_path=cfg_path)
    ctx = _context_from_worklist(worklist)
    data_version = ctx.data_version or _clean(worklist.get('data_version'))
    quality_caveats: list[str] = []
    if ctx.confidence is None:
        quality_caveats.append('confidence отсутствует: используется default_confidence_weight')
    if not ctx.data_version:
        quality_caveats.append('data_version отсутствует в worklist item')
    wt = ctx.worklist_type.lower()
    if wt == 'culling_review' and ctx.object_type == 'animal' and ctx.object_id:
        body = _build_culling_worklist_economics(input_dir=Path(input_dir), asof_date=asof_date, ctx=ctx, cfg=cfg, project_root=project_root, data_version=data_version)
    elif wt == 'milk_quality' and ctx.object_id:
        body = _build_milk_quality_worklist_economics(input_dir=Path(input_dir), asof_date=asof_date, ctx=ctx, cfg=cfg, project_root=project_root, data_version=data_version)
    elif wt == 'reproduction' and ctx.object_type == 'animal' and ctx.object_id:
        body = _build_repro_worklist_economics(input_dir=Path(input_dir), asof_date=asof_date, ctx=ctx, cfg=cfg)
    elif wt in {'vet', 'health_follow_up'} and ctx.object_type == 'animal' and ctx.object_id:
        body = _build_health_worklist_economics(input_dir=Path(input_dir), asof_date=asof_date, ctx=ctx, cfg=cfg)
    else:
        body = _build_simple_worklist_economics(ctx=ctx, cfg=cfg)
    quality_caveats.extend(list(body.get('quality_caveats') or []))
    source_versions = dict(body.get('source_versions') or {})
    source_versions.setdefault('economics_inputs_version', version['economics_inputs_version'])
    source_versions.setdefault('data_version', ctx.data_version)
    return {
        'schema': 'genomeai.economics_per_action.v1',
        'asof_date': asof_date.isoformat(),
        'worklist_id': ctx.worklist_id,
        'worklist_type': ctx.worklist_type,
        'title': ctx.title,
        'object_type': ctx.object_type,
        'object_id': ctx.object_id,
        'farm_id': ctx.farm_id,
        'site_id': ctx.site_id,
        'pen_id': ctx.pen_id,
        'status': ctx.status,
        'due_at': ctx.due_at,
        'due_bucket': ctx.due_bucket,
        'priority': ctx.priority,
        'confidence': ctx.confidence,
        'data_version': ctx.data_version,
        'qc_run': ctx.qc_run,
        'model_version': ctx.model_version,
        'scoring_run': ctx.scoring_run,
        'report_version': ctx.report_version,
        **version,
        'engine': body.get('engine'),
        'recommended_action': body.get('recommended_action'),
        'recommended_label': body.get('recommended_label'),
        'why_now': body.get('why_now'),
        'summary_metrics': dict(body.get('summary_metrics') or {}),
        'factors': list(body.get('factors') or []),
        'formula_rows': list(body.get('formula_rows') or []),
        'linked_source_facts': list(body.get('linked_source_facts') or []),
        'source_versions': source_versions,
        'quality_caveats': quality_caveats,
    }


def record_action_economics_decision_use_case(*, conn, tenant_id: str, user_id: int, username: str, role: str, snapshot: Mapping[str, Any], action: str, reason: str, comment: str | None = None, request_id: str | None = None) -> dict[str, Any]:
    if not _clean(snapshot.get('worklist_id')):
        raise ValueError('economics_worklist_id_required')
    summary = dict(snapshot.get('summary_metrics') or {})
    metadata = {
        'engine': 'economics_per_action_v1',
        'economics_inputs_version': _clean(snapshot.get('economics_inputs_version')),
        'worklist_id': _clean(snapshot.get('worklist_id')),
        'worklist_type': _clean(snapshot.get('worklist_type')),
        'expected_gain_rub': summary.get('expected_gain_rub'),
        'expected_loss_rub': summary.get('expected_loss_rub'),
        'action_cost_rub': summary.get('action_cost_rub'),
        'cost_of_delay_per_day_rub': summary.get('cost_of_delay_per_day_rub'),
        'cost_of_delay_rub': summary.get('cost_of_delay_rub'),
        'expected_net_value_rub': summary.get('expected_net_value_rub'),
        'expected_roi': summary.get('expected_roi'),
        'recommended_action': _clean(snapshot.get('recommended_action')),
        'why_now': _clean(snapshot.get('why_now')),
        'source_versions': dict(snapshot.get('source_versions') or {}),
    }
    res = append_decision_use_case(
        conn=conn,
        tenant_id=str(tenant_id),
        d=DecisionCreate(
            recommendation_id=_clean(snapshot.get('worklist_id')) or None,
            action=_clean(action) or 'reviewed',
            user_id=int(user_id),
            username=str(username),
            reason=_clean(reason) or None,
            comment=_clean(comment) or None,
            related_alert=None,
            object_type=_clean(snapshot.get('object_type')) or None,
            object_id=_clean(snapshot.get('object_id')) or None,
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
    write_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id),
        username=str(username),
        role=str(role),
        action='economics_per_action.decision.create',
        object_type='decision',
        object_id=str(res.get('decision_id') or ''),
        data_version=_clean(snapshot.get('data_version')) or None,
        request_id=request_id,
        after={'worklist_id': _clean(snapshot.get('worklist_id')), 'recommended_action': _clean(snapshot.get('recommended_action')), 'expected_gain_rub': summary.get('expected_gain_rub'), 'expected_roi': summary.get('expected_roi')},
    )
    return {'decision_id': res.get('decision_id'), 'decision': dict(res.get('after') or {}), 'metadata': metadata}


__all__ = [
    'DEFAULT_CFG_PATH',
    'build_action_economics_snapshot',
    'describe_action_economics_inputs_version',
    'record_action_economics_decision_use_case',
]
