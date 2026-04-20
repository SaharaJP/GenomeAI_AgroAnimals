from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from core.audit import write_audit
from core.economics.cow_value_culling import build_cow_value_snapshot
from core.economics.economics_per_action import build_action_economics_snapshot
from core.economics.fresh_cows_transition import build_fresh_cows_transition_snapshot
from core.economics.milk_quality_scc import build_milk_quality_scc_snapshot
from core.list_builder import _build_animals_df
from core.workflow import DecisionCreate, append_decision_use_case, create_worklist_use_case

DEFAULT_CFG_PATH = Path('configs/economics/operational_what_if_v1.yaml')


@dataclass(frozen=True)
class WhatIfContext:
    source: str
    scenario_family: str
    object_type: str
    object_id: str
    farm_id: str
    site_id: str
    pen_id: str
    title: str
    data_version: str
    qc_run: str
    model_version: str
    scoring_run: str
    report_version: str
    linked_source_facts: list[dict[str, Any]]
    worklist_id: str
    worklist_type: str
    confidence: float | None


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
        'version': 'operational_what_if_v1',
        'label': 'Operational what-if for herd manager v1',
        'default_delay_days': 7,
        'reproduction_delay_days': 7,
        'health_delay_days': 3,
        'quality_delay_days': 3,
        'group_move_delay_days': 7,
        'culling_delay_days': 7,
        'treat_now_gain_multiplier': 1.0,
        'treat_now_residual_loss_multiplier': 0.35,
        'no_treat_loss_multiplier': 1.15,
        'monitor_gain_multiplier': 0.55,
        'monitor_residual_loss_multiplier': 0.65,
        'protocol_change_gain_multiplier': 1.10,
        'protocol_change_cost_multiplier': 1.25,
        'protocol_change_residual_loss_multiplier': 0.30,
        'defer_gain_multiplier': 0.70,
        'defer_loss_multiplier': 1.05,
        'reprioritize_gain_multiplier': 0.90,
        'reprioritize_cost_multiplier': 0.50,
        'reprioritize_delay_days': 0,
        'group_move_expected_gain_rub': 1800.0,
        'group_move_action_cost_rub': 500.0,
        'group_move_protocol_gain_multiplier': 1.0,
        'group_move_defer_loss_multiplier': 1.15,
        'keep_action_cost_rub': 250.0,
        'cull_action_cost_rub': 550.0,
        'breed_action_cost_rub': 600.0,
        'defer_action_cost_rub': 200.0,
        'quality_protocol_gain_multiplier': 1.08,
        'quality_protocol_cost_multiplier': 1.15,
        'fresh_treat_gain_multiplier': 1.0,
        'fresh_protocol_gain_multiplier': 1.08,
        'fresh_monitor_gain_multiplier': 0.60,
    }
    defaults.update(cfg)
    return path, defaults


def describe_operational_what_if_inputs_version(*, project_root: Path | None = None, cfg_path: str | Path | None = None) -> dict[str, Any]:
    path, cfg = _load_cfg(project_root=project_root, cfg_path=cfg_path)
    raw = path.read_bytes() if path.exists() else json.dumps(cfg, ensure_ascii=False).encode('utf-8')
    digest = hashlib.sha1(raw).hexdigest()[:12]
    return {
        'economics_inputs_version': f"{_clean(cfg.get('version')) or 'operational_what_if_v1'}::{path.as_posix()}::{digest}",
        'config_path': path.as_posix(),
        'config_version': _clean(cfg.get('version')) or 'operational_what_if_v1',
        'config_digest': digest,
        'label': _clean(cfg.get('label')) or 'Operational what-if',
    }


def _context_from_worklist(worklist: Mapping[str, Any], *, scenario_family: str) -> WhatIfContext:
    linked = dict(worklist.get('linked_object') or {})
    return WhatIfContext(
        source='worklist',
        scenario_family=scenario_family,
        object_type=_clean(worklist.get('object_type') or linked.get('object_type')),
        object_id=_clean(worklist.get('object_id') or linked.get('object_id')),
        farm_id=_clean(worklist.get('farm_id')),
        site_id=_clean(worklist.get('site_id')),
        pen_id=_clean(worklist.get('group_id') or worklist.get('pen_id')),
        title=_clean(worklist.get('title')) or 'Operational work item',
        data_version=_clean(worklist.get('data_version')),
        qc_run=_clean(worklist.get('qc_run')),
        model_version=_clean(worklist.get('model_version')),
        scoring_run=_clean(worklist.get('scoring_run')),
        report_version=_clean(worklist.get('report_version')),
        linked_source_facts=[dict(x) for x in list(worklist.get('linked_source_facts') or []) if isinstance(x, Mapping)],
        worklist_id=_clean(worklist.get('worklist_id') or worklist.get('task_id')),
        worklist_type=_clean(worklist.get('worklist_type') or worklist.get('task_type')),
        confidence=_safe_float(worklist.get('confidence')),
    )


def _context_from_object(*, input_dir: Path, asof_date: date, object_type: str, object_id: str, scenario_family: str, data_version: str | None = None) -> WhatIfContext:
    farm_id = ''
    site_id = ''
    pen_id = ''
    title = f'{object_type}:{object_id}'
    if object_type == 'animal' and object_id:
        animals = _build_animals_df(input_dir=Path(input_dir), asof_date=asof_date)
        sub = animals[animals.get('animal_id', pd.Series(dtype=object)).astype(str) == str(object_id)].copy()
        if not sub.empty:
            row = dict(sub.iloc[0].to_dict())
            farm_id = _clean(row.get('farm_id'))
            site_id = _clean(row.get('site_id'))
            pen_id = _clean(row.get('pen_id'))
            title = f"Animal {object_id}"
    elif object_type in {'group', 'pen', 'site'} and object_id:
        pen_id = object_id if object_type in {'group', 'pen'} else ''
        site_id = object_id if object_type == 'site' else ''
        title = f"{object_type.title()} {object_id}"
    return WhatIfContext(
        source='object',
        scenario_family=scenario_family,
        object_type=object_type,
        object_id=object_id,
        farm_id=farm_id,
        site_id=site_id,
        pen_id=pen_id,
        title=title,
        data_version=_clean(data_version),
        qc_run='',
        model_version='',
        scoring_run='',
        report_version='',
        linked_source_facts=[],
        worklist_id='',
        worklist_type='',
        confidence=None,
    )


