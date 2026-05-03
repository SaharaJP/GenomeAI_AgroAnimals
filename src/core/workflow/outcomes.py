from __future__ import annotations

import uuid
from datetime import datetime
from statistics import mean, median
from typing import Any, Mapping, Optional

from core.audit import write_audit
from core.infra import CompletionOutcomesRepo, TasksRepo
from core.infra.web_db import utcnow_iso
from core.workflow.decisions import DecisionCreate, append_decision
from core.workflow.policies import parse_iso_dt, validate_reason_for_completion_outcome
from core.workflow.tasks import close_task, get_task, update_task_fields
from core.workflow.alerts import resolve_alert


FINAL_OUTCOME_STATUSES = frozenset({'done', 'cancelled', 'no_effect'})


def _hours_between(start: str | None, end: str | None) -> float | None:
    dt_start = parse_iso_dt(start)
    dt_end = parse_iso_dt(end)
    if not dt_start or not dt_end:
        return None
    return round(max(0.0, (dt_end - dt_start).total_seconds() / 3600.0), 3)


def _safe_float(value: Any) -> float | None:
    if value in (None, ''):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _build_metrics(before: Mapping[str, Any], now_iso: str, *, auto_alert_resolved: bool, auto_decision_created: bool) -> dict[str, Any]:
    due_at = str(before.get('due_at') or '').strip() or None
    created_at = str(before.get('created_at') or '').strip() or None
    started_at = str(before.get('started_at') or '').strip() or None
    due_dt = parse_iso_dt(due_at)
    now_dt = parse_iso_dt(now_iso)
    overdue = bool(due_dt and now_dt and due_dt < now_dt)
    created_to_outcome_h = _hours_between(created_at, now_iso)
    started_to_outcome_h = _hours_between(started_at, now_iso)
    score = None
    if overdue:
        score = 0.4
    elif started_at:
        score = 1.0
    elif created_at:
        score = 0.8
    return {
        'was_overdue_at_outcome': overdue,
        'created_to_outcome_hours': created_to_outcome_h,
        'started_to_outcome_hours': started_to_outcome_h,
        'auto_alert_resolved': bool(auto_alert_resolved),
        'auto_decision_created': bool(auto_decision_created),
        'execution_quality_score': score,
    }


def get_completion_outcome(conn, *, tenant_id: str, outcome_id: str) -> dict[str, Any] | None:
    return CompletionOutcomesRepo(conn).get(tenant_id=tenant_id, outcome_id=outcome_id)


