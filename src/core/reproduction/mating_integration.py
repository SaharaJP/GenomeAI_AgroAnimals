from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd
import yaml

from core.audit import write_audit
from core.workflow import DecisionCreate, append_decision, create_worklist_use_case, get_worklist, link_worklist_decision_use_case, list_worklists_for_object
from core.reproduction.worklists import build_reproduction_worklists_snapshot

DEFAULT_REPRO_MATING_CONFIG: dict[str, Any] = {
    'decision_action_types': ('inseminate', 'recheck', 'watch_heat'),
    'timing_decision_action_types': ('watch_heat',),
    'mating_cfg_path': 'configs/mating_plan/mating_plan_v1.yaml',
    'approval_required_on_override': True,
    'approval_required_when_blocked': True,
}

DECISION_STATUS_LABELS: dict[str, str] = {
    'ready_for_decision': 'Готово к breeding decision',
    'decision_recorded': 'Breeding decision уже записан',
    'awaiting_timing_window': 'Ожидает окна по времени',
    'blocked_no_mating_plan': 'Нет актуального mating plan',
    'blocked_inbreeding': 'Ограничено по инбридингу',
    'blocked_unavailable_bulls': 'Подходящие быки недоступны',
    'blocked_no_candidates': 'Нет допустимых кандидатов',
}