def _infer_scenario_family(*, worklist: Mapping[str, Any] | None = None, object_type: str | None = None, scenario_family: str | None = None) -> str:
    family = _clean(scenario_family).lower()
    if family:
        return family
    if worklist:
        wt = _clean(worklist.get('worklist_type')).lower()
        why_engine = _clean((worklist.get('why') or {}).get('engine')).lower()
        if wt == 'culling_review':
            return 'cull_keep'
        if wt == 'milk_quality':
            return 'milk_quality_protocol'
        if wt == 'reproduction':
            return 'repro_priority'
        if wt in {'vet', 'health_follow_up'}:
            return 'treat_protocol'
        if wt == 'movement':
            return 'group_move'
        if why_engine == 'fresh_cows_transition_economics_v1':
            return 'fresh_transition'
        return 'reprioritize'
    if _clean(object_type) == 'group':
        return 'group_move'
    return 'cull_keep'


def _summary(*, gain: float, loss: float, action_cost: float, delay_per_day: float, delay_days: int, note: str = '', uncertainty: str = 'medium', caveat: str = '') -> dict[str, Any]:
    cost_of_delay = float(delay_per_day) * int(delay_days)
    net = float(gain) - float(action_cost) - float(cost_of_delay)
    roi = None
    if float(action_cost) > 0:
        roi = round(net / float(action_cost), 4)
    return {
        'expected_gain_rub': round(float(gain), 2),
        'expected_loss_rub': round(float(loss), 2),
        'action_cost_rub': round(float(action_cost), 2),
        'cost_of_delay_per_day_rub': round(float(delay_per_day), 2),
        'delay_days': int(delay_days),
        'cost_of_delay_rub': round(float(cost_of_delay), 2),
        'expected_net_value_rub': round(float(net), 2),
        'expected_roi': roi,
        'uncertainty': uncertainty,
        'caveat': caveat,
        'note': note,
    }


def _scenario_record(*, key: str, label: str, action: str, summary: Mapping[str, Any], note: str, assumptions: list[str], recommended: bool = False) -> dict[str, Any]:
    out = {'scenario_key': key, 'label': label, 'action': action, 'recommended': bool(recommended), 'note': note, 'assumptions': '; '.join([str(x) for x in assumptions if str(x).strip()])}
    out.update({
        'expected_gain_rub': summary.get('expected_gain_rub'),
        'expected_loss_rub': summary.get('expected_loss_rub'),
        'action_cost_rub': summary.get('action_cost_rub'),
        'cost_of_delay_per_day_rub': summary.get('cost_of_delay_per_day_rub'),
        'delay_days': summary.get('delay_days'),
        'cost_of_delay_rub': summary.get('cost_of_delay_rub'),
        'expected_net_value_rub': summary.get('expected_net_value_rub'),
        'expected_roi': summary.get('expected_roi'),
        'uncertainty': summary.get('uncertainty'),
        'caveat': summary.get('caveat'),
    })
    return out


def _choose_recommended(rows: list[dict[str, Any]], preferred_action: str = '') -> str:
    if preferred_action:
        for row in rows:
            if _clean(row.get('action')).lower() == preferred_action.lower():
                return _clean(row.get('scenario_key'))
    ordered = sorted(rows, key=lambda r: float(r.get('expected_net_value_rub') or 0.0), reverse=True)
    return _clean(ordered[0].get('scenario_key')) if ordered else ''


