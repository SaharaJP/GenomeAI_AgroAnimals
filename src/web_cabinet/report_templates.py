from __future__ import annotations

"""T10-04: Report templates (sections + metrics selection).

This module stores templates in web.db. No calculations here.
Report generation from templates is implemented in offline-core (next sub-steps).
"""

import json
import sqlite3
from typing import Any, Optional

from core.infra import ReportTemplatesRepo

from core.infra.web_db import utcnow_iso


def _json(obj: Any, default: str) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return default


def create_template(
    conn: sqlite3.Connection,
    *,
    template_id: str,
    tenant_id: str,
    created_by: int,
    created_by_username: str,
    scope: str,
    name: str,
    description: Optional[str] = None,
    sections: Optional[list[str]] = None,
    metrics: Optional[list[str]] = None,
    options: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if scope not in {"user", "shared"}:
        raise ValueError("scope должен быть 'user' или 'shared'")
    if not name or not str(name).strip():
        raise ValueError("name обязателен")

    ts = utcnow_iso()
    row = {
        "template_id": str(template_id),
        "tenant_id": str(tenant_id),
        "created_at": ts,
        "updated_at": ts,
        "created_by": int(created_by),
        "created_by_username": str(created_by_username),
        "scope": str(scope),
        "name": str(name).strip(),
        "description": str(description).strip() if description else None,
        "sections_json": _json(sections or [], "[]"),
        "metrics_json": _json(metrics or [], "[]"),
        "options_json": _json(options or {}, "{}"),
    }

    ReportTemplatesRepo(conn).create(
        template_id=row["template_id"],
        tenant_id=row["tenant_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by=row["created_by"],
        created_by_username=row["created_by_username"],
        scope=row["scope"],
        name=row["name"],
        description=row["description"],
        sections_json=row["sections_json"],
        metrics_json=row["metrics_json"],
        options_json=row["options_json"],
    )
    return get_template(conn, tenant_id=tenant_id, template_id=template_id) or row


def update_template(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    template_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    scope: Optional[str] = None,
    sections: Optional[list[str]] = None,
    metrics: Optional[list[str]] = None,
    options: Optional[dict[str, Any]] = None,
) -> None:
    if scope is not None and scope not in {"user", "shared"}:
        raise ValueError("scope должен быть 'user' или 'shared'")

    repo = ReportTemplatesRepo(conn)
    row = repo.get(tenant_id=str(tenant_id), template_id=str(template_id))
    if not row:
        raise ValueError("template не найден")

    new_name = str(name).strip() if name is not None else str(row["name"])
    if not new_name:
        raise ValueError("name обязателен")

    repo.update(
        tenant_id=str(tenant_id),
        template_id=str(template_id),
        updated_at=utcnow_iso(),
        scope=str(scope) if scope is not None else str(row["scope"]),
        name=new_name,
        description=description if description is not None else row["description"],
        sections_json=_json(sections, row["sections_json"]) if sections is not None else row["sections_json"],
        metrics_json=_json(metrics, row["metrics_json"]) if metrics is not None else row["metrics_json"],
        options_json=_json(options, row["options_json"]) if options is not None else row["options_json"],
    )


def delete_template(conn: sqlite3.Connection, *, tenant_id: str, template_id: str) -> None:
    deleted = ReportTemplatesRepo(conn).delete(tenant_id=str(tenant_id), template_id=str(template_id))
    if deleted == 0:
        raise ValueError("template не найден")


def get_template(conn: sqlite3.Connection, *, tenant_id: str, template_id: str) -> Optional[dict[str, Any]]:
    return ReportTemplatesRepo(conn).get(tenant_id=str(tenant_id), template_id=str(template_id))


def list_templates(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: int,
    include_shared: bool = True,
    limit: int = 200,
) -> list[dict[str, Any]]:
    return ReportTemplatesRepo(conn).list(
        tenant_id=str(tenant_id),
        user_id=int(user_id),
        include_shared=bool(include_shared),
        limit=int(limit),
    )
