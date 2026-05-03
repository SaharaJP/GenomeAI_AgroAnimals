from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from core.domain import ApprovalStatus, require_draft_approval_status
from core.infra import ArtifactsRepo, WeeklyPlansRepo

from core.infra.web_db import get_settings, utcnow_iso
from .tasks_v1 import TaskCreate, create_task
from genomeai.weekly_plan_pdf import generate_weekly_plan_pdf


def _project_root() -> Path:
    return Path(os.environ.get("GENOMEAI_PROJECT_ROOT", Path(__file__).resolve().parents[1])).resolve()


def _cfg_weekly_plan() -> dict[str, Any]:
    settings = get_settings()
    repo = ArtifactsRepo(settings.project_root, settings.artifacts_root, settings.storage_dir)
    cfg = repo.read_yaml(_project_root() / "configs" / "approvals" / "weekly_plan.yaml")
    return dict(cfg.get("weekly_plan_v1") or {})


def _slug(s: str) -> str:
    v = re.sub(r"[^a-zA-Z0-9\u0400-\u04FF]+", "-", (s or "").strip().lower())
    v = v.strip("-")
    return v or "item"


def _parse_week_start(s: str) -> str:
    ss = (s or "").strip()
    if not ss:
        raise ValueError("weekly_plan.week_start пуст")
    try:
        dt = datetime.fromisoformat(ss)
        if isinstance(dt, datetime):
            return dt.date().isoformat()
        return ss
    except Exception:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", ss):
            raise ValueError("weekly_plan.week_start должен быть YYYY-MM-DD")
        return ss


