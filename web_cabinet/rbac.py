from __future__ import annotations

from typing import Callable

from fastapi import Depends, HTTPException, status

from core.infra.compat import warn_legacy_import
from core.security import *  # noqa: F401,F403
from core.security import PermissionDenied, ensure_permissions, permission_denied_detail

warn_legacy_import(legacy_path="web_cabinet.rbac", new_path="core.security")


def require_permissions(*required: str) -> Callable:
    """FastAPI dependency guard for permissions backed by core.security."""

    from .auth import get_current_user  # local import to avoid cycles

    def dep(user: dict = Depends(get_current_user)) -> dict:
        try:
            ensure_permissions(
                user.get("permissions"),
                *required,
                role=str(user.get("role") or "") or None,
                operation="require_permissions",
            )
        except PermissionDenied as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=permission_denied_detail(exc),
            ) from exc
        return user

    return dep