def _culling_scenarios(*, input_dir: Path, asof_date: date, ctx: WhatIfContext, cfg: Mapping[str, Any], project_root: Path | None) -> dict[str, Any]:
    snap = build_cow_value_snapshot(input_dir=input_dir, asof_date=asof_date, animal_id=ctx.object_id, project_root=project_root, data_version=ctx.data_version or None)
    raw_scenarios = [dict(x) for x in list(snap.get('scenarios') or [])]
    rows: list[dict[str, Any]] = []
    delay_days = int(cfg.get('culling_delay_days') or cfg.get('default_delay_days') or 7)
    delta_map = {_clean(x.get('action')): float(x.get('delta_vs_keep_rub') or 0.0) for x in raw_scenarios}
    for action, label in [('keep', 'Keep'), ('breed', 'Breed'), ('treat', 'Treat'), ('cull', 'Cull'), ('defer', 'Defer')]:
        delta = float(delta_map.get(action, 0.0))
        if action == 'defer':
            gain = max(float(snap.get('recommended_delta_vs_keep_rub') or 0.0) * float(cfg.get('defer_gain_multiplier') or 0.7), 0.0)
            loss = abs(float(snap.get('recommended_delta_vs_keep_rub') or 0.0)) * float(cfg.get('defer_loss_multiplier') or 1.05)
            action_cost = float(cfg.get('defer_action_cost_rub') or 200.0)
            note = 'Отложить решение и сохранить животное в текущем статусе ещё на bounded window.'
        else:
            gain = max(delta, 0.0)
            loss = max(-delta, 0.0)
            action_cost = float(cfg.get(f'{action}_action_cost_rub') or cfg.get('keep_action_cost_rub') or 250.0)
            note = f'Scenario from cow value / culling engine: {label.lower()}.'
        summary = _summary(
            gain=gain,
            loss=loss,
            action_cost=action_cost,
            delay_per_day=abs(float(snap.get('recommended_delta_vs_keep_rub') or 0.0)) / max(1, delay_days),
            delay_days=0 if action != 'defer' else delay_days,
            uncertainty='medium' if not list(snap.get('quality_caveats') or []) else 'high',
            caveat='; '.join(list(snap.get('quality_caveats') or [])),
            note=note,
        )
        rows.append(_scenario_record(key=action, label=label, action=action, summary=summary, note=note, assumptions=[f"delta_vs_keep_rub={round(delta,2)}"], recommended=False))
    rec = _choose_recommended(rows, preferred_action=_clean(snap.get('recommended_action')))
    for row in rows:
        row['recommended'] = _clean(row.get('scenario_key')) == rec
    formula_rows = list(snap.get('formula_rows') or []) + [
        {'metric': 'expected_net_value_rub', 'formula': 'expected_gain_rub - action_cost_rub - cost_of_delay_rub'},
        {'metric': 'expected_roi', 'formula': '(expected_net_value_rub / action_cost_rub), если action_cost_rub > 0'},
    ]
    return {
        'engine': 'cow_value_culling_v1',
        'scenario_rows': rows,
        'recommended_scenario_key': rec,
        'recommended_action': _clean(snap.get('recommended_action')),
        'recommended_label': _clean(snap.get('recommended_label')),
        'why_now': _clean(snap.get('explanation_short')),
        'factors': list(snap.get('factors') or []),
        'formula_rows': formula_rows,
        'linked_source_facts': list(snap.get('linked_source_facts') or []) + ctx.linked_source_facts,
        'quality_caveats': list(snap.get('quality_caveats') or []),
        'source_versions': {
            'economics_inputs_version': _clean(snap.get('economics_inputs_version')),
            'data_version': ctx.data_version,
        },
    }


