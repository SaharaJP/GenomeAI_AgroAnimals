from __future__ import annotations

from datetime import date
from uuid import uuid4
from typing import Any, Mapping, Optional, Sequence

from core.audit import write_audit
from core.infra.web_db import utcnow_iso
from core.domain import TaskCreate, WORKLIST_TYPES
from core.workflow.tasks import (
    _derive_worklist_type,
    create_task,
    get_task,
    list_tasks,
    list_tasks_for_object,
    take_task,
    update_task_fields,
    close_task,
)


def _normalize_confidence(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        conf = float(value)
    except Exception as exc:  # pragma: no cover
        raise ValueError(f"invalid_confidence: expected float 0..1, got {value}") from exc
    if conf < 0.0 or conf > 1.0:
        raise ValueError(f"invalid_confidence: expected float 0..1, got {conf}")
    return conf


def _normalize_linked_source_facts(value: Any) -> list[dict[str, Any]]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError("invalid_linked_source_facts: expected list")
    out: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, Mapping):
            out.append({str(k): v for k, v in dict(item).items()})
        else:
            out.append({"value": item})
    return out




def _parse_due_date(value: Any) -> date | None:
    raw = str(value or '').strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except Exception:
        return None


def _fact_text(item: Mapping[str, Any]) -> str:
    for key in (
        "label",
        "text",
        "message",
        "summary",
        "title",
        "fact",
        "reason",
        "description",
    ):
        value = str(item.get(key) or '').strip()
        if value:
            return value
    code = str(item.get('code') or item.get('reason_code') or '').strip()
    value = str(item.get('value') or '').strip()
    if code and value:
        return f"{code}: {value}"
    return code or value


def _expected_effect_text(row: Mapping[str, Any]) -> str:
    why = dict(row.get('why') or {})
    for key in ('expected_effect', 'expected_effect_text', 'effect', 'effect_text', 'impact', 'impact_text'):
        value = str(why.get(key) or '').strip()
        if value:
            return value
    for item in list(row.get('what_to_do') or []):
        if not isinstance(item, Mapping):
            continue
        for key in ('expected_effect', 'effect', 'impact', 'benefit'):
            value = str(item.get(key) or '').strip()
            if value:
                return value
    for item in list(row.get('linked_source_facts') or []):
        if not isinstance(item, Mapping):
            continue
        for key in ('expected_effect', 'effect', 'impact', 'effect_text', 'impact_text'):
            value = str(item.get(key) or '').strip()
            if value:
                return value
    wt = list(row.get('what_to_do') or [])
    if wt and isinstance(wt[0], Mapping):
        candidate = str(wt[0].get('action') or wt[0].get('title') or wt[0].get('text') or '').strip()
        if candidate:
            return candidate
    return ''


def _linked_facts_preview(row: Mapping[str, Any], *, limit: int = 3) -> list[str]:
    out: list[str] = []
    for item in list(row.get('linked_source_facts') or []):
        if not isinstance(item, Mapping):
            continue
        text = _fact_text(item)
        if text:
            out.append(text)
        if len(out) >= max(1, int(limit)):
            break
    return out


def _due_bucket(row: Mapping[str, Any], today_iso: str) -> str:
    today_dt = _parse_due_date(today_iso) or date.today()
    due_dt = _parse_due_date(row.get('due_at'))
    if due_dt is None:
        return 'undated'
    if due_dt < today_dt:
        return 'overdue'
    if due_dt == today_dt:
        return 'today'
    return 'upcoming'


def _rank_bucket(bucket: str) -> int:
    return {'overdue': 0, 'today': 1, 'undated': 2, 'upcoming': 3}.get(str(bucket or ''), 9)


def _role_worklist_types(role: str) -> tuple[str, ...]:
    role_key = str(role or '').strip()
    mapping = {
        'Operator': ('data_cleanup', 'movement', 'milk_quality'),
        'Zootech': ('reproduction', 'movement', 'culling_review', 'manager_review'),
        'Vet': ('vet', 'health_follow_up', 'milk_quality'),
        'Director': ('manager_review', 'culling_review', 'milk_quality'),
        'Admin': ('data_cleanup', 'manager_review'),
    }
    return tuple(mapping.get(role_key) or ())


