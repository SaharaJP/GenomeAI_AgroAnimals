from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from math import ceil
from pathlib import Path
from typing import Any, Optional

from core.domain import (
    TASK_CLOSED_STATUSES,
    TaskCreate,
    WORKLIST_TYPES,
    alert_open_statuses_sql,
    normalize_task_active_status_for_update,
    normalize_task_close_status,
    task_from_row,
    task_to_api_dict,
)
from core.infra import AlertsRepo, TasksRepo

from core.workflow.alerts import get_alert, resolve_alert
from core.workflow.decisions import DecisionCreate, append_decision
from core.infra.web_db import utcnow_iso, get_user_by_id
from core.workflow.catalogs import workflow_default_stage as _workflow_default_stage, workflow_stage_keys as _workflow_stage_keys, workflow_team_keys as _workflow_team_keys
from core.workflow.entities import expand_object_types, normalize_object_type
from core.workflow.policies import (
    derive_due_fields as _derive_due_fields,
    is_task_overdue as _policy_is_task_overdue,
    normalize_domain as _policy_normalize_domain,
    parse_iso_dt as _policy_parse_iso_dt,
    pick_sla_hours as _policy_pick_sla_hours,
    utcnow_dt as _policy_utcnow_dt,
    validate_reason_for_task_close,
    workflow_project_root as _workflow_project_root,
    load_workflow_yaml as _workflow_load_yaml,
)


def _utcnow_dt() -> datetime:
    return _policy_utcnow_dt()


def _parse_iso_dt(s: Optional[str]) -> Optional[datetime]:
    return _policy_parse_iso_dt(s)


def _project_root() -> Path:
    return _workflow_project_root()


@lru_cache(maxsize=8)
def _load_yaml(path: Path) -> dict[str, Any]:
    return _workflow_load_yaml(path)


def _normalize_domain(s: Optional[str]) -> Optional[str]:
    return _policy_normalize_domain(s)


def _infer_domain(task_type: str, *, rule_domain: Optional[str] = None) -> str:
    """Infer a coarse domain for a task.

    Precedence:
      1) rule_domain from configs/tasks_v1/catalog.yaml
      2) regex map configs/workflow_v2/task_domain_map.yaml
      3) default_domain from the same map
    """

    rd = _normalize_domain(rule_domain)
    if rd:
        return rd

    root = _project_root()
    cfg = _load_yaml(root / "configs" / "workflow_v2" / "task_domain_map.yaml")
    default_domain = _normalize_domain(cfg.get("default_domain")) or "data"
    rules = list(cfg.get("rules") or [])
    tt = str(task_type or "").strip()
    for r in rules:
        try:
            pat = str(r.get("match") or "").strip()
            dom = _normalize_domain(r.get("domain"))
            if not pat or not dom:
                continue
            if re.search(pat, tt, flags=re.IGNORECASE):
                return dom
        except Exception:
            continue
    return default_domain


def _pick_sla_hours(domain: str, priority: int) -> Optional[int]:
    return _policy_pick_sla_hours(domain, priority)


def _derive_worklist_type(*, worklist_type: Optional[str] = None, task_type: Optional[str] = None, domain: Optional[str] = None, related_alert: Optional[str] = None) -> str:
    explicit = str(worklist_type or '').strip().lower()
    if explicit:
        if explicit not in WORKLIST_TYPES:
            raise ValueError(f"invalid_worklist_type: expected one of {sorted(WORKLIST_TYPES)}, got {worklist_type}")
        return explicit

    task_type_s = str(task_type or '').strip().lower()
    domain_s = str(domain or '').strip().lower()
    related_alert_s = str(related_alert or '').strip().lower()
    text = ' '.join([task_type_s, domain_s, related_alert_s])

    if any(token in text for token in ('repro', 'insemin', 'heat', 'preg', 'calv')):
        return 'reproduction'
    if any(token in text for token in ('withdrawal', 'milk_quality', 'scc', 'antibiotic', 'quality')):
        return 'milk_quality'
    if any(token in text for token in ('follow_up', 'followup', 'recheck', 'monitor')):
        return 'health_follow_up'
    if any(token in text for token in ('move', 'pen', 'group_transfer', 'transport')):
        return 'movement'
    if any(token in text for token in ('cull', 'culling', 'sell_off')):
        return 'culling_review'
    if domain_s in {'qc', 'data'} or any(token in text for token in ('qc', 'schema', 'mapping', 'cleanup', 'data_correction', 'sensor')):
        return 'data_cleanup'
    if domain_s in {'econ'} or any(token in text for token in ('manager', 'director', 'review', 'approve', 'roi', 'econ', 'budget')):
        return 'manager_review'
    if domain_s == 'health' or any(token in text for token in ('vet', 'mastitis', 'lameness', 'metritis', 'health')):
        return 'vet'
    return 'manager_review'


