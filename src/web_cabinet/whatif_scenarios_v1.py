from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Optional

from core.domain import ApprovalStatus, require_draft_approval_status
from core.infra import WhatIfScenariosRepo

from core.infra.web_db import utcnow_iso


@dataclass
class WhatIfScenarioCreate:
    name: str
    description: str | None = None
    data_version: str | None = None
    params: dict[str, Any] | None = None


def create_scenario(
    conn: Any,
    *,
    tenant_id: str,
    user_id: int,
    username: str,
    s: WhatIfScenarioCreate,
) -> str:
    name = (s.name or "").strip()
    if not name:
        raise ValueError("scenario.name пуст")
    now = utcnow_iso()
    return WhatIfScenariosRepo(conn).create(
        scenario_id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        created_at=now,
        updated_at=now,
        name=name,
        description=(s.description or None),
        status=ApprovalStatus.DRAFT.value,
        created_by=int(user_id),
        created_by_username=str(username),
        data_version=(s.data_version or None),
        params=(s.params or {}),
    )


def get_scenario(conn: Any, *, tenant_id: str, scenario_id: str) -> Optional[dict[str, Any]]:
    return WhatIfScenariosRepo(conn).get(tenant_id=tenant_id, scenario_id=scenario_id)


def list_scenarios(
    conn: Any,
    *,
    tenant_id: str,
    status: str | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    return WhatIfScenariosRepo(conn).list(tenant_id=tenant_id, status=status, q=q, limit=int(limit), offset=int(offset))


def update_scenario(
    conn: Any,
    *,
    tenant_id: str,
    scenario_id: str,
    name: str | None = None,
    description: str | None = None,
    data_version: str | None = None,
    params: dict[str, Any] | None = None,
) -> None:
    repo = WhatIfScenariosRepo(conn)
    status = repo.get_status(tenant_id=tenant_id, scenario_id=scenario_id)
    if status is None:
        raise ValueError("scenario_id не найден")
    require_draft_approval_status(status, entity_label="Сценарий", action_label="редактирование", forbidden_word="запрещено")

    new_name = (name.strip() if isinstance(name, str) else None)
    if new_name is not None and not new_name:
        raise ValueError("scenario.name пуст")

    repo.update_draft(
        tenant_id=tenant_id,
        scenario_id=scenario_id,
        updated_at=utcnow_iso(),
        name=new_name,
        description=(description if description is not None else None),
        data_version=(data_version if data_version is not None else None),
        params=params,
    )


def approve_scenario(
    conn: Any,
    *,
    tenant_id: str,
    scenario_id: str,
    approved_by: int,
    approved_by_username: str,
    comment: str | None = None,
) -> None:
    repo = WhatIfScenariosRepo(conn)
    status = repo.get_status(tenant_id=tenant_id, scenario_id=scenario_id)
    if status is None:
        raise ValueError("scenario_id не найден")
    require_draft_approval_status(status, entity_label="Сценарий", action_label="approval", forbidden_word="запрещен")
    repo.approve(
        tenant_id=tenant_id,
        scenario_id=scenario_id,
        updated_at=utcnow_iso(),
        approved_by=int(approved_by),
        approved_by_username=str(approved_by_username),
        comment=(str(comment) if comment else None),
    )


def reject_scenario(
    conn: Any,
    *,
    tenant_id: str,
    scenario_id: str,
    rejected_by: int,
    rejected_by_username: str,
    comment: str | None = None,
) -> None:
    repo = WhatIfScenariosRepo(conn)
    status = repo.get_status(tenant_id=tenant_id, scenario_id=scenario_id)
    if status is None:
        raise ValueError("scenario_id не найден")
    require_draft_approval_status(status, entity_label="Сценарий", action_label="reject", forbidden_word="запрещен")
    repo.reject(
        tenant_id=tenant_id,
        scenario_id=scenario_id,
        updated_at=utcnow_iso(),
        rejected_by=int(rejected_by),
        rejected_by_username=str(rejected_by_username),
        comment=(str(comment) if comment else None),
    )


def attach_last_run(
    conn: Any,
    *,
    tenant_id: str,
    scenario_id: str,
    economics_run: str,
) -> None:
    repo = WhatIfScenariosRepo(conn)
    status = repo.get_status(tenant_id=tenant_id, scenario_id=scenario_id)
    if status == ApprovalStatus.ARCHIVED.value:
        return
    repo.attach_last_run(tenant_id=tenant_id, scenario_id=scenario_id, updated_at=utcnow_iso(), economics_run=economics_run)


def clone_scenario(
    conn: Any,
    *,
    tenant_id: str,
    source_scenario_id: str,
    user_id: int,
    username: str,
    name: str | None = None,
    description: str | None = None,
) -> str:
    repo = WhatIfScenariosRepo(conn)
    src = repo.get(tenant_id=tenant_id, scenario_id=source_scenario_id)
    if not src:
        raise ValueError("scenario_id не найден")

    new_name = (name.strip() if isinstance(name, str) else "")
    if not new_name:
        base = str(src.get("name") or "Scenario").strip() or "Scenario"
        new_name = f"{base} (copy)"

    new_desc = description if description is not None else (src.get("description") or None)
    now = utcnow_iso()
    return repo.create(
        scenario_id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        created_at=now,
        updated_at=now,
        name=new_name,
        description=(new_desc or None),
        status=ApprovalStatus.DRAFT.value,
        created_by=int(user_id),
        created_by_username=str(username),
        data_version=(str(src.get("data_version") or "") or None),
        params=dict(src.get("params") or {}),
        cloned_from_scenario_id=str(source_scenario_id),
    )


def archive_scenario(
    conn: Any,
    *,
    tenant_id: str,
    scenario_id: str,
    archived_by: int,
    archived_by_username: str,
    comment: str | None = None,
) -> None:
    repo = WhatIfScenariosRepo(conn)
    status = repo.get_status(tenant_id=tenant_id, scenario_id=scenario_id)
    if status is None:
        raise ValueError("scenario_id не найден")
    if status == ApprovalStatus.ARCHIVED.value:
        return
    repo.archive(
        tenant_id=tenant_id,
        scenario_id=scenario_id,
        updated_at=utcnow_iso(),
        archived_by=int(archived_by),
        archived_by_username=str(archived_by_username),
        comment=(str(comment).strip() if comment else None),
    )