def _matches_role_daily_focus(row: Mapping[str, Any], *, role: str, user_id: int | None = None) -> bool:
    if str(row.get('status') or '') in ('done', 'cancelled'):
        return False
    if str(role or '') in {'Consultant', 'Partner'}:
        return True
    uid = int(user_id or 0)
    owner_user_id = int(row.get('owner_user_id') or 0) if row.get('owner_user_id') not in (None, '') else 0
    if uid and owner_user_id and owner_user_id == uid:
        return True
    wanted_types = set(_role_worklist_types(role))
    wl_type = str(row.get('worklist_type') or '')
    if wl_type and wl_type in wanted_types:
        return True
    team = str(row.get('assignee_team') or '').strip().lower()
    role_team_map = {
        'Operator': {'team-data', 'team-qc'},
        'Zootech': {'team-repro', 'team-econ'},
        'Vet': {'team-health'},
        'Director': {'team-econ'},
        'Admin': {'team-data', 'team-qc'},
    }
    if team and team in role_team_map.get(str(role or ''), set()):
        return True
    if str(role or '') == 'Director' and int(row.get('priority') or 3) <= 2:
        return True
    return False


def _daily_priority_sort_key(row: Mapping[str, Any], today_iso: str) -> tuple[int, int, str, str]:
    bucket = _due_bucket(row, today_iso)
    pr = int(row.get('priority') or 3)
    due = str(row.get('due_at') or '9999-12-31')
    wid = str(row.get('worklist_id') or row.get('task_id') or '')
    return (_rank_bucket(bucket), pr, due, wid)

def _worklist_view(task: Mapping[str, Any] | None) -> dict[str, Any]:
    row = dict(task or {})
    if not row:
        return {}
    worklist_type = _derive_worklist_type(
        worklist_type=row.get("worklist_type"),
        task_type=row.get("task_type"),
        domain=row.get("domain"),
        related_alert=row.get("related_alert"),
    )
    row["worklist_type"] = worklist_type
    row["worklist_id"] = row.get("task_id")
    row["linked_alert_id"] = row.get("related_alert")
    row["linked_source_facts"] = list(row.get("linked_source_facts") or [])
    row["linked_object"] = {
        "object_type": row.get("object_type"),
        "object_id": row.get("object_id"),
    }
    row["expected_effect"] = _expected_effect_text(row)
    row["linked_facts_preview"] = _linked_facts_preview(row)
    row["signal_chain"] = {
        "signal": {
            "alert_id": row.get("related_alert"),
            "linked_source_facts": list(row.get("linked_source_facts") or []),
        },
        "triage": {
            "status": row.get("status"),
            "stage": row.get("stage"),
            "confidence": row.get("confidence"),
            "priority": row.get("priority"),
            "due_at": row.get("due_at"),
        },
        "decision": {
            "linked_decision_id": row.get("linked_decision_id"),
        },
        "task": {
            "task_id": row.get("task_id"),
            "linked_task_id": row.get("linked_task_id"),
            "owner_user_id": row.get("owner_user_id"),
            "assignee_team": row.get("assignee_team"),
        },
        "outcome": {
            "status": row.get("latest_outcome_status") or (row.get("status") if str(row.get("status") or "") in ("done", "cancelled") else None),
            "reason_code": row.get("latest_outcome_reason_code") or row.get("closed_reason"),
            "closed_reason": row.get("latest_outcome_reason_code") or row.get("closed_reason"),
            "closed_at": row.get("latest_outcome_at") or row.get("closed_at"),
            "outcome_id": row.get("latest_outcome_id"),
            "outcome_by": row.get("latest_outcome_by"),
            "comment": row.get("latest_outcome_comment"),
            "metrics": dict(row.get("outcome_metrics") or {}),
        },
    }
    return row


DEFAULT_WORKLIST_TITLES: dict[str, str] = {
    "reproduction": "Проверить воспроизводство",
    "vet": "Ветпроверка",
    "health_follow_up": "Контроль follow-up по здоровью",
    "milk_quality": "Проверить качество молока",
    "movement": "Проверить перевод/движение",
    "culling_review": "Рассмотреть выбраковку",
    "data_cleanup": "Разобрать проблемы данных",
    "manager_review": "Рассмотреть менеджерский обзор",
}


