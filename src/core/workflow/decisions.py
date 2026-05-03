from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Optional

from core.infra import DecisionsRepo

from core.infra.web_db import utcnow_iso
from core.workflow.entities import expand_object_types, normalize_object_type


@dataclass
class DecisionCreate:
    """Unified append-only decision record (Decision Log v2)."""

    recommendation_id: Optional[str]
    action: str
    user_id: int
    username: str
    reason: Optional[str]
    comment: Optional[str]
    related_alert: Optional[str]
    object_type: Optional[str]
    object_id: Optional[str]
    farm_id: Optional[str]
    group_id: Optional[str]
    data_version: Optional[str]
    model_version: Optional[str]
    report_version: Optional[str]
    qc_run: Optional[str]
    scoring_run: Optional[str]
    metadata: dict[str, Any]


def append_decision(
    conn,
    *,
    tenant_id: str,
    d: DecisionCreate,
    created_at: Optional[str] = None,
) -> str:
    """Append a decision into decision_log_v2 (append-only). Returns decision_id."""

    decision_id = uuid.uuid4().hex
    ts = created_at or utcnow_iso()
    repo = DecisionsRepo(conn)
    return repo.append(
        tenant_id=tenant_id,
        decision_id=decision_id,
        created_at=ts,
        payload={
            "recommendation_id": d.recommendation_id,
            "action": d.action,
            "user_id": int(d.user_id),
            "username": str(d.username),
            "reason": d.reason,
            "comment": d.comment,
            "related_alert": d.related_alert,
            "object_type": d.object_type,
            "object_id": d.object_id,
            "farm_id": d.farm_id,
            "group_id": d.group_id,
            "data_version": d.data_version,
            "model_version": d.model_version,
            "report_version": d.report_version,
            "qc_run": d.qc_run,
            "scoring_run": d.scoring_run,
            "metadata": d.metadata or {},
        },
    )


def get_decision(
    conn,
    *,
    tenant_id: str,
    decision_id: str,
) -> Optional[dict[str, Any]]:
    return DecisionsRepo(conn).get(tenant_id=tenant_id, decision_id=decision_id)


def list_decisions(
    conn,
    *,
    tenant_id: str,
    farm_id: Optional[str] = None,
    group_id: Optional[str] = None,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    related_alert: Optional[str] = None,
    recommendation_id: Optional[str] = None,
    action: Optional[str] = None,
    user_id: Optional[int] = None,
    data_version: Optional[str] = None,
    model_version: Optional[str] = None,
    report_version: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    repo = DecisionsRepo(conn)
    return repo.list(
        tenant_id=tenant_id,
        filters={
            "farm_id": farm_id,
            "group_id": group_id,
            "object_type": object_type,
            "object_id": object_id,
            "related_alert": related_alert,
            "recommendation_id": recommendation_id,
            "action": action,
            "user_id": user_id,
            "data_version": data_version,
            "model_version": model_version,
            "report_version": report_version,
            "q": q,
        },
        limit=limit,
        offset=offset,
    )


def list_decisions_for_object(
    conn,
    *,
    tenant_id: str,
    object_type: str,
    object_id: str,
    include_aliases: bool = True,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    """List decisions linked to an entity, tolerating object_type aliases.

    This mirrors tasks_v1.list_tasks_for_object().
    """

    if not object_id:
        return {"total": 0, "decisions": []}

    base_type = normalize_object_type(object_type) or str(object_type)
    types = expand_object_types(base_type) if include_aliases else [base_type]
    types = [t for t in types if t]
    return DecisionsRepo(conn).list_for_object(
        tenant_id=tenant_id,
        object_id=object_id,
        object_types=types,
        limit=limit,
        offset=offset,
    )
