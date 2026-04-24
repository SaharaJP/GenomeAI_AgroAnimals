from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional

from core.workflow.catalogs import workflow_stage_options
from core.workflow.policies import task_status_options
from core.workflow.tasks import list_tasks


def workflow_listing_use_case(
    *,
    conn: Any,
    tenant_id: str,
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    stage: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    """Canonical core listing payload for Workflow pages.

    Adapters may still decorate tasks with UI-specific add-ons (for example,
    recommended playbooks), but task retrieval, filter normalization and option
    payload now live in core.
    """

    stage_value = (str(stage).strip() if stage else None)
    task_type_value = (str(task_type).strip() if task_type else None)
    q_value = (str(q).strip() if q else None)
    status_value = (str(status).strip() if status else None)

    res = list_tasks(
        conn,
        tenant_id=str(tenant_id),
        status=status_value,
        task_type=task_type_value,
        stage=stage_value,
        q=q_value,
        limit=int(limit or 200),
        offset=int(offset or 0),
    )
    return {
        "total": int(res.get("total") or 0),
        "tasks": list(res.get("tasks") or []),
        "filters": SimpleNamespace(
            status=status_value or "",
            task_type=task_type_value or "",
            stage=stage_value or "",
            q=q_value or "",
        ),
        "task_statuses": list(task_status_options()),
        "stage_options": list(workflow_stage_options(include_blank=True)),
    }


__all__ = ["workflow_listing_use_case"]
