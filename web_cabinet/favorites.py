from __future__ import annotations

"""T10-04: Favorites (reports, alerts, groups, animals).

Favorites are per-user. Storage only.
"""

from typing import Any, Optional

from core.infra import FavoritesRepo

from core.infra.web_db import utcnow_iso


def add_favorite(
    conn: Any,
    *,
    tenant_id: str,
    user_id: int,
    object_type: str,
    object_id: str,
    label: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    if not object_type or not str(object_type).strip():
        raise ValueError("object_type обязателен")
    if not object_id or not str(object_id).strip():
        raise ValueError("object_id обязателен")

    FavoritesRepo(conn).add(
        tenant_id=str(tenant_id),
        user_id=int(user_id),
        object_type=str(object_type).strip(),
        object_id=str(object_id).strip(),
        created_at=utcnow_iso(),
        label=str(label).strip() if label else None,
        metadata=metadata or {},
    )


def remove_favorite(
    conn: Any,
    *,
    tenant_id: str,
    user_id: int,
    object_type: str,
    object_id: str,
) -> None:
    removed = FavoritesRepo(conn).remove(
        tenant_id=str(tenant_id),
        user_id=int(user_id),
        object_type=str(object_type).strip(),
        object_id=str(object_id).strip(),
    )
    if removed == 0:
        raise ValueError("favorite не найден")


def is_favorite(
    conn: Any,
    *,
    tenant_id: str,
    user_id: int,
    object_type: str,
    object_id: str,
) -> bool:
    return FavoritesRepo(conn).exists(
        tenant_id=str(tenant_id),
        user_id=int(user_id),
        object_type=str(object_type).strip(),
        object_id=str(object_id).strip(),
    )


def list_favorites(
    conn: Any,
    *,
    tenant_id: str,
    user_id: int,
    object_type: Optional[str] = None,
    limit: int = 300,
) -> list[dict[str, Any]]:
    return FavoritesRepo(conn).list(
        tenant_id=str(tenant_id),
        user_id=int(user_id),
        object_type=str(object_type).strip() if object_type else None,
        limit=int(limit),
    )