def _normalize_action_items(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    src = list(items or [])
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for it in src:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title") or it.get("name") or "").strip()
        if not title:
            continue
        key = str(it.get("key") or "").strip() or _slug(title)
        base = key
        n = 2
        while key in seen:
            key = f"{base}-{n}"
            n += 1
        seen.add(key)

        d: dict[str, Any] = {"key": key, "title": title}
        for k in (
            "task_type",
            "domain",
            "priority",
            "due_at",
            "owner_user_id",
            "assignee_team",
            "object_type",
            "object_id",
            "why",
            "what_to_do",
            "expected_effect",
            "citations",
            "source_run_ids",
        ):
            if k in it and it.get(k) is not None:
                d[k] = it.get(k)
        out.append(d)
    return out


@dataclass
class WeeklyPlanCreate:
    name: str
    week_start: str
    summary: str | None = None
    farm_id: str | None = None
    data_version: str | None = None
    action_items: list[dict[str, Any]] | None = None


def create_weekly_plan(
    conn: Any,
    *,
    tenant_id: str,
    user_id: int,
    username: str,
    p: WeeklyPlanCreate,
) -> str:
    name = (p.name or "").strip()
    if not name:
        raise ValueError("weekly_plan.name пуст")
    repo = WeeklyPlansRepo(conn)
    now = utcnow_iso()
    return repo.create(
        plan_id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        created_at=now,
        updated_at=now,
        week_start=_parse_week_start(p.week_start),
        name=name,
        summary=(p.summary or None),
        status=ApprovalStatus.DRAFT.value,
        farm_id=(str(p.farm_id).strip() if p.farm_id else None),
        data_version=(str(p.data_version).strip() if p.data_version else None),
        action_items=_normalize_action_items(p.action_items),
        created_by=int(user_id),
        created_by_username=str(username),
    )


def get_weekly_plan(conn: Any, *, tenant_id: str, plan_id: str) -> Optional[dict[str, Any]]:
    return WeeklyPlansRepo(conn).get(tenant_id=tenant_id, plan_id=plan_id)


def list_weekly_plans(
    conn: Any,
    *,
    tenant_id: str,
    status: str | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    return WeeklyPlansRepo(conn).list(tenant_id=tenant_id, status=status, q=q, limit=int(limit), offset=int(offset))


def list_pending_approval_weekly_plans(
    conn: Any,
    *,
    tenant_id: str,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    return WeeklyPlansRepo(conn).list_pending_approval(tenant_id=tenant_id, limit=int(limit), offset=int(offset))


def summarize_weekly_plan(plan: dict[str, Any]) -> dict[str, Any]:
    action_items = list(plan.get("action_items") or [])
    citations = [c for item in action_items if isinstance(item, dict) for c in list(item.get("citations") or []) if isinstance(c, dict)]
    source_run_ids = sorted({str(rid) for item in action_items if isinstance(item, dict) for rid in list(item.get("source_run_ids") or []) if str(rid).strip()})
    return {
        "plan_id": str(plan.get("plan_id") or ""),
        "status": str(plan.get("status") or ApprovalStatus.DRAFT.value),
        "week_start": str(plan.get("week_start") or ""),
        "name": str(plan.get("name") or ""),
        "data_version": (str(plan.get("data_version")) if plan.get("data_version") else None),
        "farm_id": (str(plan.get("farm_id")) if plan.get("farm_id") else None),
        "item_count": len(action_items),
        "citation_count": len(citations),
        "source_run_ids": source_run_ids,
        "approval_requested_at": (str(plan.get("approval_requested_at")) if plan.get("approval_requested_at") else None),
        "approval_requested_by_username": (str(plan.get("approval_requested_by_username")) if plan.get("approval_requested_by_username") else None),
        "approved_at": (str(plan.get("approved_at")) if plan.get("approved_at") else None),
        "approved_by_username": (str(plan.get("approved_by_username")) if plan.get("approved_by_username") else None),
        "pdf_rel_path": (str(plan.get("pdf_rel_path")) if plan.get("pdf_rel_path") else None),
    }


def update_weekly_plan(
    conn: Any,
    *,
    tenant_id: str,
    plan_id: str,
    name: str | None = None,
    summary: str | None = None,
    farm_id: str | None = None,
    data_version: str | None = None,
    week_start: str | None = None,
    action_items: list[dict[str, Any]] | None = None,
) -> None:
    repo = WeeklyPlansRepo(conn)
    status = repo.get_status(tenant_id=tenant_id, plan_id=plan_id)
    if status is None:
        raise ValueError("plan_id не найден")
    require_draft_approval_status(status, entity_label="План", action_label="редактирование", forbidden_word="запрещено")

    new_name = (name.strip() if isinstance(name, str) else None)
    if new_name is not None and not new_name:
        raise ValueError("weekly_plan.name пуст")

    repo.update_draft(
        tenant_id=tenant_id,
        plan_id=plan_id,
        updated_at=utcnow_iso(),
        name=new_name,
        summary=(summary if summary is not None else None),
        farm_id=(farm_id if farm_id is not None else None),
        data_version=(data_version if data_version is not None else None),
        week_start=(_parse_week_start(week_start) if isinstance(week_start, str) and week_start.strip() else None),
        action_items=(_normalize_action_items(action_items) if action_items is not None else None),
    )


def request_approval_weekly_plan(
    conn: Any,
    *,
    tenant_id: str,
    plan_id: str,
    requested_by: int,
    requested_by_username: str,
    comment: str | None = None,
) -> dict[str, Any]:
    repo = WeeklyPlansRepo(conn)
    before = repo.get(tenant_id=tenant_id, plan_id=plan_id)
    if not before:
        raise ValueError("plan_id не найден")
    require_draft_approval_status(before.get("status"), entity_label="План", action_label="отправка на approval", forbidden_word="запрещена")

    now = utcnow_iso()
    repo.request_approval(
        tenant_id=tenant_id,
        plan_id=plan_id,
        requested_at=now,
        requested_by=int(requested_by),
        requested_by_username=str(requested_by_username),
        comment=(str(comment).strip() if comment else None),
    )
    return {
        "requested_at": now,
        "requested_by_username": str(requested_by_username),
        "already_requested": bool(before.get("approval_requested_at")),
        "previous_requested_by_username": (str(before.get("approval_requested_by_username")) if before.get("approval_requested_by_username") else None),
    }


def get_weekly_plan_pdf_rel_path(*, plan: dict[str, Any]) -> str:
    data_version = str(plan.get("data_version") or "NA")
    plan_id = str(plan.get("plan_id") or "").strip()
    if not plan_id:
        raise ValueError("weekly_plan.plan_id пуст")
    return str(Path("artifacts") / data_version / "weekly_plans" / plan_id / "weekly_plan.pdf")


def export_weekly_plan_pdf(
    conn: Any,
    *,
    artifacts_root: Path,
    tenant_id: str,
    plan_id: str,
    exported_by: int,
    exported_by_username: str,
) -> dict[str, Any]:
    repo = WeeklyPlansRepo(conn)
    plan = repo.get(tenant_id=tenant_id, plan_id=plan_id)
    if not plan:
        raise ValueError("plan_id не найден")

    rep = generate_weekly_plan_pdf(artifacts_root=artifacts_root, plan=plan)
    rel_prefixed = get_weekly_plan_pdf_rel_path(plan=plan)
    now = utcnow_iso()
    repo.mark_pdf_exported(
        tenant_id=tenant_id,
        plan_id=plan_id,
        updated_at=now,
        exported_by=int(exported_by),
        exported_by_username=str(exported_by_username),
        pdf_rel_path=str(rel_prefixed),
    )
    rep["updated_at"] = now
    rep["pdf_rel_path"] = str(rel_prefixed)
    return rep


def reject_weekly_plan(
    conn: Any,
    *,
    tenant_id: str,
    plan_id: str,
    rejected_by: int,
    rejected_by_username: str,
    comment: str | None = None,
) -> None:
    repo = WeeklyPlansRepo(conn)
    status = repo.get_status(tenant_id=tenant_id, plan_id=plan_id)
    if status is None:
        raise ValueError("plan_id не найден")
    require_draft_approval_status(status, entity_label="План", action_label="reject", forbidden_word="запрещен")
    repo.reject(
        tenant_id=tenant_id,
        plan_id=plan_id,
        updated_at=utcnow_iso(),
        rejected_by=int(rejected_by),
        rejected_by_username=str(rejected_by_username),
        comment=(str(comment) if comment else None),
    )


def get_weekly_plan_tasks_map(conn: Any, *, tenant_id: str, plan_id: str) -> dict[str, str]:
    return WeeklyPlansRepo(conn).list_task_links(tenant_id=tenant_id, plan_id=plan_id)


def approve_weekly_plan(
    conn: Any,
    *,
    tenant_id: str,
    plan_id: str,
    approved_by: int,
    approved_by_username: str,
    comment: str | None = None,
) -> dict[str, Any]:
    repo = WeeklyPlansRepo(conn)
    plan = repo.get(tenant_id=tenant_id, plan_id=plan_id)
    if not plan:
        raise ValueError("plan_id не найден")
    require_draft_approval_status(plan.get("status"), entity_label="План", action_label="approval", forbidden_word="запрещен")

    action_items = list(plan.get("action_items") or [])
    data_version = str(plan.get("data_version") or "") or None
    farm_id = str(plan.get("farm_id") or "") or None

    cfg = _cfg_weekly_plan()
    default_task_type = str(cfg.get("default_task_type") or "weekly_plan.action")
    default_priority = int(cfg.get("default_priority") or 3)
    default_domain = str(cfg.get("default_domain") or "data")
    max_tasks = int(cfg.get("max_tasks_per_approval") or 50)

    created: list[str] = []
    reused: list[str] = []
    run_id = uuid.uuid4().hex
    now = utcnow_iso()

    for it in action_items[: max_tasks]:
        if not isinstance(it, dict):
            continue
        action_key = str(it.get("key") or "").strip()
        title = str(it.get("title") or "").strip()
        if not action_key or not title:
            continue
        linked = repo.get_task_link(tenant_id=tenant_id, plan_id=plan_id, action_key=action_key)
        if linked:
            reused.append(linked)
            continue

        task_type = str(it.get("task_type") or default_task_type).strip() or default_task_type
        domain = str(it.get("domain") or default_domain).strip() or default_domain
        priority = int(it.get("priority") or default_priority)
        due_at = (str(it.get("due_at")).strip() if it.get("due_at") is not None else None)
        owner_user_id = (int(it.get("owner_user_id")) if it.get("owner_user_id") is not None else None)
        assignee_team = (str(it.get("assignee_team")).strip() if it.get("assignee_team") is not None else None)
        object_type = (str(it.get("object_type")).strip() if it.get("object_type") is not None else None)
        object_id = (str(it.get("object_id")).strip() if it.get("object_id") is not None else None)

        dedupe_key = f"weekly_plan:{plan_id}|action:{action_key}"
        task_id = repo.get_active_task_by_dedupe(tenant_id=tenant_id, dedupe_key=dedupe_key)
        if not task_id:
            task_id = create_task(
                conn,
                tenant_id=tenant_id,
                t=TaskCreate(
                    task_type=task_type,
                    title=title,
                    domain=domain,
                    priority=priority,
                    due_at=due_at,
                    owner_user_id=owner_user_id,
                    assignee_team=assignee_team,
                    object_type=object_type,
                    object_id=object_id,
                    why={"source": "weekly_plan", "plan_id": plan_id, "action_key": action_key, "farm_id": farm_id} if farm_id else {"source": "weekly_plan", "plan_id": plan_id, "action_key": action_key},
                    what_to_do=list(it.get("what_to_do") or []) if isinstance(it.get("what_to_do"), list) else None,
                    data_version=data_version,
                    dedupe_key=dedupe_key,
                ),
            )
            created.append(task_id)
        else:
            reused.append(task_id)

        repo.link_task(tenant_id=tenant_id, plan_id=plan_id, action_key=action_key, task_id=task_id, created_at=now)

    repo.approve(
        tenant_id=tenant_id,
        plan_id=plan_id,
        updated_at=now,
        approved_by=int(approved_by),
        approved_by_username=str(approved_by_username),
        comment=(str(comment) if comment else None),
        tasks_created_at=(now if created else None),
        tasks_created_run_id=(run_id if created else None),
    )
    return {"tasks_created": created, "tasks_reused": reused, "tasks_run_id": run_id, "tasks_limit": max_tasks}


def archive_weekly_plan(
    conn: Any,
    *,
    tenant_id: str,
    plan_id: str,
    archived_by: int,
    archived_by_username: str,
    comment: str | None = None,
) -> None:
    repo = WeeklyPlansRepo(conn)
    status = repo.get_status(tenant_id=tenant_id, plan_id=plan_id)
    if status is None:
        raise ValueError("plan_id не найден")
    if status == ApprovalStatus.ARCHIVED.value:
        return
    repo.archive(
        tenant_id=tenant_id,
        plan_id=plan_id,
        updated_at=utcnow_iso(),
        archived_by=int(archived_by),
        archived_by_username=str(archived_by_username),
        comment=(str(comment).strip() if comment else None),
    )
