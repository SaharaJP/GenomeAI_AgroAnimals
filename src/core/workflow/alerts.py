from __future__ import annotations

"""Alert Center v2 storage + lifecycle helpers.

Web layer responsibilities:
- CRUD + lifecycle transitions (new -> acknowledged -> resolved)
- RBAC & audit logging of critical actions

Core responsibilities (src/genomeai/alerts_v2.py):
- Generate explainable alert candidates from facts (QC/ML/business rules)
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.domain import (
    ALERT_STATUSES,
    AlertCreate,
    alert_create_to_api_dict,
    assert_alert_can_acknowledge,
    alert_open_statuses_sql,
)
from core.infra import AlertsRepo

from core.workflow.decisions import DecisionCreate, append_decision
from core.workflow.entities import expand_object_types, normalize_object_type
from core.workflow.policies import validate_reason_for_alert_resolution


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _row_to_dict(r) -> Dict[str, Any]:
    return AlertsRepo.row_to_dict(r) or {}


def list_alerts(
    conn,
    *,
    tenant_id: str,
    status: Optional[str] = None,
    alert_type: Optional[str] = None,
    source: Optional[str] = None,
    owner_user_id: Optional[int] = None,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> Dict[str, Any]:
    return AlertsRepo(conn).list(
        tenant_id=tenant_id,
        filters={
            "status": status,
            "alert_type": alert_type,
            "source": source,
            "owner_user_id": owner_user_id,
            "object_type": object_type,
            "object_id": object_id,
            "q": q,
        },
        limit=limit,
        offset=offset,
    )



def list_alerts_for_object(
    conn,
    *,
    tenant_id: str,
    object_type: str,
    object_id: str,
    include_aliases: bool = True,
    status: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> Dict[str, Any]:
    """List alerts linked to an entity, tolerating object_type aliases.

    Why:
      - Some producers use object_type="pen" while UI uses "group".
      - We want profiles to show all related alerts regardless of alias.

    Notes:
      - This is a convenience wrapper; list_alerts() remains unchanged.
    """

    if not object_id:
        return {"total": 0, "alerts": []}

    base_type = normalize_object_type(object_type) or str(object_type)
    types = expand_object_types(base_type) if include_aliases else [base_type]
    types = [t for t in types if t]
    return AlertsRepo(conn).list_for_object(
        tenant_id=tenant_id,
        object_id=object_id,
        object_types=types,
        status=status,
        limit=limit,
        offset=offset,
    )



def get_alert(conn, *, tenant_id: str, alert_id: str) -> Optional[Dict[str, Any]]:
    return AlertsRepo(conn).get(tenant_id=tenant_id, alert_id=alert_id)



def create_alert(conn, *, tenant_id: str, a: AlertCreate) -> str:
    alert_id = str(uuid.uuid4())
    now = utcnow_iso()
    return AlertsRepo(conn).create(
        tenant_id=tenant_id,
        alert_id=alert_id,
        created_at=now,
        payload={
            "alert_type": a.alert_type,
            "title": a.title,
            "source": a.source,
            "cause": a.cause,
            "confidence": a.confidence,
            "object_type": a.object_type,
            "object_id": a.object_id,
            "status": "new",
            "deadline": a.deadline,
            "owner_user_id": a.owner_user_id,
            "attachments": a.attachments or [],
            "why": a.why or {},
            "what_to_do": a.what_to_do or [],
            "data_version": a.data_version,
            "qc_run": a.qc_run,
            "model_version": a.model_version,
            "scoring_run": a.scoring_run,
            "report_version": a.report_version,
            "dedupe_key": a.dedupe_key,
        },
    )



def upsert_generated_alerts(
    conn,
    *,
    tenant_id: str,
    alerts: Iterable[AlertCreate],
) -> Tuple[int, int]:
    """Insert/update generated alerts.

    Dedupe strategy:
    - If an *open* (new/acknowledged) alert with same dedupe_key exists -> update factual fields + updated_at
    - If only resolved exists -> create a new alert row
    """
    repo = AlertsRepo(conn)
    inserted = 0
    updated = 0
    for a in alerts:
        dk = (a.dedupe_key or "").strip()
        if not dk:
            create_alert(conn, tenant_id=tenant_id, a=a)
            inserted += 1
            continue

        row = repo.find_open_by_dedupe(tenant_id=tenant_id, dedupe_key=dk, open_statuses_sql=alert_open_statuses_sql())

        if row:
            repo.update_generated(
                row_id=int(row["id"]),
                updated_at=utcnow_iso(),
                payload={
                    "title": a.title,
                    "source": a.source,
                    "cause": a.cause,
                    "confidence": a.confidence,
                    "deadline": a.deadline,
                    "owner_user_id": a.owner_user_id,
                    "attachments": a.attachments or [],
                    "why": a.why or {},
                    "what_to_do": a.what_to_do or [],
                    "data_version": a.data_version,
                    "qc_run": a.qc_run,
                    "model_version": a.model_version,
                    "scoring_run": a.scoring_run,
                    "report_version": a.report_version,
                },
            )
            updated += 1
        else:
            create_alert(conn, tenant_id=tenant_id, a=a)
            inserted += 1

    return inserted, updated



def acknowledge_alert(conn, *, tenant_id: str, alert_id: str, user_id: int) -> None:
    now = utcnow_iso()
    repo = AlertsRepo(conn)
    status = repo.get_status(tenant_id=tenant_id, alert_id=alert_id)
    if status is None:
        raise KeyError("not_found")
    assert_alert_can_acknowledge(status)
    repo.acknowledge(tenant_id=tenant_id, alert_id=alert_id, user_id=int(user_id), now=now)

    try:
        a = repo.get(tenant_id=tenant_id, alert_id=alert_id)
        if a:
            username = repo.resolve_username(tenant_id=tenant_id, user_id=int(user_id))
            append_decision(
                conn,
                tenant_id=tenant_id,
                d=DecisionCreate(
                    recommendation_id=None,
                    action="alert.acknowledge",
                    user_id=int(user_id),
                    username=username,
                    reason=None,
                    comment=None,
                    related_alert=str(alert_id),
                    object_type=a.get("object_type"),
                    object_id=a.get("object_id"),
                    farm_id=None,
                    group_id=None,
                    data_version=a.get("data_version"),
                    model_version=a.get("model_version"),
                    report_version=a.get("report_version"),
                    qc_run=a.get("qc_run"),
                    scoring_run=a.get("scoring_run"),
                    metadata={
                        "alert_type": a.get("alert_type"),
                        "source": a.get("source"),
                        "cause": a.get("cause"),
                    },
                ),
                created_at=now,
            )
    except Exception:
        pass



def resolve_alert(
    conn,
    *,
    tenant_id: str,
    alert_id: str,
    user_id: int,
    reason: str,
) -> None:
    reason = validate_reason_for_alert_resolution(reason)
    now = utcnow_iso()
    repo = AlertsRepo(conn)
    status = repo.get_status(tenant_id=tenant_id, alert_id=alert_id)
    if status is None:
        raise KeyError("not_found")
    if status == "resolved":
        return
    repo.resolve(tenant_id=tenant_id, alert_id=alert_id, user_id=int(user_id), reason=reason, now=now)

    try:
        a = repo.get(tenant_id=tenant_id, alert_id=alert_id)
        if a:
            username = repo.resolve_username(tenant_id=tenant_id, user_id=int(user_id))
            append_decision(
                conn,
                tenant_id=tenant_id,
                d=DecisionCreate(
                    recommendation_id=None,
                    action="alert.resolve",
                    user_id=int(user_id),
                    username=username,
                    reason=reason or None,
                    comment=None,
                    related_alert=str(alert_id),
                    object_type=a.get("object_type"),
                    object_id=a.get("object_id"),
                    farm_id=None,
                    group_id=None,
                    data_version=a.get("data_version"),
                    model_version=a.get("model_version"),
                    report_version=a.get("report_version"),
                    qc_run=a.get("qc_run"),
                    scoring_run=a.get("scoring_run"),
                    metadata={
                        "alert_type": a.get("alert_type"),
                        "source": a.get("source"),
                        "cause": a.get("cause"),
                    },
                ),
                created_at=now,
            )
    except Exception:
        pass



def _resolve_username(conn, *, tenant_id: str, user_id: int) -> str:
    return AlertsRepo(conn).resolve_username(tenant_id=tenant_id, user_id=user_id)
