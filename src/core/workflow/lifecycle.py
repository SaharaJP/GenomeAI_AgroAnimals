from __future__ import annotations

from typing import Any, Optional

from core.workflow.alerts import acknowledge_alert, get_alert, resolve_alert
from core.workflow.decisions import DecisionCreate, append_decision, get_decision
from core.workflow.policies import (
    alert_resolve_reason_codes,
    task_close_reason_codes,
    task_close_status_options,
)
from core.workflow.tasks import close_task, get_task, take_task, update_task_fields


def acknowledge_alert_use_case(*, conn, tenant_id: str, alert_id: str, user_id: int) -> dict[str, Any]:
    before = get_alert(conn, tenant_id=tenant_id, alert_id=alert_id)
    acknowledge_alert(conn, tenant_id=tenant_id, alert_id=alert_id, user_id=int(user_id))
    after = get_alert(conn, tenant_id=tenant_id, alert_id=alert_id)
    return {
        "before": before or {},
        "after": after or {},
        "status": (after or {}).get("status"),
        "data_version": (after or before or {}).get("data_version"),
        "run_id": (after or before or {}).get("scoring_run"),
    }


def resolve_alert_use_case(*, conn, tenant_id: str, alert_id: str, user_id: int, reason: str) -> dict[str, Any]:
    before = get_alert(conn, tenant_id=tenant_id, alert_id=alert_id)
    resolve_alert(conn, tenant_id=tenant_id, alert_id=alert_id, user_id=int(user_id), reason=reason)
    after = get_alert(conn, tenant_id=tenant_id, alert_id=alert_id)
    return {
        "before": before or {},
        "after": after or {},
        "status": (after or {}).get("status"),
        "reason": str(reason or "").strip(),
        "reason_codes": list(alert_resolve_reason_codes()),
        "data_version": (after or before or {}).get("data_version"),
        "run_id": (after or before or {}).get("scoring_run"),
    }


def take_task_use_case(*, conn, tenant_id: str, task_id: str, user_id: int) -> dict[str, Any]:
    before = get_task(conn, tenant_id=tenant_id, task_id=task_id)
    take_task(conn, tenant_id=tenant_id, task_id=task_id, user_id=int(user_id))
    after = get_task(conn, tenant_id=tenant_id, task_id=task_id)
    return {
        "before": before or {},
        "after": after or {},
        "status": (after or {}).get("status"),
        "data_version": (after or before or {}).get("data_version"),
    }


def update_task_use_case(*, conn, tenant_id: str, task_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    before = get_task(conn, tenant_id=tenant_id, task_id=task_id)
    update_task_fields(conn, tenant_id=tenant_id, task_id=task_id, patch=dict(patch or {}))
    after = get_task(conn, tenant_id=tenant_id, task_id=task_id)
    return {
        "before": before or {},
        "after": after or {},
        "status": (after or {}).get("status"),
        "data_version": (after or before or {}).get("data_version"),
    }


def close_task_use_case(
    *,
    conn,
    tenant_id: str,
    task_id: str,
    user_id: int,
    username: str,
    status: str,
    reason: str,
    comment: Optional[str] = None,
    resolve_related_alert: bool = True,
) -> dict[str, Any]:
    before = get_task(conn, tenant_id=tenant_id, task_id=task_id)
    close_task(
        conn,
        tenant_id=tenant_id,
        task_id=task_id,
        user_id=int(user_id),
        username=str(username),
        status=status,
        reason=reason,
        comment=comment,
        resolve_related_alert=bool(resolve_related_alert),
    )
    after = get_task(conn, tenant_id=tenant_id, task_id=task_id)
    normalized_status = str((after or {}).get("status") or status)
    return {
        "before": before or {},
        "after": after or {},
        "status": normalized_status,
        "reason": str(reason or "").strip(),
        "reason_codes": list(task_close_reason_codes(status=normalized_status)),
        "allowed_statuses": list(task_close_status_options()),
        "data_version": (after or before or {}).get("data_version"),
        "related_alert": (after or before or {}).get("related_alert"),
    }


def append_decision_use_case(*, conn, tenant_id: str, d: DecisionCreate) -> dict[str, Any]:
    decision_id = append_decision(conn, tenant_id=tenant_id, d=d)
    after = get_decision(conn, tenant_id=tenant_id, decision_id=decision_id)
    return {
        "decision_id": decision_id,
        "after": after or {},
        "data_version": (after or {}).get("data_version") if after else d.data_version,
        "related_alert": (after or {}).get("related_alert") if after else d.related_alert,
    }


__all__ = [
    "acknowledge_alert_use_case",
    "append_decision_use_case",
    "close_task_use_case",
    "resolve_alert_use_case",
    "take_task_use_case",
    "update_task_use_case",
]