def list_completion_outcomes(
    conn,
    *,
    tenant_id: str,
    task_id: str | None = None,
    worklist_id: str | None = None,
    linked_decision_id: str | None = None,
    related_alert: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    outcome_status: str | None = None,
    worklist_type: str | None = None,
    assignee_team: str | None = None,
    outcome_role: str | None = None,
    owner_user_id: int | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    return CompletionOutcomesRepo(conn).list_rows(
        tenant_id=tenant_id,
        filters={
            'task_id': task_id,
            'worklist_id': worklist_id,
            'linked_decision_id': linked_decision_id,
            'related_alert': related_alert,
            'object_type': object_type,
            'object_id': object_id,
            'outcome_status': outcome_status,
            'worklist_type': worklist_type,
            'assignee_team': assignee_team,
            'outcome_role': outcome_role,
            'owner_user_id': owner_user_id,
            'created_from': created_from,
            'created_to': created_to,
            'q': q,
        },
        limit=limit,
        offset=offset,
    )


def _maybe_auto_link_decision(
    conn,
    *,
    tenant_id: str,
    before: Mapping[str, Any],
    outcome_status: str,
    reason_code: str,
    comment: str | None,
    user_id: int,
    username: str,
    role: str,
    now_iso: str,
    enable: bool,
) -> tuple[str | None, bool]:
    existing = str(before.get('linked_decision_id') or '').strip() or None
    if existing or not enable:
        return existing, False
    if str(before.get('object_type') or '').strip() == '' and str(before.get('related_alert') or '').strip() == '':
        return None, False
    decision_id = append_decision(
        conn,
        tenant_id=tenant_id,
        d=DecisionCreate(
            recommendation_id=None,
            action='worklist.outcome',
            user_id=int(user_id),
            username=str(username or ''),
            reason=str(reason_code),
            comment=(str(comment) if comment else None),
            related_alert=(str(before.get('related_alert')) if before.get('related_alert') else None),
            object_type=(str(before.get('object_type')) if before.get('object_type') else None),
            object_id=(str(before.get('object_id')) if before.get('object_id') else None),
            farm_id=None,
            group_id=None,
            data_version=(str(before.get('data_version')) if before.get('data_version') else None),
            model_version=(str(before.get('model_version')) if before.get('model_version') else None),
            report_version=(str(before.get('report_version')) if before.get('report_version') else None),
            qc_run=(str(before.get('qc_run')) if before.get('qc_run') else None),
            scoring_run=(str(before.get('scoring_run')) if before.get('scoring_run') else None),
            metadata={
                'task_id': before.get('task_id'),
                'worklist_id': before.get('task_id'),
                'outcome_status': outcome_status,
                'outcome_reason_code': reason_code,
                'auto_linked': True,
                'outcome_role': role,
            },
        ),
        created_at=now_iso,
    )
    update_task_fields(conn, tenant_id=tenant_id, task_id=str(before.get('task_id')), patch={'linked_decision_id': decision_id})
    return decision_id, True


def _maybe_auto_resolve_alert(
    conn,
    *,
    tenant_id: str,
    before: Mapping[str, Any],
    outcome_status: str,
    reason_code: str,
    linked_decision_id: str | None,
    user_id: int,
    enable: bool,
) -> bool:
    alert_id = str(before.get('related_alert') or '').strip() or None
    if not enable or not alert_id or outcome_status != 'done' or not linked_decision_id:
        return False
    resolve_alert(
        conn,
        tenant_id=tenant_id,
        alert_id=alert_id,
        user_id=int(user_id),
        reason=f'worklist_outcome_done:{reason_code}'[:500],
    )
    return True


def record_completion_outcome_use_case(
    *,
    conn,
    tenant_id: str,
    worklist_id: str,
    user_id: int,
    username: str,
    role: str,
    outcome_status: str,
    reason_code: str,
    comment: str | None = None,
    due_at: str | None = None,
    owner_user_id: int | None = None,
    assignee_team: str | None = None,
    priority: int | None = None,
    auto_link_decision: bool = True,
    auto_resolve_related_alert: bool = True,
    request_id: str | None = None,
) -> dict[str, Any]:
    status = str(outcome_status or '').strip()
    reason = validate_reason_for_completion_outcome(outcome_status=status, reason_code=reason_code)
    before = get_task(conn, tenant_id=tenant_id, task_id=worklist_id)
    if not before:
        raise KeyError('not_found')
    now_iso = utcnow_iso()
    auto_actions: dict[str, Any] = {}

    if status in FINAL_OUTCOME_STATUSES:
        mapped_close_status = 'cancelled' if status == 'cancelled' else 'done'
        close_task(
            conn,
            tenant_id=tenant_id,
            task_id=worklist_id,
            user_id=int(user_id),
            username=str(username or ''),
            status=mapped_close_status,
            reason=reason,
            comment=(str(comment) if comment else None),
            resolve_related_alert=False,
        )
    elif status == 'deferred':
        patch: dict[str, Any] = {
            'status': 'open',
            'stage': 'plan',
        }
        patch['due_at'] = str(due_at or before.get('due_at') or '') or None
        if owner_user_id is not None:
            patch['owner_user_id'] = int(owner_user_id)
        if assignee_team is not None:
            patch['assignee_team'] = str(assignee_team) or None
        if priority is not None:
            patch['priority'] = int(priority)
        update_task_fields(conn, tenant_id=tenant_id, task_id=worklist_id, patch=patch)
    elif status == 'escalated':
        patch = {
            'status': 'open',
            'stage': 'review',
        }
        if due_at is not None:
            patch['due_at'] = str(due_at) or None
        if owner_user_id is not None:
            patch['owner_user_id'] = int(owner_user_id)
        if assignee_team is not None:
            patch['assignee_team'] = str(assignee_team) or None
        if priority is not None:
            patch['priority'] = int(priority)
        update_task_fields(conn, tenant_id=tenant_id, task_id=worklist_id, patch=patch)
    else:
        raise ValueError(f'invalid_outcome_status: expected one of {sorted(FINAL_OUTCOME_STATUSES | {"deferred", "escalated"})}, got {status}')

    after_task = get_task(conn, tenant_id=tenant_id, task_id=worklist_id) or before
    linked_decision_id = str(after_task.get('linked_decision_id') or '').strip() or None
    created_decision_id, auto_decision_created = _maybe_auto_link_decision(
        conn,
        tenant_id=tenant_id,
        before=after_task,
        outcome_status=status,
        reason_code=reason,
        comment=comment,
        user_id=user_id,
        username=username,
        role=role,
        now_iso=now_iso,
        enable=bool(auto_link_decision and status in {'deferred', 'escalated'}),
    )
    linked_decision_id = created_decision_id or linked_decision_id
    auto_actions['decision_auto_linked'] = bool(auto_decision_created)
    auto_actions['decision_id'] = linked_decision_id

    alert_resolved = _maybe_auto_resolve_alert(
        conn,
        tenant_id=tenant_id,
        before=after_task,
        outcome_status=status,
        reason_code=reason,
        linked_decision_id=linked_decision_id,
        user_id=user_id,
        enable=bool(auto_resolve_related_alert),
    )
    auto_actions['alert_resolved'] = bool(alert_resolved)
    auto_actions['alert_id'] = after_task.get('related_alert')

    metrics = _build_metrics(before, now_iso, auto_alert_resolved=alert_resolved, auto_decision_created=auto_decision_created)
    outcome_id = uuid.uuid4().hex
    repo = CompletionOutcomesRepo(conn)
    repo.append(
        tenant_id=tenant_id,
        outcome_id=outcome_id,
        created_at=now_iso,
        payload={
            'worklist_id': worklist_id,
            'task_id': worklist_id,
            'linked_decision_id': linked_decision_id,
            'related_alert': after_task.get('related_alert'),
            'object_type': after_task.get('object_type'),
            'object_id': after_task.get('object_id'),
            'owner_user_id': after_task.get('owner_user_id'),
            'assignee_team': after_task.get('assignee_team'),
            'worklist_type': after_task.get('worklist_type'),
            'priority': after_task.get('priority'),
            'confidence': _safe_float(after_task.get('confidence')),
            'due_at': after_task.get('due_at'),
            'outcome_status': status,
            'reason_code': reason,
            'comment': (str(comment) if comment else None),
            'outcome_by': int(user_id),
            'outcome_by_username': str(username or ''),
            'outcome_role': str(role or ''),
            'request_id': (str(request_id) if request_id else None),
            'data_version': after_task.get('data_version'),
            'qc_run': after_task.get('qc_run'),
            'model_version': after_task.get('model_version'),
            'scoring_run': after_task.get('scoring_run'),
            'report_version': after_task.get('report_version'),
            'metrics': metrics,
            'auto_actions': auto_actions,
        },
    )

    TasksRepo(conn).update_fields(
        tenant_id=tenant_id,
        task_id=worklist_id,
        sets=[
            'latest_outcome_id=?',
            'latest_outcome_status=?',
            'latest_outcome_reason_code=?',
            'latest_outcome_at=?',
            'latest_outcome_by=?',
            'latest_outcome_comment=?',
            'outcome_metrics_json=?',
            'linked_decision_id=?',
            'updated_at=?',
        ],
        args=[
            outcome_id,
            status,
            reason,
            now_iso,
            int(user_id),
            (str(comment) if comment else None),
            __import__('json').dumps(metrics, ensure_ascii=False),
            linked_decision_id,
            now_iso,
        ],
    )
    after = get_task(conn, tenant_id=tenant_id, task_id=worklist_id) or after_task
    outcome = repo.get(tenant_id=tenant_id, outcome_id=outcome_id) or {'outcome_id': outcome_id, 'outcome_status': status, 'reason_code': reason}

    write_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id or 0),
        username=str(username or ''),
        role=str(role or ''),
        action='completion_outcome.record',
        object_type='completion_outcome',
        object_id=str(outcome_id),
        data_version=(after or {}).get('data_version'),
        before=dict(before or {}),
        after={'task': dict(after or {}), 'outcome': dict(outcome or {})},
        status='OK',
        request_id=(str(request_id) if request_id else None),
    )
    return {
        'before': before or {},
        'after': after or {},
        'outcome': outcome,
        'auto_actions': auto_actions,
    }