def _worklist_based_scenarios(*, base: Mapping[str, Any], ctx: WhatIfContext, family: str, cfg: Mapping[str, Any]) -> dict[str, Any]:
    sm = dict(base.get('summary_metrics') or {})
    base_gain = float(sm.get('expected_gain_rub') or 0.0)
    base_loss = float(sm.get('expected_loss_rub') or 0.0)
    base_cost = float(sm.get('action_cost_rub') or 0.0)
    delay_per_day = float(sm.get('cost_of_delay_per_day_rub') or 0.0)
    uncertainty = 'medium' if not list(base.get('quality_caveats') or []) else 'high'
    caveat = '; '.join(list(base.get('quality_caveats') or []))
    rows: list[dict[str, Any]] = []

    if family == 'treat_protocol':
        delay_days = int(cfg.get('health_delay_days') or 3)
        treat = _summary(gain=base_gain * float(cfg.get('treat_now_gain_multiplier') or 1.0), loss=base_loss * float(cfg.get('treat_now_residual_loss_multiplier') or 0.35), action_cost=base_cost, delay_per_day=delay_per_day, delay_days=0, uncertainty=uncertainty, caveat=caveat, note='Treat now.')
        rows.append(_scenario_record(key='treat_now', label='Treat now', action='treat', summary=treat, note='Немедленное выполнение health/vet action.', assumptions=['treat_now_gain_multiplier', 'treat_now_residual_loss_multiplier']))
        no_treat = _summary(gain=0.0, loss=base_loss * float(cfg.get('no_treat_loss_multiplier') or 1.15), action_cost=0.0, delay_per_day=delay_per_day, delay_days=delay_days, uncertainty='high', caveat=(caveat + '; no_treat scenario increases uncertainty').strip('; '), note='Do not treat in bounded horizon.')
        rows.append(_scenario_record(key='no_treat', label='Do not treat', action='defer', summary=no_treat, note='Отказ от лечения на bounded horizon.', assumptions=['no_treat_loss_multiplier']))
        protocol = _summary(gain=base_gain * float(cfg.get('protocol_change_gain_multiplier') or 1.1), loss=base_loss * float(cfg.get('protocol_change_residual_loss_multiplier') or 0.30), action_cost=base_cost * float(cfg.get('protocol_change_cost_multiplier') or 1.25), delay_per_day=delay_per_day, delay_days=0, uncertainty='medium', caveat=caveat, note='Change protocol.')
        rows.append(_scenario_record(key='change_protocol', label='Change protocol', action='treat', summary=protocol, note='Пересмотреть protocol/route/priority.', assumptions=['protocol_change_gain_multiplier', 'protocol_change_cost_multiplier']))
        monitor = _summary(gain=base_gain * float(cfg.get('monitor_gain_multiplier') or 0.55), loss=base_loss * float(cfg.get('monitor_residual_loss_multiplier') or 0.65), action_cost=base_cost * 0.4, delay_per_day=delay_per_day, delay_days=1, uncertainty='high', caveat=(caveat + '; monitor-first has lower certainty').strip('; '), note='Monitor first.')
        rows.append(_scenario_record(key='monitor_24h', label='Monitor 24h', action='defer', summary=monitor, note='Короткий monitor-first сценарий.', assumptions=['monitor_gain_multiplier', 'monitor_residual_loss_multiplier']))
        preferred = 'treat_now'
    elif family == 'repro_priority':
        delay_days = int(cfg.get('reproduction_delay_days') or 7)
        breed = _summary(gain=base_gain, loss=max(base_loss - base_gain, 0.0), action_cost=float(cfg.get('breed_action_cost_rub') or base_cost), delay_per_day=delay_per_day, delay_days=0, uncertainty=uncertainty, caveat=caveat, note='Breed / repro follow-up now.')
        rows.append(_scenario_record(key='breed_now', label='Breed / execute now', action='breed', summary=breed, note='Выполнить repro action сейчас.', assumptions=['base repro economics']))
        defer = _summary(gain=base_gain * float(cfg.get('defer_gain_multiplier') or 0.7), loss=base_loss * float(cfg.get('defer_loss_multiplier') or 1.05), action_cost=base_cost, delay_per_day=delay_per_day, delay_days=delay_days, uncertainty='high', caveat=(caveat + '; defer lowers expected conversion').strip('; '), note='Defer repro action.')
        rows.append(_scenario_record(key='defer_7d', label='Defer 7d', action='defer', summary=defer, note='Отложить repro action.', assumptions=['defer_gain_multiplier', 'defer_loss_multiplier']))
        reprio = _summary(gain=base_gain * float(cfg.get('reprioritize_gain_multiplier') or 0.9), loss=base_loss * 0.5, action_cost=base_cost * float(cfg.get('reprioritize_cost_multiplier') or 0.5), delay_per_day=delay_per_day, delay_days=int(cfg.get('reprioritize_delay_days') or 0), uncertainty='medium', caveat=caveat, note='Raise priority today.')
        rows.append(_scenario_record(key='reprioritize_today', label='Reprioritize today', action='defer', summary=reprio, note='Поднять приоритет и выполнить в первую очередь.', assumptions=['reprioritize_gain_multiplier', 'reprioritize_cost_multiplier']))
        preferred = 'breed_now'
    elif family == 'group_move':
        delay_days = int(cfg.get('group_move_delay_days') or 7)
        gain = float(cfg.get('group_move_expected_gain_rub') or base_gain or 1800.0)
        cost = float(cfg.get('group_move_action_cost_rub') or base_cost or 500.0)
        move = _summary(gain=gain, loss=max(base_loss - gain, 0.0), action_cost=cost, delay_per_day=max(delay_per_day, gain / max(1, delay_days)), delay_days=0, uncertainty='medium', caveat='Group move is an operational heuristic unless ration/context evidence is available.', note='Move group now.')
        rows.append(_scenario_record(key='move_now', label='Move group now', action='move_group', summary=move, note='Перевести в другую группу сейчас.', assumptions=['group_move_expected_gain_rub']))
        keep = _summary(gain=0.0, loss=base_loss or gain * 0.6, action_cost=0.0, delay_per_day=max(delay_per_day, gain / max(1, delay_days)), delay_days=0, uncertainty='high', caveat='Staying in current group keeps current risk/exposure.', note='Keep current group.')
        rows.append(_scenario_record(key='keep_current_group', label='Keep current group', action='keep', summary=keep, note='Оставить в текущей группе.', assumptions=['bounded status-quo loss']))
        defer = _summary(gain=gain * float(cfg.get('defer_gain_multiplier') or 0.7), loss=(base_loss or gain) * float(cfg.get('group_move_defer_loss_multiplier') or 1.15), action_cost=cost, delay_per_day=max(delay_per_day, gain / max(1, delay_days)), delay_days=delay_days, uncertainty='high', caveat='Deferring group move increases cost of delay.', note='Defer group move.')
        rows.append(_scenario_record(key='defer_move', label='Defer move', action='defer', summary=defer, note='Отложить перевод группы.', assumptions=['group_move_defer_loss_multiplier']))
        preferred = 'move_now'
    elif family == 'milk_quality_protocol':
        delay_days = int(cfg.get('quality_delay_days') or 3)
        treat = _summary(gain=base_gain, loss=max(base_loss - base_gain, 0.0), action_cost=base_cost, delay_per_day=delay_per_day, delay_days=0, uncertainty=uncertainty, caveat=caveat, note='Quality follow-up now.')
        rows.append(_scenario_record(key='treat_now', label='Act now', action='treat', summary=treat, note='Изолировать/перепроверить/лечить сейчас.', assumptions=['base milk quality economics']))
        protocol = _summary(gain=base_gain * float(cfg.get('quality_protocol_gain_multiplier') or 1.08), loss=base_loss * 0.4, action_cost=base_cost * float(cfg.get('quality_protocol_cost_multiplier') or 1.15), delay_per_day=delay_per_day, delay_days=0, uncertainty='medium', caveat=caveat, note='Change milking / handling protocol.')
        rows.append(_scenario_record(key='change_protocol', label='Change protocol', action='treat', summary=protocol, note='Скорректировать milk quality protocol.', assumptions=['quality_protocol_gain_multiplier', 'quality_protocol_cost_multiplier']))
        defer = _summary(gain=base_gain * float(cfg.get('defer_gain_multiplier') or 0.7), loss=base_loss * float(cfg.get('defer_loss_multiplier') or 1.05), action_cost=base_cost, delay_per_day=delay_per_day, delay_days=delay_days, uncertainty='high', caveat=(caveat + '; deferred quality response increases penalty exposure').strip('; '), note='Defer quality action.')
        rows.append(_scenario_record(key='defer_3d', label='Defer 3d', action='defer', summary=defer, note='Отложить quality action.', assumptions=['defer_gain_multiplier', 'defer_loss_multiplier']))
        preferred = 'treat_now'
    elif family == 'fresh_transition':
        delay_days = int(cfg.get('health_delay_days') or 3)
        treat = _summary(gain=base_gain * float(cfg.get('fresh_treat_gain_multiplier') or 1.0), loss=max(base_loss - base_gain, 0.0), action_cost=base_cost, delay_per_day=delay_per_day, delay_days=0, uncertainty=uncertainty, caveat=caveat, note='Fresh-cow follow-up now.')
        rows.append(_scenario_record(key='treat_now', label='Treat / inspect now', action='treat', summary=treat, note='Выполнить fresh transition follow-up сейчас.', assumptions=['fresh_treat_gain_multiplier']))
        protocol = _summary(gain=base_gain * float(cfg.get('fresh_protocol_gain_multiplier') or 1.08), loss=base_loss * 0.45, action_cost=base_cost * 1.1, delay_per_day=delay_per_day, delay_days=0, uncertainty='medium', caveat=caveat, note='Adjust fresh protocol.')
        rows.append(_scenario_record(key='change_protocol', label='Adjust protocol', action='treat', summary=protocol, note='Скорректировать protocol/checklist для fresh group.', assumptions=['fresh_protocol_gain_multiplier']))
        monitor = _summary(gain=base_gain * float(cfg.get('fresh_monitor_gain_multiplier') or 0.6), loss=base_loss * 0.7, action_cost=base_cost * 0.5, delay_per_day=delay_per_day, delay_days=1, uncertainty='high', caveat=(caveat + '; monitor-first leaves residual transition risk').strip('; '), note='Monitor 24h.')
        rows.append(_scenario_record(key='monitor_24h', label='Monitor 24h', action='defer', summary=monitor, note='Короткий monitor-first сценарий.', assumptions=['fresh_monitor_gain_multiplier']))
        preferred = 'treat_now'
    else:
        delay_days = int(cfg.get('default_delay_days') or 7)
        do_now = _summary(gain=base_gain, loss=max(base_loss - base_gain, 0.0), action_cost=base_cost, delay_per_day=delay_per_day, delay_days=0, uncertainty=uncertainty, caveat=caveat, note='Execute now.')
        rows.append(_scenario_record(key='execute_now', label='Execute now', action='reviewed', summary=do_now, note='Выполнить действие сейчас.', assumptions=['base action economics']))
        reprio = _summary(gain=base_gain * float(cfg.get('reprioritize_gain_multiplier') or 0.9), loss=base_loss * 0.5, action_cost=base_cost * float(cfg.get('reprioritize_cost_multiplier') or 0.5), delay_per_day=delay_per_day, delay_days=0, uncertainty='medium', caveat=caveat, note='Reprioritize now.')
        rows.append(_scenario_record(key='reprioritize', label='Reprioritize', action='defer', summary=reprio, note='Поднять/снизить приоритет без отказа от действия.', assumptions=['reprioritize_gain_multiplier']))
        defer = _summary(gain=base_gain * float(cfg.get('defer_gain_multiplier') or 0.7), loss=base_loss * float(cfg.get('defer_loss_multiplier') or 1.05), action_cost=base_cost, delay_per_day=delay_per_day, delay_days=delay_days, uncertainty='high', caveat=(caveat + '; delay adds bounded cost').strip('; '), note='Defer.')
        rows.append(_scenario_record(key='defer', label='Defer', action='defer', summary=defer, note='Отложить действие.', assumptions=['defer_gain_multiplier']))
        preferred = 'execute_now'

    recommended = _choose_recommended(rows, preferred_action=preferred)
    for row in rows:
        row['recommended'] = _clean(row.get('scenario_key')) == recommended
    formula_rows = list(base.get('formula_rows') or []) + [
        {'metric': 'expected_net_value_rub', 'formula': 'expected_gain_rub - action_cost_rub - cost_of_delay_rub'},
        {'metric': 'expected_roi', 'formula': '(expected_net_value_rub / action_cost_rub), если action_cost_rub > 0'},
    ]
    return {
        'engine': _clean(base.get('engine')) or 'economics_per_action_v1',
        'scenario_rows': rows,
        'recommended_scenario_key': recommended,
        'recommended_action': _clean(base.get('recommended_action')) or preferred,
        'recommended_label': _clean(base.get('recommended_label')) or preferred,
        'why_now': _clean(base.get('why_now')),
        'factors': list(base.get('factors') or []),
        'formula_rows': formula_rows,
        'linked_source_facts': list(base.get('linked_source_facts') or []) + ctx.linked_source_facts,
        'quality_caveats': list(base.get('quality_caveats') or []),
        'source_versions': dict(base.get('source_versions') or {}),
    }