def _write_worklist_audit(
    conn,
    *,
    tenant_id: str,
    user_id: int,
    username: str,
    role: str,
    action: str,
    worklist_id: str,
    data_version: str | None,
    request_id: str | None,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> None:
    write_audit(
        conn,
        tenant_id=str(tenant_id),
        user_id=int(user_id or 0),
        username=str(username or ""),
        role=str(role or ""),
        action=action,
        object_type="worklist",
        object_id=str(worklist_id),
        data_version=(str(data_version) if data_version not in (None, "") else None),
        before=dict(before or {}),
        after=dict(after or {}),
        status="OK",
        request_id=(str(request_id) if request_id not in (None, "") else None),
    )


def create_worklist_use_case(
    *,
    conn,
    tenant_id: str,
    worklist_type: str,
    user_id: int,
    username: str,
    role: str,
    title: str | None = None,
    task_type: str | None = None,
    domain: str | None = None,
    priority: int = 3,
    due_at: str | None = None,
    owner_user_id: int | None = None,
    assignee_team: str | None = None,
    confidence: float | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    related_alert: str | None = None,
    linked_decision_id: str | None = None,
    linked_task_id: str | None = None,
    linked_source_facts: list[dict[str, Any]] | None = None,
    attachments: list[dict[str, Any]] | None = None,
    why: dict[str, Any] | None = None,
    what_to_do: list[dict[str, Any]] | None = None,
    data_version: str | None = None,
    qc_run: str | None = None,
    model_version: str | None = None,
    scoring_run: str | None = None,
    report_version: str | None = None,
    dedupe_key: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    wl_type = _derive_worklist_type(worklist_type=worklist_type)
    conf = _normalize_confidence(confidence)
    src_facts = _normalize_linked_source_facts(linked_source_facts)
    task = TaskCreate(
        task_type=str(task_type or f"worklist.{wl_type}"),
        title=str(title or DEFAULT_WORKLIST_TITLES.get(wl_type) or wl_type),
        domain=domain,
        priority=int(priority or 3),
        due_at=due_at,
        owner_user_id=(int(owner_user_id) if owner_user_id is not None else None),
        assignee_team=assignee_team,
        related_alert=(str(related_alert) if related_alert else None),
        object_type=(str(object_type) if object_type else None),
        object_id=(str(object_id) if object_id else None),
        worklist_type=wl_type,
        confidence=conf,
        linked_decision_id=(str(linked_decision_id) if linked_decision_id else None),
        linked_task_id=(str(linked_task_id) if linked_task_id else None),
        linked_source_facts=src_facts,
        attachments=list(attachments or []),
        why=dict(why or {}),
        what_to_do=list(what_to_do or []),
        data_version=(str(data_version) if data_version else None),
        qc_run=(str(qc_run) if qc_run else None),
        model_version=(str(model_version) if model_version else None),
        scoring_run=(str(scoring_run) if scoring_run else None),
        report_version=(str(report_version) if report_version else None),
        dedupe_key=(str(dedupe_key) if dedupe_key else None),
    )
    task_id = create_task(conn, tenant_id=tenant_id, t=task)
    after = get_worklist(conn, tenant_id=tenant_id, worklist_id=task_id)
    _write_worklist_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user_id or 0),
        username=str(username or ""),
        role=str(role or ""),
        action="worklist.create",
        worklist_id=task_id,
        data_version=(after or {}).get("data_version") or data_version,
        request_id=request_id,
        before=None,
        after=after,
    )
    return {"worklist_id": task_id, "after": after or {}}



def get_worklist(conn, *, tenant_id: str, worklist_id: str) -> dict[str, Any] | None:
    task = get_task(conn, tenant_id=tenant_id, task_id=worklist_id)
    if not task:
        return None
    return _worklist_view(task)