def _decode_task_row(d: dict[str, Any]) -> dict[str, Any]:
    if not d.get('stage'):
        st = str(d.get('status') or '')
        d['stage'] = st if st in TASK_CLOSED_STATUSES else _default_stage_open()
    d['attachments'] = json.loads(d.get('attachments_json') or '[]')
    d['why'] = json.loads(d.get('why_json') or '{}')
    d['what_to_do'] = json.loads(d.get('what_to_do_json') or '[]')
    d['linked_source_facts'] = json.loads(d.get('linked_source_facts_json') or '[]')
    d['outcome_metrics'] = json.loads(d.get('outcome_metrics_json') or '{}')
    d['worklist_type'] = _derive_worklist_type(
        worklist_type=d.get('worklist_type'),
        task_type=d.get('task_type'),
        domain=d.get('domain'),
        related_alert=d.get('related_alert'),
    )
    d['is_overdue'] = _is_overdue(d)
    d = task_to_api_dict(task_from_row(d))
    d.pop('attachments_json', None)
    d.pop('why_json', None)
    d.pop('what_to_do_json', None)
    d.pop('linked_source_facts_json', None)
    d.pop('outcome_metrics_json', None)
    return d


# ---- Workflow 2.0: stages (Kanban) + teams catalog (config-driven) ----


def _stage_keys() -> tuple[str, ...]:
    return _workflow_stage_keys()


def _default_stage_open() -> str:
    return _workflow_default_stage()