def _milk_quality_object_scenarios(*, input_dir: Path, asof_date: date, ctx: WhatIfContext, cfg: Mapping[str, Any], project_root: Path | None) -> dict[str, Any]:
    snap = build_milk_quality_scc_snapshot(
        input_dir=input_dir,
        asof_date=asof_date,
        project_root=project_root,
        data_version=ctx.data_version or None,
        farm_id=ctx.farm_id or None,
        pen_id=(ctx.object_id if ctx.object_type in {'group', 'pen'} else ctx.pen_id) or None,
    )
    rows_src = list(snap.get('animal_contributions') or []) if ctx.object_type == 'animal' else list(snap.get('group_contributions') or [])
    row = next((dict(x) for x in rows_src if _clean(x.get('animal_id') or x.get('pen_id')) == ctx.object_id), {})
    attributed = abs(float(row.get('attributed_economic_adjustment_rub') or 0.0))
    delay_days = int(cfg.get('quality_delay_days') or 3)
    base_delay = attributed / max(1, delay_days)
    scen = []
    act_now = _summary(gain=attributed, loss=max(attributed * 0.2, 0.0), action_cost=650.0, delay_per_day=base_delay, delay_days=0, uncertainty='medium', caveat='Batch SCC estimate only.', note='Act now')
    scen.append(_scenario_record(key='act_now', label='Act now', action='treat', summary=act_now, note='Выполнить quality follow-up сейчас.', assumptions=['attributed_economic_adjustment_rub']))
    prot = _summary(gain=attributed * float(cfg.get('quality_protocol_gain_multiplier') or 1.08), loss=attributed * 0.15, action_cost=650.0 * float(cfg.get('quality_protocol_cost_multiplier') or 1.15), delay_per_day=base_delay, delay_days=0, uncertainty='medium', caveat='Protocol scenario uses bounded uplift.', note='Change protocol')
    scen.append(_scenario_record(key='change_protocol', label='Change protocol', action='treat', summary=prot, note='Пересмотреть milking / handling protocol.', assumptions=['quality_protocol_gain_multiplier']))
    defer = _summary(gain=attributed * 0.7, loss=attributed * 1.05, action_cost=650.0, delay_per_day=base_delay, delay_days=delay_days, uncertainty='high', caveat='Deferral increases penalty exposure.', note='Defer')
    scen.append(_scenario_record(key='defer_3d', label='Defer 3d', action='defer', summary=defer, note='Отложить quality action.', assumptions=['defer_gain_multiplier']))
    rec = _choose_recommended(scen, preferred_action='act_now')
    for rowx in scen:
        rowx['recommended'] = _clean(rowx.get('scenario_key')) == rec
    return {
        'engine': 'milk_quality_scc_cockpit_v1',
        'scenario_rows': scen,
        'recommended_scenario_key': rec,
        'recommended_action': 'treat',
        'recommended_label': 'Act now',
        'why_now': f"attributed_adjustment={round(attributed,2)} ₽",
        'factors': [
            {'factor': 'estimated_bulk_tank_scc', 'value': (snap.get('bulk_tank') or {}).get('estimated_bulk_tank_scc'), 'effect_direction': 'negative', 'note': 'Bulk tank estimate from batch data.'},
            {'factor': 'attributed_economic_adjustment_rub', 'value': row.get('attributed_economic_adjustment_rub'), 'effect_direction': 'negative', 'note': 'Вклад объекта в penalty/bonus.'},
        ],
        'formula_rows': list(snap.get('formula_rows') or []) + [{'metric': 'expected_net_value_rub', 'formula': 'expected_gain_rub - action_cost_rub - cost_of_delay_rub'}],
        'linked_source_facts': list(row.get('linked_source_facts') or []) + ctx.linked_source_facts,
        'quality_caveats': list(snap.get('quality_caveats') or []),
        'source_versions': {'economics_inputs_version': _clean(snap.get('economics_inputs_version')), 'data_version': ctx.data_version},
    }