def list_worklists(
    conn,
    *,
    tenant_id: str,
    status: str | None = None,
    worklist_type: str | None = None,
    owner_user_id: int | None = None,
    related_alert: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    due_before: str | None = None,
    stage: str | None = None,
    domain: str | None = None,
    assignee_team: str | None = None,
    linked_decision_id: str | None = None,
    linked_task_id: str | None = None,
    overdue_only: bool = False,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    res = list_tasks(
        conn,
        tenant_id=tenant_id,
        status=status,
        owner_user_id=owner_user_id,
        related_alert=related_alert,
        object_type=object_type,
        object_id=object_id,
        due_before=due_before,
        stage=stage,
        domain=domain,
        assignee_team=assignee_team,
        worklist_type=worklist_type,
        linked_decision_id=linked_decision_id,
        linked_task_id=linked_task_id,
        overdue_only=overdue_only,
        q=q,
        limit=limit,
        offset=offset,
    )
    items = [_worklist_view(x) for x in list(res.get("tasks") or [])]
    if worklist_type:
        wanted = _derive_worklist_type(worklist_type=worklist_type)
        items = [x for x in items if str(x.get("worklist_type") or "") == wanted]
    return {"total": len(items), "worklists": items}



def list_worklists_for_object(
    conn,
    *,
    tenant_id: str,
    object_type: str,
    object_id: str,
    worklist_type: str | None = None,
    include_aliases: bool = True,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    res = list_tasks_for_object(
        conn,
        tenant_id=tenant_id,
        object_type=object_type,
        object_id=object_id,
        include_aliases=include_aliases,
        limit=limit,
        offset=offset,
    )
    items = [_worklist_view(x) for x in list(res.get("tasks") or [])]
    if worklist_type:
        wanted = _derive_worklist_type(worklist_type=worklist_type)
        items = [x for x in items if str(x.get("worklist_type") or "") == wanted]
    return {"total": len(items), "worklists": items}



def triage_worklist_use_case(
    *,
    conn,
    tenant_id: str,
    worklist_id: str,
    user_id: int,
    username: str,
    role: str,
    confidence: float | None = None,
    priority: int | None = None,
    due_at: str | None = None,
    owner_user_id: int | None = None,
    assignee_team: str | None = None,
    linked_source_facts: list[dict[str, Any]] | None = None,
    linked_decision_id: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    before = get_worklist(conn, tenant_id=tenant_id, worklist_id=worklist_id)
    patch: dict[str, Any] = {"stage": "triage", "status": "open"}
    if confidence is not None:
        patch["confidence"] = _normalize_confidence(confidence)
    if priority is not None:
        patch["priority"] = int(priority)
    if due_at is not None:
        patch["due_at"] = due_at
    if owner_user_id is not None:
        patch["owner_user_id"] = int(owner_user_id)
    if assignee_team is not None:
        patch["assignee_team"] = str(assignee_team)
    if linked_source_facts is not None:
        patch["linked_source_facts"] = _normalize_linked_source_facts(linked_source_facts)
    if linked_decision_id is not None:
        patch["linked_decision_id"] = str(linked_decision_id) or None
    update_task_fields(conn, tenant_id=tenant_id, task_id=worklist_id, patch=patch)
    after = get_worklist(conn, tenant_id=tenant_id, worklist_id=worklist_id)
    _write_worklist_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user_id or 0),
        username=str(username or ""),
        role=str(role or ""),
        action="worklist.triage",
        worklist_id=worklist_id,
        data_version=(after or before or {}).get("data_version"),
        request_id=request_id,
        before=before,
        after=after,
    )
    return {"before": before or {}, "after": after or {}}



def start_worklist_use_case(
    *,
    conn,
    tenant_id: str,
    worklist_id: str,
    user_id: int,
    username: str,
    role: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    before = get_worklist(conn, tenant_id=tenant_id, worklist_id=worklist_id)
    take_task(conn, tenant_id=tenant_id, task_id=worklist_id, user_id=int(user_id))
    update_task_fields(conn, tenant_id=tenant_id, task_id=worklist_id, patch={"stage": "execute", "status": "in_progress"})
    after = get_worklist(conn, tenant_id=tenant_id, worklist_id=worklist_id)
    _write_worklist_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user_id or 0),
        username=str(username or ""),
        role=str(role or ""),
        action="worklist.start",
        worklist_id=worklist_id,
        data_version=(after or before or {}).get("data_version"),
        request_id=request_id,
        before=before,
        after=after,
    )
    return {"before": before or {}, "after": after or {}}



def link_worklist_decision_use_case(
    *,
    conn,
    tenant_id: str,
    worklist_id: str,
    linked_decision_id: str,
    user_id: int,
    username: str,
    role: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    before = get_worklist(conn, tenant_id=tenant_id, worklist_id=worklist_id)
    update_task_fields(
        conn,
        tenant_id=tenant_id,
        task_id=worklist_id,
        patch={"linked_decision_id": str(linked_decision_id), "stage": "review"},
    )
    after = get_worklist(conn, tenant_id=tenant_id, worklist_id=worklist_id)
    _write_worklist_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user_id or 0),
        username=str(username or ""),
        role=str(role or ""),
        action="worklist.link_decision",
        worklist_id=worklist_id,
        data_version=(after or before or {}).get("data_version"),
        request_id=request_id,
        before=before,
        after=after,
    )
    return {"before": before or {}, "after": after or {}}