def _normalize_stage(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    v = str(s).strip().lower()
    if v == "":
        return None
    if v in TASK_CLOSED_STATUSES:
        return v
    return v if v in _stage_keys() else None


def _teams_catalog() -> tuple[str, ...]:
    return _workflow_team_keys()


def _validate_team(team: Optional[str]) -> Optional[str]:
    if team is None:
        return None
    v = str(team).strip()
    if v == "":
        return None
    catalog = _teams_catalog()
    if catalog and v not in catalog:
        raise ValueError(f"invalid_assignee_team: expected one of {list(catalog)}, got {v}")
    return v


# ---- Workflow 2.0: assignee user display helpers ----

def _attach_owner_usernames(conn: Any, *, tenant_id: str, items: list[dict[str, Any]]) -> None:
    """Attach owner_username for UI friendliness.

    Keeps DB as source of truth: owner_user_id stores assignee user id.
    """

    cache: dict[int, str] = {}
    for t in items:
        try:
            uid = t.get('owner_user_id')
            if uid is None:
                t['owner_username'] = None
                continue
            uid_i = int(uid)
            if uid_i in cache:
                t['owner_username'] = cache[uid_i]
                continue
            u = get_user_by_id(conn, user_id=uid_i, tenant_id=tenant_id)
            uname = (u or {}).get('username')
            cache[uid_i] = str(uname) if uname else ''
            t['owner_username'] = (str(uname) if uname else None)
        except Exception:
            t['owner_username'] = None




def create_task(conn: Any, *, tenant_id: str, t: TaskCreate) -> str:
    task_id = uuid.uuid4().hex
    now = utcnow_iso()

    # --- Workflow 2.0: domain + SLA defaults (config-driven) ---
    domain = _normalize_domain(t.domain) or _infer_domain(t.task_type)
    priority = int(t.priority or 3)

    due_fields = _derive_due_fields(
        due_at=(str(t.due_at).strip() if t.due_at else None),
        sla_hours=(int(t.sla_hours) if t.sla_hours is not None else None),
        domain=domain,
        priority=priority,
        now=_parse_iso_dt(now) or _utcnow_dt(),
    )
    due_at = due_fields["due_at"]
    sla_hours = due_fields["sla_hours"]
    sla_source = due_fields["sla_source"]

    # --- Workflow 2.0: validate team + set stage defaults ---
    team = _validate_team(t.assignee_team)
    stage = _normalize_stage(t.stage) or _default_stage_open()

    return TasksRepo(conn).insert(
        tenant_id=tenant_id,
        task_id=task_id,
        created_at=now,
        payload={
            "task_type": t.task_type,
            "title": t.title,
            "domain": domain,
            "priority": priority,
            "status": "open",
            "due_at": due_at,
            "owner_user_id": int(t.owner_user_id) if t.owner_user_id is not None else None,
            "assignee_team": team,
            "sla_hours": int(sla_hours) if sla_hours is not None else None,
            "sla_source": (str(sla_source) if sla_source else None),
            "stage": stage,
            "related_alert": t.related_alert,
            "object_type": t.object_type,
            "object_id": t.object_id,
            "worklist_type": _derive_worklist_type(worklist_type=t.worklist_type, task_type=t.task_type, domain=domain, related_alert=t.related_alert),
            "confidence": (float(t.confidence) if t.confidence is not None else None),
            "linked_decision_id": t.linked_decision_id,
            "linked_task_id": t.linked_task_id,
            "linked_source_facts": t.linked_source_facts or [],
            "attachments": t.attachments or [],
            "why": t.why or {},
            "what_to_do": t.what_to_do or [],
            "data_version": t.data_version,
            "qc_run": t.qc_run,
            "model_version": t.model_version,
            "scoring_run": t.scoring_run,
            "report_version": t.report_version,
            "dedupe_key": t.dedupe_key,
            "source_insight_id": t.source_insight_id,
        },
    )


def get_task(conn: Any, *, tenant_id: str, task_id: str) -> Optional[dict[str, Any]]:
    row = TasksRepo(conn).get_row(tenant_id=tenant_id, task_id=task_id)
    if not row:
        return None
    d = dict(row)
    d = _decode_task_row(d)
    try:
        _attach_owner_usernames(conn, tenant_id=tenant_id, items=[d])
    except Exception:
        pass
    return d


def _is_overdue(t: dict[str, Any]) -> bool:
    return _policy_is_task_overdue(t)


def list_tasks(
    conn: Any,
    *,
    tenant_id: str,
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    owner_user_id: Optional[int] = None,
    related_alert: Optional[str] = None,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    due_before: Optional[str] = None,
    stage: Optional[str] = None,
    domain: Optional[str] = None,
    assignee_team: Optional[str] = None,
    worklist_type: Optional[str] = None,
    linked_decision_id: Optional[str] = None,
    linked_task_id: Optional[str] = None,
    overdue_only: bool = False,
    q: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    where = ["tenant_id=?"]
    args: list[Any] = [tenant_id]

    def add(cond: str, val: Any):
        where.append(cond)
        args.append(val)

    if status:
        add("status=?", status)
    if task_type:
        add("task_type=?", task_type)
    if owner_user_id is not None:
        add("owner_user_id=?", int(owner_user_id))
    if related_alert:
        add("related_alert=?", related_alert)
    if object_type:
        add("object_type=?", object_type)
    if object_id:
        add("object_id=?", object_id)
    if due_before:
        add("due_at<=?", due_before)
    if stage:
        stg = _normalize_stage(stage)
        if not stg:
            raise ValueError(f"invalid_stage_filter: expected one of {_stage_keys()} (or done/cancelled), got {stage}")
        add("stage=?", stg)
    if domain:
        add("domain=?", _normalize_domain(domain) or str(domain))
    if assignee_team:
        add("assignee_team=?", str(assignee_team).strip())
    if worklist_type:
        add("worklist_type=?", _derive_worklist_type(worklist_type=worklist_type))
    if linked_decision_id:
        add("linked_decision_id=?", str(linked_decision_id).strip())
    if linked_task_id:
        add("linked_task_id=?", str(linked_task_id).strip())
    if overdue_only:
        # SQLite string compare is ISO-friendly; we only use this for basic filtering.
        where.append("status IN ('open','in_progress')")
        where.append("due_at IS NOT NULL")
        where.append("due_at < ?")
        args.append(_utcnow_dt().isoformat())
    if q:
        where.append("(title LIKE ? OR task_type LIKE ? OR closed_reason LIKE ?)")
        qq = f"%{q}%"
        args.extend([qq, qq, qq])

    repo_res = TasksRepo(conn).list_rows(
        tenant_id=tenant_id,
        filters={
            "status": status,
            "task_type": task_type,
            "owner_user_id": owner_user_id,
            "related_alert": related_alert,
            "object_type": object_type,
            "object_id": object_id,
            "due_before": due_before,
            "stage": stage,
            "domain": (_normalize_domain(domain) or str(domain)) if domain else None,
            "assignee_team": (str(assignee_team).strip() if assignee_team else None),
            "worklist_type": (_derive_worklist_type(worklist_type=worklist_type) if worklist_type else None),
            "linked_decision_id": (str(linked_decision_id).strip() if linked_decision_id else None),
            "linked_task_id": (str(linked_task_id).strip() if linked_task_id else None),
            "overdue_only": bool(overdue_only),
            "overdue_ts": _utcnow_dt().isoformat(),
            "q": q,
        },
        limit=limit,
        offset=offset,
    )

    items: list[dict[str, Any]] = []
    for d in repo_res["rows"]:
        d = dict(d)
        d = _decode_task_row(d)
        items.append(d)

    try:
        _attach_owner_usernames(conn, tenant_id=tenant_id, items=items)
    except Exception:
        pass

    return {"total": int(repo_res["total"]), "tasks": items}


def list_tasks_for_object(
    conn: Any,
    *,
    tenant_id: str,
    object_type: str,
    object_id: str,
    include_aliases: bool = True,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    """List tasks linked to an entity, tolerating object_type aliases.

    Why:
      - Some producers use object_type="pen" while UI uses "group".
      - We want profiles to show all related tasks regardless of alias.

    Notes:
      - This is a convenience wrapper; list_tasks() remains unchanged.
    """

    if not object_id:
        return {"total": 0, "tasks": []}

    base_type = normalize_object_type(object_type) or str(object_type)
    types = expand_object_types(base_type) if include_aliases else [base_type]
    types = [t for t in types if t]
    if not types:
        return {"total": 0, "tasks": []}

    repo_res = TasksRepo(conn).list_rows_for_object(
        tenant_id=tenant_id,
        object_id=object_id,
        object_types=types,
        limit=limit,
        offset=offset,
    )

    items: list[dict[str, Any]] = []
    for d in repo_res["rows"]:
        d = dict(d)
        d = _decode_task_row(d)
        items.append(d)

    try:
        _attach_owner_usernames(conn, tenant_id=tenant_id, items=items)
    except Exception:
        pass

    return {"total": int(repo_res["total"]), "tasks": items}


def take_task(conn: Any, *, tenant_id: str, task_id: str, user_id: int) -> None:
    now = utcnow_iso()
    status = TasksRepo(conn).fetch_status(tenant_id=tenant_id, task_id=task_id)
    if status is None:
        raise KeyError("not_found")
    if status in TASK_CLOSED_STATUSES:
        raise ValueError("already_closed")
    TasksRepo(conn).take(tenant_id=tenant_id, task_id=task_id, user_id=int(user_id), now=now)


def assign_task(
    conn: Any,
    *,
    tenant_id: str,
    task_id: str,
    owner_user_id: Optional[int] = None,
    assignee_team: Optional[str] = None,
) -> None:
    now = utcnow_iso()
    status = TasksRepo(conn).fetch_status(tenant_id=tenant_id, task_id=task_id)
    if status is None:
        raise KeyError("not_found")
    if status in TASK_CLOSED_STATUSES:
        raise ValueError("already_closed")

    ouid = (int(owner_user_id) if owner_user_id is not None else None)
    team = _validate_team(assignee_team)
    if ouid is None and not team:
        raise ValueError("assignee_required")

    TasksRepo(conn).assign(tenant_id=tenant_id, task_id=task_id, owner_user_id=ouid, assignee_team=team, now=now)




def update_task_fields(
    conn: Any,
    *,
    tenant_id: str,
    task_id: str,
    patch: dict[str, Any],
) -> None:
    """Update editable task fields (Workflow 2.0).

    Notes:
      - This does NOT close tasks (done/cancelled). Use close_task() for that to keep Decision Log semantics.
      - Allowed status transitions here: open <-> in_progress.
      - due_at can be set explicitly or cleared (then re-derived from SLA defaults).

    Errors are raised as ValueError/KeyError with human-readable codes.
    """

    now = utcnow_iso()

    cur = TasksRepo(conn).get_row(tenant_id=tenant_id, task_id=task_id)
    if not cur:
        raise KeyError("not_found")

    status0 = str(cur["status"])
    if status0 in TASK_CLOSED_STATUSES:
        raise ValueError("already_closed")

    sets: list[str] = []
    args: list[Any] = []

    def _set(col: str, val: Any):
        sets.append(f"{col}=?")
        args.append(val)

    # priority
    if "priority" in patch and patch.get("priority") is not None:
        try:
            pr = int(patch.get("priority"))
        except Exception:
            raise ValueError(f"invalid_priority: expected int 1..5, got {patch.get('priority')}")
        if pr < 1 or pr > 5:
            raise ValueError(f"invalid_priority: must be 1..5, got {pr}")
        _set("priority", pr)

    # domain
    if "domain" in patch and patch.get("domain") is not None:
        dom = _normalize_domain(patch.get("domain"))
        if not dom:
            raise ValueError(f"invalid_domain: expected one of health/repro/data/qc/econ, got {patch.get('domain')}")
        _set("domain", dom)

    # status (only open/in_progress)
    if "status" in patch and patch.get("status") is not None:
        st = normalize_task_active_status_for_update(patch.get("status"))
        _set("status", st)
        if st == "in_progress":
            # started_at is set once
            _set("started_at", cur["started_at"] or now)

    # assignee / team
    assignee_changed = False
    if "owner_user_id" in patch:
        owner_raw = patch.get("owner_user_id")
        if owner_raw in (None, ''):
            _set("owner_user_id", None)
        else:
            try:
                ouid = int(owner_raw)
            except Exception:
                raise ValueError(f"invalid_owner_user_id: expected int, got {patch.get('owner_user_id')}")
            _set("owner_user_id", ouid)
        assignee_changed = True

    if "assignee_team" in patch:
        team_raw = patch.get("assignee_team")
        team = _validate_team(team_raw)
        _set("assignee_team", team)
        assignee_changed = True

    if assignee_changed:
        _set("assigned_at", cur["assigned_at"] or now)

    # due_at / SLA
    if "due_at" in patch:
        due_raw = patch.get("due_at")
        due_at = (str(due_raw).strip() if due_raw is not None else None)
        if due_at == "":
            due_at = None

        # effective domain/priority for SLA fallback
        dom_eff = (
            _normalize_domain(patch.get("domain"))
            or _normalize_domain(cur.get("domain"))
            or _infer_domain(str(cur.get("task_type") or ""))
        )
        pr_eff = int(patch.get("priority") or cur.get("priority") or 3)

        due_fields = _derive_due_fields(
            due_at=due_at,
            sla_hours=(int(cur.get("sla_hours")) if cur.get("sla_hours") is not None and due_at is None else None),
            domain=dom_eff,
            priority=pr_eff,
            now=_parse_iso_dt(now) or _utcnow_dt(),
        )
        _set("due_at", due_fields["due_at"])
        if due_fields["sla_hours"] is not None:
            _set("sla_hours", int(due_fields["sla_hours"]))
        _set("sla_source", due_fields["sla_source"])

    # stage (Kanban)
    if "stage" in patch:
        stg_raw = patch.get("stage")
        if stg_raw is None or (isinstance(stg_raw, str) and stg_raw.strip() == ""):
            stg = _default_stage_open()
        else:
            stg = _normalize_stage(stg_raw)
        if not stg:
            raise ValueError(f"invalid_stage: expected one of {_stage_keys()} (or done/cancelled), got {stg_raw}")
        _set("stage", stg)

    if "worklist_type" in patch and patch.get("worklist_type") is not None:
        _set("worklist_type", _derive_worklist_type(worklist_type=patch.get("worklist_type")))

    if "confidence" in patch:
        conf_raw = patch.get("confidence")
        if conf_raw in (None, ""):
            _set("confidence", None)
        else:
            try:
                conf = float(conf_raw)
            except Exception:
                raise ValueError(f"invalid_confidence: expected float 0..1, got {conf_raw}")
            if conf < 0.0 or conf > 1.0:
                raise ValueError(f"invalid_confidence: expected float 0..1, got {conf}")
            _set("confidence", conf)

    if "linked_decision_id" in patch:
        val = str(patch.get("linked_decision_id") or "").strip() or None
        _set("linked_decision_id", val)

    if "linked_task_id" in patch:
        val = str(patch.get("linked_task_id") or "").strip() or None
        _set("linked_task_id", val)

    if "linked_source_facts" in patch:
        facts = patch.get("linked_source_facts")
        if facts in (None, ""):
            facts = []
        if not isinstance(facts, list):
            raise ValueError("invalid_linked_source_facts: expected list")
        _set("linked_source_facts_json", json.dumps(facts, ensure_ascii=False))

    if "attachments" in patch:
        attachments = patch.get("attachments")
        if attachments in (None, ""):
            attachments = []
        if not isinstance(attachments, list):
            raise ValueError("invalid_attachments: expected list")
        _set("attachments_json", json.dumps(attachments, ensure_ascii=False))

    if "why" in patch:
        why = patch.get("why")
        if why in (None, ""):
            why = {}
        if not isinstance(why, dict):
            raise ValueError("invalid_why: expected dict")
        _set("why_json", json.dumps(why, ensure_ascii=False))

    if "what_to_do" in patch:
        what_to_do = patch.get("what_to_do")
        if what_to_do in (None, ""):
            what_to_do = []
        if not isinstance(what_to_do, list):
            raise ValueError("invalid_what_to_do: expected list")
        _set("what_to_do_json", json.dumps(what_to_do, ensure_ascii=False))

    if "latest_outcome_id" in patch:
        _set("latest_outcome_id", str(patch.get("latest_outcome_id") or "").strip() or None)
    if "latest_outcome_status" in patch:
        _set("latest_outcome_status", str(patch.get("latest_outcome_status") or "").strip() or None)
    if "latest_outcome_reason_code" in patch:
        _set("latest_outcome_reason_code", str(patch.get("latest_outcome_reason_code") or "").strip() or None)
    if "latest_outcome_at" in patch:
        _set("latest_outcome_at", str(patch.get("latest_outcome_at") or "").strip() or None)
    if "latest_outcome_by" in patch:
        value = patch.get("latest_outcome_by")
        _set("latest_outcome_by", (int(value) if value not in (None, "") else None))
    if "latest_outcome_comment" in patch:
        _set("latest_outcome_comment", str(patch.get("latest_outcome_comment") or "").strip() or None)
    if "outcome_metrics" in patch:
        metrics = patch.get("outcome_metrics")
        if metrics in (None, ""):
            metrics = {}
        if not isinstance(metrics, dict):
            raise ValueError("invalid_outcome_metrics: expected dict")
        _set("outcome_metrics_json", json.dumps(metrics, ensure_ascii=False))

    if not sets:
        return

    _set("updated_at", now)

    TasksRepo(conn).update_fields(tenant_id=tenant_id, task_id=task_id, sets=sets, args=args)


def close_task(
    conn: Any,
    *,
    tenant_id: str,
    task_id: str,
    user_id: int,
    username: str,
    status: str,
    reason: str,
    comment: Optional[str] = None,
    resolve_related_alert: bool = True,
) -> None:
    status = normalize_task_close_status(status)
    reason = validate_reason_for_task_close(status=status, reason=reason)

    now = utcnow_iso()
    t = get_task(conn, tenant_id=tenant_id, task_id=task_id)
    if not t:
        raise KeyError("not_found")
    if t["status"] in TASK_CLOSED_STATUSES:
        # idempotent
        return

    TasksRepo(conn).close(
        tenant_id=tenant_id,
        task_id=task_id,
        status=status,
        stage=("done" if status == "done" else "cancelled"),
        user_id=int(user_id),
        reason=reason,
        comment=(comment or "").strip() or None,
        now=now,
    )

    # Decision Log v2: closing a task is a decision in unified format.
    try:
        decision_id = append_decision(
            conn,
            tenant_id=tenant_id,
            d=DecisionCreate(
                recommendation_id=None,
                action="task.close",
                user_id=int(user_id),
                username=str(username),
                reason=reason,
                comment=(comment or "").strip() or None,
                related_alert=t.get("related_alert"),
                object_type=t.get("object_type"),
                object_id=t.get("object_id"),
                farm_id=None,
                group_id=None,
                data_version=t.get("data_version"),
                model_version=t.get("model_version"),
                report_version=t.get("report_version"),
                qc_run=t.get("qc_run"),
                scoring_run=t.get("scoring_run"),
                metadata={
                    "task_id": task_id,
                    "task_type": t.get("task_type"),
                    "priority": t.get("priority"),
                    "status": status,
                },
            ),
            created_at=now,
        )
        try:
            TasksRepo(conn).update_fields(tenant_id=tenant_id, task_id=task_id, sets=["linked_decision_id=?", "updated_at=?"], args=[decision_id, now])
        except Exception:
            pass
    except Exception:
        pass

    # Optionally resolve related alert.
    try:
        if resolve_related_alert and status == "done" and t.get("related_alert"):
            resolve_alert(
                conn,
                tenant_id=tenant_id,
                alert_id=str(t.get("related_alert")),
                user_id=int(user_id),
                reason=f"task_done:{reason}"[:500],
            )
    except Exception:
        pass


def upsert_tasks_from_alerts(
    conn: Any,
    *,
    tenant_id: str,
    catalog: dict[str, Any],
    data_version: Optional[str] = None,
    limit_alerts: int = 1000,
) -> dict[str, int]:
    """Create (deduped) tasks for eligible alerts.

    This is intentionally simple: tasks are derived from alerts_v2 and serve as worklists.
    Dedupe key: tenant_id + alert_id + task_type.
    """

    mapping: dict[str, Any] = dict(catalog.get("from_alerts") or {})
    if not mapping:
        return {"inserted": 0, "skipped": 0}

    rows = AlertsRepo(conn).list_open_candidates_for_tasking(tenant_id=tenant_id, open_statuses_sql=alert_open_statuses_sql(), data_version=data_version, limit_alerts=limit_alerts)

    inserted = 0
    skipped = 0

    for r in rows:
        alert_type = str(r["alert_type"])
        rule = mapping.get(alert_type)
        if not rule:
            skipped += 1
            continue

        task_type = str(rule.get("task_type") or "action")
        rule_domain = _normalize_domain(rule.get("domain"))
        domain = rule_domain or _infer_domain(task_type)
        title = str(rule.get("title") or f"{task_type}: {r['title']}")
        priority = int(rule.get("priority") or 3)
        due_days = int(rule.get("due_days") or 0)
        rule_sla_hours = (int(rule.get("sla_hours")) if rule.get("sla_hours") is not None else None)

        due_at = None
        if r["deadline"]:
            due_at = str(r["deadline"])
        elif due_days > 0:
            due_at = (_utcnow_dt() + timedelta(days=due_days)).isoformat()
        else:
            # Use rule SLA or config SLA when no explicit deadlines
            sla_h = rule_sla_hours if rule_sla_hours is not None else _pick_sla_hours(domain, priority)
            if sla_h is not None:
                due_at = (_utcnow_dt() + timedelta(hours=int(sla_h))).isoformat()

        alert_dk = str(r['dedupe_key'] or '').strip()
        base = alert_dk if alert_dk else str(r['alert_id'])
        dedupe_key = (f"alertdk:{base}|task:{task_type}" if alert_dk else f"alert:{base}|task:{task_type}")
        if TasksRepo(conn).exists_active_dedupe(tenant_id=tenant_id, dedupe_key=dedupe_key):
            skipped += 1
            continue

        t = TaskCreate(
            task_type=task_type,
            title=title,
            domain=domain,
            priority=priority,
            due_at=due_at,
            owner_user_id=(int(r["owner_user_id"]) if r["owner_user_id"] is not None else None),
            related_alert=str(r["alert_id"]),
            object_type=str(r["object_type"]) if r["object_type"] else None,
            object_id=str(r["object_id"]) if r["object_id"] else None,
            worklist_type=_derive_worklist_type(task_type=task_type, domain=domain, related_alert=str(r["alert_type"] or "")),
            confidence=(float(r["confidence"]) if r["confidence"] is not None else None),
            linked_source_facts=[{"source": "alert", "alert_id": str(r["alert_id"])}],
            attachments=json.loads(r["attachments_json"] or "[]"),
            why=json.loads(r["why_json"] or "{}"),
            what_to_do=json.loads(r["what_to_do_json"] or "[]"),
            data_version=str(r["data_version"]) if r["data_version"] else None,
            qc_run=str(r["qc_run"]) if r["qc_run"] else None,
            model_version=str(r["model_version"]) if r["model_version"] else None,
            scoring_run=str(r["scoring_run"]) if r["scoring_run"] else None,
            report_version=str(r["report_version"]) if r["report_version"] else None,
            dedupe_key=dedupe_key,
        )
        create_task(conn, tenant_id=tenant_id, t=t)
        inserted += 1

    return {"inserted": int(inserted), "skipped": int(skipped)}


# ---- T12-02: Auto-tasking from critical alerts + QC issues (config-driven) ----


def _load_auto_tasking_cfg() -> dict[str, Any]:
    root = _project_root()
    return _load_yaml(root / "configs" / "workflow_v2" / "auto_tasking.yaml")


def _severity_from_catalog(alert_type: str) -> Optional[str]:
    try:
        from genomeai.alerts_v2 import load_alert_catalog  # type: ignore

        cat = load_alert_catalog(_project_root() / "configs" / "alerts_v2" / "catalog.yaml")
        ent = cat.get(str(alert_type))
        if not ent:
            return None
        return str(getattr(ent, "severity", None) or "").strip().upper() or None
    except Exception:
        return None


def _severity_for_alert(alert_type: str, why: dict[str, Any] | None) -> str:
    sev = _severity_from_catalog(alert_type)
    if sev:
        return sev
    try:
        wsev = (why or {}).get("severity")
        if wsev is None:
            return "UNKNOWN"
        return str(wsev).strip().upper() or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def auto_create_tasks_from_alerts(
    conn: Any,
    *,
    tenant_id: str,
    catalog: dict[str, Any],
    data_version: Optional[str] = None,
    limit_alerts: int = 2000,
) -> dict[str, Any]:
    """Auto-create tasks for eligible alerts (critical + QC).

    Eligibility and fallback behavior are driven by configs/workflow_v2/auto_tasking.yaml.

    Dedupe policy:
      - prefer alert.dedupe_key (stable per object+reason)
      - fallback to alert_id
      - task dedupe key = (alert_dedupe_key or alert_id) + task_type

    Returns counts + list of created task_ids (capped).
    """

    cfg = _load_auto_tasking_cfg()
    if not bool(cfg.get("enabled", False)):
        return {"eligible": 0, "inserted": 0, "skipped": 0, "task_ids": []}

    # Validate config fields (human-readable errors)
    try:
        critical_severities = {str(x).strip().upper() for x in (cfg.get("critical_severities") or []) if str(x).strip()}
        force_sources = {str(x).strip() for x in (cfg.get("force_sources") or []) if str(x).strip()}
        force_prefixes = [str(x).strip() for x in (cfg.get("force_prefixes") or []) if str(x).strip()]
        force_alert_types = {str(x).strip() for x in (cfg.get("force_alert_types") or []) if str(x).strip()}
        max_tasks = int(cfg.get("max_tasks_per_generate") or 500)
    except Exception as e:
        raise ValueError(f"auto_tasking_config_invalid: {e}")

    fallback = dict(cfg.get("fallback_task") or {})
    fb_task_type = str(fallback.get("task_type") or "alert_followup")
    fb_title_prefix = str(fallback.get("title_prefix") or "Разобрать алерт: ")
    pr_by_sev = dict(fallback.get("priority_by_severity") or {})

    mapping: dict[str, Any] = dict(catalog.get("from_alerts") or {})

    rows = AlertsRepo(conn).list_open_candidates_for_tasking(tenant_id=tenant_id, open_statuses_sql=alert_open_statuses_sql(), data_version=data_version, limit_alerts=limit_alerts)

    eligible = 0
    inserted = 0
    skipped = 0
    task_ids: list[str] = []

    for r in rows:
        if inserted >= max_tasks:
            break

        a_type = str(r["alert_type"] or "")
        a_source = str(r["source"] or "")
        why = json.loads(r["why_json"] or "{}")
        sev = _severity_for_alert(a_type, why)

        is_eligible = False
        if a_type in force_alert_types:
            is_eligible = True
        if a_source in force_sources:
            is_eligible = True
        if any(a_type.startswith(p) for p in force_prefixes):
            is_eligible = True
        if (sev in critical_severities):
            is_eligible = True

        if not is_eligible:
            continue
        eligible += 1

        rule = mapping.get(a_type)
        task_type = str((rule or {}).get("task_type") or fb_task_type)
        title = str((rule or {}).get("title") or f"{fb_title_prefix}{str(r['title'] or '')}")
        priority = int((rule or {}).get("priority") or pr_by_sev.get(sev) or pr_by_sev.get("UNKNOWN") or 3)
        rule_domain = (rule or {}).get("domain")
        domain = _normalize_domain(rule_domain) or _infer_domain(task_type)

        due_at = None
        if r["deadline"]:
            due_at = str(r["deadline"])
        else:
            due_days = int((rule or {}).get("due_days") or 0)
            if due_days > 0:
                due_at = (_utcnow_dt() + timedelta(days=due_days)).isoformat()
            else:
                sla_h = _pick_sla_hours(domain, priority)
                if sla_h is not None:
                    due_at = (_utcnow_dt() + timedelta(hours=int(sla_h))).isoformat()

        alert_dk = str(r['dedupe_key'] or '').strip()
        base = alert_dk if alert_dk else str(r["alert_id"])
        dedupe_key = (f"alertdk:{base}|task:{task_type}" if alert_dk else f"alert:{base}|task:{task_type}")

        if TasksRepo(conn).exists_active_dedupe(tenant_id=tenant_id, dedupe_key=dedupe_key):
            skipped += 1
            continue

        t = TaskCreate(
            task_type=task_type,
            title=title,
            domain=domain,
            priority=priority,
            due_at=due_at,
            owner_user_id=(int(r["owner_user_id"]) if r["owner_user_id"] is not None else None),
            related_alert=str(r["alert_id"]),
            object_type=str(r["object_type"]) if r["object_type"] else None,
            object_id=str(r["object_id"]) if r["object_id"] else None,
            attachments=json.loads(r["attachments_json"] or "[]"),
            why=why,
            what_to_do=json.loads(r["what_to_do_json"] or "[]"),
            data_version=str(r["data_version"]) if r["data_version"] else None,
            qc_run=str(r["qc_run"]) if r["qc_run"] else None,
            model_version=str(r["model_version"]) if r["model_version"] else None,
            scoring_run=str(r["scoring_run"]) if r["scoring_run"] else None,
            report_version=str(r["report_version"]) if r["report_version"] else None,
            dedupe_key=dedupe_key,
        )
        tid = create_task(conn, tenant_id=tenant_id, t=t)
        inserted += 1
        if len(task_ids) < 50:
            task_ids.append(tid)

    return {"eligible": int(eligible), "inserted": int(inserted), "skipped": int(skipped), "task_ids": task_ids}





def _load_metrics_defaults() -> tuple[int, tuple[int, ...]]:
    root = _project_root()
    cfg = _load_yaml(root / "configs" / "workflow_v2" / "metrics.yaml")
    try:
        window_days = int(cfg.get("window_days") or 30)
    except Exception:
        window_days = 30

    ps_raw = cfg.get("lead_time_percentiles") or [50, 90]
    ps: list[int] = []
    for x in list(ps_raw):
        try:
            xi = int(x)
        except Exception:
            continue
        if 0 <= xi <= 100:
            ps.append(xi)
    if not ps:
        ps = [50, 90]
    return window_days, tuple(ps)


def compute_tasks_metrics(
    conn: Any,
    *,
    tenant_id: str,
    window_days: Optional[int] = None,
) -> dict[str, Any]:
    """Compute Workflow 2.0 execution metrics for Director Cabinet.

    This is a thin wrapper around offline-core genomeai.workflow_v2.metrics.
    """

    from genomeai.workflow_v2.metrics import MetricsConfig, compute_tasks_metrics as _core_compute

    wd0, ps0 = _load_metrics_defaults()
    wd = int(window_days) if window_days is not None else int(wd0)

    tasks = TasksRepo(conn).list_metric_rows(tenant_id=tenant_id)

    # Stage fallback for older tasks (to make by_stage breakdown useful)
    for t in tasks:
        if not t.get("stage"):
            st = str(t.get("status") or "")
            if st in TASK_CLOSED_STATUSES:
                t["stage"] = st
            elif st in TASK_ACTIVE_STATUSES:
                t["stage"] = _default_stage_open()

    return _core_compute(tasks, config=MetricsConfig(window_days=wd, percentiles=ps0))



def compute_tasks_overdue_list(
    conn: Any,
    *,
    tenant_id: str,
    limit: int = 20,
    domain: Optional[str] = None,
    assignee_team: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Top overdue tasks for Director dashboards (Workflow 2.0).

    Thin wrapper around offline-core genomeai.workflow_v2.metrics.rank_overdue_tasks.
    """

    from genomeai.workflow_v2.metrics import rank_overdue_tasks

    tasks = TasksRepo(conn).list_overdue_rows(
        tenant_id=tenant_id,
        domain=_normalize_domain(domain) or str(domain) if domain else None,
        assignee_team=str(assignee_team).strip() if assignee_team else None,
    )
    ranked = rank_overdue_tasks(tasks, limit=int(limit or 20))
    # Ensure stage fallback for older tasks
    for t in ranked:
        if not t.get("stage"):
            t["stage"] = _default_stage_open()
    return ranked


def load_tasks_catalog(path) -> dict[str, Any]:
    """Load tasks catalog YAML if available."""
    try:
        import yaml  # type: ignore

        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