def _fresh_object_scenarios(*, input_dir: Path, asof_date: date, ctx: WhatIfContext, cfg: Mapping[str, Any], project_root: Path | None) -> dict[str, Any]:
    snap = build_fresh_cows_transition_snapshot(input_dir=input_dir, asof_date=asof_date, project_root=project_root, data_version=ctx.data_version or None, animal_id=(ctx.object_id if ctx.object_type == 'animal' else None), pen_id=(ctx.object_id if ctx.object_type in {'group', 'pen'} else ctx.pen_id or None))
    rows_src = list(snap.get('animal_rows') or [])
    row = next((dict(x) for x in rows_src if _clean(x.get('animal_id')) == ctx.object_id), {}) if ctx.object_type == 'animal' else {}
    base_loss = float(row.get('expected_loss_rub') or 0.0) or float((snap.get('summary_metrics') or {}).get('expected_loss_rub') or 0.0)
    base_gain = float(row.get('expected_gain_rub') or 0.0) or base_loss * 0.55
    delay_per_day = float(row.get('cost_of_delay_per_day_rub') or 0.0) or (base_loss / max(1, int(cfg.get('health_delay_days') or 3)))
    scen = []
    treat = _summary(gain=base_gain * float(cfg.get('fresh_treat_gain_multiplier') or 1.0), loss=max(base_loss - base_gain, 0.0), action_cost=900.0, delay_per_day=delay_per_day, delay_days=0, uncertainty='medium', caveat='Fresh transition uses bounded heuristic.', note='Treat/inspect now')
    scen.append(_scenario_record(key='treat_now', label='Treat / inspect now', action='treat', summary=treat, note='Выполнить fresh follow-up сейчас.', assumptions=['fresh_treat_gain_multiplier']))
    protocol = _summary(gain=base_gain * float(cfg.get('fresh_protocol_gain_multiplier') or 1.08), loss=base_loss * 0.45, action_cost=990.0, delay_per_day=delay_per_day, delay_days=0, uncertainty='medium', caveat='Protocol scenario uses bounded uplift.', note='Change protocol')
    scen.append(_scenario_record(key='change_protocol', label='Change protocol', action='treat', summary=protocol, note='Скорректировать protocol/checklist.', assumptions=['fresh_protocol_gain_multiplier']))
    monitor = _summary(gain=base_gain * float(cfg.get('fresh_monitor_gain_multiplier') or 0.6), loss=base_loss * 0.7, action_cost=450.0, delay_per_day=delay_per_day, delay_days=1, uncertainty='high', caveat='Monitor-first leaves residual risk.', note='Monitor 24h')
    scen.append(_scenario_record(key='monitor_24h', label='Monitor 24h', action='defer', summary=monitor, note='Короткий monitor-first сценарий.', assumptions=['fresh_monitor_gain_multiplier']))
    rec = _choose_recommended(scen, preferred_action='treat_now')
    for rowx in scen:
        rowx['recommended'] = _clean(rowx.get('scenario_key')) == rec
    return {
        'engine': 'fresh_cows_transition_economics_v1',
        'scenario_rows': scen,
        'recommended_scenario_key': rec,
        'recommended_action': 'treat',
        'recommended_label': 'Treat / inspect now',
        'why_now': _clean((snap.get('summary_metrics') or {}).get('high_risk_n')) or 'fresh transition risk',
        'factors': list(row.get('factors') or []),
        'formula_rows': list(snap.get('formula_rows') or []) + [{'metric': 'expected_net_value_rub', 'formula': 'expected_gain_rub - action_cost_rub - cost_of_delay_rub'}],
        'linked_source_facts': list(row.get('linked_source_facts') or []) + ctx.linked_source_facts,
        'quality_caveats': list(snap.get('quality_caveats') or []),
        'source_versions': {'economics_inputs_version': _clean(snap.get('economics_inputs_version')), 'data_version': ctx.data_version},
    }