def close_worklist_use_case(
    *,
    conn,
    tenant_id: str,
    worklist_id: str,
    user_id: int,
    username: str,
    role: str,
    status: str,
    reason: str,
    comment: str | None = None,
    resolve_related_alert: bool = True,
    request_id: str | None = None,
) -> dict[str, Any]:
    before = get_worklist(conn, tenant_id=tenant_id, worklist_id=worklist_id)
    from core.workflow.outcomes import record_completion_outcome_use_case

    outcome_status = 'done' if str(status or '').strip() == 'done' else 'cancelled'
    outcome_res = record_completion_outcome_use_case(
        conn=conn,
        tenant_id=tenant_id,
        worklist_id=worklist_id,
        user_id=int(user_id),
        username=str(username or ''),
        role=str(role or ''),
        outcome_status=outcome_status,
        reason_code=str(reason),
        comment=(str(comment) if comment else None),
        auto_link_decision=True,
        auto_resolve_related_alert=bool(resolve_related_alert),
        request_id=request_id,
    )
    after = get_worklist(conn, tenant_id=tenant_id, worklist_id=worklist_id)
    _write_worklist_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user_id or 0),
        username=str(username or ""),
        role=str(role or ""),
        action="worklist.close",
        worklist_id=worklist_id,
        data_version=(after or before or {}).get("data_version"),
        request_id=request_id,
        before=before,
        after=after,
    )
    return {"before": before or {}, "after": after or {}, "outcome": outcome_res.get('outcome') or {}, "auto_actions": outcome_res.get('auto_actions') or {}}


def list_worklists_for_role_today(
    conn,
    *,
    tenant_id: str,
    role: str,
    user_id: int | None = None,
    today_iso: str | None = None,
    q: str | None = None,
    include_upcoming: bool = False,
    limit: int = 100,
) -> dict[str, Any]:
    today = str(today_iso or date.today().isoformat())
    base = list_worklists(
        conn,
        tenant_id=tenant_id,
        status=None,
        q=q,
        limit=max(int(limit) * 4, 200),
        offset=0,
    )
    filtered: list[dict[str, Any]] = []
    for item in list(base.get('worklists') or []):
        row = dict(item)
        if not _matches_role_daily_focus(row, role=role, user_id=user_id):
            continue
        due_bucket = _due_bucket(row, today)
        row['due_bucket'] = due_bucket
        row['is_due_today'] = due_bucket == 'today'
        row['is_overdue'] = due_bucket == 'overdue' or bool(row.get('is_overdue'))
        if not include_upcoming and due_bucket == 'upcoming':
            continue
        filtered.append(row)
    filtered.sort(key=lambda row: _daily_priority_sort_key(row, today))
    summary = {
        'role': str(role or ''),
        'today': today,
        'total': len(filtered),
        'overdue': sum(1 for row in filtered if str(row.get('due_bucket')) == 'overdue'),
        'today_due': sum(1 for row in filtered if str(row.get('due_bucket')) == 'today'),
        'undated': sum(1 for row in filtered if str(row.get('due_bucket')) == 'undated'),
        'high_priority': sum(1 for row in filtered if int(row.get('priority') or 3) <= 2),
        'types': sorted({str(row.get('worklist_type') or '') for row in filtered if str(row.get('worklist_type') or '').strip()}),
    }
    return {'summary': summary, 'worklists': filtered[: max(1, int(limit))]}


def accept_worklist_use_case(
    *,
    conn,
    tenant_id: str,
    worklist_id: str,
    user_id: int,
    username: str,
    role: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    before = get_worklist(conn, tenant_id=tenant_id, worklist_id=worklist_id)
    update_task_fields(conn, tenant_id=tenant_id, task_id=worklist_id, patch={'stage': 'execute', 'status': 'in_progress', 'owner_user_id': int(user_id)})
    take_task(conn, tenant_id=tenant_id, task_id=worklist_id, user_id=int(user_id))
    after = get_worklist(conn, tenant_id=tenant_id, worklist_id=worklist_id)
    _write_worklist_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user_id or 0),
        username=str(username or ''),
        role=str(role or ''),
        action='worklist.accept',
        worklist_id=worklist_id,
        data_version=(after or before or {}).get('data_version'),
        request_id=request_id,
        before=before,
        after=after,
    )
    return {'before': before or {}, 'after': after or {}}


