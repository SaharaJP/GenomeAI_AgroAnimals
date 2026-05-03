from __future__ import annotations

"""T10-04: Saved views (filters/widgets/page state).

Notes:
- This is *web-cabinet* storage only (UI state). No offline-core calculations.
- Scope:
  - user: visible only to creator
  - shared: visible to all users in tenant
"""

import json
from dataclasses import dataclass
from typing import Any, Optional

from core.infra import SavedViewsRepo

from core.infra.web_db import utcnow_iso


@dataclass
class SavedView:
    view_id: str
    tenant_id: str
    created_at: str
    updated_at: str
    created_by: int
    created_by_username: str
    scope: str
    name: str
    description: str | None
    page_key: str
    state: dict[str, Any]
    data_version: str | None
    run_id: str | None


def _to_row(v: SavedView) -> tuple:
    return (
        v.view_id,
        v.tenant_id,
        v.created_at,
        v.updated_at,
        int(v.created_by),
        str(v.created_by_username),
        str(v.scope),
        str(v.name),
        v.description,
        str(v.page_key),
        json.dumps(v.state, ensure_ascii=False),
        v.data_version,
        v.run_id,
    )


def create_saved_view(
    conn: Any,
    *,
    view_id: str,
    tenant_id: str,
    created_by: int,
    created_by_username: str,
    scope: str,
    name: str,
    page_key: str,
    state: dict[str, Any],
    description: Optional[str] = None,
    data_version: Optional[str] = None,
    run_id: Optional[str] = None,
) -> SavedView:
    if scope not in {"user", "shared"}:
        raise ValueError("scope должен быть 'user' или 'shared'")
    if not name or not str(name).strip():
        raise ValueError("name обязателен")
    if not page_key or not str(page_key).strip():
        raise ValueError("page_key обязателен")
    if not isinstance(state, dict):
        raise ValueError("state должен быть JSON-объектом")

    ts = utcnow_iso()
    v = SavedView(
        view_id=str(view_id),
        tenant_id=str(tenant_id),
        created_at=ts,
        updated_at=ts,
        created_by=int(created_by),
        created_by_username=str(created_by_username),
        scope=str(scope),
        name=str(name).strip(),
        description=str(description).strip() if description else None,
        page_key=str(page_key).strip(),
        state=state,
        data_version=str(data_version) if data_version else None,
        run_id=str(run_id) if run_id else None,
    )
    SavedViewsRepo(conn).create(
        view_id=v.view_id,
        tenant_id=v.tenant_id,
        created_at=v.created_at,
        updated_at=v.updated_at,
        created_by=v.created_by,
        created_by_username=v.created_by_username,
        scope=v.scope,
        name=v.name,
        description=v.description,
        page_key=v.page_key,
        state=v.state,
        data_version=v.data_version,
        run_id=v.run_id,
    )
    return v


def update_saved_view(
    conn: Any,
    *,
    tenant_id: str,
    view_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    state: Optional[dict[str, Any]] = None,
    scope: Optional[str] = None,
    data_version: Optional[str] = None,
    run_id: Optional[str] = None,
) -> None:
    if scope is not None and scope not in {"user", "shared"}:
        raise ValueError("scope должен быть 'user' или 'shared'")
    if state is not None and not isinstance(state, dict):
        raise ValueError("state должен быть JSON-объектом")

    repo = SavedViewsRepo(conn)
    row = repo.get(tenant_id=str(tenant_id), view_id=str(view_id))
    if not row:
        raise ValueError("saved view не найден")

    upd = {
        "updated_at": utcnow_iso(),
        "name": str(name).strip() if name is not None else row["name"],
        "description": description if description is not None else row["description"],
        "scope": str(scope) if scope is not None else row["scope"],
        "state_json": json.dumps(state, ensure_ascii=False) if state is not None else row["state_json"],
        "data_version": data_version if data_version is not None else row["data_version"],
        "run_id": run_id if run_id is not None else row["run_id"],
    }
    if not upd["name"]:
        raise ValueError("name обязателен")

    repo.update(
        tenant_id=str(tenant_id),
        view_id=str(view_id),
        updated_at=upd["updated_at"],
        name=upd["name"],
        description=upd["description"],
        scope=upd["scope"],
        state_json=upd["state_json"],
        data_version=upd["data_version"],
        run_id=upd["run_id"],
    )


def delete_saved_view(conn: Any, *, tenant_id: str, view_id: str) -> None:
    deleted = SavedViewsRepo(conn).delete(tenant_id=str(tenant_id), view_id=str(view_id))
    if deleted == 0:
        raise ValueError("saved view не найден")


def get_saved_view(conn: Any, *, tenant_id: str, view_id: str) -> Optional[dict[str, Any]]:
    return SavedViewsRepo(conn).get(tenant_id=str(tenant_id), view_id=str(view_id))


def list_saved_views(
    conn: Any,
    *,
    tenant_id: str,
    user_id: int,
    page_key: Optional[str] = None,
    include_shared: bool = True,
    limit: int = 200,
) -> list[dict[str, Any]]:
    return SavedViewsRepo(conn).list(
        tenant_id=str(tenant_id),
        user_id=int(user_id),
        page_key=str(page_key) if page_key else None,
        include_shared=bool(include_shared),
        limit=int(limit),
    )