def aggregate_execution_quality_metrics(
    conn,
    *,
    tenant_id: str,
    created_from: str | None = None,
    created_to: str | None = None,
    worklist_type: str | None = None,
    assignee_team: str | None = None,
    outcome_role: str | None = None,
) -> dict[str, Any]:
    rows = CompletionOutcomesRepo(conn).metric_rows(
        tenant_id=tenant_id,
        filters={
            'created_from': created_from,
            'created_to': created_to,
            'worklist_type': worklist_type,
            'assignee_team': assignee_team,
            'outcome_role': outcome_role,
        },
    )
    total = len(rows)
    by_status: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    by_team: dict[str, int] = {}
    turnaround_values: list[float] = []
    on_time_known = 0
    on_time_good = 0
    auto_alert_resolved = 0
    auto_decision_linked = 0
    for row in rows:
        st = str(row.get('outcome_status') or '')
        rs = str(row.get('reason_code') or '')
        team = str(row.get('assignee_team') or '') or 'unassigned'
        by_status[st] = by_status.get(st, 0) + 1
        by_reason[rs] = by_reason.get(rs, 0) + 1
        by_team[team] = by_team.get(team, 0) + 1
        metrics = dict(row.get('metrics') or {})
        auto = dict(row.get('auto_actions') or {})
        if metrics.get('created_to_outcome_hours') is not None:
            try:
                turnaround_values.append(float(metrics.get('created_to_outcome_hours')))
            except Exception:
                pass
        if 'was_overdue_at_outcome' in metrics:
            on_time_known += 1
            if not bool(metrics.get('was_overdue_at_outcome')):
                on_time_good += 1
        if bool(auto.get('alert_resolved')):
            auto_alert_resolved += 1
        if bool(auto.get('decision_auto_linked')) or bool(row.get('linked_decision_id')):
            auto_decision_linked += 1
    bottlenecks = [
        {'team': team, 'count': count}
        for team, count in sorted(by_team.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        if count > 0
    ]
    return {
        'total': total,
        'by_outcome_status': by_status,
        'by_reason_code': by_reason,
        'on_time_rate': round(on_time_good / on_time_known, 4) if on_time_known else None,
        'auto_alert_resolution_rate': round(auto_alert_resolved / total, 4) if total else None,
        'decision_link_rate': round(auto_decision_linked / total, 4) if total else None,
        'mean_created_to_outcome_hours': round(mean(turnaround_values), 3) if turnaround_values else None,
        'median_created_to_outcome_hours': round(median(turnaround_values), 3) if turnaround_values else None,
        'bottlenecks': bottlenecks,
        'filters': {
            'created_from': created_from,
            'created_to': created_to,
            'worklist_type': worklist_type,
            'assignee_team': assignee_team,
            'outcome_role': outcome_role,
        },
    }


__all__ = [
    'FINAL_OUTCOME_STATUSES',
    'aggregate_execution_quality_metrics',
    'get_completion_outcome',
    'list_completion_outcomes',
    'record_completion_outcome_use_case',
]