def postpone_worklist_use_case(
    *,
    conn,
    tenant_id: str,
    worklist_id: str,
    user_id: int,
    username: str,
    role: str,
    due_at: str,
    priority: int | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    before = get_worklist(conn, tenant_id=tenant_id, worklist_id=worklist_id)
    patch: dict[str, Any] = {'due_at': str(due_at), 'status': 'open', 'stage': 'plan'}
    if priority is not None:
        patch['priority'] = int(priority)
    update_task_fields(conn, tenant_id=tenant_id, task_id=worklist_id, patch=patch)
    after = get_worklist(conn, tenant_id=tenant_id, worklist_id=worklist_id)
    _write_worklist_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user_id or 0),
        username=str(username or ''),
        role=str(role or ''),
        action='worklist.postpone',
        worklist_id=worklist_id,
        data_version=(after or before or {}).get('data_version'),
        request_id=request_id,
        before=before,
        after=after,
    )
    return {'before': before or {}, 'after': after or {}}


def append_worklist_comment_use_case(
    *,
    conn,
    tenant_id: str,
    worklist_id: str,
    user_id: int,
    username: str,
    role: str,
    comment: str,
    source: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    raw_comment = str(comment or '').strip()
    if not raw_comment:
        raise ValueError('comment_required')
    before = get_worklist(conn, tenant_id=tenant_id, worklist_id=worklist_id)
    if not before:
        raise KeyError('not_found')
    attachments = list(before.get('attachments') or [])
    comment_row = {
        'kind': 'comment',
        'comment_id': f"wlc-{uuid4().hex[:8]}",
        'comment': raw_comment,
        'created_at': utcnow_iso(),
        'created_by': int(user_id or 0),
        'created_by_username': str(username or ''),
        'created_by_role': str(role or ''),
        'source': str(source or 'mobile_worklists'),
    }
    attachments.append(comment_row)
    update_task_fields(conn, tenant_id=tenant_id, task_id=worklist_id, patch={'attachments': attachments})
    after = get_worklist(conn, tenant_id=tenant_id, worklist_id=worklist_id)
    _write_worklist_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user_id or 0),
        username=str(username or ''),
        role=str(role or ''),
        action='worklist.comment',
        worklist_id=worklist_id,
        data_version=(after or before or {}).get('data_version'),
        request_id=request_id,
        before={'comments': len(list(before.get('attachments') or []))},
        after={'comments': len(list((after or {}).get('attachments') or [])), 'last_comment': raw_comment},
    )
    return {'before': before or {}, 'after': after or {}, 'comment': comment_row}


def escalate_worklist_use_case(
    *,
    conn,
    tenant_id: str,
    worklist_id: str,
    user_id: int,
    username: str,
    role: str,
    assignee_team: str | None = None,
    owner_user_id: int | None = None,
    priority: int | None = None,
    due_at: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    before = get_worklist(conn, tenant_id=tenant_id, worklist_id=worklist_id)
    patch: dict[str, Any] = {'stage': 'review', 'status': 'open'}
    if assignee_team is not None:
        patch['assignee_team'] = str(assignee_team) or None
    if owner_user_id is not None:
        patch['owner_user_id'] = int(owner_user_id)
    if priority is not None:
        patch['priority'] = int(priority)
    if due_at is not None:
        patch['due_at'] = str(due_at) or None
    update_task_fields(conn, tenant_id=tenant_id, task_id=worklist_id, patch=patch)
    after = get_worklist(conn, tenant_id=tenant_id, worklist_id=worklist_id)
    _write_worklist_audit(
        conn,
        tenant_id=tenant_id,
        user_id=int(user_id or 0),
        username=str(username or ''),
        role=str(role or ''),
        action='worklist.escalate',
        worklist_id=worklist_id,
        data_version=(after or before or {}).get('data_version'),
        request_id=request_id,
        before=before,
        after=after,
    )
    return {'before': before or {}, 'after': after or {}}


__all__ = [
    "DEFAULT_WORKLIST_TITLES",
    "create_worklist_use_case",
    "get_worklist",
    "list_worklists",
    "list_worklists_for_role_today",
    "list_worklists_for_object",
    "triage_worklist_use_case",
    "start_worklist_use_case",
    "accept_worklist_use_case",
    "postpone_worklist_use_case",
    "append_worklist_comment_use_case",
    "escalate_worklist_use_case",
    "link_worklist_decision_use_case",
    "close_worklist_use_case",
]
