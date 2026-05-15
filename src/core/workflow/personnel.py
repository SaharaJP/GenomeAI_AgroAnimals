"""P1-4a-6: workflow use-cases for /api/app/v1/personnel.

Wraps PersonnelRepo with masking, id generation, and ISO-time helpers.
The endpoint layer (web_cabinet) is responsible for the RBAC gate
(personnel.read / personnel.read_pii / personnel.manage) and for emitting
audit events; this module is pure business logic.
"""
from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any, Optional

from core.domain.records import Personnel
from core.infra.repositories import PersonnelRepo


def utcnow_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def generate_personnel_id() -> str:
    return f"prsn_{uuid.uuid4().hex[:12]}"


def row_to_personnel(row: dict[str, Any]) -> Personnel:
    hired_at = row.get("hired_at")
    if hired_at is not None and not isinstance(hired_at, str):
        hired_at = hired_at.isoformat()
    created_at = row.get("created_at")
    if created_at is not None and not isinstance(created_at, str):
        created_at = created_at.isoformat()
    updated_at = row.get("updated_at")
    if updated_at is not None and not isinstance(updated_at, str):
        updated_at = updated_at.isoformat()
    user_id = row.get("user_id")
    if user_id is not None:
        user_id = int(user_id)
    return Personnel(
        personnel_id=row["personnel_id"],
        full_name=row["full_name"],
        position=row["position"],
        group_id=row.get("group_id"),
        photo_ref=row.get("photo_ref"),
        phone=row.get("phone"),
        email=row.get("email"),
        hired_at=hired_at,
        user_id=user_id,
        tenant_id=row.get("tenant_id"),
        created_at=created_at,
        updated_at=updated_at,
    )


def list_personnel(
    conn,
    *,
    tenant_id: str,
    group_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    pii_visible: bool,
) -> tuple[int, list[Personnel]]:
    page = PersonnelRepo(conn).list_rows(
        tenant_id=tenant_id,
        group_id=group_id,
        limit=limit,
        offset=offset,
    )
    items = [row_to_personnel(r) for r in page["items"]]
    if not pii_visible:
        items = [p.masked() for p in items]
    return int(page["total"]), items


def create_personnel(
    conn,
    *,
    tenant_id: str,
    full_name: str,
    position: str,
    group_id: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    hired_at: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Personnel:
    pid = generate_personnel_id()
    now = utcnow_iso()
    PersonnelRepo(conn).insert(
        tenant_id=tenant_id,
        personnel_id=pid,
        full_name=full_name,
        position=position,
        group_id=group_id,
        phone=phone,
        email=email,
        hired_at=hired_at,
        user_id=user_id,
        now=now,
    )
    row = PersonnelRepo(conn).get_row(tenant_id=tenant_id, personnel_id=pid)
    if row is None:
        raise RuntimeError("personnel.insert lost row")
    return row_to_personnel(row)


__all__ = [
    "create_personnel",
    "generate_personnel_id",
    "list_personnel",
    "row_to_personnel",
    "utcnow_iso",
]