def build_operational_what_if_snapshot(*, input_dir: Path, asof_date: date, worklist: Mapping[str, Any] | None = None, object_type: str | None = None, object_id: str | None = None, scenario_family: str | None = None, project_root: Path | None = None, cfg_path: str | Path | None = None, data_version: str | None = None) -> dict[str, Any]:
    path, cfg = _load_cfg(project_root=project_root, cfg_path=cfg_path)
    version = describe_operational_what_if_inputs_version(project_root=project_root, cfg_path=cfg_path)
    family = _infer_scenario_family(worklist=worklist, object_type=object_type, scenario_family=scenario_family)
    if worklist is not None:
        ctx = _context_from_worklist(worklist, scenario_family=family)
    else:
        ctx = _context_from_object(input_dir=Path(input_dir), asof_date=asof_date, object_type=_clean(object_type), object_id=_clean(object_id), scenario_family=family, data_version=data_version)
    if not ctx.object_type or not ctx.object_id:
        raise ValueError('operational_what_if_object_required')

    if family == 'cull_keep':
        body = _culling_scenarios(input_dir=Path(input_dir), asof_date=asof_date, ctx=ctx, cfg=cfg, project_root=project_root)
    elif worklist is not None:
        base = build_action_economics_snapshot(input_dir=Path(input_dir), asof_date=asof_date, worklist=worklist, project_root=project_root)
        body = _worklist_based_scenarios(base=base, ctx=ctx, family=family, cfg=cfg)
    elif family == 'milk_quality_protocol':
        body = _milk_quality_object_scenarios(input_dir=Path(input_dir), asof_date=asof_date, ctx=ctx, cfg=cfg, project_root=project_root)
    elif family == 'fresh_transition':
        body = _fresh_object_scenarios(input_dir=Path(input_dir), asof_date=asof_date, ctx=ctx, cfg=cfg, project_root=project_root)
    elif family == 'group_move':
        pseudo = {
            'worklist_id': '', 'worklist_type': 'movement', 'title': ctx.title, 'object_type': ctx.object_type, 'object_id': ctx.object_id,
            'farm_id': ctx.farm_id, 'site_id': ctx.site_id, 'group_id': ctx.pen_id or ctx.object_id, 'pen_id': ctx.pen_id or ctx.object_id,
            'status': 'open', 'due_bucket': 'today', 'data_version': ctx.data_version,
        }
        base = build_action_economics_snapshot(input_dir=Path(input_dir), asof_date=asof_date, worklist=pseudo, project_root=project_root)
        body = _worklist_based_scenarios(base=base, ctx=ctx, family=family, cfg=cfg)
    else:
        pseudo = {
            'worklist_id': '', 'worklist_type': 'manager_review', 'title': ctx.title, 'object_type': ctx.object_type, 'object_id': ctx.object_id,
            'farm_id': ctx.farm_id, 'site_id': ctx.site_id, 'group_id': ctx.pen_id, 'pen_id': ctx.pen_id,
            'status': 'open', 'due_bucket': 'today', 'data_version': ctx.data_version,
        }
        base = build_action_economics_snapshot(input_dir=Path(input_dir), asof_date=asof_date, worklist=pseudo, project_root=project_root)
        body = _worklist_based_scenarios(base=base, ctx=ctx, family=family, cfg=cfg)

    rows = [dict(x) for x in list(body.get('scenario_rows') or [])]
    recommended = _clean(body.get('recommended_scenario_key'))
    selected = next((dict(x) for x in rows if _clean(x.get('scenario_key')) == recommended), dict(rows[0]) if rows else {})
    quality_caveats = list(body.get('quality_caveats') or [])
    if not ctx.data_version:
        quality_caveats.append('data_version отсутствует в object/worklist context')
    return {
        'schema': 'genomeai.operational_what_if.v1',
        'asof_date': asof_date.isoformat(),
        'source': ctx.source,
        'scenario_family': family,
        'object_type': ctx.object_type,
        'object_id': ctx.object_id,
        'farm_id': ctx.farm_id,
        'site_id': ctx.site_id,
        'pen_id': ctx.pen_id,
        'title': ctx.title,
        'worklist_id': ctx.worklist_id,
        'worklist_type': ctx.worklist_type,
        'data_version': ctx.data_version,
        'qc_run': ctx.qc_run,
        'model_version': ctx.model_version,
        'scoring_run': ctx.scoring_run,
        'report_version': ctx.report_version,
        **version,
        'engine': body.get('engine'),
        'recommended_scenario_key': recommended,
        'recommended_action': _clean(body.get('recommended_action')),
        'recommended_label': _clean(body.get('recommended_label')),
        'why_now': _clean(body.get('why_now')),
        'scenario_rows': rows,
        'selected_summary': selected,
        'factors': list(body.get('factors') or []),
        'formula_rows': list(body.get('formula_rows') or []),
        'linked_source_facts': list(body.get('linked_source_facts') or []),
        'quality_caveats': quality_caveats,
        'source_versions': dict(body.get('source_versions') or {}),
    }


