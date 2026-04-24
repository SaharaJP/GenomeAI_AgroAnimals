from __future__ import annotations

from typing import Any, Optional

from core.workflow.alerts import list_alerts
from core.workflow.policies import task_active_status_options
from core.workflow.tasks import compute_tasks_metrics, compute_tasks_overdue_list


def tasks_metrics_use_case(
    *,
    conn: Any,
    tenant_id: str,
    window_days: Optional[int] = None,
) -> dict[str, Any]:
    """Canonical core entrypoint for workflow execution metrics."""

    metrics = compute_tasks_metrics(conn, tenant_id=str(tenant_id), window_days=window_days)
    return {
        "metrics": metrics,
        "window_days": int(metrics.get("window_days") or (window_days or 0) or 0),
        "active_total": int(metrics.get("active_total") or 0),
        "active_overdue": int(metrics.get("active_overdue") or 0),
        "overdue_rate_active": float(metrics.get("overdue_rate_active") or 0.0),
    }


def overdue_tasks_use_case(
    *,
    conn: Any,
    tenant_id: str,
    limit: int = 20,
    domain: Optional[str] = None,
    assignee_team: Optional[str] = None,
) -> dict[str, Any]:
    """Canonical core entrypoint for top overdue active tasks."""

    items = compute_tasks_overdue_list(
        conn,
        tenant_id=str(tenant_id),
        limit=int(limit or 20),
        domain=(str(domain).strip() if domain else None),
        assignee_team=(str(assignee_team).strip() if assignee_team else None),
    )
    return {
        "items": list(items or []),
        "count": int(len(items or [])),
        "limit": int(limit or 20),
        "domain": (str(domain).strip() if domain else None),
        "assignee_team": (str(assignee_team).strip() if assignee_team else None),
    }


def operational_summary_use_case(
    *,
    conn: Any,
    tenant_id: str,
    recent_tasks_limit: int = 15,
) -> dict[str, Any]:
    """Workflow snapshot for both UIs from a single core path.

    Keeps the UI thin: counts and recent-open-task selection are assembled in core.
    """

    tenant = str(tenant_id)
    alerts_new = int(list_alerts(conn, tenant_id=tenant, status="new", limit=1, offset=0).get("total") or 0)
    alerts_ack = int(list_alerts(conn, tenant_id=tenant, status="acknowledged", limit=1, offset=0).get("total") or 0)
    alerts_resolved = int(list_alerts(conn, tenant_id=tenant, status="resolved", limit=1, offset=0).get("total") or 0)

    active_statuses = tuple(task_active_status_options())
    ph = ",".join("?" for _ in active_statuses)
    task_open = int(
        (conn.execute(
            f"SELECT COUNT(1) FROM tasks_v1 WHERE tenant_id=? AND status IN ({ph})",
            (tenant, *active_statuses),
        ).fetchone() or [0])[0]
    )
    task_done = int(
        (conn.execute(
            "SELECT COUNT(1) FROM tasks_v1 WHERE tenant_id=? AND status='done'",
            (tenant,),
        ).fetchone() or [0])[0]
    )

    recent_rows = conn.execute(
        f"""
        SELECT task_id, title, status, priority, due_at, owner_user_id, created_at
        FROM tasks_v1
        WHERE tenant_id=? AND status IN ({ph})
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (tenant, *active_statuses, int(recent_tasks_limit)),
    ).fetchall()
    recent_open_tasks = []
    for row in recent_rows:
        item = dict(row)
        item["deadline"] = item.get("due_at")
        recent_open_tasks.append(item)

    return {
        "alerts": {
            "new": alerts_new,
            "acknowledged": alerts_ack,
            "resolved": alerts_resolved,
        },
        "tasks": {
            "open": task_open,
            "done": task_done,
        },
        "recent_open_tasks": recent_open_tasks,
        "recent_tasks_limit": int(recent_tasks_limit),
    }


__all__ = [
    "operational_summary_use_case",
    "overdue_tasks_use_case",
    "tasks_metrics_use_case",
]