DECISION_NEXT_STEP: dict[str, str] = {
    'ready_for_decision': 'Выбрать рекомендованного быка и записать breeding decision.',
    'decision_recorded': 'Проверить исполнение решения и linked worklist.',
    'awaiting_timing_window': 'Дождаться подтверждения окна и вернуться к breeding decision.',
    'blocked_no_mating_plan': 'Построить mating plan или обновить артефакт по текущей версии данных.',
    'blocked_inbreeding': 'Передать на review: нет допустимых пар по ограничениям инбридинга.',
    'blocked_unavailable_bulls': 'Передать на review или обновить каталог/доступность быков.',
    'blocked_no_candidates': 'Проверить bulls list, breeding goals и pedigree constraints.',
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


def _latest_run_dir(root: Path) -> Path | None:
    if not root.exists():
        return None
    dirs = [p for p in root.iterdir() if p.is_dir()]
    if not dirs:
        return None
    return sorted(dirs, key=lambda p: p.name)[-1]


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            raw = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
            if isinstance(raw, dict):
                return raw
    except Exception:
        pass
    return {}


def _load_latest_mating_plan(*, artifacts_root: Path, data_version: str, mating_plan_run: str | None = None) -> tuple[str | None, pd.DataFrame]:
    root = Path(artifacts_root) / str(data_version) / 'mating_plan'
    run_dir = (root / str(mating_plan_run)) if str(mating_plan_run or '').strip() else _latest_run_dir(root)
    if not run_dir:
        return None, pd.DataFrame()
    csv = run_dir / 'mating_plan.csv'
    return run_dir.name, _read_csv(csv)


def _load_latest_constraints(*, artifacts_root: Path, data_version: str, pedigree_run: str | None = None) -> tuple[str | None, pd.DataFrame]:
    root = Path(artifacts_root) / str(data_version) / 'pedigree'
    run_dir = (root / str(pedigree_run)) if str(pedigree_run or '').strip() else _latest_run_dir(root)
    if not run_dir:
        return None, pd.DataFrame()
    csv = run_dir / 'inbreeding_constraints.csv'
    return run_dir.name, _read_csv(csv)


def _recommended_bulls_for_cow(df: pd.DataFrame, cow_id: str, bulls_df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []
    rows = df[df.get('cow_id', pd.Series(dtype=object)).astype(str) == str(cow_id)].copy()
    if rows.empty:
        return []
    bull_map: dict[str, dict[str, Any]] = {}
    if not bulls_df.empty:
        b = bulls_df.copy()
        if 'bull_id' in b.columns:
            for r in b.to_dict(orient='records'):
                bull_map[str(r.get('bull_id') or '')] = dict(r)
    out: list[dict[str, Any]] = []
    for r in rows.sort_values(['rank', 'score'], ascending=[True, False]).to_dict(orient='records'):
        bull_id = _clean(r.get('bull_id'))
        bull_meta = dict(bull_map.get(bull_id) or {})
        available_raw = bull_meta.get('available')
        available = None if available_raw is None or (isinstance(available_raw, float) and pd.isna(available_raw)) else bool(available_raw)
        out.append({
            'bull_id': bull_id,
            'rank': int(r.get('rank') or 0),
            'score': float(r.get('score') or 0.0),
            'confidence': _clean(r.get('confidence')) or '—',
            'reasons': _clean(r.get('reasons')) or '—',
            'constraints_reason_code': _clean(r.get('constraints_reason_code')) or 'OK',
            'constraints_confidence': _clean(r.get('constraints_confidence')) or '—',
            'available': available,
            'breed': _clean(bull_meta.get('breed')),
            'origin': _clean(bull_meta.get('origin')),
            'dose_price_rub': bull_meta.get('dose_price_rub') if 'dose_price_rub' in bull_meta else bull_meta.get('dose_price'),
        })
    return out


def _constraint_summary_for_cow(df: pd.DataFrame, cow_id: str, bulls_df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {'status': 'none', 'allowed_bulls_n': 0, 'forbidden_bulls_n': 0, 'reason_code': 'NO_CONSTRAINTS'}
    c = df[df.get('cow_id', pd.Series(dtype=object)).astype(str) == str(cow_id)].copy()
    if c.empty:
        return {'status': 'none', 'allowed_bulls_n': 0, 'forbidden_bulls_n': 0, 'reason_code': 'NO_CONSTRAINTS'}

    c['bull_id'] = c.get('bull_id', pd.Series(dtype=object)).astype(str)
    if 'allowed' in c.columns:
        allowed = c[c['allowed'].astype(bool) == True].copy()  # noqa: E712
        forbidden = c[c['allowed'].astype(bool) != True].copy()
    else:
        allowed = c.copy()
        forbidden = pd.DataFrame(columns=c.columns)
    allowed_bulls = set(allowed['bull_id'].astype(str).tolist())
    forbidden_bulls = set(forbidden['bull_id'].astype(str).tolist())

    unavailable_allowed_n = 0
    if not bulls_df.empty and 'bull_id' in bulls_df.columns:
        bb = bulls_df.copy()
        bb['bull_id'] = bb['bull_id'].astype(str)
        if 'available' in bb.columns:
            allowed_df = bb[bb['bull_id'].isin(allowed_bulls)].copy()
            if not allowed_df.empty:
                unavailable_allowed_n = int((allowed_df['available'].fillna(False).astype(bool) == False).sum())  # noqa: E712

    if not allowed_bulls and forbidden_bulls:
        reason_code = _clean(forbidden.get('reason_code', pd.Series(dtype=object)).astype(str).iloc[0] if not forbidden.empty and 'reason_code' in forbidden.columns else 'COMMON_ANCESTOR_WITHIN_N')
        return {
            'status': 'blocked_inbreeding',
            'allowed_bulls_n': 0,
            'forbidden_bulls_n': len(forbidden_bulls),
            'unavailable_allowed_bulls_n': unavailable_allowed_n,
            'reason_code': reason_code or 'COMMON_ANCESTOR_WITHIN_N',
        }
    if allowed_bulls and unavailable_allowed_n >= len(allowed_bulls):
        return {
            'status': 'blocked_unavailable_bulls',
            'allowed_bulls_n': len(allowed_bulls),
            'forbidden_bulls_n': len(forbidden_bulls),
            'unavailable_allowed_bulls_n': unavailable_allowed_n,
            'reason_code': 'UNAVAILABLE_BULLS_ONLY',
        }
    return {
        'status': 'ok',
        'allowed_bulls_n': len(allowed_bulls),
        'forbidden_bulls_n': len(forbidden_bulls),
        'unavailable_allowed_bulls_n': unavailable_allowed_n,
        'reason_code': 'OK',
    }


def _load_existing_breeding_decisions(conn, *, tenant_id: str, animal_id: str) -> list[dict[str, Any]]:
    if conn is None:
        return []
    try:
        rows = list_worklists_for_object  # quiet linter for shared imports
        cur = conn.execute(
            """
            SELECT decision_id, created_at, action, object_id, metadata, data_version
            FROM decision_log_v2
            WHERE tenant_id=? AND object_type='animal' AND object_id=? AND action LIKE 'BREEDING_DECISION.%'
            ORDER BY created_at DESC, id DESC
            LIMIT 20
            """,
            (str(tenant_id), str(animal_id)),
        )
        out = []
        for row in cur.fetchall():
            metadata_raw = row['metadata'] if isinstance(row, Mapping) else row[4]
            try:
                metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) and metadata_raw.strip() else {}
            except Exception:
                metadata = {}
            out.append({
                'decision_id': row['decision_id'] if isinstance(row, Mapping) else row[0],
                'created_at': row['created_at'] if isinstance(row, Mapping) else row[1],
                'action': row['action'] if isinstance(row, Mapping) else row[2],
                'metadata': metadata,
                'data_version': row['data_version'] if isinstance(row, Mapping) else row[5],
            })
        return out
    except Exception:
        return []


def build_repro_mating_integration_snapshot(
    *,
    input_dir: Path,
    artifacts_root: Path,
    data_version: str,
    asof_date: date,
    conn=None,
    tenant_id: str | None = None,
    animal_id: str | None = None,
    pen_id: str | None = None,
    mating_plan_run: str | None = None,
    pedigree_run: str | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = dict(DEFAULT_REPRO_MATING_CONFIG)
    cfg.update(dict(config or {}))

    repro_snapshot = build_reproduction_worklists_snapshot(
        input_dir=Path(input_dir),
        asof_date=asof_date,
        conn=conn,
        tenant_id=tenant_id,
        animal_id=animal_id,
        pen_id=pen_id,
    )
    repro_rows = list(repro_snapshot.get('items') or [])

    if animal_id:
        repro_rows = [r for r in repro_rows if _clean(r.get('animal_id')) == _clean(animal_id)]
    if pen_id:
        repro_rows = [r for r in repro_rows if _clean(r.get('pen_id')) == _clean(pen_id)]

    base = Path(input_dir)
    bulls_df = _read_csv(base / 'dm_bulls.csv')
    mating_run_id, mating_df = _load_latest_mating_plan(artifacts_root=Path(artifacts_root), data_version=str(data_version), mating_plan_run=mating_plan_run)
    pedigree_run_id, constraints_df = _load_latest_constraints(artifacts_root=Path(artifacts_root), data_version=str(data_version), pedigree_run=pedigree_run)
    mating_cfg = _load_yaml(Path(cfg.get('mating_cfg_path') or 'configs/mating_plan/mating_plan_v1.yaml'))
    weights = dict(mating_cfg.get('weights') or {})
    need_boost = dict(mating_cfg.get('need_boost') or {})

    decision_action_types = {str(x).strip() for x in (cfg.get('decision_action_types') or []) if str(x).strip()}
    timing_action_types = {str(x).strip() for x in (cfg.get('timing_decision_action_types') or []) if str(x).strip()}

    queue: list[dict[str, Any]] = []
    for row in repro_rows:
        action_type = _clean(row.get('action_type'))
        if action_type not in decision_action_types:
            continue
        animal_key = _clean(row.get('animal_id'))
        if not animal_key:
            continue
        recs = _recommended_bulls_for_cow(mating_df, animal_key, bulls_df)
        constr = _constraint_summary_for_cow(constraints_df, animal_key, bulls_df)
        existing_decisions = _load_existing_breeding_decisions(conn, tenant_id=str(tenant_id or 'default'), animal_id=animal_key)
        existing_worklist_id = _clean(row.get('existing_worklist_id'))
        existing_linked_decision_id = ''
        if conn is not None and existing_worklist_id:
            try:
                wl = get_worklist(conn, tenant_id=str(tenant_id or 'default'), worklist_id=existing_worklist_id) or {}
                existing_linked_decision_id = _clean(wl.get('linked_decision_id'))
            except Exception:
                existing_linked_decision_id = ''

        if existing_decisions or existing_linked_decision_id:
            decision_status = 'decision_recorded'
        elif action_type in timing_action_types and action_type != 'inseminate':
            decision_status = 'awaiting_timing_window'
        elif recs:
            decision_status = 'ready_for_decision'
        elif not mating_run_id:
            decision_status = 'blocked_no_mating_plan'
        elif constr.get('status') == 'blocked_inbreeding':
            decision_status = 'blocked_inbreeding'
        elif constr.get('status') == 'blocked_unavailable_bulls':
            decision_status = 'blocked_unavailable_bulls'
        else:
            decision_status = 'blocked_no_candidates'

        pending_decision = decision_status == 'ready_for_decision'
        requires_approval = bool(
            (cfg.get('approval_required_when_blocked') and decision_status.startswith('blocked_'))
            or decision_status == 'awaiting_timing_window'
        )

        linked_source_facts = list(row.get('linked_source_facts') or [])
        linked_source_facts.append({'label': 'Due action', 'text': _clean(row.get('action_label')) or action_type or '—'})
        if mating_run_id:
            linked_source_facts.append({'label': 'Mating plan run', 'text': mating_run_id})
        if pedigree_run_id:
            linked_source_facts.append({'label': 'Pedigree run', 'text': pedigree_run_id})
        if constr.get('reason_code') and constr.get('reason_code') != 'OK':
            linked_source_facts.append({'label': 'Constraint', 'text': str(constr.get('reason_code'))})

        queue.append({
            **dict(row),
            'decision_status': decision_status,
            'decision_status_label': DECISION_STATUS_LABELS.get(decision_status, decision_status),
            'pending_decision': pending_decision,
            'requires_approval': requires_approval,
            'approval_hint': 'Нужен manager review / approval.' if requires_approval else '',
            'next_breeding_step': DECISION_NEXT_STEP.get(decision_status, 'Открыть mating surface и выбрать следующий шаг.'),
            'mating_plan_run': mating_run_id or '',
            'pedigree_run': pedigree_run_id or '',
            'top_recommendations': recs,
            'constraints_summary': constr,
            'breeding_goal_weights': weights,
            'breeding_need_boost': need_boost,
            'linked_source_facts': linked_source_facts,
            'existing_breeding_decisions': existing_decisions,
            'existing_linked_decision_id': existing_linked_decision_id,
            'source_versions': {
                'data_version': str(data_version or ''),
                'mating_plan_run': mating_run_id or '',
                'pedigree_run': pedigree_run_id or '',
            },
            'recommendation_id': f"mating_plan:{mating_run_id}:{animal_key}" if mating_run_id else '',
        })

    queue.sort(key=lambda r: (str(r.get('due_at') or ''), int(r.get('priority') or 9), str(r.get('animal_id') or '')))
    summary = {
        'total': len(queue),
        'ready_for_decision_n': sum(1 for r in queue if str(r.get('decision_status')) == 'ready_for_decision'),
        'decision_recorded_n': sum(1 for r in queue if str(r.get('decision_status')) == 'decision_recorded'),
        'blocked_n': sum(1 for r in queue if str(r.get('decision_status')).startswith('blocked_')),
        'requires_approval_n': sum(1 for r in queue if bool(r.get('requires_approval'))),
        'with_mating_plan_n': sum(1 for r in queue if str(r.get('mating_plan_run') or '').strip()),
        'without_mating_plan_n': sum(1 for r in queue if not str(r.get('mating_plan_run') or '').strip()),
    }
    by_status: dict[str, int] = {}
    for row in queue:
        by_status[str(row.get('decision_status') or '—')] = by_status.get(str(row.get('decision_status') or '—'), 0) + 1
    summary['by_status'] = by_status

    return {
        'summary': summary,
        'queue': queue,
        'breeding_goal_weights': weights,
        'breeding_need_boost': need_boost,
        'source_versions': {'data_version': str(data_version or ''), 'mating_plan_run': mating_run_id or '', 'pedigree_run': pedigree_run_id or ''},
    }


def append_breeding_decision_use_case(
    *,
    conn,
    tenant_id: str,
    animal_id: str,
    chosen_bull_id: str,
    user_id: int,
    username: str,
    role: str,
    reason: str,
    comment: str | None = None,
    farm_id: str | None = None,
    group_id: str | None = None,
    data_version: str | None = None,
    mating_plan_run: str | None = None,
    pedigree_run: str | None = None,
    worklist_id: str | None = None,
    recommendation_id: str | None = None,
    recommendation_rank: int | None = None,
    override: bool = False,
    approval_required: bool = False,
    constraints: Mapping[str, Any] | None = None,
    source_versions: Mapping[str, Any] | None = None,
    source_facts: Sequence[Mapping[str, Any]] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    animal_id = _clean(animal_id)
    bull_id = _clean(chosen_bull_id)
    if not animal_id:
        raise ValueError('animal_id_required')
    if not bull_id:
        raise ValueError('bull_id_required')
    if not _clean(reason):
        raise ValueError('reason_required')

    action = 'BREEDING_DECISION.OVERRIDE' if bool(override) else 'BREEDING_DECISION.CONFIRM'
    d = DecisionCreate(
        recommendation_id=_clean(recommendation_id) or (f'mating_plan:{mating_plan_run}:{animal_id}' if _clean(mating_plan_run) else None),
        action=action,
        user_id=int(user_id or 0),
        username=str(username or ''),
        reason=_clean(reason),
        comment=(_clean(comment) or None),
        related_alert=None,
        object_type='animal',
        object_id=animal_id,
        farm_id=(_clean(farm_id) or None),
        group_id=(_clean(group_id) or None),
        data_version=(_clean(data_version) or None),
        model_version=None,
        report_version=None,
        qc_run=None,
        scoring_run=None,
        metadata={
            'decision_kind': 'breeding_decision',
            'chosen_bull_id': bull_id,
            'recommendation_rank': recommendation_rank,
            'mating_plan_run': _clean(mating_plan_run),
            'pedigree_run': _clean(pedigree_run),
            'override': bool(override),
            'approval_required': bool(approval_required),
            'constraints': dict(constraints or {}),
            'source_versions': dict(source_versions or {}),
            'source_facts': list(source_facts or []),
            'request_id': _clean(request_id),
        },
    )
    decision_id = append_decision(conn, tenant_id=str(tenant_id), d=d)
    linked = None
    if _clean(worklist_id):
        linked = link_worklist_decision_use_case(
            conn=conn,
            tenant_id=str(tenant_id),
            worklist_id=str(worklist_id),
            linked_decision_id=str(decision_id),
            user_id=int(user_id or 0),
            username=str(username or ''),
            role=str(role or ''),
            request_id=request_id,
        )
    write_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id or 0),
        username=str(username or ''),
        role=str(role or ''),
        action='repro_mating.append_decision',
        object_type='animal',
        object_id=animal_id,
        data_version=(_clean(data_version) or None),
        before={},
        after={'decision_id': decision_id, 'bull_id': bull_id, 'worklist_id': _clean(worklist_id), 'override': bool(override), 'approval_required': bool(approval_required)},
        status='OK',
        request_id=(_clean(request_id) or None),
    )
    return {'decision_id': str(decision_id), 'linked': linked or {}, 'action': action}


def create_breeding_review_worklist_use_case(
    *,
    conn,
    tenant_id: str,
    animal_id: str,
    user_id: int,
    username: str,
    role: str,
    title: str,
    why: Mapping[str, Any],
    linked_source_facts: Sequence[Mapping[str, Any]],
    due_at: str | None = None,
    farm_id: str | None = None,
    group_id: str | None = None,
    data_version: str | None = None,
    dedupe_key: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    return create_worklist_use_case(
        conn=conn,
        tenant_id=str(tenant_id),
        worklist_type='manager_review',
        user_id=int(user_id or 0),
        username=str(username or ''),
        role=str(role or ''),
        title=str(title or f'Breeding review · {animal_id}'),
        task_type='repro.breeding_review',
        domain='repro',
        priority=1,
        due_at=str(due_at or ''),
        owner_user_id=None,
        assignee_team='team-repro',
        confidence=0.9,
        object_type='animal',
        object_id=str(animal_id),
        linked_source_facts=list(linked_source_facts or []),
        why={**dict(why or {}), 'farm_id': _clean(farm_id), 'group_id': _clean(group_id)},
        what_to_do=[{'action': 'manager_review', 'label': 'Провести breeding review / approval.'}],
        data_version=(_clean(data_version) or None),
        dedupe_key=_clean(dedupe_key) or None,
        request_id=request_id,
    )


__all__ = [
    'DEFAULT_REPRO_MATING_CONFIG',
    'DECISION_STATUS_LABELS',
    'append_breeding_decision_use_case',
    'build_repro_mating_integration_snapshot',
    'create_breeding_review_worklist_use_case',
]