def record_operational_what_if_decision_use_case(*, conn, tenant_id: str, user_id: int, username: str, role: str, snapshot: Mapping[str, Any], scenario_key: str, reason: str, comment: str | None = None, request_id: str | None = None) -> dict[str, Any]:
    rows = [dict(x) for x in list(snapshot.get('scenario_rows') or [])]
    chosen = next((dict(x) for x in rows if _clean(x.get('scenario_key')) == _clean(scenario_key)), None)
    if not chosen:
        raise ValueError('operational_what_if_scenario_not_found')
    metadata = {
        'engine': 'operational_what_if_v1',
        'scenario_family': _clean(snapshot.get('scenario_family')),
        'economics_inputs_version': _clean(snapshot.get('economics_inputs_version')),
        'selected_scenario': chosen,
        'recommended_scenario_key': _clean(snapshot.get('recommended_scenario_key')),
        'source_engine': _clean(snapshot.get('engine')),
        'source_versions': dict(snapshot.get('source_versions') or {}),
        'linked_source_facts': list(snapshot.get('linked_source_facts') or []),
        'worklist_id': _clean(snapshot.get('worklist_id')),
    }
    res = append_decision_use_case(
        conn=conn,
        tenant_id=str(tenant_id),
        d=DecisionCreate(
            recommendation_id=_clean(snapshot.get('worklist_id')) or None,
            action=_clean(chosen.get('action')) or 'reviewed',
            user_id=int(user_id),
            username=str(username),
            reason=_clean(reason) or _clean(chosen.get('scenario_key')),
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
        action='operational_what_if.decision.create',
        object_type='decision',
        object_id=str(res.get('decision_id') or ''),
        data_version=_clean(snapshot.get('data_version')) or None,
        request_id=request_id,
        after={'scenario_family': snapshot.get('scenario_family'), 'scenario_key': _clean(chosen.get('scenario_key')), 'expected_net_value_rub': chosen.get('expected_net_value_rub')},
    )
    return {'decision_id': res.get('decision_id'), 'decision': dict(res.get('after') or {}), 'metadata': metadata}


def create_operational_what_if_followup_worklist_use_case(*, conn, tenant_id: str, user_id: int, username: str, role: str, snapshot: Mapping[str, Any], scenario_key: str, due_at: str | None = None, request_id: str | None = None) -> dict[str, Any]:
    rows = [dict(x) for x in list(snapshot.get('scenario_rows') or [])]
    chosen = next((dict(x) for x in rows if _clean(x.get('scenario_key')) == _clean(scenario_key)), None)
    if not chosen:
        raise ValueError('operational_what_if_scenario_not_found')
    family = _clean(snapshot.get('scenario_family'))
    worklist_type = {
        'cull_keep': 'culling_review',
        'treat_protocol': 'health_follow_up',
        'repro_priority': 'reproduction',
        'group_move': 'movement',
        'milk_quality_protocol': 'milk_quality',
        'fresh_transition': 'health_follow_up',
    }.get(family, 'manager_review')
    title = f"Operational what-if · {_clean(chosen.get('label')) or _clean(chosen.get('scenario_key'))}"
    why = {
        'summary': f"Operational what-if · {_clean(snapshot.get('scenario_family'))}",
        'engine': 'operational_what_if_v1',
        'economics_inputs_version': _clean(snapshot.get('economics_inputs_version')),
        'source_engine': _clean(snapshot.get('engine')),
        'selected_scenario': _clean(chosen.get('scenario_key')),
        'expected_net_value_rub': chosen.get('expected_net_value_rub'),
    }
    todo = [
        {'action': f"Scenario: {_clean(chosen.get('label')) or _clean(chosen.get('scenario_key'))}"},
        {'action': f"Expected net value: {float(chosen.get('expected_net_value_rub') or 0.0):.0f} ₽"},
        {'action': f"Cost of delay: {float(chosen.get('cost_of_delay_rub') or 0.0):.0f} ₽"},
    ]
    res = create_worklist_use_case(
        conn=conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id),
        username=str(username),
        role=str(role),
        worklist_type=worklist_type,
        title=title,
        owner_user_id=None,
        assignee_team={'cull_keep': 'team-econ', 'treat_protocol': 'team-health', 'repro_priority': 'team-repro', 'group_move': 'team-econ', 'milk_quality_protocol': 'team-qc', 'fresh_transition': 'team-health'}.get(family, 'team-econ'),
        object_type=_clean(snapshot.get('object_type')) or None,
        object_id=_clean(snapshot.get('object_id')) or None,
        due_at=_clean(due_at) or None,
        priority=1 if bool(chosen.get('recommended')) else 2,
        confidence=None,
        linked_source_facts=list(snapshot.get('linked_source_facts') or []),
        what_to_do=todo,
        why=why,
        data_version=_clean(snapshot.get('data_version')) or None,
        qc_run=_clean(snapshot.get('qc_run')) or None,
        model_version=_clean(snapshot.get('model_version')) or None,
        scoring_run=_clean(snapshot.get('scoring_run')) or None,
        report_version=_clean(snapshot.get('report_version')) or None,
        request_id=request_id,
    )
    write_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id),
        username=str(username),
        role=str(role),
        action='operational_what_if.worklist.create',
        object_type='worklist',
        object_id=str(res.get('worklist_id') or ''),
        data_version=_clean(snapshot.get('data_version')) or None,
        request_id=request_id,
        after={'scenario_family': snapshot.get('scenario_family'), 'scenario_key': _clean(chosen.get('scenario_key')), 'worklist_type': worklist_type},
    )
    return {'worklist_id': res.get('worklist_id'), 'worklist': dict(res.get('worklist') or {}), 'metadata': why}


__all__ = [
    'DEFAULT_CFG_PATH',
    'build_operational_what_if_snapshot',
    'describe_operational_what_if_inputs_version',
    'record_operational_what_if_decision_use_case',
    'create_operational_what_if_followup_worklist_use_case',
]
