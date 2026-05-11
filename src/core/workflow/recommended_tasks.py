"""Build RecommendedTask proposals from open insights.

This module is purely a *projection* — it does not persist anything. It takes
insights (canonical InsightItem-shaped dicts) and produces one RecommendedTask
per insight.recommendation, deriving sensible defaults for editable fields
(priority/assignee_role/due_at). The actual task-creation happens via a
separate endpoint (P1-2b: POST /worklists/from-recommended).
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

SEVERITY_TO_PRIORITY: dict[str, int] = {
    'critical': 1,
    'urgent':   1,
    'high':     1,
    'warn':     2,
    'warning':  2,
    'medium':   2,
    'info':     3,
    'low':      4,
}
DEFAULT_PRIORITY = 3

INSIGHT_TYPE_TO_ROLE: dict[str, str] = {
    'production':   'Zootech',
    'reproduction': 'Zootech',
    'feeding':      'Zootech',
    'health':       'Vet',
    'welfare':      'Vet',
    'economics':    'Director',
}
DEFAULT_ROLE = 'Operator'

ACTIVE_STATUSES = {'to_check', 'in_progress', 'new', 'open'}


def _priority_from_severity(severity: Optional[str]) -> int:
    if not severity:
        return DEFAULT_PRIORITY
    return SEVERITY_TO_PRIORITY.get(str(severity).lower(), DEFAULT_PRIORITY)


def _role_from_type(insight_type: Optional[str]) -> str:
    if not insight_type:
        return DEFAULT_ROLE
    return INSIGHT_TYPE_TO_ROLE.get(str(insight_type).lower(), DEFAULT_ROLE)


def _is_active(status: Optional[str]) -> bool:
    return str(status or '').lower() in ACTIVE_STATUSES


def build_recommended_tasks_from_insights(
    insights: Iterable[Any],
    *,
    only_active: bool = True,
) -> list[dict[str, Any]]:
    """Project a list of insights into recommended-task proposals.

    Accepts InsightItem-shaped objects (pydantic model or dict). Returns a flat
    list of dicts compatible with the RecommendedTask contract.
    """
    out: list[dict[str, Any]] = []
    for ins in insights:
        if hasattr(ins, 'model_dump'):
            ins_d = ins.model_dump()
        elif isinstance(ins, dict):
            ins_d = ins
        else:
            continue

        if only_active and not _is_active(ins_d.get('status')):
            continue

        insight_id = str(ins_d.get('insight_id') or '').strip()
        if not insight_id:
            continue

        recommendations = ins_d.get('recommendations') or []
        priority = _priority_from_severity(ins_d.get('severity'))
        role = _role_from_type(ins_d.get('type'))
        domain = str(ins_d.get('type') or '') or None
        body = str(ins_d.get('body') or '').strip()
        title_prefix = str(ins_d.get('title') or '').strip()
        severity = str(ins_d.get('severity') or 'info')

        if recommendations:
            for idx, rec in enumerate(recommendations):
                if not isinstance(rec, dict):
                    continue
                rec_text = str(rec.get('text') or '').strip()
                if not rec_text:
                    continue
                out.append({
                    'recommended_task_id': f'rec_{insight_id}_{idx}',
                    'source_insight_id': insight_id,
                    'title': rec_text,
                    'description': body or None,
                    'priority': priority,
                    'due_at': rec.get('deadline') or None,
                    'assignee_role': role,
                    'assignee_user_id': None,
                    'domain': domain,
                    'why_summary': f'{title_prefix} (severity={severity})' if title_prefix else f'severity={severity}',
                })
        else:
            action = str(ins_d.get('action') or '').strip()
            if not action:
                continue
            out.append({
                'recommended_task_id': f'rec_{insight_id}_action',
                'source_insight_id': insight_id,
                'title': action,
                'description': body or None,
                'priority': priority,
                'due_at': None,
                'assignee_role': role,
                'assignee_user_id': None,
                'domain': domain,
                'why_summary': f'{title_prefix} (severity={severity})' if title_prefix else f'severity={severity}',
            })

    return out
